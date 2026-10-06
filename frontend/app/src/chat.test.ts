import { expect, test } from 'bun:test';
import { parseServerFrame, ReceiveQueue, settleHeartbeat, validateSyncProgress } from './chat';
const base={event:'message.created',event_id:'00000000-0000-4000-8000-000000000001',timestamp:'2026-10-01T00:00:00Z',conversation_id:'c',sender_id:'peer',payload:{message_id:'00000000-0000-4000-8000-000000000002',type:'text',text:'hello',order_key:'00000000000000000001'}};
test('rejects numeric order keys instead of losing canonical precision',()=>{
 expect(()=>parseServerFrame({...base,payload:{...base.payload,order_key:1}},'me')).toThrow();
});
test('rejects recipient disclosure of sender C1 and private identity',()=>{
 expect(()=>parseServerFrame({...base,payload:{...base.payload,client_message_id:'00000000-0000-4000-8000-000000000003'}},'me')).toThrow();
 expect(()=>parseServerFrame({...base,subject_id:'private'},'me')).toThrow();
});
test('hidden empty sync can advance but has_more without progress is rejected',()=>{
 expect(()=>validateSyncProgress('a','b',true)).not.toThrow();
 expect(()=>validateSyncProgress('a','a',true)).toThrow();
 expect(()=>validateSyncProgress('a','a',false)).not.toThrow();
});
test('only exact outstanding heartbeat nonce plus correlation completes that ping',()=>{
 const pending=new Map([['request',{nonce:' A ',sent:100}]]);
 const pong={event:'heartbeat.pong',event_id:base.event_id,timestamp:base.timestamp,correlation_id:'request',payload:{nonce:'A'}};
 expect(settleHeartbeat(pending,pong)).toBe(false);expect(pending.size).toBe(1);
 expect(settleHeartbeat(pending,{...pong,correlation_id:'old',payload:{nonce:' A '}})).toBe(false);expect(pending.size).toBe(1);
 expect(settleHeartbeat(pending,{...pong,payload:{nonce:' A '}})).toBe(true);expect(pending.size).toBe(0);
 expect(settleHeartbeat(pending,{...pong,payload:{nonce:' A '}})).toBe(false);
});
test('a detached socket receive queue cannot stall the replacement handshake executor',async()=>{
 const oldQueue=new ReceiveQueue();let finish!:(value:void)=>void;
 const stalled=new Promise<void>(resolve=>{finish=resolve;});let oldContinuation=false;
 const oldWork=oldQueue.enqueue(async()=>{await stalled;if(!oldQueue.abort.signal.aborted)oldContinuation=true;});
 await Promise.resolve();oldQueue.close();
 const replacement=new ReceiveQueue();let accepted=false;await replacement.enqueue(async()=>{accepted=true;});
 expect(accepted).toBe(true);finish();await oldWork;expect(oldContinuation).toBe(false);
});
