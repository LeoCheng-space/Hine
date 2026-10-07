import type { SessionController } from './session';
import type { ApiResult, AttachmentView, BootstrapConversation, ConversationDetail, ConversationSummary, MessageView } from './types';
import { applyEvents, boolean, ChatRepository, compareMessage, ConversationAuthority, emptyPartition, entity, fields, installSnapshot, integer, parseMessage, parseReceipt, receiptCanRetryAutomatically, record, recordReceiptFailure, rejoinConversation, RepositoryCancelled, settleIntent, status, StorageFault, storeMessage, string, timestamp, uuid, withdrawConversation } from './repository';
import type { ConversationTicket, Partition, ScrollAnchor, SendIntent, SendPayload, WireEvent } from './repository';
import { AttachmentTransferError } from './attachment-transfer';

class ChatFault extends Error {constructor(readonly code:string,readonly retryable=false,readonly retryAfterMs?:number){super(code);}}
function role(value:unknown):'admin'|'member'{if(value!=='admin'&&value!=='member')throw new ChatFault('INVALID_WIRE');return value;}
function summary(value:unknown):ConversationSummary {
 const p=record(value);const id=entity(p.id);if(p.type!=='direct'&&p.type!=='group')throw new ChatFault('INVALID_WIRE');
 if(p.type==='direct'&&p.title!==null)throw new ChatFault('INVALID_WIRE');return {id,type:p.type,title:p.title===null?null:string(p.title),unread_count:integer(p.unread_count)};
}
function bootstrapConversation(value:unknown,user:string):BootstrapConversation {
 const p=record(value);fields(p,['id','type','title','unread_count','my_role','recent_messages']);const s=summary(p);
 if(!Array.isArray(p.recent_messages)||(s.type==='direct'&&p.my_role!==null))throw new ChatFault('INVALID_WIRE');
 const messages=p.recent_messages.map(m=>parseMessage(m,user));if(messages.some(m=>m.conversation_id!==s.id||(s.type==='group'&&m.receipt!==null)))throw new ChatFault('INVALID_WIRE');
 return {...s,my_role:p.my_role===null?null:role(p.my_role),recent_messages:messages};
}
function conversationDetail(value:unknown):ConversationDetail {
 const p=record(value);fields(p,['id','type','title','unread_count','members','created_at','membership_version']);const s=summary(p);
 if(!Array.isArray(p.members)||p.members.length>50||(s.type==='direct'&&p.membership_version!==null))throw new ChatFault('INVALID_WIRE');
 return {...s,members:p.members.map(value=>{const member=record(value);fields(member,['user_id','role']);return {user_id:entity(member.user_id),role:role(member.role)};}),created_at:timestamp(p.created_at),membership_version:p.membership_version===null?null:integer(p.membership_version,1)};
}
export function parseServerFrame(value:unknown,user:string):WireEvent {
 const e=record(value);fields(e,['event','event_id','timestamp','payload'],['conversation_id','sender_id','correlation_id']);
 const event=string(e.event),p=record(e.payload);const frame:WireEvent={event,event_id:uuid(e.event_id),timestamp:timestamp(e.timestamp),payload:p};
 if(e.conversation_id!==undefined)frame.conversation_id=entity(e.conversation_id);if(e.sender_id!==undefined)frame.sender_id=entity(e.sender_id);if(e.correlation_id!==undefined)frame.correlation_id=uuid(e.correlation_id);
 const conversational=['message.ack','message.created','message.status','receipt.ack','conversation.member_added','conversation.member_removed','conversation.updated'];
 if(conversational.includes(event)!==(frame.conversation_id!==undefined))throw new ChatFault('INVALID_WIRE');
 if((event==='message.created')!==(frame.sender_id!==undefined))throw new ChatFault('INVALID_WIRE');
 if(['auth.accepted','heartbeat.pong','message.ack','receipt.ack','sync.bootstrap.page','sync.batch'].includes(event)&&!frame.correlation_id)throw new ChatFault('INVALID_WIRE');
 if(!['auth.accepted','heartbeat.pong','message.ack','receipt.ack','sync.bootstrap.page','sync.batch','error'].includes(event)&&frame.correlation_id)throw new ChatFault('INVALID_WIRE');
 switch(event){
  case 'auth.accepted':fields(p,['user_id','device_id','expires_at','session_generation','heartbeat_interval_seconds','heartbeat_timeout_seconds']);entity(p.user_id);string(p.device_id);timestamp(p.expires_at);integer(p.session_generation,1);if(p.heartbeat_interval_seconds!==30||p.heartbeat_timeout_seconds!==90)throw new ChatFault('INVALID_WIRE');break;
  case 'heartbeat.pong':fields(p,['nonce']);string(p.nonce);break;
  case 'message.ack':fields(p,['client_message_id','message_id','status']);uuid(p.client_message_id);uuid(p.message_id);if(p.status!=='persisted')throw new ChatFault('INVALID_WIRE');break;
  case 'message.created':{
   fields(p,['message_id','type','order_key'],['client_message_id','text','attachment_id']);
   parseMessage({id:p.message_id,event_id:frame.event_id,conversation_id:frame.conversation_id,sender_id:frame.sender_id,created_at:frame.timestamp,order_key:p.order_key,type:p.type,receipt:null,...(p.type==='text'?{text:p.text}:{attachment_id:p.attachment_id}),...(p.client_message_id===undefined?{}:{client_message_id:p.client_message_id})},user);
   if((p.type==='text'&&p.attachment_id!==undefined)||(p.type!=='text'&&p.text!==undefined))throw new ChatFault('INVALID_WIRE');break;
  }
  case 'message.status':parseReceipt(p);break;
  case 'receipt.ack':fields(p,['message_id','status','changed']);uuid(p.message_id);status(p.status);boolean(p.changed);break;
  case 'conversation.member_added':fields(p,['member_id','role','actor_id','membership_version']);entity(p.member_id);role(p.role);entity(p.actor_id);integer(p.membership_version,1);break;
  case 'conversation.member_removed':fields(p,['member_id','change','membership_version'],['actor_id']);entity(p.member_id);if(p.change!=='removed'||(p.member_id===user&&p.actor_id!==undefined))throw new ChatFault('INVALID_WIRE');if(p.actor_id!==undefined)entity(p.actor_id);integer(p.membership_version,1);break;
  case 'conversation.updated':{
   fields(p,['changes','actor_id','membership_version']);entity(p.actor_id);integer(p.membership_version,1);const changes=record(p.changes);
   if(changes.kind==='title'){fields(changes,['kind','title']);string(changes.title);}else if(changes.kind==='role'){fields(changes,['kind','member_id','role']);entity(changes.member_id);role(changes.role);}else throw new ChatFault('INVALID_WIRE');break;
  }
  case 'sync.bootstrap.page':{
   fields(p,['snapshot_id','start_cursor','conversations','next_page_token','has_more']);entity(p.snapshot_id);string(p.start_cursor);const more=boolean(p.has_more);
   if(!Array.isArray(p.conversations)||more!==(p.next_page_token!==null))throw new ChatFault('INVALID_WIRE');if(p.next_page_token!==null)string(p.next_page_token);
   const conversations=p.conversations.map(value=>bootstrapConversation(value,user));if(conversations.reduce((n,c)=>n+1+c.recent_messages.length,0)>100)throw new ChatFault('INVALID_WIRE');break;
  }
  case 'sync.batch':{
   fields(p,['snapshot_boundary','events','next_cursor','has_more']);string(p.snapshot_boundary);string(p.next_cursor);boolean(p.has_more);if(!Array.isArray(p.events)||p.events.length>100)throw new ChatFault('INVALID_WIRE');
   for(const item of p.events){const nested=parseServerFrame(item,user);if(!['message.created','message.status','conversation.member_added','conversation.member_removed','conversation.updated'].includes(nested.event))throw new ChatFault('INVALID_WIRE');}break;
  }
  case 'presence.changed':fields(p,['user_id','presence']);entity(p.user_id);if(!['online','offline','unknown'].includes(string(p.presence)))throw new ChatFault('INVALID_WIRE');break;
  case 'error':fields(p,['code','message','retryable'],['retry_after_ms']);string(p.code);string(p.message);boolean(p.retryable);if(p.retry_after_ms!==undefined)integer(p.retry_after_ms);break;
  default:throw new ChatFault('INVALID_WIRE');
 }
 return frame;
}
export function validateSyncProgress(cursor:string,next:string,hasMore:boolean):void {if(hasMore&&next===cursor)throw new ChatFault('SYNC_NON_PROGRESS');}
export interface PendingHeartbeat {nonce:string;sent:number}
export function settleHeartbeat(pending:Map<string,PendingHeartbeat>,frame:WireEvent):boolean {const id=frame.correlation_id;if(frame.event!=='heartbeat.pong'||!id)return false;const ping=pending.get(id);if(!ping||ping.nonce!==frame.payload.nonce)return false;pending.delete(id);return true;}
export class ReceiveQueue {
 readonly abort=new AbortController();private tail:Promise<void>=Promise.resolve();
 enqueue(work:()=>Promise<void>):Promise<void>{const next=this.tail.then(async()=>{if(!this.abort.signal.aborted)await work();});this.tail=next.catch(()=>{});return next;}
 close():void {this.abort.abort();}
}
export interface ChatSnapshot {
 connection:'stopped'|'connecting'|'authenticating'|'ready'|'offline'|'blocked';error:string|null;currentConversation:string|null;messages:Record<string,MessageView[]>;
 conversations:Record<string,ConversationSummary>;details:Record<string,ConversationDetail>;intents:Record<string,SendIntent>;receipts:Partition['receipts'];drafts:Record<string,string>;anchors:Record<string,ScrollAnchor>;denied:string[];presence:Record<string,'online'|'offline'|'unknown'>;historyMore:Record<string,boolean>;
}
interface PendingRequest {event:string;expected:string;epoch:number;conversation?:string;payload:Record<string,unknown>;resolve:(frame:WireEvent)=>void;reject:(error:Error)=>void;timer:number}
interface Binding {user:string;device:string;generation:number;token:string;expires:string}
export interface AttachmentSendState {phase:'uploading'|'waiting'|'ready';error:string|null;retryable:boolean}
interface AttachmentOperation {userId:string;deviceId:string;conversationId:string;task:()=>Promise<AttachmentView>;ready:AttachmentView|null;running:Promise<void>|null;blocked:boolean;state:AttachmentSendState}
interface SocketScope {socket:WebSocket;queue:ReceiveQueue}
interface SelfJoinWork {epoch:number;ticket:ConversationTicket;work:Promise<void>}
interface RouteOpening {id:string;epoch:number;join?:SelfJoinWork}
export class ChatController {
 private listeners=new Set<()=>void>();private snapshot:ChatSnapshot={connection:'stopped',error:null,currentConversation:null,messages:{},conversations:{},details:{},intents:{},receipts:{},drafts:{},anchors:{},denied:[],presence:{},historyMore:{}};
 private state=emptyPartition();private repository:ChatRepository|null=null;private binding:Binding|null=null;private epoch=0;private ws:WebSocket|null=null;private accepted=false;private started=false;private fatal=false;private unsubscribe:(()=>void)|null=null;
 private pending=new Map<string,PendingRequest>();private heartbeat=new Map<string,PendingHeartbeat>();private heartbeatNonce=0;private timers:number[]=[];private interval:number|undefined;private heartbeatTimer:number|undefined;
 private scope:SocketScope|null=null;private authority=new ConversationAuthority();private verifiedGroups=new Set<string>();private observedDenied=new Set<string>();private authorityReconciled=false;
 private reconnectBoundaries=new Map<string,number>();private recoveringReceipts:Promise<void>|null=null;
 // Metadata versions survive detail-cache eviction independently of self-join authorization.
 private metadataVersions=new Map<string,number>();
 private selfJoins=new Map<string,SelfJoinWork>();private pendingOpening:RouteOpening|null=null;
 private reads=new Set<{id:string|null;abort:AbortController}>();private manualIntentRetries=new Set<string>();
 private bindingWork:Promise<void>=Promise.resolve();private syncing:Promise<void>|null=null;private flushing:Promise<void>|null=null;private liveDuringBootstrap:WireEvent[]|null=null;private revocationVersion=0;private historyCursors:Record<string,string|null|undefined>={};private historyLoading=new Map<string,Promise<void>>();private currentRoute:string|null=null;private blockedToken:string|null=null;
 private flushRequested=false;
 private attachmentOperations=new Map<string,AttachmentOperation>();
 constructor(readonly session:SessionController){}
 subscribe=(listener:()=>void):(()=>void)=>{this.listeners.add(listener);return()=>this.listeners.delete(listener);};
 getSnapshot=():ChatSnapshot=>this.snapshot;
 private publish(extra:Partial<ChatSnapshot>={}):void {const messages:Record<string,MessageView[]>={};for(const [id,items] of Object.entries(this.state.messages))messages[id]=this.state.conversations[id]?.type==='group'&&!this.verifiedGroups.has(id)?[]:items;this.snapshot={...this.snapshot,messages,conversations:this.state.conversations,details:this.state.details,intents:this.state.intents,receipts:this.state.receipts,drafts:this.state.drafts,anchors:this.state.anchors,denied:[...this.observedDenied],...extra};for(const listener of this.listeners)listener();}
 async start():Promise<void>{if(this.started)return;this.started=true;this.unsubscribe=this.session.subscribe(this.onSession);window.addEventListener('online',this.foreground);window.addEventListener('offline',this.offline);document.addEventListener('visibilitychange',this.foreground);this.interval=window.setInterval(this.foreground,this.session.config.SYNC_RECONCILE_SECONDS*1000);this.onSession();await this.bindingWork;}
 async stop():Promise<void>{this.started=false;this.unsubscribe?.();this.unsubscribe=null;window.removeEventListener('online',this.foreground);window.removeEventListener('offline',this.offline);document.removeEventListener('visibilitychange',this.foreground);window.clearInterval(this.interval);this.interval=undefined;++this.epoch;this.disconnect();await this.repository?.close();this.repository=null;this.binding=null;this.state=emptyPartition();this.currentRoute=null;this.publish({connection:'stopped',currentConversation:null,presence:{},historyMore:{}});}
 private onSession=():void=>{
  const context=this.session.getSnapshot().context;const next=context.state==='authenticated'?{user:context.user_id,device:context.device_id,generation:context.session_generation,token:context.access_token,expires:context.expires_at}:null;
  if(next&&this.binding&&Object.keys(next).every(k=>next[k as keyof Binding]===this.binding?.[k as keyof Binding]))return;
  const previous=this.binding;if((!next&&context.state==='logged_out')||(next&&previous&&(next.user!==previous.user||next.device!==previous.device)))this.currentRoute=null;
  const previousRepository=this.repository;this.repository=null;
  const epoch=++this.epoch;this.disconnect();this.binding=next;this.fatal=false;this.state=emptyPartition();this.historyCursors={};this.historyLoading.clear();this.publish({connection:next?'connecting':'stopped',currentConversation:null,error:null,presence:{},historyMore:{}});
  this.bindingWork=this.bindingWork.then(async()=>{
   await previousRepository?.close();if(epoch!==this.epoch||!next||!this.started)return;
   try{const repository=new ChatRepository(next.user,next.device);const state=await repository.open();if(epoch!==this.epoch){await repository.close();return;}this.repository=repository;this.state=state;this.rememberGroupBoundaries();this.publish();this.connect(epoch);}catch(error){if(epoch===this.epoch)this.failClosed(error);}
  });
 };
 private valid(epoch=this.epoch):boolean {const context=this.session.getSnapshot().context;return this.started&&!this.fatal&&epoch===this.epoch&&this.binding!==null&&this.blockedToken!==this.binding.token&&context.state==='authenticated'&&context.access_token===this.binding.token&&Date.parse(context.expires_at)>Date.now();}
 private rememberGroupBoundaries():void {this.reconnectBoundaries.clear();for(const conversation of Object.values(this.state.conversations))if(conversation.type==='group'&&!this.state.denied.includes(conversation.id)&&(this.state.selfMembershipVersions[conversation.id]??0)>0)this.reconnectBoundaries.set(conversation.id,this.state.selfMembershipVersions[conversation.id]);}
 private verifyCompletedReconnection():void {for(const [id,boundary] of this.reconnectBoundaries)if(this.state.selfMembershipVersions[id]===boundary&&!this.state.denied.includes(id)&&!this.observedDenied.has(id))this.verifiedGroups.add(id);this.reconnectBoundaries.clear();}
 private disconnect():void {this.rememberGroupBoundaries();this.pendingOpening=null;this.selfJoins.clear();this.accepted=false;this.authorityReconciled=false;this.scope?.queue.close();this.scope=null;for(const read of this.reads)read.abort.abort();this.reads.clear();this.authority.invalidateAll();this.metadataVersions.clear();this.verifiedGroups.clear();this.observedDenied.clear();this.historyLoading.clear();this.liveDuringBootstrap=null;this.syncing=null;this.flushing=null;this.recoveringReceipts=null;window.clearInterval(this.heartbeatTimer);this.heartbeatTimer=undefined;for(const timer of this.timers)window.clearTimeout(timer);this.timers=[];for(const pending of this.pending.values()){window.clearTimeout(pending.timer);pending.reject(new ChatFault('OUTCOME_UNCONFIRMED',true));}this.pending.clear();this.heartbeat.clear();const socket=this.ws;this.ws=null;if(socket){socket.onopen=null;socket.onmessage=null;socket.onclose=null;socket.onerror=null;socket.close(1000);} }
 private invalidateConversation(id:string,resetMetadata=true):void {this.authority.invalidate(id);this.selfJoins.delete(id);if(this.pendingOpening?.id===id)this.pendingOpening.join=undefined;if(resetMetadata)this.metadataVersions.delete(id);this.verifiedGroups.delete(id);this.reconnectBoundaries.delete(id);delete this.historyCursors[id];this.historyLoading.delete(id);for(const read of this.reads)if(read.id===id)read.abort.abort();}
 private rest<T>(path:string,id:string|null,valid:()=>boolean):Promise<ApiResult<T>> {
  const read={id,abort:new AbortController()};this.reads.add(read);
  return new Promise<ApiResult<T>>((resolve,reject)=>{
   let complete=false;
   const finish=(error:unknown,result?:ApiResult<T>):void=>{if(complete)return;complete=true;window.clearTimeout(timer);read.abort.signal.removeEventListener('abort',cancel);this.reads.delete(read);if(!valid())reject(new RepositoryCancelled());else if(error)reject(error);else if(result)resolve(result);};
   const cancel=():void=>finish(new RepositoryCancelled());read.abort.signal.addEventListener('abort',cancel,{once:true});
   const timer=window.setTimeout(()=>{finish(new ChatFault('DEPENDENCY_UNAVAILABLE',true));read.abort.abort();},10_000);
   if(!valid()){cancel();return;}
   void this.session.request<T>(path,{signal:read.abort.signal}).then(result=>finish(null,result),error=>finish(error));
  });
 }
 private failClosed(error:unknown):void {this.fatal=true;++this.epoch;this.disconnect();this.state=emptyPartition();this.publish({connection:'blocked',currentConversation:null,error:error instanceof StorageFault?error.message:'聊天資料驗證失敗，已停止連線。請重新載入。',presence:{}});if(error instanceof StorageFault)this.session.failStorage(error);}
 private connect(epoch:number):void {
  if(!this.valid(epoch)||!this.repository||this.ws)return;if(!navigator.onLine){this.publish({connection:'offline'});return;}
  const socket=new WebSocket(this.session.config.WS_URL),scope:SocketScope={socket,queue:new ReceiveQueue()};this.ws=socket;this.scope=scope;this.publish({connection:'connecting'});
  socket.onopen=()=>{if(!this.valid(epoch)||this.ws!==socket){socket.close();return;}this.publish({connection:'authenticating'});const binding=this.binding;if(!binding)return;
   void this.request('auth.authenticate','auth.accepted',{access_token:binding.token,device_id:binding.device},undefined,true).then(frame=>{
    if(!this.valid(epoch)||this.ws!==socket)return;const p=frame.payload;
    if(p.user_id!==binding.user||p.device_id!==binding.device||p.session_generation!==binding.generation||Date.parse(string(p.expires_at))!==Date.parse(binding.expires)){this.failClosed(new ChatFault('AUTH_BINDING_MISMATCH'));return;}
    this.accepted=true;this.publish({connection:'ready',error:null});this.heartbeatTimer=window.setInterval(()=>this.ping(epoch),30_000);
    void this.reconcile().then(async()=>{if(this.scope!==scope||!this.valid(epoch))return;if(this.currentRoute)await this.openChat(this.currentRoute);await this.flush();}).catch(error=>this.operationError(error));
   }).catch(error=>{if(this.valid(epoch)&&this.scope===scope){this.operationError(error);this.connectionLost(epoch);}});
  };
  socket.onmessage=event=>{if(!this.valid(epoch)||this.ws!==socket)return;if(typeof event.data!=='string'||new TextEncoder().encode(event.data).byteLength>1_048_576){this.failClosed(new ChatFault('INVALID_WIRE'));return;}
   void scope.queue.enqueue(async()=>{if(!this.valid(epoch)||this.scope!==scope||scope.queue.abort.signal.aborted)return;const frame=parseServerFrame(JSON.parse(event.data),this.binding?.user??'');await this.receive(frame,epoch,scope);}).catch(error=>{if(this.valid(epoch)&&this.scope===scope&&!(error instanceof RepositoryCancelled))this.failClosed(error);});
  };
  socket.onclose=()=>{if(this.ws===socket)this.connectionLost(epoch);};socket.onerror=()=>{if(this.ws===socket)this.connectionLost(epoch);};
 }
 private connectionLost(epoch:number):void {if(epoch!==this.epoch)return;this.disconnect();this.publish({connection:'offline',error:'連線中斷；未確認的訊息保留原傳送意圖。'});if(this.valid(epoch)&&navigator.onLine){const timer=window.setTimeout(()=>this.connect(epoch),1500);this.timers.push(timer);}}
 private foreground=():void=>{if(document.visibilityState!=='visible'||!navigator.onLine||!this.valid())return;if(!this.ws)this.connect(this.epoch);else if(this.accepted)void this.reconcile().then(()=>this.flush()).catch(error=>this.operationError(error));};
 private offline=():void=>{this.connectionLost(this.epoch);};
 private ping(epoch:number):void {
  if(!this.valid(epoch)||!this.accepted)return;const now=performance.now();if([...this.heartbeat.values()].some(item=>now-item.sent>=90_000)){this.connectionLost(epoch);return;}
  const eventId=crypto.randomUUID(),nonce=String(++this.heartbeatNonce);this.heartbeat.set(eventId,{nonce,sent:now});this.ws?.send(JSON.stringify({event:'heartbeat.ping',event_id:eventId,timestamp:new Date().toISOString(),payload:{nonce}}));
  const timer=window.setTimeout(()=>{if(this.valid(epoch)&&this.heartbeat.has(eventId))this.connectionLost(epoch);},90_000);this.timers.push(timer);
 }
 private request(event:string,expected:string,payload:Record<string,unknown>,conversation?:string,authenticate=false):Promise<WireEvent> {
  if(!this.valid()||!this.ws||this.ws.readyState!==WebSocket.OPEN||(!authenticate&&!this.accepted))return Promise.reject(new ChatFault('DEPENDENCY_UNAVAILABLE',true));
  let resolve!:(frame:WireEvent)=>void,reject!:(error:Error)=>void;const promise=new Promise<WireEvent>((accept,deny)=>{resolve=accept;reject=deny;});const id=crypto.randomUUID(),epoch=this.epoch;
  const timer=window.setTimeout(()=>{this.pending.delete(id);reject(new ChatFault('OUTCOME_UNCONFIRMED',true));if(['auth.authenticate','sync.request','sync.bootstrap.request'].includes(event))this.connectionLost(epoch);},10_000);
  this.pending.set(id,{event,expected,epoch,conversation,payload,resolve,reject,timer});
  try{this.ws.send(JSON.stringify({event,event_id:id,timestamp:new Date().toISOString(),payload,...(conversation?{conversation_id:conversation}:{})}));}catch{clearTimeout(timer);this.pending.delete(id);reject(new ChatFault('OUTCOME_UNCONFIRMED',true));}
  return promise;
 }
 private async receive(frame:WireEvent,epoch:number,scope:SocketScope):Promise<void> {
  if(this.scope!==scope||scope.queue.abort.signal.aborted)return;
  if(frame.event==='heartbeat.pong'){settleHeartbeat(this.heartbeat,frame);return;}
  if(frame.correlation_id){const pending=this.pending.get(frame.correlation_id);if(!pending||pending.epoch!==epoch)return;
   if(frame.event==='error'){clearTimeout(pending.timer);this.pending.delete(frame.correlation_id);const p=frame.payload;pending.reject(new ChatFault(string(p.code),boolean(p.retryable),p.retry_after_ms===undefined?undefined:integer(p.retry_after_ms)));if(p.code==='UNAUTHENTICATED')this.invalidate();return;}
   if(frame.event!==pending.expected||frame.conversation_id!==pending.conversation)throw new ChatFault('INVALID_CORRELATION');
   if(frame.event==='message.ack'&&frame.payload.client_message_id!==pending.payload.client_message_id)throw new ChatFault('INVALID_CORRELATION');
   if(frame.event==='receipt.ack'&&frame.payload.message_id!==pending.payload.message_id)throw new ChatFault('INVALID_CORRELATION');
   if(frame.event==='receipt.ack'&&pending.event==='message.read'&&frame.payload.status!=='read')throw new ChatFault('INVALID_RECEIPT_TRANSITION');
   clearTimeout(pending.timer);this.pending.delete(frame.correlation_id);pending.resolve(frame);return;
  }
  if(frame.event==='error'){if(frame.payload.code==='UNAUTHENTICATED')this.invalidate();else this.publish({error:'即時服務暫時無法完成操作。'});return;}
  if(!this.accepted)throw new ChatFault('W02_REQUIRED');
  if(frame.event==='presence.changed'){const p=frame.payload,presence=p.presence;if(presence==='online'||presence==='offline'||presence==='unknown')this.publish({presence:{...this.snapshot.presence,[entity(p.user_id)]:presence}});return;}
  const selfJoin=frame.event==='conversation.member_added'&&frame.payload.member_id===this.binding?.user;
  const selfRemoval=frame.event==='conversation.member_removed'&&frame.payload.member_id===this.binding?.user;
  const id=frame.conversation_id,sourceValid=():boolean=>this.scope===scope&&!scope.queue.abort.signal.aborted&&this.valid(epoch);
  if((selfJoin||selfRemoval)&&id){if(integer(frame.payload.membership_version,1)<=(this.state.selfMembershipVersions[id]??0))return;this.invalidateConversation(id);if(selfRemoval){if(this.pendingOpening?.id===id)this.pendingOpening=null;this.observedDenied.add(id);++this.revocationVersion;this.liveDuringBootstrap=null;}this.publish();}
  else if(this.state.seen.includes(frame.event_id))return;
  const ticket=id?this.authority.capture(id):null,frameValid=():boolean=>sourceValid()&&(!id||ticket!==null&&this.authority.isCurrent(id,ticket));
  if(selfJoin&&id&&ticket){
   const joining:SelfJoinWork={epoch,ticket,work:this.commitSelfJoin(frame,id,epoch,frameValid)};this.selfJoins.set(id,joining);
   if(this.pendingOpening?.id===id&&this.pendingOpening.epoch===epoch)this.pendingOpening.join=joining;
   try{await joining.work;}catch(error){if(frameValid())this.operationError(error);return;}finally{if(this.selfJoins.get(id)===joining)this.selfJoins.delete(id);}
   if(frameValid())void this.loadHistory(id).catch(error=>this.operationError(error));return;
  }
  if(!frameValid())return;
  const events=[frame],metadata=id&&frame.event.startsWith('conversation.');
  this.liveDuringBootstrap?.push(frame);await this.commit(state=>applyEvents(state,events,this.binding?.user??''),epoch,frameValid,id&&metadata?[id]:undefined,metadata?events:undefined);
  if(frame.event==='conversation.member_removed'&&frame.payload.member_id===this.binding?.user){this.blockAttachments(string(frame.conversation_id));if(this.currentRoute===frame.conversation_id){this.currentRoute=null;this.publish({currentConversation:null,error:'你已無法存取這個群組。'});}window.dispatchEvent(new Event('hine-conversations-changed'));}
  if(!selfJoin&&['conversation.member_added','conversation.updated','conversation.member_removed'].includes(frame.event)&&!this.state.denied.includes(frame.conversation_id??''))void this.fetchDetail(string(frame.conversation_id),epoch).catch(error=>this.operationError(error));
  if(frame.event==='message.created')void this.flush();
 }
 private async commitSelfJoin(frame:WireEvent,id:string,epoch:number,valid:()=>boolean):Promise<void> {
  const detail=await this.readDetail(id,epoch,valid);if(!valid())throw new RepositoryCancelled();
  const events=[frame],joins={[frame.event_id]:detail};this.liveDuringBootstrap?.push(frame);
  await this.commit(state=>applyEvents(state,events,this.binding?.user??'',joins),epoch,valid,[id],events);
  if(!valid())throw new RepositoryCancelled();this.observedDenied.delete(id);this.verifiedGroups.add(id);this.publish();
 }
 private invalidate():void {this.blockedToken=this.binding?.token??null;++this.epoch;this.disconnect();this.state=emptyPartition();this.publish({connection:'blocked',currentConversation:null,error:'工作階段已失效，請重新登入。',presence:{}});this.session.invalidateAuthentication();}
 private async commit(change:(state:Partition)=>void,epoch=this.epoch,guard:()=>boolean=()=>true,metadataIds?:Iterable<string>,metadataEvents?:Iterable<WireEvent>,snapshotAuthorities?:Record<string,ConversationDetail>):Promise<void> {
  const repository=this.repository;if(!repository||!this.valid(epoch))throw new ChatFault('UNAUTHENTICATED');
  const versions=metadataIds?new Map<string,number>():null;
  try{
   const result=await repository.update(metadataIds?state=>{
    // Live metadata is accepted for an authorized group even when its detail is evicted.
    if(versions&&metadataEvents&&!snapshotAuthorities)for(const event of metadataEvents){
     const id=event.conversation_id;if(!event.event.startsWith('conversation.')||!id||state.conversations[id]?.type!=='group'||state.seen.includes(event.event_id)||state.denied.includes(id))continue;
     const version=integer(event.payload.membership_version,1);
     if(version>=(state.details[id]?.membership_version??0)&&version>(this.metadataVersions.get(id)??0))versions.set(id,Math.max(version,versions.get(id)??0));
    }
    change(state);
    // Snapshot replay accepts observed metadata against the newly installed projection,
    // not the old partition's seen/denied/detail state. Self boundaries remain separate.
    if(versions&&metadataEvents&&snapshotAuthorities)for(const event of metadataEvents){
     const id=event.conversation_id;if(!event.event.startsWith('conversation.')||!id||state.conversations[id]?.type!=='group'||state.denied.includes(id)||(event.event!=='conversation.updated'&&event.payload.member_id===this.binding?.user))continue;
     const version=integer(event.payload.membership_version,1);if(version>(this.metadataVersions.get(id)??0))versions.set(id,Math.max(version,versions.get(id)??0));
    }
    if(versions){
     for(const id of versions.keys())if(state.conversations[id]?.type!=='group'||state.denied.includes(id))versions.delete(id);
     if(metadataIds)for(const id of metadataIds){
      if(state.conversations[id]?.type!=='group'||state.denied.includes(id))continue;
      // The snapshot authority may have been bounded out inside installSnapshot.
      const version=Math.max(state.details[id]?.membership_version??0,snapshotAuthorities?.[id]?.membership_version??0);
      if(version>(this.metadataVersions.get(id)??0))versions.set(id,Math.max(version,versions.get(id)??0));
     }
    }
   }:change,()=>this.valid(epoch)&&guard());
   if(!this.valid(epoch)||!guard())throw new RepositoryCancelled();
   if(versions)for(const [id,version] of versions)this.metadataVersions.set(id,Math.max(version,this.metadataVersions.get(id)??0));
   this.state=result;this.publish();
  }catch(error){if(epoch===this.epoch&&!(error instanceof RepositoryCancelled))this.failClosed(error);throw error;}
 }
 private operationError(error:unknown):void {if(error instanceof StorageFault||error instanceof RepositoryCancelled||!this.valid())return;if(error instanceof ChatFault&&error.code==='UNAUTHENTICATED')return;this.publish({error:'操作尚未完成，請稍後核對或重試。'});}
 async reconcile():Promise<void> {
  if(!this.valid()||!this.accepted)return;if(this.syncing)return this.syncing;
  const epoch=this.epoch,scope=this.scope,sourceValid=():boolean=>this.valid(epoch)&&this.scope===scope&&scope!==null&&!scope.queue.abort.signal.aborted;
  const work=async():Promise<void>=>{
   if(!this.state.cursor)await this.bootstrap(epoch,'first_login');
   if(!sourceValid()||!this.state.cursor)return;
   let boundary:string|undefined;
   do{
    const cursor=this.state.cursor;if(!cursor)return;
    const frame=await this.request('sync.request','sync.batch',{cursor,...(boundary?{snapshot_boundary:boundary}:{})});if(!sourceValid())return;
    const p=frame.payload,next=string(p.next_cursor),returnedBoundary=string(p.snapshot_boundary),more=boolean(p.has_more);
    if(boundary&&boundary!==returnedBoundary)throw new ChatFault('SYNC_BOUNDARY_MISMATCH');boundary=returnedBoundary;validateSyncProgress(cursor,next,more);
    const events=(p.events as unknown[]).map(value=>parseServerFrame(value,this.binding?.user??''));
    const boundaries=events.filter(event=>(event.event==='conversation.member_added'||event.event==='conversation.member_removed')&&event.payload.member_id===this.binding?.user&&integer(event.payload.membership_version,1)>(this.state.selfMembershipVersions[string(event.conversation_id)]??0));
    const changed=new Set(boundaries.map(event=>string(event.conversation_id)));
    for(const event of boundaries)if(event.event==='conversation.member_removed'&&this.pendingOpening?.id===event.conversation_id)this.pendingOpening=null;
    for(const id of changed)this.invalidateConversation(id);
    const touched=new Set(events.flatMap(event=>event.conversation_id?[event.conversation_id]:[]));
    const tickets=new Map([...touched].map(id=>[id,this.authority.capture(id)]));
    const batchValid=():boolean=>sourceValid()&&[...tickets].every(([id,ticket])=>this.authority.isCurrent(id,ticket));
    const joins:Record<string,ConversationDetail>={},deniedInBatch:string[]=[];
    for(const event of boundaries)if(event.event==='conversation.member_added'){
     const id=string(event.conversation_id);
     try{joins[event.event_id]=await this.readDetail(id,epoch,batchValid);}
     catch(error){if(!batchValid())throw new RepositoryCancelled();if(error instanceof Error&&'code' in error&&['FORBIDDEN','NOT_FOUND'].includes(String(error.code)))deniedInBatch.push(id);else throw error;}
    }
    if(boundaries.some(event=>event.event==='conversation.member_removed')){++this.revocationVersion;this.liveDuringBootstrap=null;}
    if(events.length||next!==cursor)await this.commit(state=>{for(const id of deniedInBatch)withdrawConversation(state,id);applyEvents(state,events,this.binding?.user??'',joins);state.cursor=next;},epoch,batchValid,events.some(event=>event.event.startsWith('conversation.'))?touched:undefined,events);
    void this.flush();
    for(const id of changed){if(this.state.denied.includes(id)){this.observedDenied.add(id);this.blockAttachments(id);}else{this.observedDenied.delete(id);this.verifiedGroups.add(id);}}
    for(const event of events)if(['conversation.member_added','conversation.updated','conversation.member_removed'].includes(event.event)&&event.payload.member_id!==this.binding?.user&&!this.state.denied.includes(event.conversation_id??''))void this.fetchDetail(string(event.conversation_id),epoch).catch(error=>this.operationError(error));
    if(this.currentRoute&&this.observedDenied.has(this.currentRoute)){this.currentRoute=null;this.publish({currentConversation:null,error:'你已無法存取這個群組。'});}else this.publish();
    if(!more)break;
   }while(sourceValid());
   if(sourceValid()){this.verifyCompletedReconnection();this.authorityReconciled=true;this.publish();void this.recoverPendingGroupReceipts(epoch,sourceValid);window.dispatchEvent(new Event('hine-conversations-changed'));}
  };
  const promise=work().catch(async error=>{if(!sourceValid())return;if(error instanceof ChatFault&&error.code==='SYNC_RESET_REQUIRED'){await this.bootstrap(epoch,'cursor_reset');if(sourceValid()){this.authorityReconciled=true;void this.recoverPendingGroupReceipts(epoch,sourceValid);}return;}throw error;});
  this.syncing=promise;try{await promise;}finally{if(this.syncing===promise)this.syncing=null;}
 }
 private async bootstrap(epoch:number,reason:'first_login'|'cursor_reset'):Promise<void> {
  this.reconnectBoundaries.clear();
  const staged=emptyPartition(),version=this.revocationVersion,scope=this.scope;
  const sourceValid=():boolean=>this.valid(epoch)&&this.scope===scope&&scope!==null&&!scope.queue.abort.signal.aborted&&version===this.revocationVersion;
  let snapshotId:string|undefined,start:string|undefined,pageToken:string|undefined;const tokens=new Set<string>();this.liveDuringBootstrap=[];
  try{
   do{
    const frame=await this.request('sync.bootstrap.request','sync.bootstrap.page',{reason,...(snapshotId?{snapshot_id:snapshotId,page_token:pageToken}:{})});if(!sourceValid()||!this.liveDuringBootstrap)throw new RepositoryCancelled();const p=frame.payload;
    const id=entity(p.snapshot_id),cursor=string(p.start_cursor);if((snapshotId&&snapshotId!==id)||(start&&start!==cursor))throw new ChatFault('SNAPSHOT_MISMATCH');snapshotId=id;start=cursor;
    for(const value of p.conversations as unknown[]){const conversation=bootstrapConversation(value,this.binding?.user??'');staged.conversations[conversation.id]={id:conversation.id,type:conversation.type,title:conversation.title,unread_count:conversation.unread_count};for(const message of conversation.recent_messages)storeMessage(staged,message,this.binding?.user??'');}
    if(!boolean(p.has_more))break;pageToken=string(p.next_page_token);if(tokens.has(pageToken))throw new ChatFault('SNAPSHOT_NON_PROGRESS');tokens.add(pageToken);
   }while(sourceValid());
   if(!start||!sourceValid()||!this.liveDuringBootstrap)throw new RepositoryCancelled();
   const groups=Object.values(staged.conversations).filter(conversation=>conversation.type==='group');
   for(const group of groups){this.invalidateConversation(group.id);this.blockAttachments(group.id);}
   const tickets=new Map(groups.map(group=>[group.id,this.authority.capture(group.id)]));
   const stageValid=():boolean=>sourceValid()&&this.liveDuringBootstrap!==null&&[...tickets].every(([id,ticket])=>this.authority.isCurrent(id,ticket));
   const authorities:Record<string,ConversationDetail>={};
   for(const group of groups){
    authorities[group.id]=await this.readDetail(group.id,epoch,stageValid);
    const page=await this.readHistory(group.id,epoch,undefined,stageValid);
    staged.messages[group.id]=page.messages;
   }
   const observed=this.liveDuringBootstrap;if(!observed||!stageValid())throw new RepositoryCancelled();
   await this.commit(state=>installSnapshot(state,staged,observed,start??'',this.binding?.user??'',authorities),epoch,stageValid,tickets.keys(),observed,authorities);
   for(const group of groups){this.observedDenied.delete(group.id);this.verifiedGroups.add(group.id);delete this.historyCursors[group.id];}
   this.publish();
  }finally{if(this.scope===scope)this.liveDuringBootstrap=null;}
 }
 private async readDetail(id:string,epoch:number,extra:()=>boolean=()=>true):Promise<ConversationDetail> {
  const ticket=this.authority.capture(id),valid=():boolean=>this.valid(epoch)&&extra()&&this.authority.isCurrent(id,ticket);
  const response=await this.rest<unknown>(`/conversations/${encodeURIComponent(id)}`,id,valid);
  if(!valid())throw new RepositoryCancelled();const detail=conversationDetail(response.data);if(detail.id!==id)throw new ChatFault('INVALID_WIRE');return detail;
 }
 private async fetchDetail(id:string,epoch:number,opening=false):Promise<ConversationDetail|undefined> {
  let ticket=this.authority.capture(id);const valid=():boolean=>this.valid(epoch)&&this.authority.isCurrent(id,ticket);
  try{
   const detail=await this.readDetail(id,epoch,valid);if(!valid())throw new RepositoryCancelled();
   const restore=this.state.denied.includes(id),unknownGroup=opening&&detail.type==='group'&&!this.verifiedGroups.has(id);
   if(restore||unknownGroup){this.invalidateConversation(id,restore);ticket=this.authority.capture(id);}
   await this.commit(state=>{
    const current=state.details[id];if(detail.membership_version!==null&&detail.membership_version<Math.max(current?.membership_version??0,this.metadataVersions.get(id)??0))return;
    if(restore)rejoinConversation(state,detail);
    else{if(unknownGroup){delete state.messages[id];delete state.anchors[id];for(const receipt of Object.values(state.receipts))if(receipt.conversationId===id&&receipt.confirmed!==receipt.desired){receipt.blocked=true;receipt.error='MEMBERSHIP_RECHECK_REQUIRED';}}state.details[id]=detail;state.conversations[id]={id:detail.id,type:detail.type,title:detail.title,unread_count:detail.unread_count};}
   },epoch,valid,[id]);
   if(restore)this.observedDenied.delete(id);this.publish();return this.state.details[id];
  }catch(error){if(valid()&&error instanceof Error&&'code' in error&&['FORBIDDEN','NOT_FOUND'].includes(String(error.code)))await this.withdraw(id);throw error;}
 }
 async refreshConversation(conversationId:string):Promise<void> {
  const id=entity(conversationId),epoch=this.epoch,ticket=this.authority.capture(id);
  if(this.syncing)await this.syncing;
  if(!this.valid(epoch)||!this.authority.isCurrent(id,ticket))throw new RepositoryCancelled();
  await this.fetchDetail(id,epoch,false);
  if(!this.valid(epoch)||!this.authority.isCurrent(id,ticket))throw new RepositoryCancelled();
 }
 private currentOpening(opening:RouteOpening):boolean {return this.pendingOpening===opening&&this.currentRoute===opening.id&&this.valid(opening.epoch);}
 private async activateOpening(opening:RouteOpening,joining?:SelfJoinWork):Promise<void> {
  if(joining){
   if(joining.epoch!==opening.epoch||!this.authority.isCurrent(opening.id,joining.ticket))throw new RepositoryCancelled();
   await joining.work;if(!this.authority.isCurrent(opening.id,joining.ticket))throw new RepositoryCancelled();
  }
  if(!this.currentOpening(opening))return;if(this.state.denied.includes(opening.id)||this.observedDenied.has(opening.id))throw new RepositoryCancelled();
  this.publish({currentConversation:opening.id});if(this.historyCursors[opening.id]===undefined)await this.loadHistory(opening.id);
 }
 async openChat(conversationId:string):Promise<void> {
  const id=entity(conversationId),epoch=this.epoch,opening:RouteOpening={id,epoch,join:this.selfJoins.get(id)};this.pendingOpening=opening;this.currentRoute=id;this.publish({currentConversation:null,error:null});
  let joined:SelfJoinWork|undefined;
  try{
   if(!this.valid(epoch)||!this.repository)return;if(this.syncing)await this.syncing;if(!this.currentOpening(opening))return;
   if(!opening.join)await this.fetchDetail(id,epoch,true);
   joined=opening.join;await this.activateOpening(opening,joined);
  }catch(error){
   const joining=opening.join;
   // A cancelled old read is replaced only by this route's current authorized self-join.
   if(joined||!(error instanceof RepositoryCancelled)||!this.currentOpening(opening)||!joining||joining.epoch!==epoch||!this.authority.isCurrent(id,joining.ticket))throw error;
   await this.activateOpening(opening,joining);
  }finally{if(this.pendingOpening===opening)this.pendingOpening=null;}
 }
 closeChat():void {this.pendingOpening=null;this.currentRoute=null;this.publish({currentConversation:null});}
 async withdraw(conversationId:string):Promise<void> {if(this.pendingOpening?.id===conversationId)this.pendingOpening=null;this.invalidateConversation(conversationId);this.observedDenied.add(conversationId);++this.revocationVersion;this.liveDuringBootstrap=null;this.blockAttachments(conversationId);this.publish();await this.commit(state=>withdrawConversation(state,conversationId));if(this.currentRoute===conversationId){this.currentRoute=null;this.publish({currentConversation:null,error:'你已無法存取這個群組。'});}window.dispatchEvent(new Event('hine-conversations-changed'));}
 private async readHistory(id:string,epoch:number,before:string|undefined,extra:()=>boolean=()=>true):Promise<{messages:MessageView[];cursor:string|null}> {
  const ticket=this.authority.capture(id),valid=():boolean=>this.valid(epoch)&&extra()&&this.authority.isCurrent(id,ticket);
  const response=await this.rest<{items:unknown[]}>(`/conversations/${encodeURIComponent(id)}/messages?limit=20${before?`&before=${encodeURIComponent(before)}`:''}`,id,valid);
  if(!valid())throw new RepositoryCancelled();const data=record(response.data);fields(data,['items']);if(!Array.isArray(data.items)||!response.meta)throw new ChatFault('INVALID_WIRE');
  const messages=data.items.map(value=>parseMessage(value,this.binding?.user??''));if(messages.length>50||messages.some(message=>message.conversation_id!==id))throw new ChatFault('INVALID_WIRE');
  const cursor=response.meta.next_cursor;if(cursor!==null)string(cursor);if(cursor!==null&&cursor===before)throw new ChatFault('HISTORY_NON_PROGRESS');return {messages,cursor};
 }
 async loadHistory(id:string):Promise<void> {
  const existing=this.historyLoading.get(id);if(existing)return existing;
  if(this.historyCursors[id]===null||!this.valid()||this.state.denied.includes(id))return;
  const epoch=this.epoch,ticket=this.authority.capture(id),valid=():boolean=>this.valid(epoch)&&this.authority.isCurrent(id,ticket)&&!this.state.denied.includes(id);
  const work=async():Promise<void>=>{
   try{
    let page;const before=this.historyCursors[id]??undefined;let continuation=before!==undefined;
    try{page=await this.readHistory(id,epoch,before,valid);}
    catch(error){if(!valid()||!(error instanceof Error&&'code' in error&&['CURSOR_INVALID','CURSOR_EXPIRED'].includes(String(error.code))))throw error;continuation=false;page=await this.readHistory(id,epoch,undefined,valid);}
    if(!valid())throw new RepositoryCancelled();page.messages.sort(compareMessage);
    await this.commit(state=>{for(const message of page.messages)storeMessage(state,message,this.binding?.user??'');if(page.messages.length&&continuation)state.historyWindow={conversationId:id,firstMessageId:page.messages[0].id,lastMessageId:page.messages[page.messages.length-1].id};},epoch,valid);
    if(!valid())throw new RepositoryCancelled();this.historyCursors[id]=page.cursor;if(this.state.conversations[id]?.type==='group')this.verifiedGroups.add(id);
    this.publish({historyMore:{...this.snapshot.historyMore,[id]:page.cursor!==null}});void this.flush();
   }catch(error){if(valid()&&error instanceof Error&&'code' in error&&['FORBIDDEN','NOT_FOUND'].includes(String(error.code)))await this.withdraw(id);throw error;}
  };
  const promise=work();this.historyLoading.set(id,promise);
  try{await promise;}finally{if(this.historyLoading.get(id)===promise)this.historyLoading.delete(id);}
 }
 async jumpLatest(id:string):Promise<void> {
  const epoch=this.epoch,ticket=this.authority.capture(id),valid=():boolean=>this.valid(epoch)&&this.authority.isCurrent(id,ticket)&&!this.state.denied.includes(id);
  const page=await this.readHistory(id,epoch,undefined,valid);if(!valid())throw new RepositoryCancelled();
  await this.commit(state=>{state.historyWindow=null;delete state.anchors[id];for(const message of page.messages)storeMessage(state,message,this.binding?.user??'');},epoch,valid);
  this.historyCursors[id]=page.cursor;this.publish({historyMore:{...this.snapshot.historyMore,[id]:page.cursor!==null}});
 }
 private recoverPendingGroupReceipts(epoch:number,sourceValid:()=>boolean):Promise<void> {
  if(this.recoveringReceipts)return this.recoveringReceipts;
  const work=async():Promise<void>=>{
   const groups=new Set(Object.values(this.state.receipts).filter(receipt=>receipt.error==='MEMBERSHIP_RECHECK_REQUIRED'&&receipt.confirmed!==receipt.desired&&!this.state.denied.includes(receipt.conversationId)).map(receipt=>receipt.conversationId));
   for(const id of groups){
    if(!sourceValid())return;
    const ticket=this.authority.capture(id),valid=():boolean=>sourceValid()&&this.authority.isCurrent(id,ticket)&&!this.state.denied.includes(id);
    const pending=new Set(Object.values(this.state.receipts).filter(receipt=>receipt.conversationId===id&&receipt.error==='MEMBERSHIP_RECHECK_REQUIRED').map(receipt=>receipt.messageId));let before:string|undefined;
    const stop=async(code:'FORBIDDEN'|'NOT_FOUND'):Promise<void>=>{
     if(!valid())throw new RepositoryCancelled();
     await this.commit(state=>{for(const messageId of pending){const receipt=state.receipts[messageId];if(receipt&&receipt.conversationId===id&&receipt.error==='MEMBERSHIP_RECHECK_REQUIRED'&&receipt.confirmed!==receipt.desired){receipt.blocked=true;receipt.autoRetryStopped=true;receipt.error=code;}}},epoch,valid);
    };
    try{
     while(pending.size&&valid()){
      const page=await this.readHistory(id,epoch,before,valid),found=page.messages.filter(message=>pending.has(message.id));
      if(found.length)await this.commit(state=>{for(const message of found)storeMessage(state,message,this.binding?.user??'');},epoch,valid);
      for(const message of found)pending.delete(message.id);
      if(page.cursor===null){if(pending.size)await stop('NOT_FOUND');break;}
      before=page.cursor;
     }
    }catch(error){
     if(!sourceValid())return;
     if(error instanceof RepositoryCancelled||!valid())continue;
     if(error instanceof Error&&'code' in error&&(error.code==='FORBIDDEN'||error.code==='NOT_FOUND'))await stop(error.code);
     else this.operationError(error);
    }
   }
   if(sourceValid())void this.flush();
  };
  const promise=work().catch(error=>this.operationError(error));this.recoveringReceipts=promise;void promise.finally(()=>{if(this.recoveringReceipts===promise)this.recoveringReceipts=null;});return promise;
 }
 private async send(conversationId:string,payload:SendPayload):Promise<void> {
  if(!this.valid()||this.state.denied.includes(conversationId)||!this.state.details[conversationId])throw new ChatFault('FORBIDDEN');const c1=crypto.randomUUID();
  await this.commit(state=>{state.intents[c1]={clientMessageId:c1,conversationId,payload,createdAt:new Date().toISOString(),status:'pending',messageId:null,error:null,retryAt:null,authorizationVersion:state.details[conversationId]?.membership_version??null,observed:false};if(payload.type==='text')state.drafts[conversationId]='';});void this.flush();
 }
 async sendText(conversationId:string,text:string):Promise<void> {if(!text.length||[...text].length>4096)throw new ChatFault('INVALID_ARGUMENT');await this.send(conversationId,{type:'text',text});}
 async sendAttachment(conversationId:string,attachmentId:string,kind:'image'|'file'):Promise<void> {await this.send(conversationId,{type:kind,attachment_id:entity(attachmentId)});}
 getAttachmentTransfer(conversationId:string):AttachmentSendState|null {const context=this.session.getSnapshot().context;if(context.state!=='authenticated')return null;return this.attachmentOperations.get(JSON.stringify([context.user_id,context.device_id,conversationId]))?.state??null;}
 async transferAttachment(conversationId:string,task:()=>Promise<AttachmentView>):Promise<void> {
  const context=this.session.getSnapshot().context;if(context.state!=='authenticated'||!this.valid()||this.state.denied.includes(conversationId))throw new ChatFault('UNAUTHENTICATED');
  const key=JSON.stringify([context.user_id,context.device_id,conversationId]),previous=this.attachmentOperations.get(key);if(previous?.running)return previous.running;
  const operation:AttachmentOperation={userId:context.user_id,deviceId:context.device_id,conversationId,task,ready:null,running:null,blocked:false,state:{phase:'uploading',error:null,retryable:false}};
  this.attachmentOperations.set(key,operation);await this.runAttachment(operation,key);
 }
 async retryAttachment(conversationId:string):Promise<void> {
  const context=this.session.getSnapshot().context;if(context.state!=='authenticated')throw new ChatFault('UNAUTHENTICATED');const key=JSON.stringify([context.user_id,context.device_id,conversationId]),operation=this.attachmentOperations.get(key);
  if(!operation||operation.blocked||!operation.state.retryable)throw new ChatFault('FORBIDDEN');await this.runAttachment(operation,key);
 }
 private runAttachment(operation:AttachmentOperation,key:string):Promise<void> {
  if(operation.running)return operation.running;
  const run=async():Promise<void>=>{
   operation.state={phase:'uploading',error:null,retryable:false};this.publish();
   try{
    if(!operation.ready){const ready=await operation.task();if(ready.state!=='ready')throw new AttachmentTransferError('UPLOAD_NOT_READY',false);operation.ready=ready;}
    const context=this.session.getSnapshot().context;if(context.state!=='authenticated'||context.user_id!==operation.userId||context.device_id!==operation.deviceId||!this.valid())throw new ChatFault('UNAUTHENTICATED');
    if(operation.blocked||this.state.denied.includes(operation.conversationId))throw new ChatFault('FORBIDDEN');
    if(this.syncing)await this.syncing;else if(!this.authorityReconciled)await this.reconcile();
    const epoch=this.epoch;await this.fetchDetail(operation.conversationId,epoch);
    const current=this.session.getSnapshot().context;if(!this.valid(epoch)||current.state!=='authenticated'||current.user_id!==operation.userId||current.device_id!==operation.deviceId)throw new ChatFault('UNAUTHENTICATED');
    if(operation.blocked)throw new ChatFault('FORBIDDEN');await this.sendAttachment(operation.conversationId,operation.ready.id,operation.ready.kind);
    if(this.attachmentOperations.get(key)===operation)this.attachmentOperations.delete(key);this.publish();
   }catch(error){
    if(error instanceof AttachmentTransferError&&error.retry)operation.task=error.retry;
    const permanent=operation.blocked||error instanceof StorageFault||error instanceof Error&&'code' in error&&['FORBIDDEN','NOT_FOUND','INVALID_ARGUMENT','UPLOAD_EXPIRED','CONFLICT'].includes(String(error.code));
    operation.state={phase:operation.ready?'ready':'waiting',error:error instanceof AttachmentTransferError?error.message:'附件尚未傳送；原上傳嘗試或已核驗附件已保留。',retryable:!permanent&&(operation.ready!==null||error instanceof AttachmentTransferError&&error.retry!==null)};this.publish();throw error;
   }
  };
  const promise=run();operation.running=promise;void promise.finally(()=>{if(operation.running===promise)operation.running=null;}).catch(()=>{});return promise;
 }
 private blockAttachments(conversationId:string):void {
  const binding=this.binding;if(!binding)return;
  let changed=false;for(const operation of this.attachmentOperations.values())if(operation.conversationId===conversationId&&operation.userId===binding.user&&operation.deviceId===binding.device&&!operation.blocked){operation.blocked=true;operation.state={phase:'waiting',error:'對話權限已變更，舊附件傳送意圖已停止。',retryable:false};changed=true;}
  if(changed)this.publish();
 }
 async retryIntent(c1:string):Promise<void> {const intent=this.state.intents[c1];if(!intent||intent.status==='persisted'||this.state.denied.includes(intent.conversationId)||intent.retryAt!==null&&intent.retryAt>Date.now())return;this.manualIntentRetries.add(c1);await this.commit(state=>{const value=state.intents[c1];value.status='unknown';value.autoRetryStopped=false;if(value.error!=='MEMBERSHIP_RECHECK_REQUIRED')value.error=null;});void this.flush();}
 async setDraft(id:string,text:string):Promise<void> {await this.persistLocal(id,text);}
 async saveAnchor(id:string,anchor:ScrollAnchor):Promise<void> {await this.persistLocal(id,anchor);}
 private async persistLocal(id:string,value:string|ScrollAnchor):Promise<void> {
  const epoch=this.epoch,ticket=this.authority.capture(id),repository=this.repository,valid=():boolean=>this.valid(epoch)&&this.authority.isCurrent(id,ticket)&&!this.state.denied.includes(id)&&!this.observedDenied.has(id);
  if(!repository||!valid())return;
  try{if(typeof value==='string')await repository.writeDraft(id,value,valid);else await repository.writeAnchor(id,value,valid);if(!valid())return;this.state=typeof value==='string'?{...this.state,drafts:{...this.state.drafts,[id]:value}}:{...this.state,anchors:{...this.state.anchors,[id]:value}};this.publish();}
  catch(error){if(error instanceof RepositoryCancelled)return;if(epoch===this.epoch)this.failClosed(error);throw error;}
 }
 async receipt(messageId:string,conversationId:string,kind:'delivered'|'read'):Promise<void> {
  const epoch=this.epoch,ticket=this.authority.capture(conversationId),valid=():boolean=>this.valid(epoch)&&this.authority.isCurrent(conversationId,ticket)&&!this.state.denied.includes(conversationId)&&!this.observedDenied.has(conversationId);
  const message=this.state.messages[conversationId]?.find(m=>m.id===messageId);if(!message||message.sender_id===this.binding?.user||!valid())return;
  await this.commit(state=>{const receipt=state.receipts[messageId]??{messageId,conversationId,desired:kind,confirmed:null,error:null,retryAt:null,blocked:false,autoRetryStopped:false};if(kind==='read')receipt.desired='read';state.receipts[messageId]=receipt;},epoch,valid);void this.flush();
 }
 async retryReceipts(conversationId:string):Promise<void> {
  if(!this.valid()||this.state.denied.includes(conversationId))return;
  await this.commit(state=>{for(const receipt of Object.values(state.receipts))if(receipt.conversationId===conversationId&&receipt.autoRetryStopped&&!receipt.blocked)receipt.autoRetryStopped=false;});void this.flush();
 }
 private flush():Promise<void> {
  if(this.flushing){this.flushRequested=true;return this.flushing;}
  if(!this.valid()||!this.accepted)return Promise.resolve();
  const epoch=this.epoch,scope=this.scope,sourceValid=():boolean=>this.valid(epoch)&&this.scope===scope&&scope!==null&&!scope.queue.abort.signal.aborted;
  const work=async():Promise<void>=>{
   for(const intent of Object.values(this.state.intents)){
    if(!sourceValid()||!this.accepted)return;
    const manual=this.manualIntentRetries.has(intent.clientMessageId);
    if(!this.authorityReconciled||intent.status==='persisted'||intent.status==='rejected'||this.state.denied.includes(intent.conversationId)||(intent.retryAt!==null&&intent.retryAt>Date.now())||(!manual&&intent.autoRetryStopped)||(!manual&&intent.error!==null&&intent.error!=='RATE_LIMITED')||(!manual&&intent.error==='RATE_LIMITED'&&intent.retryAt===null))continue;
    this.manualIntentRetries.delete(intent.clientMessageId);const ticket=this.authority.capture(intent.conversationId);
    try{
     const sendValid=():boolean=>{const value=this.state.intents[intent.clientMessageId];return sourceValid()&&this.authority.isCurrent(intent.conversationId,ticket)&&!this.state.denied.includes(intent.conversationId)&&!this.observedDenied.has(intent.conversationId)&&value?.status==='unknown'&&value.conversationId===intent.conversationId&&(value.error!=='MEMBERSHIP_RECHECK_REQUIRED'||manual);};
     await this.commit(state=>{const value=state.intents[intent.clientMessageId];if(!value||state.denied.includes(intent.conversationId)||value.status==='persisted'||value.status==='rejected'||value.error==='MEMBERSHIP_RECHECK_REQUIRED'&&!manual)throw new RepositoryCancelled();value.status='unknown';},epoch,()=>sourceValid()&&this.authority.isCurrent(intent.conversationId,ticket)&&!this.observedDenied.has(intent.conversationId));
     if(!sendValid())throw new RepositoryCancelled();
     const frame=await this.request('message.send','message.ack',{client_message_id:intent.clientMessageId,...intent.payload},intent.conversationId);
     if(!sourceValid())return;await this.commit(state=>settleIntent(state,intent.clientMessageId,uuid(frame.payload.message_id)),epoch,sourceValid);
    }catch(error){
     if(error instanceof RepositoryCancelled)continue;
     if(!sourceValid())return;const fault=error instanceof ChatFault?error:new ChatFault('OUTCOME_UNCONFIRMED',true),current=this.authority.isCurrent(intent.conversationId,ticket);
     await this.commit(state=>{const value=state.intents[intent.clientMessageId];if(!value||value.status==='persisted')return;value.status=fault.code==='OUTCOME_UNCONFIRMED'||fault.retryable?'unknown':'rejected';if(!current||value.error==='MEMBERSHIP_RECHECK_REQUIRED')value.error='MEMBERSHIP_RECHECK_REQUIRED';else value.error=fault.code==='OUTCOME_UNCONFIRMED'?null:fault.code;if(fault.code==='RATE_LIMITED'){if(fault.retryAfterMs===undefined)value.autoRetryStopped=true;else value.retryAt=Math.max(value.retryAt??0,Date.now()+fault.retryAfterMs);}},epoch,sourceValid);
     if(current&&['FORBIDDEN','NOT_FOUND'].includes(fault.code))await this.withdraw(intent.conversationId);
     if(fault.code==='OUTCOME_UNCONFIRMED'){this.connectionLost(epoch);return;}
    }
   }
   for(const receipt of Object.values(this.state.receipts)){
    if(!sourceValid()||!this.accepted)return;
    if(!receiptCanRetryAutomatically(receipt,Date.now()))continue;
    try{
     const frame=await this.request(receipt.desired==='read'?'message.read':'message.received','receipt.ack',{message_id:receipt.messageId},receipt.conversationId);if(!sourceValid())return;
     await this.commit(state=>{const value=state.receipts[receipt.messageId];if(!value)return;const confirmed=status(frame.payload.status);if(value.confirmed!=='read')value.confirmed=confirmed;value.error=null;value.retryAt=null;value.autoRetryStopped=false;},epoch,sourceValid);
    }catch(error){
     if(!sourceValid())return;const fault=error instanceof ChatFault?error:new ChatFault('OUTCOME_UNCONFIRMED',true);
     await this.commit(state=>{const value=state.receipts[receipt.messageId];if(value)recordReceiptFailure(value,fault.code,fault.retryable,fault.retryAfterMs,Date.now());},epoch,sourceValid);
     if(fault.code==='OUTCOME_UNCONFIRMED'){this.connectionLost(epoch);return;}
    }
   }
  };
  const promise=work().catch(error=>this.operationError(error));this.flushing=promise;
  void promise.finally(()=>{if(this.flushing===promise){this.flushing=null;const requested=this.flushRequested;this.flushRequested=false;if(requested&&sourceValid())queueMicrotask(()=>{void this.flush();});}});return promise;
 }
}
