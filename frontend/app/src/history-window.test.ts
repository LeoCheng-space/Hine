import { expect, test } from 'bun:test';
import { boundedPartition, emptyPartition, storeMessage } from './repository';
import type { MessageView } from './types';
function ownMessage(index:number):MessageView {
 const suffix=String(index).padStart(12,'0');
 return {id:`00000000-0000-4000-8000-${suffix}`,event_id:`10000000-0000-4000-8000-${suffix}`,conversation_id:'g',sender_id:'me',created_at:'2026-10-01T00:00:00Z',order_key:String(index).padStart(20,'0'),type:'text',text:`actual history record ${index}`,receipt:null};
}
test('a requested older page remains viewable around the active reading anchor beyond 200 messages',()=>{
 const state=emptyPartition();state.conversations.g={id:'g',type:'group',title:'group',unread_count:0};
 for(let index=21;index<=220;index++)storeMessage(state,ownMessage(index),'me');
 const olderPage=Array.from({length:20},(_,index)=>ownMessage(index+1));
 for(const message of olderPage)storeMessage(state,message,'me');
 state.anchors.g={messageId:olderPage[0].id,offset:8,atLatest:false};
 boundedPartition(state);
 expect(state.messages.g.filter(message=>message.order_key<'00000000000000000021').map(message=>message.id)).toEqual(olderPage.map(message=>message.id));
 expect(state.messages.g.length).toBeLessThanOrEqual(220);
});
