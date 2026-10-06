import { ChatController } from '../src/chat';
import { ChatRepository, ConversationAuthority, record, RepositoryCancelled, StorageFault } from '../src/repository';
import type { SessionController } from '../src/session';
import type { AccessSession, ConversationCreateResult, MessageView } from '../src/types';

// Run only in a fresh, parent-owned HTTPS browser context against the real native API/WSS.
// Peer credentials must come from a separately authenticated native fixture, never a fake provider.
export const nativeTransitionDiagnostic:{stage:string;initialHistoryMore:boolean|null;queriedPages:number;pageSizes:number[];olderPageCount:number;finalHistoryMore:boolean|null;oldestRetained:boolean}={stage:'not_started',initialHistoryMore:null,queriedPages:0,pageSizes:[],olderPageCount:0,finalHistoryMore:null,oldestRetained:false};
function assert(condition:unknown,message:string):asserts condition {if(!condition)throw new Error(message);}
async function until(predicate:()=>boolean,label:string):Promise<void>{const deadline=performance.now()+20_000;while(!predicate()){if(performance.now()>=deadline)throw new Error(label);await new Promise<void>(resolve=>window.setTimeout(resolve,20));}}
function gateResponse(path:string):{reached:Promise<void>;release:()=>void;restore:()=>void} {
 const original=window.fetch;let reached!:(value:void)=>void,release!:(value:void)=>void,armed=true;
 const seen=new Promise<void>(resolve=>{reached=resolve;}),held=new Promise<void>(resolve=>{release=resolve;});
 window.fetch=new Proxy(original,{async apply(target,thisArg,args){
  const input:unknown=args[0],init:unknown=args[1],response:unknown=await Reflect.apply(target,thisArg,args);
  assert(response instanceof Response,'Actual fetch did not return a native Response.');
  const request=input instanceof Request?input:null,url=new URL(request?.url??String(input),location.href);
  const method=init!==null&&typeof init==='object'&&'method' in init&&typeof init.method==='string'?init.method:request?.method??'GET';
  if(armed&&method==='GET'&&url.pathname===path){armed=false;const body=await response.text();const buffered=new Response(body,{status:response.status,headers:response.headers});reached();await held;return buffered;}
  return response;
 }});
 return {reached:seen,release:()=>release(),restore:()=>{window.fetch=original;release();}};
}
export async function runNativeControllerTransitions(session:SessionController,peer:{userId:string;accessToken:string}):Promise<{message:MessageView;userId:string;deviceId:string}> {
 const context=session.getSnapshot().context;assert(context.state==='authenticated','Use an actual authenticated fixture SessionController.');
 const owner={userId:context.user_id,deviceId:context.device_id},chat=new ChatController(session);
 const peerRequest=async(path:string,json?:unknown,method='POST'):Promise<void>=>{
  const response=await fetch(`${session.config.API_BASE_URL}${path}`,{method,credentials:'omit',headers:{Authorization:`Bearer ${peer.accessToken}`,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},...(json===undefined?{}:{body:JSON.stringify(json)}),signal:AbortSignal.timeout(10_000)});
  assert(response.ok,'Actual peer mutation failed.');
 };
 let gate:{reached:Promise<void>;release:()=>void;restore:()=>void}|null=null;
 try{
  nativeTransitionDiagnostic.stage='controller_start';
  await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual W02 did not arrive.');
  const created=await session.request<ConversationCreateResult>('/conversations/groups',{method:'POST',idempotencyKey:crypto.randomUUID(),json:{title:'native transition fixture',member_ids:[peer.userId]}}),id=created.data.id,path=`/conversations/${encodeURIComponent(id)}`;
  await session.request(`${path}/members/${encodeURIComponent(peer.userId)}`,{method:'PATCH',json:{role:'admin'}});
  nativeTransitionDiagnostic.stage='fixture_messages_21';
  await chat.openChat(id);
  const oldPrefix=`old-membership-${crypto.randomUUID()}`;
  for(let index=0;index<21;index++){const text=`${oldPrefix}-${index}`;await chat.sendText(id,text);await until(()=>chat.getSnapshot().messages[id]?.some(message=>message.text===text)??false,'Real persisted message did not project.');await new Promise<void>(resolve=>window.setTimeout(resolve,250));}
  nativeTransitionDiagnostic.stage='same_account_stop_start_open';
  await chat.stop();await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Reload W02 did not arrive.');await chat.openChat(id);
  assert(chat.getSnapshot().historyMore[id]===true,'Fixture must have a real A19 continuation.');
  gate=gateResponse(`${new URL(session.config.API_BASE_URL,location.origin).pathname}${path}/messages`);
  const oldHistory=chat.loadHistory(id).catch(error=>{if(!(error instanceof RepositoryCancelled))throw error;});
  await gate.reached;
  nativeTransitionDiagnostic.stage='old_A19_held_before_removal';
  await session.request(`${path}/members/${encodeURIComponent(owner.userId)}`,{method:'DELETE'});await chat.withdraw(id);
  await peerRequest(`${path}/members`,{user_id:owner.userId});await peerRequest(path,{title:'renamed after real rejoin'},'PATCH');
  await chat.openChat(id);
  const fresh=`new-membership-${crypto.randomUUID()}`;await chat.sendText(id,fresh);await until(()=>chat.getSnapshot().messages[id]?.some(message=>message.text===fresh)??false,'New membership did not project.');
  gate.release();await oldHistory;gate.restore();gate=null;
  assert(!(chat.getSnapshot().messages[id]??[]).some(message=>message.type==='text'&&message.text.startsWith(oldPrefix)),'Old successful A19 resurrected a previous membership body.');
  const current=chat.getSnapshot().messages[id].find(message=>message.text===fresh);assert(current,'Actual current message required for native repository test.');
  nativeTransitionDiagnostic.stage='old_self_join_A12_held_before_refresh';
  await session.request(`${path}/members/${encodeURIComponent(owner.userId)}`,{method:'DELETE'});await chat.withdraw(id);
  gate=gateResponse(`${new URL(session.config.API_BASE_URL,location.origin).pathname}${path}`);
  await peerRequest(`${path}/members`,{user_id:owner.userId});await gate.reached;
  await session.refresh();
  await until(()=>chat.getSnapshot().connection==='ready','Old stalled A12 blocked the replacement socket W02.');
  gate.release();gate.restore();gate=null;
  await chat.openChat(id);
  assert(!(chat.getSnapshot().messages[id]??[]).some(message=>message.type==='text'&&message.text.startsWith(oldPrefix)),'Old socket continuation reinstated old membership.');
  return {...owner,message:current};
 }finally{gate?.restore();await chat.stop();}
}
async function nativePartition(userId:string,deviceId:string):Promise<Record<string,unknown>> {
 const database=await new Promise<IDBDatabase>((resolve,reject)=>{const request=indexedDB.open('hine-chat-v1');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
 try{return await new Promise<Record<string,unknown>>((resolve,reject)=>{const request=database.transaction('partitions').objectStore('partitions').get(JSON.stringify([userId,deviceId]));request.onsuccess=()=>resolve(record(request.result));request.onerror=()=>reject(request.error);});}finally{database.close();}
}
export async function runNativeRepositoryTransitions(fixture:{message:MessageView;userId:string;deviceId:string}):Promise<void> {
 const repository=new ChatRepository(fixture.userId,fixture.deviceId),authority=new ConversationAuthority(),id=fixture.message.conversation_id;
 await repository.open();const before=JSON.stringify(await nativePartition(fixture.userId,fixture.deviceId));
 const originalPut=IDBObjectStore.prototype.put;let projectionWrites=0;
 IDBObjectStore.prototype.put=function(this:IDBObjectStore,value:unknown,key?:IDBValidKey){if(this.name==='partitions')++projectionWrites;return originalPut.call(this,value,key);};
 try{await repository.writeDraft(id,'native persistent draft',()=>true);await repository.writeAnchor(id,{messageId:fixture.message.id,offset:13.5,atLatest:false},()=>true);}finally{IDBObjectStore.prototype.put=originalPut;}
 assert(projectionWrites===0,'Draft/anchor updates rewrote historical projection bodies.');assert(JSON.stringify(await nativePartition(fixture.userId,fixture.deviceId))===before,'Local edit changed projection or SyncCursor.');
 const ticket=authority.capture(id),first=repository.writeDraft(id,'current generation',()=>true);
 const stale=repository.update(state=>{state.messages[id]=[fixture.message];state.cursor='must-not-install';},()=>authority.isCurrent(id,ticket));authority.invalidate(id);
 await first;let cancelled=false;try{await stale;}catch(error){cancelled=error instanceof RepositoryCancelled;}assert(cancelled,'Queued old-generation transaction was not cancelled.');assert(JSON.stringify(await nativePartition(fixture.userId,fixture.deviceId))===before,'Cancelled transaction partially committed body/cursor.');
 await repository.close();let failed=false;try{await repository.writeDraft(id,'must fail',()=>true);}catch(error){failed=error instanceof StorageFault;}assert(failed,'Closed actual IndexedDB silently used memory persistence.');
 const reloaded=new ChatRepository(fixture.userId,fixture.deviceId);try{const state=await reloaded.open();assert(state.drafts[id]==='current generation','Native draft did not survive repository reopen.');assert(state.anchors[id]?.messageId===fixture.message.id&&state.anchors[id].offset===13.5,'Native pixel anchor did not survive reopen.');}finally{await reloaded.close();}
}

async function peerApi(session:SessionController,peer:AccessSession,path:string,method:string,json?:unknown):Promise<unknown> {
 const response=await fetch(`${session.config.API_BASE_URL}${path}`,{method,credentials:'omit',headers:{Authorization:`Bearer ${peer.access_token}`,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},...(json===undefined?{}:{body:JSON.stringify(json)}),signal:AbortSignal.timeout(10_000)});
 assert(response.ok,'Actual peer API mutation failed.');return response.status===204?null:record(await response.json()).data;
}
async function fixtureGroup(session:SessionController,chat:ChatController,peer:AccessSession,title:string):Promise<string> {
 const result=await session.request<ConversationCreateResult>('/conversations/groups',{method:'POST',idempotencyKey:crypto.randomUUID(),json:{title,member_ids:[peer.user_id]}});
 await session.request(`/conversations/${encodeURIComponent(result.data.id)}/members/${encodeURIComponent(peer.user_id)}`,{method:'PATCH',json:{role:'admin'}});
 await chat.openChat(result.data.id);await chat.reconcile();return result.data.id;
}
async function peerText(session:SessionController,peer:AccessSession,conversationId:string,text:string):Promise<string> {
 return new Promise<string>((resolve,reject)=>{
  const socket=new WebSocket(session.config.WS_URL),auth=crypto.randomUUID(),send=crypto.randomUUID(),c1=crypto.randomUUID();
  const timer=window.setTimeout(()=>{socket.close();reject(new Error('Actual peer W01/W06 timed out.'));},10_000);
  socket.onopen=()=>socket.send(JSON.stringify({event:'auth.authenticate',event_id:auth,timestamp:new Date().toISOString(),payload:{access_token:peer.access_token,device_id:peer.device_id}}));
  socket.onmessage=event=>{try{
   const frame=record(JSON.parse(String(event.data))),payload=record(frame.payload);
   if(frame.event==='error')throw new Error('Actual peer protocol operation failed.');
   if(frame.event==='auth.accepted'&&frame.correlation_id===auth){assert(payload.user_id===peer.user_id&&payload.device_id===peer.device_id&&payload.session_generation===peer.session_generation,'Actual peer W02 binding mismatch.');socket.send(JSON.stringify({event:'message.send',event_id:send,timestamp:new Date().toISOString(),conversation_id:conversationId,payload:{client_message_id:c1,type:'text',text}}));}
   if(frame.event==='message.ack'&&frame.correlation_id===send){assert(payload.client_message_id===c1&&payload.status==='persisted'&&typeof payload.message_id==='string','Actual peer ACK mismatch.');window.clearTimeout(timer);socket.close();resolve(payload.message_id);}
  }catch(error){window.clearTimeout(timer);socket.close();reject(error);}};
  socket.onerror=()=>{window.clearTimeout(timer);reject(new Error('Actual peer socket failed.'));};
 });
}
function holdReadCommands(targetMessage:()=>string|ReadonlySet<string>|null,observe?:(frame:Record<string,unknown>)=>void):{release:()=>void;restore:()=>void;held:()=>boolean} {
 const original=window.WebSocket,deferred:Array<()=>void>=[];let enabled=true;
 window.WebSocket=new Proxy(original,{construct(target,args,newTarget){
  const socket:unknown=Reflect.construct(target,args,newTarget);assert(socket instanceof original,'Actual socket constructor did not return native WebSocket.');
  const send=socket.send;
  socket.send=new Proxy(send,{apply(method,thisArg,data){
   const value:unknown=data[0];if(typeof value==='string'){const frame=record(JSON.parse(value));observe?.(frame);const target=targetMessage();if(enabled&&frame.event==='message.read'&&(typeof target==='string'?record(frame.payload).message_id===target:target?.has(String(record(frame.payload).message_id)))){deferred.push(()=>{if(socket.readyState===original.OPEN)Reflect.apply(method,socket,data);});return;}}
   return Reflect.apply(method,thisArg,data);
  }});
  return socket;
 }});
 const release=():void=>{enabled=false;for(const send of deferred.splice(0))send();};
 return {release,held:()=>deferred.length>0,restore:()=>{release();window.WebSocket=original;}};
}
export async function runHistoryWindowAndPendingReadRegressions(session:SessionController,peer:AccessSession,caseOnly:'history'|'pendingRead'|'both'='both'):Promise<void> {
 const context=session.getSnapshot().context;assert(context.state==='authenticated','Actual authenticated native fixture required.');
 const chat=new ChatController(session);let targetMessage:string|null=null;const reads=holdReadCommands(()=>targetMessage);
 try{
  nativeTransitionDiagnostic.stage='history_over_200_start';await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual W02 missing.');
  const id=await fixtureGroup(session,chat,peer,'native active history window'),marker=`history-window-${crypto.randomUUID()}`;
  const first=await peerText(session,peer,id,`${marker}-peer-oldest`);await until(()=>chat.getSnapshot().messages[id]?.some(message=>message.id===first)??false,'Actual peer message not projected.');
  await until(()=>chat.getSnapshot().receipts[first]?.confirmed==='delivered','Actual W08 not acknowledged.');
  for(let index=0;index<(caseOnly==='pendingRead'?21:221);index++){const text=`${marker}-${index}`;await chat.sendText(id,text);await until(()=>chat.getSnapshot().messages[id]?.some(message=>message.text===text)??false,'Actual own history fixture message missing.');await new Promise<void>(resolve=>window.setTimeout(resolve,250));}
  if(caseOnly!=='pendingRead'){
  nativeTransitionDiagnostic.stage='actual_history_pages_past_200';
  nativeTransitionDiagnostic.initialHistoryMore=null;nativeTransitionDiagnostic.queriedPages=0;nativeTransitionDiagnostic.pageSizes=[];nativeTransitionDiagnostic.olderPageCount=0;
  const original=session.request.bind(session);const queried:string[][]=[];
  session.request=new Proxy(original,{async apply(method,thisArg,args){
   const result:unknown=await Reflect.apply(method,thisArg,args);const path:unknown=args[0];
   if(typeof path==='string'&&path.startsWith(`/conversations/${encodeURIComponent(id)}/messages?`)){const items=record(record(result).data).items;assert(Array.isArray(items),'Actual A19 items missing.');nativeTransitionDiagnostic.queriedPages++;nativeTransitionDiagnostic.pageSizes.push(items.length);queried.push(items.map(value=>{const key=record(value).id;assert(typeof key==='string','Actual message ID missing.');return key;}));}
   return result;
  }});
  try{
   await chat.stop();await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual unchanged reconnect W02 missing.');await chat.openChat(id);
   nativeTransitionDiagnostic.initialHistoryMore=chat.getSnapshot().historyMore[id]??null;
   assert(nativeTransitionDiagnostic.initialHistoryMore!==null,'openChat completed before its actual initial A19 installed pagination readiness.');
   for(let page=0;page<12&&chat.getSnapshot().historyMore[id];page++){await chat.loadHistory(id);nativeTransitionDiagnostic.olderPageCount++;const requested=queried.at(-1);assert(requested,'No actual A19 page was recorded.');const visible=new Set((chat.getSnapshot().messages[id]??[]).map(message=>message.id));assert(requested.every(messageId=>visible.has(messageId)),'A19 cursor advanced while the fetched older page was discarded.');}
  }finally{session.request=original;}
  nativeTransitionDiagnostic.finalHistoryMore=chat.getSnapshot().historyMore[id]??null;nativeTransitionDiagnostic.oldestRetained=chat.getSnapshot().messages[id]?.some(message=>message.id===first)??false;
  await until(()=>chat.getSnapshot().messages[id]?.some(message=>message.id===first)??false,'Oldest authorized history remains unreachable after pagination.');
  }
  if(caseOnly==='history')return;
  targetMessage=first;await chat.receipt(first,id,'read');await until(()=>reads.held(),'Actual pending read command was not held.');
  nativeTransitionDiagnostic.stage='pending_group_read_older_20_refresh';
  await session.refresh();await until(()=>chat.getSnapshot().connection==='ready','Actual refresh W02 missing.');await chat.openChat(id);
  const receipt=chat.getSnapshot().receipts[first];assert(receipt?.desired==='read','Durable read intent disappeared on unchanged refresh.');assert(!receipt.blocked&&receipt.error!=='MEMBERSHIP_RECHECK_REQUIRED','Unchanged membership stranded the older-than-20 pending read.');
  reads.release();await until(()=>chat.getSnapshot().receipts[first]?.confirmed==='read','Original native pending read never reconciled.');
 }finally{reads.restore();await chat.stop();}
}
export async function runQueuedSendBoundaryRegression(session:SessionController,peer:AccessSession):Promise<void> {
 const context=session.getSnapshot().context;assert(context.state==='authenticated','Actual authenticated native fixture required.');
 const chat=new ChatController(session),originalPut=IDBObjectStore.prototype.put;let database:IDBDatabase|null=null,holding:IDBTransaction|null=null,releaseHold=false,holdStarted=false;
 let held!:(value:void)=>void;const reached=new Promise<void>(resolve=>{held=resolve;});
 const marker=`must-not-cross-membership-${crypto.randomUUID()}`,ownerKey=JSON.stringify([context.user_id,context.device_id]);
 const attempts:string[]=[];const transport=holdReadCommands(()=>null,frame=>{if(frame.event==='message.send'&&record(frame.payload).text===marker)attempts.push(String(record(frame.payload).client_message_id));});
 try{
  nativeTransitionDiagnostic.stage='queued_send_boundary_setup';await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual W02 missing.');
  const id=await fixtureGroup(session,chat,peer,'native queued send boundary'),path=`/conversations/${encodeURIComponent(id)}`;
  database=await new Promise<IDBDatabase>((resolve,reject)=>{const request=indexedDB.open('hine-chat-v1');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
  const ownerDatabase=database;
  IDBObjectStore.prototype.put=function(this:IDBObjectStore,value:unknown,key?:IDBValidKey){
   const request=originalPut.call(this,value,key);
   if(!holdStarted&&this.name==='partitions'&&key===ownerKey){const intents=record(record(value).intents);const pending=Object.values(intents).some(value=>{const intent=record(value),payload=record(intent.payload);return intent.status==='pending'&&payload.text===marker;});if(pending){
    holdStarted=true;holding=ownerDatabase.transaction('partitions','readwrite');const transaction=holding,store=transaction.objectStore('partitions');
    const pump=():void=>{const read=store.get(ownerKey);read.onsuccess=()=>{held();if(!releaseHold)pump();};};pump();
   }}
   return request;
  };
  await chat.sendText(id,marker);await reached;
  nativeTransitionDiagnostic.stage='queued_presend_then_actual_remove_rejoin';
  await session.request(`${path}/members/${encodeURIComponent(context.user_id)}`,{method:'DELETE'});const withdrawal=chat.withdraw(id);
  await peerApi(session,peer,`${path}/members`,'POST',{user_id:context.user_id});
  releaseHold=true;await withdrawal;IDBObjectStore.prototype.put=originalPut;await chat.reconcile();
  assert(attempts.length===0,'The pre-send transaction crossed a conversation boundary and still emitted W05.');
  const history=await session.request<{items:MessageView[]}>(`${path}/messages?limit=50`);
  assert(!history.data.items.some(message=>message.type==='text'&&message.text===marker),'Old queued C1 persisted in the new membership.');
  const retained=Object.values(chat.getSnapshot().intents).find(intent=>intent.payload.type==='text'&&intent.payload.text===marker);assert(retained,'Authority cancellation lost the original C1 intent.');assert(retained.status!=='persisted','Authority cancellation was represented as successful persistence.');
 }finally{releaseHold=true;transport.restore();IDBObjectStore.prototype.put=originalPut;database?.close();await chat.stop();}
}
export async function runAllTouchedConversationBatchRegression(session:SessionController,peer:AccessSession):Promise<void> {
 const context=session.getSnapshot().context;assert(context.state==='authenticated','Actual authenticated native fixture required.');
 const chat=new ChatController(session);let gate:{reached:Promise<void>;release:()=>void;restore:()=>void}|null=null;
 try{
  nativeTransitionDiagnostic.stage='mixed_batch_setup';await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual W02 missing.');
  const a=await fixtureGroup(session,chat,peer,'native batch conversation A'),aPath=`/conversations/${encodeURIComponent(a)}`;await chat.reconcile();await chat.stop();
  const oldBody=`pre-rejoin-A-${crypto.randomUUID()}`,oldMessage=await peerText(session,peer,a,oldBody);
  const created=record(await peerApi(session,peer,'/conversations/groups','POST',{title:'native batch self join B',member_ids:[context.user_id]}));assert(typeof created.id==='string','Actual group B ID missing.');
  const b=created.id,bPath=`/conversations/${encodeURIComponent(b)}`;
  gate=gateResponse(`${new URL(session.config.API_BASE_URL,location.origin).pathname}${bPath}`);
  nativeTransitionDiagnostic.stage='mixed_batch_B_authorization_held';await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual restart W02 missing.');await gate.reached;
  const beforeVersion=chat.getSnapshot().details[a]?.membership_version??0;
  await peerApi(session,peer,`${aPath}/members/${encodeURIComponent(context.user_id)}`,'DELETE');await peerApi(session,peer,`${aPath}/members`,'POST',{user_id:context.user_id});
  await until(()=>!chat.getSnapshot().denied.includes(a)&&(chat.getSnapshot().details[a]?.membership_version??0)>beforeVersion,'Live A rejoin did not complete while B was awaiting A12.');
  nativeTransitionDiagnostic.stage='mixed_batch_old_A_body_after_B_release';gate.release();gate.restore();gate=null;
  try{await chat.reconcile();}catch(error){if(!(error instanceof RepositoryCancelled))throw error;await chat.reconcile();}
  const snapshot=chat.getSnapshot();assert(!(snapshot.messages[a]??[]).some(message=>message.id===oldMessage),'Prepared W16 reinstalled A old body after A changed generation.');
  const projection=await nativePartition(context.user_id,context.device_id),messages=record(projection.messages)[a];assert(!Array.isArray(messages)||!messages.some(message=>record(message).id===oldMessage),'Prepared W16 advanced its cursor together with an unauthorized A projection.');
 }finally{gate?.restore();await chat.stop();}
}

// The expiry callback is a parent-owned PostgreSQL fixture fault, not a new product API.
// Execute against the owned API schema with bound user ID:
export const nativeReceiptCursorExpirySql="UPDATE sync_cursors SET expires_at=CURRENT_TIMESTAMP-INTERVAL '1 second' WHERE user_id=$1";
export async function runReceiptRecoveryRegressions(session:SessionController,peer:AccessSession,expireOwnCursor:(userId:string)=>Promise<void>,caseOnly:'inaccessibleFirst'|'prejoinAbsent'):Promise<void> {
 const owner=session.getSnapshot().context;assert(owner.state==='authenticated','Actual native fixture session required.');
 const chat=new ChatController(session),targets=new Set<string>(),transport=holdReadCommands(()=>targets);
 const original=session.request.bind(session);const queries:Record<string,number>={};let phase='setup';
 session.request=new Proxy(original,{async apply(method,thisArg,args){
  const path:unknown=args[0];if(typeof path==='string'&&path.includes('/messages?')){const id=path.split('/')[2];queries[id]=(queries[id]??0)+1;}
  return Reflect.apply(method,thisArg,args);
 }});
 try{
  nativeTransitionDiagnostic.stage=`recovery_${caseOnly}_setup`;await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual W02 missing.');
  const a=await fixtureGroup(session,chat,peer,'native recovery first group'),aPath=`/conversations/${encodeURIComponent(a)}`;
  const b=await fixtureGroup(session,chat,peer,'native recovery authorized later group');
  const first=await peerText(session,peer,a,`old recovery A ${crypto.randomUUID()}`);
  await chat.openChat(a);await until(()=>chat.getSnapshot().receipts[first]?.confirmed==='delivered','Actual first-group W08 missing.');
  const later=await peerText(session,peer,b,`older authorized recovery B ${crypto.randomUUID()}`);
  await chat.openChat(b);await until(()=>chat.getSnapshot().receipts[later]?.confirmed==='delivered','Actual later-group W08 missing.');
  for(let index=0;index<21;index++){const text=`authorized later B ${crypto.randomUUID()}`;await chat.sendText(b,text);await until(()=>chat.getSnapshot().messages[b]?.some(message=>message.text===text)??false,'Actual later-group history missing.');await new Promise<void>(resolve=>window.setTimeout(resolve,250));}
  await chat.reconcile();
  targets.add(first);targets.add(later);await chat.receipt(first,a,'read');await until(()=>transport.held(),'Actual first-group read not pending.');
  await chat.receipt(later,b,'read');await chat.stop();
  await session.request(`${aPath}/members/${encodeURIComponent(owner.user_id)}`,{method:'DELETE'});
  if(caseOnly==='prejoinAbsent'){await peerApi(session,peer,`${aPath}/members`,'POST',{user_id:owner.user_id});await peerText(session,peer,a,`new join recovery A ${crypto.randomUUID()}`);}
  await expireOwnCursor(owner.user_id);phase='recover';nativeTransitionDiagnostic.stage=`recovery_${caseOnly}_actual_cursor_reset`;
  await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual reset W02 missing.');
  await chat.reconcile();transport.release();
  await until(()=>chat.getSnapshot().receipts[later]?.confirmed==='read','Unavailable first-group recovery starved the authorized later-group read.');
  const firstReceipt=chat.getSnapshot().receipts[first];assert(firstReceipt?.desired==='read','Original unavailable desired receipt was lost.');assert(firstReceipt.confirmed!=='read','Unavailable target was fabricated as read.');
  assert(firstReceipt.blocked&&firstReceipt.autoRetryStopped&&['FORBIDDEN','NOT_FOUND'].includes(firstReceipt.error??''),'Complete current-authority recovery did not persist a terminal blocked state.');
  const count=queries[a]??0;nativeTransitionDiagnostic.stage=`recovery_${caseOnly}_second_reconcile_no_rescan`;await chat.reconcile();
  assert((queries[a]??0)===count,'A completed unavailable-target history scan restarted during another reconciliation.');
 }catch(error){nativeTransitionDiagnostic.stage=`recovery_${caseOnly}_${phase}_failed`;throw error;}
 finally{transport.restore();session.request=original;await chat.stop();}
}
