import { describe, expect, test } from 'bun:test';
import { applyEvents, emptyPartition, installSnapshot, mergeMessage, mergeReceipt, settleIntent, storeMessage } from './repository';
import type { MessageView } from './types';
const message: MessageView = { id:'00000000-0000-4000-8000-000000000001',event_id:'00000000-0000-4000-8000-000000000002',conversation_id:'g',sender_id:'peer',created_at:'2026-10-01T00:00:00Z',order_key:'09007199254740993001',type:'text',text:'original',receipt:null };
describe('durable projection transitions', () => {
 test('orders keys beyond numeric precision without collapsing adjacent messages', () => {
  const older = {...message,id:'00000000-0000-4000-8000-000000000003',order_key:'09007199254740993000'};
  expect(mergeMessage([message],older).map(m=>m.id)).toEqual([older.id,message.id]);
 });
 test('late delivered status never downgrades read', () => {
  const read = {kind:'direct' as const,message_id:message.id,recipient_id:'peer',status:'read' as const,updated_at:'2026-10-01T00:00:01Z'};
  expect(mergeReceipt(read,{...read,status:'delivered',updated_at:'2026-10-01T00:00:02Z'}).status).toBe('read');
 });
 test('ACK coalesces existing intent without replacing its original content', () => {
  const state=emptyPartition();
  state.intents.c={clientMessageId:'c',conversationId:'g',payload:{type:'text',text:'original'},createdAt:'2026-10-01T00:00:00Z',status:'unknown',messageId:null,error:null,retryAt:null};
  settleIntent(state,'c',message.id);
  expect(state.intents.c.payload).toEqual({type:'text',text:'original'});
  expect(state.intents.c.status).toBe('persisted');
 });
 test('self removal purges only revoked body and quarantines intent', () => {
  const state=emptyPartition(); state.messages.g=[message]; state.messages.other=[{...message,conversation_id:'other'}];
  state.intents.c={clientMessageId:'c',conversationId:'g',payload:{type:'text',text:'original'},createdAt:'2026-10-01T00:00:00Z',status:'unknown',messageId:null,error:null,retryAt:null};
  applyEvents(state,[{event:'conversation.member_removed',event_id:'00000000-0000-4000-8000-000000000004',timestamp:'2026-10-01T00:00:00Z',conversation_id:'g',payload:{member_id:'me',change:'removed',membership_version:2}}],'me');
  expect(state.messages.g).toBeUndefined(); expect(state.messages.other).toHaveLength(1);
  expect(state.intents.c.status).toBe('rejected'); expect(state.denied).toContain('g');
 });
 test('replayed stable event does not duplicate message',()=>{
  const state=emptyPartition(); const event={event:'message.created',event_id:message.event_id,timestamp:message.created_at,conversation_id:'g',sender_id:'peer',payload:{message_id:message.id,type:'text',text:'original',order_key:message.order_key}};
  applyEvents(state,[event,event],'me'); expect(state.messages.g).toHaveLength(1);
 });
 test('snapshot replacement keeps live observations and unsettled C1 while installing one H',()=>{
  const state=emptyPartition(),staged=emptyPartition();state.cursor='old';state.messages.g=[message];state.intents.c={clientMessageId:'c',conversationId:'g',payload:{type:'text',text:'not confirmed'},createdAt:'2026-10-01T00:00:00Z',status:'unknown',messageId:null,error:null,retryAt:null};
  staged.conversations.g={id:'g',type:'group',title:'group',unread_count:2};
  installSnapshot(state,staged,[{event:'message.created',event_id:message.event_id,timestamp:message.created_at,conversation_id:'g',sender_id:'peer',payload:{message_id:message.id,type:'text',text:'original',order_key:message.order_key}}],'H','me');
  expect(state.cursor).toBe('H');expect(state.messages.g).toHaveLength(1);expect(state.intents.c.status).toBe('unknown');
 });
 test('snapshot cannot restore a denied group even when staged before self-removal',()=>{
  const state=emptyPartition(),staged=emptyPartition();state.denied=['g'];staged.conversations.g={id:'g',type:'group',title:'old group',unread_count:0};staged.messages.g=[message];
  expect(()=>installSnapshot(state,staged,[{event:'conversation.member_removed',event_id:'00000000-0000-4000-8000-000000000008',timestamp:message.created_at,conversation_id:'g',payload:{member_id:'me',change:'removed',membership_version:5}}],'H','me')).toThrow();expect(state.messages.g).toBeUndefined();expect(state.cursor).toBeNull();
 });
 test('live direct status arriving before snapshot message is not lost or downgraded',()=>{
  const state=emptyPartition(),staged=emptyPartition();const direct={...message,conversation_id:'d'};
  state.statuses[direct.id]={kind:'direct',message_id:direct.id,recipient_id:'me',status:'read',updated_at:'2026-10-01T00:00:01Z'};staged.conversations.d={id:'d',type:'direct',title:null,unread_count:0};staged.messages.d=[direct];
  installSnapshot(state,staged,[],'H','me');expect(state.messages.d[0].receipt?.status).toBe('read');
 });
 test('W07 before W06 settles one original intent and ACK cannot create a duplicate bubble',()=>{
  const state=emptyPartition(),c1='00000000-0000-4000-8000-000000000005';state.intents[c1]={clientMessageId:c1,conversationId:'g',payload:{type:'text',text:'original'},createdAt:message.created_at,status:'unknown',messageId:null,error:null,retryAt:null};
  storeMessage(state,{...message,sender_id:'me',client_message_id:c1},'me');settleIntent(state,c1,message.id);
  expect(state.messages.g).toHaveLength(1);expect(state.intents[c1].messageId).toBe(message.id);expect(state.intents[c1].payload).toEqual({type:'text',text:'original'});
 });
 test('mismatched canonical payload cannot silently settle an original C1',()=>{
  const state=emptyPartition(),c1='00000000-0000-4000-8000-000000000005';state.intents[c1]={clientMessageId:c1,conversationId:'g',payload:{type:'text',text:'original'},createdAt:message.created_at,status:'unknown',messageId:null,error:null,retryAt:null};
  expect(()=>storeMessage(state,{...message,sender_id:'me',client_message_id:c1,text:'different'},'me')).toThrow();expect(state.intents[c1].status).toBe('unknown');
 });
 test('a new self-join boundary never restores the earlier staged group body',()=>{
  const state=emptyPartition(),staged=emptyPartition();state.conversations.g={id:'g',type:'group',title:'group',unread_count:0};state.messages.g=[{...message,id:'00000000-0000-4000-8000-000000000009',event_id:'00000000-0000-4000-8000-000000000010',text:'after rejoin'}];staged.conversations.g=state.conversations.g;staged.messages.g=[message];
  state.selfMembershipVersions.g=5;
  installSnapshot(state,staged,[{event:'conversation.member_added',event_id:'00000000-0000-4000-8000-000000000008',timestamp:message.created_at,conversation_id:'g',payload:{member_id:'me',role:'member',actor_id:'owner',membership_version:5}},{event:'message.created',event_id:'00000000-0000-4000-8000-000000000010',timestamp:message.created_at,conversation_id:'g',sender_id:'peer',payload:{message_id:'00000000-0000-4000-8000-000000000009',type:'text',text:'after rejoin',order_key:message.order_key}}],'H','me');
  expect(state.messages.g.map(item=>item.text)).toEqual(['after rejoin']);
 });
 test('late prior-membership removal cannot withdraw the A12-confirmed newer membership',()=>{
  const state=emptyPartition();state.messages.g=[message];state.details.g={id:'g',type:'group',title:'group',unread_count:0,members:[{user_id:'me',role:'member'}],membership_version:5,created_at:message.created_at};
  state.selfMembershipVersions.g=5;
  applyEvents(state,[{event:'conversation.member_removed',event_id:'00000000-0000-4000-8000-000000000008',timestamp:message.created_at,conversation_id:'g',payload:{member_id:'me',change:'removed',membership_version:2}}],'me');
  expect(state.denied).toEqual([]);expect(state.messages.g).toHaveLength(1);
 });
 test('one batch removal plus authorized rejoin accepts only the new-boundary message',()=>{
  const state=emptyPartition();state.messages.g=[message];
  const removed={event:'conversation.member_removed',event_id:'00000000-0000-4000-8000-000000000011',timestamp:message.created_at,conversation_id:'g',payload:{member_id:'me',change:'removed',membership_version:2}};
  const joined={event:'conversation.member_added',event_id:'00000000-0000-4000-8000-000000000012',timestamp:message.created_at,conversation_id:'g',payload:{member_id:'me',role:'member',actor_id:'owner',membership_version:3}};
  const created={event:'message.created',event_id:'00000000-0000-4000-8000-000000000013',timestamp:message.created_at,conversation_id:'g',sender_id:'peer',payload:{message_id:'00000000-0000-4000-8000-000000000014',type:'text',text:'new boundary',order_key:'09007199254740993002'}};
  applyEvents(state,[removed,joined,created],'me',{[joined.event_id]:{id:'g',type:'group',title:'group',unread_count:1,members:[{user_id:'me',role:'member'}],membership_version:3,created_at:message.created_at}});
  expect(state.messages.g.map(item=>item.text)).toEqual(['new boundary']);expect(state.denied).toEqual([]);
 });
});
