import { ChatController } from '../src/chat';
import { record, RepositoryCancelled } from '../src/repository';
import type { SessionController } from '../src/session';
import type { AccessSession, ConversationCreateResult, ConversationDetail, ConversationMutationResult, MemberMutationResult } from '../src/types';
export { SessionController } from '../src/session';

// Parent-owned fresh HTTPS browser context, actual authenticated SessionController,
// and separately authenticated peer. Every response/frame/partition is product-owned.
export const detailNativeDiagnostic:{stage:string;capturedVersions:Array<number|null>;ownerAuthentications:number;queuedBeforeRelease:boolean;preparedGroups:number;evicted:boolean}={stage:'not_started',capturedVersions:[],ownerAuthentications:0,queuedBeforeRelease:false,preparedGroups:0,evicted:false};
interface DetailGate {count:(version:number|null)=>number;returned:(version:number|null)=>number;consumed:(version:number|null)=>number;requests:()=>number;pendingResponses:()=>number;releaseCaptured:(version:number|null,request:number)=>void;release:(version:number|null)=>void;restore:()=>void}
interface PartitionHold {release:()=>Promise<void>}
interface NativeOperationOutcome {done:()=>boolean;result:Promise<unknown>}
export interface DetailSameAuthorityResult {membershipVersion:3;ownerAuthentications:number;queued:boolean}
function assert(condition:unknown,message:string):asserts condition {if(!condition)throw new Error(message);}
async function until(predicate:()=>boolean,label:string):Promise<void>{const deadline=performance.now()+8_000;while(!predicate()){if(performance.now()>=deadline)throw new Error(label);const {promise,resolve}=Promise.withResolvers<void>();window.setTimeout(resolve,10);await promise;}}
function nextTurn():Promise<void>{const {promise,resolve}=Promise.withResolvers<void>();window.setTimeout(resolve,0);return promise;}
function ownerOf(session:SessionController):{user:string;device:string;generation:number}{const context=session.getSnapshot().context;assert(context.state==='authenticated','Actual authenticated native fixture SessionController required.');return {user:context.user_id,device:context.device_id,generation:context.session_generation};}
function outcome(work:Promise<void>):NativeOperationOutcome {let done=false;return {done:()=>done,result:work.then(()=>{done=true;return null;},error=>{done=true;return error;})};}
function observeSocket(session:SessionController):{versions:number[];authentications:()=>number;conversation:(id:string)=>void;restore:()=>void} {
 const original=window.WebSocket,owner=ownerOf(session),versions:number[]=[];let id:string|null=null,authentications=0;
 window.WebSocket=new Proxy(original,{construct(target,args,newTarget){
  const value:unknown=Reflect.construct(target,args,newTarget);assert(value instanceof original,'Socket observer must retain native WebSocket.');
  value.addEventListener('message',event=>{if(typeof event.data!=='string')return;const frame=record(JSON.parse(event.data)),payload=record(frame.payload);
   if(frame.event==='auth.accepted'&&payload.user_id===owner.user&&payload.device_id===owner.device){++authentications;detailNativeDiagnostic.ownerAuthentications=authentications;}
   if((frame.event==='conversation.updated'||frame.event==='conversation.member_removed')&&frame.conversation_id===id&&typeof payload.membership_version==='number')versions.push(payload.membership_version);
  });return value;
 }});
 return {versions,authentications:()=>authentications,conversation:value=>{id=value;},restore:()=>{window.WebSocket=original;}};
}
function detailGate(session:SessionController,id:string,versions:ReadonlyArray<number|null>,selective=false):DetailGate {
 const original=window.fetch,path=new URL(`${session.config.API_BASE_URL}/conversations/${encodeURIComponent(id)}`).pathname;
 let started=0,received=0;
 const held=new Map<number|null,{promise:Promise<void>;release:()=>void}>(),captured=new Map<number|null,number>(),returned=new Map<number|null,number>(),consumed=new Map<number|null,number>();
 const individual=selective?new Map<number|null,Map<number,()=>void>>():null,released=selective?new Set<number>():null;
 for(const version of versions){const {promise,resolve}=Promise.withResolvers<void>();held.set(version,{promise,release:resolve});}
 window.fetch=new Proxy(original,{async apply(target,thisArg,args){
  const input:unknown=args[0],init:unknown=args[1],request=input instanceof Request?input:null,url=new URL(request?.url??String(input),location.href);
  const method=init!==null&&typeof init==='object'&&'method' in init&&typeof init.method==='string'?init.method:request?.method??'GET';
  const matching=method==='GET'&&url.pathname===path,ordinal=matching?++started:0;
  const value:unknown=await Reflect.apply(target,thisArg,args);assert(value instanceof Response,'HTTP gate must retain an actual native response.');
  if(!matching||!value.ok){if(matching)++received;return value;}
  // Buffer and return the exact HTTP bytes and headers; do not fabricate detail rows.
  const bytes=await value.arrayBuffer(),data=record(record(JSON.parse(new TextDecoder().decode(bytes))).data),version=data.membership_version;
  assert(version===null||typeof version==='number','Actual A12 membership version missing.');
  captured.set(version,(captured.get(version)??0)+1);detailNativeDiagnostic.capturedVersions.push(version);++received;
  const gate=held.get(version);if(gate){if(individual&&released){if(!released.has(ordinal)){const {promise,resolve}=Promise.withResolvers<void>();let entries=individual.get(version);if(!entries){entries=new Map();individual.set(version,entries);}entries.set(ordinal,resolve);await promise;entries.delete(ordinal);}}else await gate.promise;}
  returned.set(version,(returned.get(version)??0)+1);
  const buffered=new Response(bytes,{status:value.status,statusText:value.statusText,headers:value.headers}),json=buffered.json.bind(buffered);
  buffered.json=async()=>{const result:unknown=await json();consumed.set(version,(consumed.get(version)??0)+1);return result;};return buffered;
 }});
 const release=(version:number|null):void=>{const gate=held.get(version);held.delete(version);gate?.release();for(const resolve of individual?.get(version)?.values()??[])resolve();individual?.delete(version);};
 const releaseCaptured=(version:number|null,request:number):void=>{assert(released,'Selective native response gate required.');released.add(request);individual?.get(version)?.get(request)?.();};
 return {count:version=>captured.get(version)??0,returned:version=>returned.get(version)??0,consumed:version=>consumed.get(version)??0,requests:()=>started,pendingResponses:()=>started-received,releaseCaptured,release,restore:()=>{window.fetch=original;for(const version of [...held.keys()])release(version);}};
}
async function partition(user:string,device:string):Promise<Record<string,unknown>> {
 const opened=Promise.withResolvers<IDBDatabase>(),request=indexedDB.open('hine-chat-v1');request.onsuccess=()=>opened.resolve(request.result);request.onerror=()=>opened.reject(request.error);const database=await opened.promise;
 try{const read=Promise.withResolvers<Record<string,unknown>>(),transaction=database.transaction('partitions'),request=transaction.objectStore('partitions').get(JSON.stringify([user,device]));let value:unknown;request.onsuccess=()=>{value=request.result;};transaction.oncomplete=()=>read.resolve(record(value));transaction.onabort=()=>read.reject(new Error('Native partition read aborted.'));transaction.onerror=()=>read.reject(new Error('Native partition read failed.'));return await read.promise;}finally{database.close();}
}
async function holdPartition(user:string,device:string):Promise<PartitionHold> {
 const opened=Promise.withResolvers<IDBDatabase>(),request=indexedDB.open('hine-chat-v1');request.onsuccess=()=>opened.resolve(request.result);request.onerror=()=>opened.reject(request.error);const database=await opened.promise;
 let released=false;const {promise:reached,resolve:ready}=Promise.withResolvers<void>();
 const transaction=database.transaction('partitions','readwrite'),store=transaction.objectStore('partitions'),key=JSON.stringify([user,device]);
 const {promise:completed,resolve,reject}=Promise.withResolvers<void>();transaction.oncomplete=()=>resolve();transaction.onabort=()=>reject(new Error('Native partition hold aborted.'));transaction.onerror=()=>reject(new Error('Native partition hold failed.'));
 const pump=():void=>{const request=store.get(key);request.onsuccess=()=>{ready();if(!released)pump();};};pump();
 await Promise.race([reached,completed.then(()=>{throw new Error('Native partition hold ended before reaching its read.');})]);
 return {release:async()=>{released=true;try{await completed;}finally{database.close();}}};
}
async function createGroup(session:SessionController,chat:ChatController,peer:AccessSession):Promise<string> {
 await chat.reconcile();
 const created=await session.request<ConversationCreateResult>('/conversations/groups',{method:'POST',idempotencyKey:crypto.randomUUID(),json:{title:'detail version one',member_ids:[peer.user_id]}});
 assert(created.data.membership_version===1,'Fresh actual A14 must start at version one.');
 await until(()=>chat.getSnapshot().details[created.data.id]?.membership_version===1,'Actual live self-join did not install initial detail.');await chat.reconcile();
 const owner=ownerOf(session),stored=await partition(owner.user,owner.device);assert(record(stored.selfMembershipVersions)[created.data.id]===1,'Actual initial self-join commit did not settle before openChat.');
 await chat.openChat(created.data.id);
 assert(chat.getSnapshot().details[created.data.id]?.membership_version===1,'Actual initial A12 did not install version one.');return created.data.id;
}
async function peerApi(session:SessionController,peer:AccessSession,path:string,method:string,json?:unknown):Promise<unknown> {
 const response=await fetch(`${session.config.API_BASE_URL}${path}`,{method,credentials:'omit',headers:{Authorization:`Bearer ${peer.access_token}`,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},...(json===undefined?{}:{body:JSON.stringify(json)}),signal:AbortSignal.timeout(8_000)});
 assert(response.ok,'Actual peer API mutation failed.');return response.status===204?null:record(await response.json()).data;
}
async function peerText(session:SessionController,peer:AccessSession,id:string):Promise<string> {
 const {promise,resolve,reject}=Promise.withResolvers<string>();
  const socket=new WebSocket(session.config.WS_URL),auth=crypto.randomUUID(),send=crypto.randomUUID(),c1=crypto.randomUUID();
  const fail=():void=>{window.clearTimeout(timer);socket.close();reject(new Error('Actual peer W01/W05/W06 failed.'));};
  const timer=window.setTimeout(fail,8_000);
  socket.onopen=()=>socket.send(JSON.stringify({event:'auth.authenticate',event_id:auth,timestamp:new Date().toISOString(),payload:{access_token:peer.access_token,device_id:peer.device_id}}));
  socket.onmessage=event=>{try{const frame=record(JSON.parse(String(event.data))),payload=record(frame.payload);
   if(frame.event==='error'){fail();return;}
   if(frame.event==='auth.accepted'&&frame.correlation_id===auth){assert(payload.user_id===peer.user_id&&payload.device_id===peer.device_id&&payload.session_generation===peer.session_generation,'Actual peer W02 binding mismatch.');socket.send(JSON.stringify({event:'message.send',event_id:send,timestamp:new Date().toISOString(),conversation_id:id,payload:{client_message_id:c1,type:'text',text:`native detail unread ${crypto.randomUUID()}`}}));}
   if(frame.event==='message.ack'&&frame.correlation_id===send){assert(payload.client_message_id===c1&&payload.status==='persisted'&&typeof payload.message_id==='string','Actual peer W06 mismatch.');window.clearTimeout(timer);socket.close();resolve(payload.message_id);}
  }catch{fail();}};socket.onerror=fail;
 return promise;
}
function assertDetail(actual:ConversationDetail|undefined,owner:string,peer:string,caseOnly:'title'|'role'|'members'):void {
 assert(actual?.membership_version===3,'Delayed actual A12 version two downgraded installed version three.');
 assert(actual.title===(caseOnly==='title'?'detail version three':'detail version two'),'Delayed actual A12 restored an obsolete title.');
 assert(actual.members.length===(caseOnly==='members'?1:2),'Delayed actual A12 restored an obsolete member list.');
 assert(actual.members.find(member=>member.user_id===owner)?.role==='admin','Current owner role was lost.');
 assert(caseOnly==='members'?!actual.members.some(member=>member.user_id===peer):actual.members.find(member=>member.user_id===peer)?.role==='admin','Delayed actual A12 restored an obsolete peer role or member.');
}

export async function runDetailSameAuthorityRegression(session:SessionController,peer:AccessSession,caseOnly:'title'|'role'|'members'='role',queued=false):Promise<DetailSameAuthorityResult> {
 const owner=ownerOf(session),trace=observeSocket(session),chat=new ChatController(session);let gate:DetailGate|null=null,hold:PartitionHold|null=null,unsubscribe:(()=>void)|null=null,retainedMessage:string|null=null,retainedReceipt:string|null=null;
 detailNativeDiagnostic.stage=`${queued?'queued':'reverse'}_${caseOnly}_setup`;detailNativeDiagnostic.capturedVersions=[];detailNativeDiagnostic.queuedBeforeRelease=false;
 try{
  await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual owner W02 missing.');const id=await createGroup(session,chat,peer),path=`/conversations/${encodeURIComponent(id)}`;trace.conversation(id);
  const baselineAuthentications=trace.authentications();let errors=0,connectionChanges=0;unsubscribe=chat.subscribe(()=>{const snapshot=chat.getSnapshot();if(snapshot.error!==null)++errors;if(snapshot.connection!=='ready')++connectionChanges;});
  gate=detailGate(session,id,[2,3]);
  if(caseOnly==='title'){const changed=await session.request<MemberMutationResult>(`${path}/members/${encodeURIComponent(peer.user_id)}`,{method:'PATCH',json:{role:'admin'}});assert(changed.data.membership_version===2,'Actual A17 did not produce version two.');}
  else{const changed=await session.request<ConversationMutationResult>(path,{method:'PATCH',json:{title:'detail version two'}});assert(changed.data.membership_version===2,'Actual A15 did not produce version two.');}
  await until(()=>gate!.count(2)>=1&&trace.versions.includes(2),'Actual W20-driven version-two A12 was not captured.');
  const slow=outcome(chat.refreshConversation(id));await until(()=>gate!.count(2)>=2,'Explicit old consumer A12 was not captured.');
  if(queued)hold=await holdPartition(owner.user,owner.device);
  detailNativeDiagnostic.stage=`${queued?'queued':'reverse'}_${caseOnly}_actual_version_three`;
  if(caseOnly==='title'){const changed=await session.request<ConversationMutationResult>(path,{method:'PATCH',json:{title:'detail version three'}});assert(changed.data.membership_version===3,'Actual A15 did not produce version three.');}
  else if(caseOnly==='role'){const changed=await session.request<MemberMutationResult>(`${path}/members/${encodeURIComponent(peer.user_id)}`,{method:'PATCH',json:{role:'admin'}});assert(changed.data.membership_version===3,'Actual A17 did not produce version three.');}
  else await session.request(`${path}/members/${encodeURIComponent(peer.user_id)}`,{method:'DELETE'});
  await until(()=>trace.versions.includes(3),'Actual version-three group event was not received.');await nextTurn();
  if(!queued)await until(()=>chat.getSnapshot().details[id]?.membership_version===3,'Actual version-three group event did not finish its commit.');
  const fresh=outcome(chat.refreshConversation(id));await until(()=>gate!.count(3)>=1,'Actual fresh A12 did not observe version three.');gate.release(3);
  if(queued){
   await until(()=>gate!.consumed(3)>=1,'Fresh actual HTTP bytes were not consumed by the API adapter.');await nextTurn();
   assert(!fresh.done()&&chat.getSnapshot().details[id]?.membership_version===2,'Native IDB hold did not leave version three queued behind version two.');
   gate.release(2);await until(()=>gate!.consumed(2)>=2,'Old actual HTTP bytes were not consumed by the API adapter.');await nextTurn();
   assert(!slow.done()&&!fresh.done(),'Native IDB commit escaped the real transaction hold.');detailNativeDiagnostic.queuedBeforeRelease=true;
   await hold!.release();hold=null;
  }else{
   assert(await fresh.result===null,'Fresh actual A12 consumer failed.');assertDetail(chat.getSnapshot().details[id],owner.user,peer.user_id,caseOnly);
   if(caseOnly!=='members'){
    retainedMessage=await peerText(session,peer,id);const messageId=retainedMessage;
    await until(()=>chat.getSnapshot().messages[id]?.some(message=>message.id===messageId)??false,'Current native group W07 missing.');await until(()=>chat.getSnapshot().receipts[messageId]?.confirmed==='delivered','Current native group W08 missing.');
    await chat.setDraft(id,'current native detail draft');await chat.refreshConversation(id);
    assert(chat.getSnapshot().details[id]?.unread_count===1,'A same-version fresh group A12 was discarded.');retainedReceipt=JSON.stringify(chat.getSnapshot().receipts[messageId]);
   }
   gate.release(2);
  }
  assert(await fresh.result===null,'Fresh queued A12 consumer failed.');assert(await slow.result===null,'An obsolete same-authority A12 was reported as an unknown or cancelled operation.');
  // Both queued fire-and-forget and explicit refreshes have drained before the checks.
  await nextTurn();assertDetail(chat.getSnapshot().details[id],owner.user,peer.user_id,caseOnly);
  assert(chat.getSnapshot().conversations[id]?.title===chat.getSnapshot().details[id]?.title,'Summary/title projection downgraded independently.');
  if(retainedMessage){assert(chat.getSnapshot().details[id]?.unread_count===1&&chat.getSnapshot().conversations[id]?.unread_count===1,'Obsolete A12 restored an older unread count.');assert(chat.getSnapshot().messages[id]?.some(message=>message.id===retainedMessage),'Metadata arbitration cleared a current authorized body.');assert(JSON.stringify(chat.getSnapshot().receipts[retainedMessage])===retainedReceipt,'Metadata arbitration changed an existing C2.');assert(chat.getSnapshot().drafts[id]==='current native detail draft','Metadata arbitration cleared the current native draft.');}
  const stored=await partition(owner.user,owner.device),storedDetail=record(record(stored.details)[id]);
  assert(storedDetail.membership_version===3&&storedDetail.title===chat.getSnapshot().details[id]?.title,'Native durable detail was downgraded by old HTTP bytes.');
  assert(record(stored.selfMembershipVersions)[id]===1,'A metadata refresh consumed the original self-join boundary.');
  assert(errors===0&&connectionChanges===0&&trace.authentications()===baselineAuthentications,'Stale same-authority A12 caused a false unknown outcome or network reconnect.');
  detailNativeDiagnostic.stage=`${queued?'queued':'reverse'}_${caseOnly}_passed`;return {membershipVersion:3,ownerAuthentications:trace.authentications(),queued};
 }finally{gate?.restore();await hold?.release();unsubscribe?.();trace.restore();await chat.stop();}
}
export function runDetailQueuedCommitRegression(session:SessionController,peer:AccessSession):Promise<DetailSameAuthorityResult>{return runDetailSameAuthorityRegression(session,peer,'role',true);}

export async function runDetailRevocationRejoinRegression(session:SessionController,peer:AccessSession):Promise<{membershipVersion:number;ownerAuthentications:number}> {
 const owner=ownerOf(session),trace=observeSocket(session),chat=new ChatController(session);let gate:DetailGate|null=null;
 detailNativeDiagnostic.stage='revocation_rejoin_setup';detailNativeDiagnostic.capturedVersions=[];
 try{
  await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual owner W02 missing.');const id=await createGroup(session,chat,peer),path=`/conversations/${encodeURIComponent(id)}`;
  await session.request(`${path}/members/${encodeURIComponent(peer.user_id)}`,{method:'PATCH',json:{role:'admin'}});await chat.refreshConversation(id);await chat.reconcile();
  const oldBody=`native private old membership ${crypto.randomUUID()}`;await chat.sendText(id,oldBody);await until(()=>chat.getSnapshot().messages[id]?.some(message=>message.text===oldBody)??false,'Actual old W06 fixture missing.');
  gate=detailGate(session,id,[2]);const stale=outcome(chat.refreshConversation(id));await until(()=>gate!.count(2)>=1,'Actual pre-withdrawal A12 bytes not held.');
  detailNativeDiagnostic.stage='revocation_actual_remove_refresh_rejoin';
  await session.request(`${path}/members/${encodeURIComponent(owner.user)}`,{method:'DELETE'});await chat.withdraw(id);
  assert(chat.getSnapshot().details[id]===undefined&&chat.getSnapshot().denied.includes(id),'Actual withdrawal retained forbidden metadata.');
  assert(await stale.result instanceof RepositoryCancelled,'Withdrawal did not cancel the old conversation ticket.');
  await session.refresh();assert(ownerOf(session).generation>owner.generation,'Actual A03 did not rotate the session generation.');await until(()=>chat.getSnapshot().connection==='ready','Replacement actual owner W02 missing.');await chat.reconcile();
  await peerApi(session,peer,`${path}/members`,'POST',{user_id:owner.user});await until(()=>chat.getSnapshot().details[id]?.membership_version===4&&!chat.getSnapshot().denied.includes(id),'Actual version-four self join did not commit.');await peerApi(session,peer,path,'PATCH',{title:'detail after actual rejoin'});
  await chat.openChat(id);await chat.reconcile();const current=chat.getSnapshot().details[id];assert(current?.membership_version===5&&current.title==='detail after actual rejoin','Actual post-rejoin A12 not installed.');
  gate.release(2);await until(()=>gate!.returned(2)>=1,'Old successful HTTP bytes were not released.');await nextTurn();
  assert(chat.getSnapshot().details[id]?.membership_version===5&&chat.getSnapshot().details[id]?.title==='detail after actual rejoin','Old-session A12 crossed withdrawal/rejoin authority.');
  assert(!chat.getSnapshot().denied.includes(id)&&chat.getSnapshot().currentConversation===id,'Old response reinstated denial or lost the current chat.');
  assert(!(chat.getSnapshot().messages[id]??[]).some(message=>message.text===oldBody),'Old successful detail revived a pre-join private body.');
  const stored=await partition(owner.user,owner.device);assert(record(stored.selfMembershipVersions)[id]===4,'Metadata version five swallowed the actual version-four self-join boundary.');
  assert(record(record(stored.details)[id]).membership_version===5,'Old detail crossed into the durable replacement generation.');
  assert(chat.getSnapshot().connection==='ready'&&chat.getSnapshot().error===null,'Cancelled old generation poisoned the new connection.');
  detailNativeDiagnostic.stage='revocation_rejoin_passed';return {membershipVersion:5,ownerAuthentications:trace.authentications()};
 }finally{gate?.restore();trace.restore();await chat.stop();}
}

export async function runDetailDirectNullRegression(session:SessionController,peer:AccessSession):Promise<{membershipVersion:null;unreadCount:number}> {
 const owner=ownerOf(session),chat=new ChatController(session);detailNativeDiagnostic.stage='direct_null_setup';
 try{
  await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual owner W02 missing.');const created=await session.request<ConversationCreateResult>('/conversations/direct',{method:'POST',json:{peer_user_id:peer.user_id}});
  assert(created.data.membership_version===null&&created.data.title===null,'Actual A13 direct metadata is not nullable.');const id=created.data.id;await chat.openChat(id);await chat.reconcile();
  const before=await session.request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`);assert(before.data.membership_version===null,'Actual direct A12 version is not null.');
  const messageId=await peerText(session,peer,id);await until(()=>chat.getSnapshot().messages[id]?.some(message=>message.id===messageId)??false,'Actual peer direct W07 missing.');
  await chat.refreshConversation(id);const actual=chat.getSnapshot().details[id];
  assert(actual?.membership_version===null&&actual.title===null,'Null membership version was treated as a group version.');assert(actual.unread_count===before.data.unread_count+1,'A later null-version A12 was incorrectly discarded.');
  assert(actual.members.length===2&&actual.members.some(member=>member.user_id===owner.user)&&actual.members.some(member=>member.user_id===peer.user_id),'Direct members were changed by the version guard.');
  const stored=await partition(owner.user,owner.device);assert(record(record(stored.details)[id]).membership_version===null,'Native IDB changed direct membership null.');
  assert(chat.getSnapshot().connection==='ready'&&chat.getSnapshot().error===null,'Direct null-version refresh created a false operation failure.');detailNativeDiagnostic.stage='direct_null_passed';return {membershipVersion:null,unreadCount:actual.unread_count};
 }finally{await chat.stop();}
}

export async function runDetailEvictionRegression(session:SessionController,peer:AccessSession,caseOnly:'installedDetail'|'summaryAfterEviction'|'roleAfterEviction'='installedDetail'):Promise<{preparedGroups:201;summaryTitle:string;ownerAuthentications:number}> {
 const owner=ownerOf(session),trace=observeSocket(session),chat=new ChatController(session);let gate:DetailGate|null=null,unsubscribe:(()=>void)|null=null;
 detailNativeDiagnostic.stage=caseOnly==='installedDetail'?'eviction_preparing_actual_201_groups':`${caseOnly==='roleAfterEviction'?'role':'summary'}_after_eviction_preparing_actual_201_groups`;detailNativeDiagnostic.capturedVersions=[];detailNativeDiagnostic.preparedGroups=0;detailNativeDiagnostic.evicted=false;
 try{
  await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual owner W02 missing.');const id=await createGroup(session,chat,peer),path=`/conversations/${encodeURIComponent(id)}`;trace.conversation(id);detailNativeDiagnostic.preparedGroups=1;
  // Prepare 199 actual, empty, owner-only groups before holding any target HTTP.
  // No messages/anchors protect the target from the existing detail-cache bound.
  for(let index=0;index<199;index++){
   const created=await session.request<ConversationCreateResult>('/conversations/groups',{method:'POST',idempotencyKey:crypto.randomUUID(),json:{title:`native eviction padding ${index}`,member_ids:[]}});
   assert(created.data.membership_version===1,'Actual padding A14 did not start at version one.');
   await until(()=>chat.getSnapshot().details[created.data.id]?.membership_version===1,'Actual padding self-join did not install its detail.');
   ++detailNativeDiagnostic.preparedGroups;
  }
  await chat.reconcile();
  // The 201st group is real but not yet visible to the owner; adding the owner
  // later yields exactly one new authorized detail while the old A12 is held.
  const finalGroup=record(await peerApi(session,peer,'/conversations/groups','POST',{title:'native eviction final private group',member_ids:[]}));
  assert(typeof finalGroup.id==='string'&&finalGroup.membership_version===1,'Actual peer A14 did not create the final group.');const finalId=finalGroup.id;++detailNativeDiagnostic.preparedGroups;
  assert(chat.getSnapshot().details[id]?.membership_version===1,'Target was evicted before the 201st authorized detail.');
  assert(!chat.getSnapshot().messages[id]?.length&&!chat.getSnapshot().anchors[id],'Target must have no cache-eviction protection.');
  const baselineAuthentications=trace.authentications();let errors=0,connectionChanges=0;unsubscribe=chat.subscribe(()=>{if(chat.getSnapshot().error!==null)++errors;if(chat.getSnapshot().connection!=='ready')++connectionChanges;});
  if(caseOnly!=='installedDetail'){
   const stage=caseOnly==='roleAfterEviction'?'role_after_eviction':'summary_after_eviction',title=caseOnly==='roleAfterEviction'?'native roles newer than evicted detail':'native summary newer than evicted detail';
   detailNativeDiagnostic.stage=`${stage}_actual_201st_self_join`;
   await peerApi(session,peer,`/conversations/${encodeURIComponent(finalId)}/members`,'POST',{user_id:owner.user});
   await until(()=>chat.getSnapshot().details[finalId]?.membership_version===2&&chat.getSnapshot().details[id]===undefined,'Actual 201st detail did not evict the version-one target.');await chat.reconcile();
   const evicted=await partition(owner.user,owner.device);assert(record(evicted.details)[id]===undefined,'Native IDB did not evict version-one target detail.');
   assert(record(record(evicted.conversations)[id]).title==='detail version one','Version-one retained summary changed before any mutation.');assert(record(evicted.selfMembershipVersions)[id]===1,'Eviction changed the independent self-join boundary.');detailNativeDiagnostic.evicted=true;
   gate=detailGate(session,id,[2,3]);detailNativeDiagnostic.stage=`${stage}_holding_two_and_three`;
   if(caseOnly==='roleAfterEviction'){const changed=await session.request<ConversationMutationResult>(path,{method:'PATCH',json:{title}});assert(changed.data.membership_version===2,'Actual post-eviction A15 did not produce version two.');}
   else{const changed=await session.request<MemberMutationResult>(`${path}/members/${encodeURIComponent(peer.user_id)}`,{method:'PATCH',json:{role:'admin'}});assert(changed.data.membership_version===2,'Actual post-eviction A17 did not produce version two.');}
   await until(()=>gate!.count(2)>=1&&trace.versions.includes(2),'Actual post-eviction version-two W20/A12 not captured.');
   const slow=outcome(chat.refreshConversation(id));await until(()=>gate!.count(2)>=2,'Explicit post-eviction version-two HTTP not held.');
   assert(chat.getSnapshot().details[id]===undefined,'A held version-two A12 installed a full detail.');
   if(caseOnly==='roleAfterEviction'){const changed=await session.request<MemberMutationResult>(`${path}/members/${encodeURIComponent(peer.user_id)}`,{method:'PATCH',json:{role:'admin'}});assert(changed.data.membership_version===3,'Actual post-eviction A17 did not produce version three.');}
   else{const changed=await session.request<ConversationMutationResult>(path,{method:'PATCH',json:{title}});assert(changed.data.membership_version===3,'Actual post-eviction A15 did not produce version three.');}
   await until(()=>trace.versions.includes(3)&&chat.getSnapshot().conversations[id]?.title===title&&gate!.count(3)>=1,'Actual post-eviction W20 did not commit current metadata.');
   assert(chat.getSnapshot().details[id]===undefined,'Held version-three A12 installed a full detail before the summary-only check.');
   const currentSummary=await partition(owner.user,owner.device);assert(record(currentSummary.details)[id]===undefined&&record(record(currentSummary.conversations)[id]).title===title,'Native IDB did not retain the current summary with evicted detail.');
   const fresh=outcome(chat.refreshConversation(id));await until(()=>gate!.count(3)>=2,'Explicit actual version-three HTTP not held.');await chat.setDraft(id,'native summary-only draft');
   detailNativeDiagnostic.stage=`${stage}_releasing_two_before_three`;gate.release(2);
   assert(await slow.result===null,'Obsolete summary-only detail created a false operation failure.');await until(()=>gate!.consumed(2)===gate!.count(2),'Old summary-only HTTP consumers did not drain.');await nextTurn();
   assert(!fresh.done()&&gate.count(3)>=2&&gate.consumed(3)===0,'Version-three HTTP escaped its native byte gate and could hide a downgrade.');
   assert(chat.getSnapshot().conversations[id]?.title===title,'Delayed version-two A12 downgraded a newer W20 summary committed after detail eviction.');
   assert(chat.getSnapshot().details[id]===undefined,caseOnly==='roleAfterEviction'?'Delayed version-two A12 installed obsolete roles after an accepted version-three event with no cached detail.':'Delayed version-two A12 reinstalled obsolete metadata while all current A12 responses remained held.');
   const retained=await partition(owner.user,owner.device);assert(record(retained.details)[id]===undefined&&record(record(retained.conversations)[id]).title===title,'Old actual A12 downgraded the durable current metadata.');
   gate.release(3);assert(await fresh.result===null,'Current summary-only A12 failed after its release.');await nextTurn();
   assert(chat.getSnapshot().details[id]?.membership_version===3&&chat.getSnapshot().conversations[id]?.title===title,'Actual current detail did not hydrate after metadata arbitration.');assert(chat.getSnapshot().details[id]?.members.find(member=>member.user_id===peer.user_id)?.role==='admin','Actual current role was not hydrated.');
   assert(chat.getSnapshot().drafts[id]==='native summary-only draft','Summary metadata arbitration cleared the actual draft.');const stored=await partition(owner.user,owner.device);assert(record(stored.selfMembershipVersions)[id]===1,'Summary version three consumed the self-join boundary.');
   assert(errors===0&&connectionChanges===0&&trace.authentications()===baselineAuthentications,'Summary-only obsolete A12 caused a false error or reconnect.');
   detailNativeDiagnostic.stage=`${stage}_passed`;return {preparedGroups:201,summaryTitle:title,ownerAuthentications:trace.authentications()};
  }
  detailNativeDiagnostic.stage='eviction_holding_actual_version_two';gate=detailGate(session,id,[2]);
  const promoted=await session.request<MemberMutationResult>(`${path}/members/${encodeURIComponent(peer.user_id)}`,{method:'PATCH',json:{role:'admin'}});assert(promoted.data.membership_version===2,'Actual eviction A17 did not produce version two.');
  await until(()=>gate!.count(2)>=1&&trace.versions.includes(2),'Actual version-two W20/A12 not captured.');
  const slow=outcome(chat.refreshConversation(id));await until(()=>gate!.count(2)>=2,'Explicit actual old detail not captured.');
  const renamed=await session.request<ConversationMutationResult>(path,{method:'PATCH',json:{title:'detail survives native cache eviction'}});assert(renamed.data.membership_version===3,'Actual eviction A15 did not produce version three.');
  await until(()=>trace.versions.includes(3)&&chat.getSnapshot().details[id]?.membership_version===3,'Actual version-three event did not install.');await chat.reconcile();await chat.refreshConversation(id);
  await until(()=>gate!.pendingResponses()===0&&gate!.consumed(3)===gate!.count(3),'Current actual HTTP consumers did not drain before eviction.');await nextTurn();
  // This actual granular local write is a queue barrier, not injected state.
  // Drafts do not protect details in boundedPartition.
  await chat.setDraft(id,'native draft survives detail eviction');
  assert(chat.getSnapshot().details[id]?.membership_version===3&&chat.getSnapshot().conversations[id]?.title==='detail survives native cache eviction','Current actual A12 was not installed before eviction.');
  detailNativeDiagnostic.stage='eviction_actual_201st_self_join';
  await peerApi(session,peer,`/conversations/${encodeURIComponent(finalId)}/members`,'POST',{user_id:owner.user});
  await until(()=>chat.getSnapshot().details[finalId]?.membership_version===2&&chat.getSnapshot().details[id]===undefined,'Actual 201st detail did not evict the unprotected target.');
  const evicted=await partition(owner.user,owner.device);assert(record(evicted.details)[id]===undefined,'Native IDB did not evict the target detail.');
  assert(record(record(evicted.conversations)[id]).title==='detail survives native cache eviction','Eviction incorrectly discarded the retained current summary.');assert(record(evicted.selfMembershipVersions)[id]===1,'Metadata version was conflated with the self-join boundary.');detailNativeDiagnostic.evicted=true;
  detailNativeDiagnostic.stage='eviction_releasing_obsolete_http';gate.release(2);
  assert(await slow.result===null,'Evicted obsolete detail created a false operation failure.');await until(()=>gate!.consumed(2)===gate!.count(2),'Old native HTTP consumers did not drain.');await nextTurn();
  assert(chat.getSnapshot().conversations[id]?.title==='detail survives native cache eviction','Delayed version-two A12 downgraded the retained summary after detail eviction.');
  const current=chat.getSnapshot().details[id];assert(current===undefined||current.membership_version===3,'Delayed version-two A12 reinstalled evicted obsolete metadata.');
  const stored=await partition(owner.user,owner.device);assert(record(record(stored.conversations)[id]).title==='detail survives native cache eviction','Old actual A12 downgraded the durable summary after eviction.');const storedDetail=record(stored.details)[id];assert(storedDetail===undefined||record(storedDetail).membership_version===3,'Old actual A12 persisted obsolete evicted metadata.');
  assert(chat.getSnapshot().drafts[id]==='native draft survives detail eviction','Metadata floor changed the real draft.');assert(record(stored.selfMembershipVersions)[id]===1,'Eviction recovery consumed the self-join boundary.');
  assert(errors===0&&connectionChanges===0&&trace.authentications()===baselineAuthentications,'Evicted stale A12 caused a false unknown outcome or reconnect.');
  detailNativeDiagnostic.stage='eviction_passed';return {preparedGroups:201,summaryTitle:'detail survives native cache eviction',ownerAuthentications:trace.authentications()};
 }finally{gate?.restore();unsubscribe?.();trace.restore();await chat.stop();}
}

export function runDetailSummaryAfterEvictionRegression(session:SessionController,peer:AccessSession):Promise<{preparedGroups:201;summaryTitle:string;ownerAuthentications:number}>{return runDetailEvictionRegression(session,peer,'summaryAfterEviction');}

export function runDetailRoleAfterEvictionRegression(session:SessionController,peer:AccessSession):Promise<{preparedGroups:201;summaryTitle:string;ownerAuthentications:number}>{return runDetailEvictionRegression(session,peer,'roleAfterEviction');}

export async function runDetailUncachedBootstrapReplayRegression(session:SessionController,peer:AccessSession):Promise<{membershipVersion:3;ownerAuthentications:number}> {
 const owner=ownerOf(session),trace=observeSocket(session),chat=new ChatController(session);let gate:DetailGate|null=null,unsubscribe:(()=>void)|null=null;
 detailNativeDiagnostic.stage='uncached_bootstrap_preparing_actual_group';detailNativeDiagnostic.capturedVersions=[];detailNativeDiagnostic.preparedGroups=0;detailNativeDiagnostic.evicted=false;
 try{
  // Create the real group before this context has any chat connection/projection.
  const created=await session.request<ConversationCreateResult>('/conversations/groups',{method:'POST',idempotencyKey:crypto.randomUUID(),json:{title:'native uncached snapshot version one',member_ids:[peer.user_id]}});
  assert(created.data.membership_version===1,'Actual uncached A14 did not start at version one.');const id=created.data.id,path=`/conversations/${encodeURIComponent(id)}`;trace.conversation(id);detailNativeDiagnostic.preparedGroups=1;
  gate=detailGate(session,id,[1,2,3]);await chat.start();await until(()=>chat.getSnapshot().connection==='ready'&&gate!.count(1)>=1,'Actual first bootstrap A12 version one was not held.');
  const uncached=await partition(owner.user,owner.device);assert(record(uncached.details)[id]===undefined&&record(uncached.conversations)[id]===undefined,'Bootstrap replay fixture must begin with an actually uncached group.');
  const baselineAuthentications=trace.authentications();let errors=0,connectionChanges=0;unsubscribe=chat.subscribe(()=>{if(chat.getSnapshot().error!==null)++errors;if(chat.getSnapshot().connection!=='ready')++connectionChanges;});
  detailNativeDiagnostic.stage='uncached_bootstrap_holding_live_two_and_three';
  const two=await session.request<ConversationMutationResult>(path,{method:'PATCH',json:{title:'native uncached snapshot version two'}});assert(two.data.membership_version===2,'Actual staging A15 did not produce version two.');
  await until(()=>trace.versions.includes(2)&&gate!.count(2)>=1,'Actual staging W20/version-two A12 not captured.');
  const three=await session.request<ConversationMutationResult>(path,{method:'PATCH',json:{title:'native uncached snapshot version three'}});assert(three.data.membership_version===3,'Actual staging A15 did not produce version three.');
  await until(()=>trace.versions.includes(3)&&gate!.count(3)>=1,'Actual staging W20/version-three A12 not captured.');
  assert(chat.getSnapshot().details[id]===undefined&&chat.getSnapshot().conversations[id]===undefined,'Live events incorrectly installed an uncached group before the actual snapshot.');
  detailNativeDiagnostic.stage='uncached_bootstrap_releasing_snapshot_one';gate.release(1);
  await until(()=>chat.getSnapshot().conversations[id]?.title==='native uncached snapshot version three'&&chat.getSnapshot().details[id]?.membership_version===1,'Actual staged replay did not install the newer summary with its captured version-one authority detail.');
  await chat.reconcile();await until(()=>gate!.pendingResponses()===0,'Actual post-bootstrap HTTP responses did not reach their gates.');await chat.setDraft(id,'native staged snapshot draft');
  const staged=await partition(owner.user,owner.device);assert(record(record(staged.details)[id]).membership_version===1&&record(record(staged.conversations)[id]).title==='native uncached snapshot version three','Native IDB did not commit the actual uncached staged replay.');
  assert(gate.consumed(3)===0,'Current HTTP escaped before the staged replay monotonicity check.');
  detailNativeDiagnostic.stage='uncached_bootstrap_releasing_obsolete_two';gate.release(2);
  await until(()=>gate!.consumed(2)===gate!.count(2),'Actual old staging HTTP was not consumed.');await nextTurn();await chat.setDraft(id,'native staged snapshot draft');
  assert(gate.consumed(3)===0,'Current version-three HTTP repaired the staged summary before its assertion.');
  assert(chat.getSnapshot().conversations[id]?.title==='native uncached snapshot version three','Delayed version-two A12 downgraded an uncached bootstrap-replayed version-three summary.');
  assert(chat.getSnapshot().details[id]?.membership_version!==2,'Old staging A12 installed obsolete metadata after current snapshot replay.');
  const retained=await partition(owner.user,owner.device);assert(record(record(retained.conversations)[id]).title==='native uncached snapshot version three','Old staging A12 downgraded the durable replayed summary.');
  gate.release(3);await chat.refreshConversation(id);await until(()=>gate!.pendingResponses()===0&&gate!.consumed(3)===gate!.count(3),'Current staging HTTP did not drain.');await nextTurn();
  assert(chat.getSnapshot().details[id]?.membership_version===3&&chat.getSnapshot().conversations[id]?.title==='native uncached snapshot version three','Current actual metadata did not hydrate after staged replay arbitration.');
  const stored=await partition(owner.user,owner.device);assert(record(record(stored.details)[id]).membership_version===3&&record(stored.selfMembershipVersions)[id]===1,'Snapshot metadata floor altered durable authority/detail separation.');
  assert(chat.getSnapshot().drafts[id]==='native staged snapshot draft','Staging metadata arbitration cleared the actual draft.');
  assert(errors===0&&connectionChanges===0&&trace.authentications()===baselineAuthentications,'Staged stale A12 caused a false unknown outcome or reconnect.');
  detailNativeDiagnostic.stage='uncached_bootstrap_passed';return {membershipVersion:3,ownerAuthentications:trace.authentications()};
 }finally{gate?.restore();unsubscribe?.();trace.restore();await chat.stop();}
}

function gateInitialMembershipFrames(session:SessionController):{arm:()=>void;bind:(id:string)=>void;count:()=>number;releaseThroughSelfJoin:()=>number;restore:()=>void} {
 const original=window.WebSocket,owner=ownerOf(session),held:Array<{socket:WebSocket;event:MessageEvent<unknown>;member:string}>=[],listeners:Array<{socket:WebSocket;listener:(event:MessageEvent<unknown>)=>void}>=[];
 let armed=false,id:string|null=null;
 window.WebSocket=new Proxy(original,{construct(target,args,newTarget){
  const value:unknown=Reflect.construct(target,args,newTarget);assert(value instanceof original,'Membership gate must retain native WebSocket.');const socket=value;
  const listener=(event:MessageEvent<unknown>):void=>{
   if(!armed||typeof event.data!=='string')return;const frame=record(JSON.parse(event.data)),payload=record(frame.payload);
   if(frame.event!=='conversation.member_added'||payload.actor_id!==owner.user||typeof frame.conversation_id!=='string'||typeof payload.member_id!=='string'||id!==null&&frame.conversation_id!==id)return;
   id=frame.conversation_id;
   // Delay delivery of this actual native MessageEvent, never fabricate/rewrite a frame.
   event.stopImmediatePropagation();held.push({socket,event,member:payload.member_id});
  };
  socket.addEventListener('message',listener);listeners.push({socket,listener});return socket;
 }});
 const deliver=(entry:{socket:WebSocket;event:MessageEvent<unknown>}):void=>{const callback=entry.socket.onmessage;if(callback)Reflect.apply(callback,entry.socket,[entry.event]);};
 return {
  arm:()=>{armed=true;},
  bind:value=>{assert(id===null||id===value,'Held membership frames belong to a different actual group.');id=value;},
  count:()=>held.length,
  releaseThroughSelfJoin:()=>{const last=held.findIndex(entry=>entry.member===owner.user);assert(last>=0,'Actual self-join frame not captured.');let preceding=0;for(let index=0;index<=last;index++){const entry=held.shift();assert(entry,'Captured native membership frame missing.');if(entry.member!==owner.user)++preceding;deliver(entry);}return preceding;},
  restore:()=>{armed=false;for(const {socket,listener} of listeners)socket.removeEventListener('message',listener);while(held.length){const entry=held.shift();assert(entry,'Captured native membership frame missing.');deliver(entry);}window.WebSocket=original;},
 };
}

export async function runDetailSelfJoinOpeningRegression(session:SessionController,peer:AccessSession,caseOnly:'openingFirst'|'joinFirst'|'routeClosed'|'withdrawn'='openingFirst'):Promise<{selfJoinVersion:number;activated:boolean;ownerAuthentications:number}> {
 const owner=ownerOf(session),trace=observeSocket(session),frames=gateInitialMembershipFrames(session),chat=new ChatController(session);let gate:DetailGate|null=null,unsubscribe:(()=>void)|null=null;
 detailNativeDiagnostic.stage=`opening_self_join_${caseOnly}_setup`;detailNativeDiagnostic.capturedVersions=[];detailNativeDiagnostic.preparedGroups=0;detailNativeDiagnostic.evicted=false;
 try{
  await chat.start();await until(()=>chat.getSnapshot().connection==='ready','Actual owner W02 missing.');await chat.reconcile();frames.arm();
  const created=await session.request<ConversationCreateResult>('/conversations/groups',{method:'POST',idempotencyKey:crypto.randomUUID(),json:{title:'native pending route opening',member_ids:[peer.user_id]}});
  assert(created.data.membership_version===1,'Actual opening A14 did not start at version one.');const id=created.data.id,path=`/conversations/${encodeURIComponent(id)}`;frames.bind(id);detailNativeDiagnostic.preparedGroups=1;
  await until(()=>frames.count()===2,'Actual multi-member A14 W11 deliveries were not held.');gate=detailGate(session,id,[1,2,3],true);
  const baselineAuthentications=trace.authentications();let errors=0,connectionChanges=0;unsubscribe=chat.subscribe(()=>{if(chat.getSnapshot().error!==null)++errors;if(chat.getSnapshot().connection!=='ready')++connectionChanges;});
  let opening:NativeOperationOutcome,preceding:number,allowedRequests:number;
  if(caseOnly==='joinFirst'){
   preceding=frames.releaseThroughSelfJoin();await until(()=>gate!.requests()>=preceding+1&&gate!.count(1)>=1,'Actual fresh self-join A12 was not held.');
   allowedRequests=preceding+1;const nextRequest=gate.requests()+1;gate.releaseCaptured(1,nextRequest);
   opening=outcome(chat.openChat(id));
   if(gate.requests()>allowedRequests){await until(()=>gate!.returned(1)>=1,'Actual competing opening A12 was not returned.');await nextTurn();await chat.setDraft(id,'native opening draft');}
  }else{
   opening=outcome(chat.openChat(id));await until(()=>gate!.count(1)>=1,'Actual original opening A12 was not held.');
   preceding=frames.releaseThroughSelfJoin();allowedRequests=preceding+2;await until(()=>gate!.requests()>=allowedRequests,'Actual fresh self-join A12 was not started after opening.');
  }
  detailNativeDiagnostic.stage=`opening_self_join_${caseOnly}_fresh_authority_held`;
  if(caseOnly==='routeClosed')chat.closeChat();
  if(caseOnly==='withdrawn'){
   await session.request(`${path}/members/${encodeURIComponent(peer.user_id)}`,{method:'PATCH',json:{role:'admin'}});
   await peerApi(session,peer,`${path}/members/${encodeURIComponent(owner.user)}`,'DELETE');await chat.withdraw(id);
   gate.release(1);gate.release(2);gate.release(3);const result=await opening.result;assert(result instanceof RepositoryCancelled,'Withdrawal did not cancel the original pending route opening.');await nextTurn();
   const stored=await partition(owner.user,owner.device);assert(chat.getSnapshot().currentConversation===null&&chat.getSnapshot().denied.includes(id)&&chat.getSnapshot().details[id]===undefined,'Old pending self-join activated a withdrawn room.');
   assert(record(stored.details)[id]===undefined&&Array.isArray(stored.denied)&&stored.denied.includes(id),'Old pending self-join restored withdrawn native authority.');
   assert(trace.authentications()===baselineAuthentications&&connectionChanges===0,'Privacy cancellation caused a network reconnect.');detailNativeDiagnostic.stage='opening_self_join_withdrawn_passed';return {selfJoinVersion:Number(record(stored.selfMembershipVersions)[id]??0),activated:false,ownerAuthentications:trace.authentications()};
  }
  gate.release(1);await until(()=>chat.getSnapshot().details[id]?.membership_version===1,'Actual current group detail did not install.');await nextTurn();await chat.setDraft(id,'native opening draft');
  const stored=await partition(owner.user,owner.device);assert(record(stored.selfMembershipVersions)[id]===1,'Fresh self-join boundary was lost to opening metadata invalidation.');
  assert(chat.getSnapshot().details[id]?.members.length===2&&!chat.getSnapshot().denied.includes(id),'Actual current multi-member authority was not installed.');
  const result=await opening.result;
  if(caseOnly==='routeClosed'){assert(result===null||result instanceof RepositoryCancelled,'Route closure produced an unrelated failure.');assert(chat.getSnapshot().currentConversation===null,'A fresh self-join activated an abandoned route.');}
  else{assert(result===null,'A fresh authorized self-join did not complete the pending route opening.');assert(chat.getSnapshot().currentConversation===id,'Fresh current membership left the requested room inactive.');assert(gate.requests()<=allowedRequests,'Pending route handoff performed an extra A12 instead of using the current self-join authority.');}
  assert(errors===0&&connectionChanges===0&&trace.authentications()===baselineAuthentications,'Pending route handoff created a false error or reconnect.');detailNativeDiagnostic.stage=`opening_self_join_${caseOnly}_passed`;return {selfJoinVersion:1,activated:caseOnly!=='routeClosed',ownerAuthentications:trace.authentications()};
 }finally{gate?.restore();frames.restore();unsubscribe?.();trace.restore();await chat.stop();}
}
