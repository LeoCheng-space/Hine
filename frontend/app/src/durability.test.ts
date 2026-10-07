import { expect, test } from 'bun:test';
import { applyEvents, boundedPartition, ConversationAuthority, emptyPartition, installSnapshot, recordReceiptFailure, receiptCanRetryAutomatically, storeMessage } from './repository';
import { parseServerFrame } from './chat';
import type { ConversationDetail, MessageView } from './types';
const m:MessageView={id:'00000000-0000-4000-8000-000000000001',event_id:'00000000-0000-4000-8000-000000000002',conversation_id:'g',sender_id:'peer',created_at:'2026-10-01T00:00:00Z',order_key:'00000000000000000001',type:'text',text:'old membership body',receipt:null};
const detail:ConversationDetail={id:'g',type:'group',title:'renamed after rejoin',unread_count:0,members:[{user_id:'me',role:'member'}],membership_version:4,created_at:m.created_at};
test('unseen self join 3 is applied even when A12 metadata is already version 4',()=>{
 const state=emptyPartition();state.details.g=detail;state.conversations.g=detail;state.messages.g=[m];state.selfMembershipVersions.g=1;
 const join={event:'conversation.member_added',event_id:'00000000-0000-4000-8000-000000000003',timestamp:m.created_at,conversation_id:'g',payload:{member_id:'me',actor_id:'owner',role:'member',membership_version:3}};
 applyEvents(state,[join],'me',{[join.event_id]:detail});
 expect(state.messages.g).toBeUndefined();expect(state.selfMembershipVersions.g).toBe(3);expect(state.details.g.membership_version).toBe(4);
});
test('a successful A12 or A19 from before withdrawal remains stale after rejoin',()=>{
 const authority=new ConversationAuthority(),old=authority.capture('g');authority.invalidate('g');authority.invalidate('g');
 expect(authority.isCurrent('g',old)).toBe(false);expect(authority.isCurrent('other',authority.capture('other'))).toBe(true);
 const newRead=authority.capture('g');authority.invalidateAll();expect(authority.isCurrent('g',newRead)).toBe(false);
});
test('non-self W20 metadata versions do not consume the self-join boundary or pending C2',()=>{
 const state=emptyPartition();state.details.g={...detail,title:'version one',membership_version:1,members:[{user_id:'me',role:'admin'},{user_id:'peer',role:'member'}]};state.conversations.g=state.details.g;state.selfMembershipVersions.g=1;
 storeMessage(state,m,'me');state.receipts[m.id].desired='read';
 const title=parseServerFrame({event:'conversation.updated',event_id:'00000000-0000-4000-8000-000000000010',timestamp:m.created_at,conversation_id:'g',payload:{actor_id:'me',membership_version:2,changes:{kind:'title',title:'version two'}}},'me');
 const promoted=parseServerFrame({event:'conversation.updated',event_id:'00000000-0000-4000-8000-000000000011',timestamp:m.created_at,conversation_id:'g',payload:{actor_id:'me',membership_version:3,changes:{kind:'role',member_id:'peer',role:'admin'}}},'me');
 applyEvents(state,[title,promoted],'me');
 expect(state.details.g.title).toBe('version two');expect(state.details.g.membership_version).toBe(3);expect(state.details.g.members).toEqual([{user_id:'me',role:'admin'},{user_id:'peer',role:'admin'}]);
 expect(state.selfMembershipVersions.g).toBe(1);expect(state.messages.g).toEqual([m]);expect(state.receipts[m.id].desired).toBe('read');expect(state.receipts[m.id].blocked).toBe(false);
});
test('late non-self metadata events leave newer title, roles, members and pending C2 intact',()=>{
 const state=emptyPartition();state.cursor='current cursor';state.details.g={...detail,title:'version three',membership_version:3,members:[{user_id:'me',role:'admin'},{user_id:'peer',role:'admin'}]};state.conversations.g=state.details.g;state.selfMembershipVersions.g=1;
 storeMessage(state,m,'me');state.receipts[m.id].desired='read';
 const stale=[
  {event:'conversation.updated',event_id:'00000000-0000-4000-8000-000000000012',timestamp:m.created_at,conversation_id:'g',payload:{actor_id:'me',membership_version:2,changes:{kind:'title',title:'obsolete title'}}},
  {event:'conversation.updated',event_id:'00000000-0000-4000-8000-000000000013',timestamp:m.created_at,conversation_id:'g',payload:{actor_id:'me',membership_version:2,changes:{kind:'role',member_id:'peer',role:'member'}}},
  {event:'conversation.member_removed',event_id:'00000000-0000-4000-8000-000000000014',timestamp:m.created_at,conversation_id:'g',payload:{actor_id:'me',membership_version:2,member_id:'peer',change:'removed'}},
 ].map(value=>parseServerFrame(value,'me'));
 applyEvents(state,stale,'me');
 expect(state.details.g.title).toBe('version three');expect(state.conversations.g.title).toBe('version three');expect(state.details.g.membership_version).toBe(3);expect(state.details.g.members).toEqual([{user_id:'me',role:'admin'},{user_id:'peer',role:'admin'}]);
 expect(state.cursor).toBe('current cursor');expect(state.selfMembershipVersions.g).toBe(1);expect(state.messages.g).toEqual([m]);expect(state.receipts[m.id].desired).toBe('read');expect(state.receipts[m.id].blocked).toBe(false);expect(state.seen).toEqual(stale.map(event=>event.event_id));
});
test('replacement H never reinstalls cached old group messages, receipts or statuses',()=>{
 const state=emptyPartition(),staged=emptyPartition();state.cursor='expired';state.conversations.g=detail;storeMessage(state,m,'me');state.statuses[m.id]={kind:'direct',message_id:m.id,recipient_id:'me',status:'read',updated_at:m.created_at};
 staged.conversations.g=detail;
 installSnapshot(state,staged,[],'new-H','me');
 expect(state.messages.g??[]).toEqual([]);expect(state.statuses[m.id]).toBeUndefined();expect(state.receipts[m.id]?.blocked).toBe(true);expect(state.cursor).toBe('new-H');
});
test('authorized replacement snapshot recovers a group denied before staging',()=>{
 const state=emptyPartition(),staged=emptyPartition();state.denied=['g'];staged.conversations.g=detail;staged.messages.g=[{...m,text:'currently authorized snapshot'}];
 installSnapshot(state,staged,[],'H','me');expect(state.denied).toEqual([]);expect(state.messages.g[0].text).toBe('currently authorized snapshot');
});
test('self revocation observed during staging rejects H before any snapshot mutation',()=>{
 const state=emptyPartition(),staged=emptyPartition();state.cursor='old';staged.conversations.g=detail;
 const removed={event:'conversation.member_removed',event_id:'00000000-0000-4000-8000-000000000004',timestamp:m.created_at,conversation_id:'g',payload:{member_id:'me',change:'removed',membership_version:5}};
 expect(()=>installSnapshot(state,staged,[removed],'bad-H','me')).toThrow();expect(state.cursor).toBe('old');expect(state.conversations.g).toBeUndefined();
});
test('missing rate delay stops receipt automation and preserves an existing later deadline',()=>{
 const state=emptyPartition();storeMessage(state,m,'me');const receipt=state.receipts[m.id];
 recordReceiptFailure(receipt,'RATE_LIMITED',true,5000,1000);expect(receipt.retryAt).toBe(6000);
 recordReceiptFailure(receipt,'RATE_LIMITED',true,undefined,2000);expect(receipt.retryAt).toBe(6000);expect(receipt.autoRetryStopped).toBe(true);expect(receiptCanRetryAutomatically(receipt,7000)).toBe(false);
 receipt.autoRetryStopped=false;expect(receiptCanRetryAutomatically(receipt,5999)).toBe(false);expect(receiptCanRetryAutomatically(receipt,6000)).toBe(true);
});
test('settled caches are bounded but unresolved C1 and pending receipts survive',()=>{
 const state=emptyPartition();state.conversations.g=detail;
 for(let n=1;n<=2500;n++){const id=`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;state.messages.g??=[];state.messages.g.push({...m,id,event_id:id,order_key:String(n).padStart(20,'0')});state.seen.push(id);state.intents[id]={clientMessageId:id,conversationId:'g',payload:{type:'text',text:'original'},createdAt:m.created_at,status:'persisted',messageId:id,error:null,retryAt:null};state.receipts[id]={messageId:id,conversationId:'g',desired:'read',confirmed:'read',error:null,retryAt:null,blocked:false,autoRetryStopped:false};}
 const first=state.messages.g[0];state.receipts[first.id].confirmed=null;state.intents.unresolved={clientMessageId:'unresolved',conversationId:'g',payload:{type:'text',text:'keep original'},createdAt:m.created_at,status:'unknown',messageId:null,error:null,retryAt:null};
 boundedPartition(state);
 expect(state.messages.g.length).toBeLessThanOrEqual(201);expect(state.messages.g.some(message=>message.id===first.id)).toBe(true);expect(state.intents.unresolved.payload).toEqual({type:'text',text:'keep original'});expect(state.receipts[first.id].confirmed).toBeNull();expect(Object.keys(state.intents).length).toBeLessThanOrEqual(501);
});
