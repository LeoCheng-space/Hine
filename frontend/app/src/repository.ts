import type { ConversationDetail, ConversationSummary, MessageView, ReceiptProjection } from './types';

export interface WireEvent { event:string; event_id:string; timestamp:string; payload:Record<string,unknown>; conversation_id?:string; sender_id?:string; correlation_id?:string }
export type SendPayload = {type:'text';text:string}|{type:'image'|'file';attachment_id:string};
export interface SendIntent { clientMessageId:string;conversationId:string;payload:SendPayload;createdAt:string;status:'pending'|'unknown'|'persisted'|'rejected';messageId:string|null;error:string|null;retryAt:number|null;authorizationVersion?:number|null;observed?:boolean;autoRetryStopped?:boolean }
export interface PendingReceipt { messageId:string;conversationId:string;desired:'delivered'|'read';confirmed:'delivered'|'read'|null;error:string|null;retryAt:number|null;blocked:boolean;autoRetryStopped:boolean }
export interface ScrollAnchor { messageId:string;offset:number;atLatest:boolean }
export interface HistoryWindow {conversationId:string;firstMessageId:string;lastMessageId:string}
export interface Partition {
 schema:3;cursor:string|null;messages:Record<string,MessageView[]>;conversations:Record<string,ConversationSummary>;details:Record<string,ConversationDetail>;
 intents:Record<string,SendIntent>;receipts:Record<string,PendingReceipt>;statuses:Record<string,ReceiptProjection>;drafts:Record<string,string>;anchors:Record<string,ScrollAnchor>;denied:string[];seen:string[];selfMembershipVersions:Record<string,number>;historyWindow:HistoryWindow|null;
}
export class StorageFault extends Error { constructor(){super('本機儲存失敗，已停止聊天。請釋放網站儲存空間並重新載入。');this.name='StorageFault';} }
export function emptyPartition():Partition {return {schema:3,cursor:null,messages:{},conversations:{},details:{},intents:{},receipts:{},statuses:{},drafts:{},anchors:{},denied:[],seen:[],selfMembershipVersions:{},historyWindow:null};}
export class RepositoryCancelled extends Error {constructor(){super('STALE_CONVERSATION');}}
export interface ConversationTicket {root:number;generation:number}
export class ConversationAuthority {
 private root=0;private generations:Record<string,number>={};
 capture(id:string):ConversationTicket {return {root:this.root,generation:this.generations[id]??0};}
 isCurrent(id:string,ticket:ConversationTicket):boolean {return ticket.root===this.root&&ticket.generation===(this.generations[id]??0);}
 invalidate(id:string):void {this.generations[id]=(this.generations[id]??0)+1;}
 invalidateAll():void {++this.root;this.generations={};}
}
export function receiptCanRetryAutomatically(receipt:PendingReceipt,now:number):boolean {return !receipt.blocked&&!receipt.autoRetryStopped&&receipt.confirmed!=='read'&&receipt.confirmed!==receipt.desired&&(receipt.retryAt===null||receipt.retryAt<=now);}
export function recordReceiptFailure(receipt:PendingReceipt,code:string,retryable:boolean,delay:number|undefined,now:number):void {
 receipt.error=code;receipt.blocked=!retryable;
 if(delay!==undefined)receipt.retryAt=Math.max(receipt.retryAt??0,now+delay);
 if(code==='RATE_LIMITED'&&delay===undefined)receipt.autoRetryStopped=true;
}
export function boundedPartition(state:Partition):void {
 const protectedMessages=new Set(Object.values(state.receipts).filter(receipt=>receipt.confirmed!==receipt.desired).map(receipt=>receipt.messageId));
 for(const intent of Object.values(state.intents))if(intent.status!=='persisted'&&intent.messageId)protectedMessages.add(intent.messageId);
 for(const anchor of Object.values(state.anchors))protectedMessages.add(anchor.messageId);
 let remaining=2000;const ids=Object.keys(state.messages).sort((a,b)=>{if(a===state.historyWindow?.conversationId)return -1;if(b===state.historyWindow?.conversationId)return 1;const x=state.messages[a].at(-1)?.order_key??'',y=state.messages[b].at(-1)?.order_key??'';return x>y?-1:x<y?1:0;});
 for(const id of ids){
  const messages=state.messages[id],anchor=state.anchors[id],window=state.historyWindow?.conversationId===id?state.historyWindow:null;
  const first=window?messages.findIndex(message=>message.id===window.firstMessageId):-1,last=window?messages.findIndex(message=>message.id===window.lastMessageId):-1;
  const anchorIndex=anchor&&!anchor.atLatest?messages.findIndex(message=>message.id===anchor.messageId):-1;
  const focus=first>=0?first:anchorIndex,start=focus>=0?Math.max(0,Math.min(focus-80,messages.length-180)):Math.max(0,messages.length-200);
  if(first>=0&&last>=first)for(const message of messages.slice(first,last+1))protectedMessages.add(message.id);
  const retained:MessageView[]=[];let ordinary=0;
  for(let index=0;index<messages.length;index++){const message=messages[index],inWindow=focus>=0?index>=start&&index<start+180||index>=messages.length-20:index>=start;if(protectedMessages.has(message.id))retained.push(message);else if(inWindow&&ordinary<200&&remaining>0){retained.push(message);++ordinary;--remaining;}}
  state.messages[id]=retained;
 }
 const retained=new Set(Object.values(state.messages).flat().map(message=>message.id));
 const statuses=Object.values(state.statuses).sort((a,b)=>a.updated_at>b.updated_at?-1:1);for(const projection of statuses.slice(2000))if(!retained.has(projection.message_id))delete state.statuses[projection.message_id];
 const settledIntents=Object.values(state.intents).filter(intent=>intent.status==='persisted'&&intent.messageId!==null).sort((a,b)=>a.createdAt>b.createdAt?-1:1);
 for(const intent of settledIntents.slice(500))delete state.intents[intent.clientMessageId];
 const settledReceipts=Object.values(state.receipts).filter(receipt=>receipt.confirmed===receipt.desired);
 for(const receipt of settledReceipts)if(!retained.has(receipt.messageId))delete state.receipts[receipt.messageId];
 state.seen=state.seen.slice(-4000);
 const details=Object.keys(state.details);for(const id of details.slice(0,Math.max(0,details.length-200)))if(!state.messages[id]?.length&&!state.anchors[id])delete state.details[id];
}
export function record(value:unknown):Record<string,unknown> {if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('INVALID_WIRE');return value as Record<string,unknown>;}
export function fields(value:Record<string,unknown>,required:string[],optional:string[]=[]):void {if(required.some(k=>!Object.hasOwn(value,k))||Object.keys(value).some(k=>!required.includes(k)&&!optional.includes(k)))throw new Error('INVALID_WIRE');}
export function string(value:unknown):string {if(typeof value!=='string'||!value.length||/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value))throw new Error('INVALID_WIRE');return value;}
export function entity(value:unknown):string {const result=string(value);if([...result].length>128)throw new Error('INVALID_WIRE');return result;}
export function uuid(value:unknown):string {const result=string(value);if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(result))throw new Error('INVALID_WIRE');return result;}
export function timestamp(value:unknown):string {const result=string(value);if(!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)$/.test(result)||!Number.isFinite(Date.parse(result)))throw new Error('INVALID_WIRE');return result;}
export function integer(value:unknown,min=0):number {if(typeof value!=='number'||!Number.isSafeInteger(value)||value<min)throw new Error('INVALID_WIRE');return value;}
export function boolean(value:unknown):boolean {if(typeof value!=='boolean')throw new Error('INVALID_WIRE');return value;}
export function status(value:unknown):'delivered'|'read' {if(value!=='delivered'&&value!=='read')throw new Error('INVALID_WIRE');return value;}
export function parseReceipt(value:unknown):ReceiptProjection {const p=record(value);fields(p,['kind','message_id','recipient_id','status','updated_at']);if(p.kind!=='direct')throw new Error('INVALID_WIRE');return {kind:'direct',message_id:uuid(p.message_id),recipient_id:entity(p.recipient_id),status:status(p.status),updated_at:timestamp(p.updated_at)};}
export function parseMessage(value:unknown,userId:string):MessageView {
 const p=record(value);fields(p,['id','event_id','conversation_id','sender_id','created_at','order_key','type','receipt'],['text','attachment_id','client_message_id']);
 const sender=entity(p.sender_id),order=string(p.order_key);if(!/^\d{20}$/.test(order))throw new Error('INVALID_WIRE');
 const base={id:uuid(p.id),event_id:uuid(p.event_id),conversation_id:entity(p.conversation_id),sender_id:sender,created_at:timestamp(p.created_at),order_key:order,receipt:p.receipt===null?null:parseReceipt(p.receipt)};
 if(base.receipt&&base.receipt.message_id!==base.id)throw new Error('INVALID_WIRE');
 const c1=p.client_message_id===undefined?{}:{client_message_id:uuid(p.client_message_id)};if(p.client_message_id!==undefined&&sender!==userId)throw new Error('INVALID_WIRE');
 if(p.type==='text'&&p.attachment_id===undefined){const text=string(p.text);if([...text].length>4096)throw new Error('INVALID_WIRE');return {...base,...c1,type:'text',text};}
 if((p.type==='image'||p.type==='file')&&p.text===undefined)return {...base,...c1,type:p.type,attachment_id:entity(p.attachment_id)};
 throw new Error('INVALID_WIRE');
}
export function mergeReceipt(old:ReceiptProjection|null,next:ReceiptProjection):ReceiptProjection {if(!old)return next;if(old.message_id!==next.message_id||old.recipient_id!==next.recipient_id)throw new Error('INVALID_WIRE');if(old.status==='read'&&next.status==='delivered')return old;if(old.status===next.status&&Date.parse(old.updated_at)>Date.parse(next.updated_at))return old;return next;}
export function compareMessage(a:MessageView,b:MessageView):number {return a.order_key<b.order_key?-1:a.order_key>b.order_key?1:a.id<b.id?-1:a.id>b.id?1:0;}
export function mergeMessage(messages:MessageView[],next:MessageView):MessageView[] {const old=messages.find(m=>m.id===next.id);if(old&&(old.event_id!==next.event_id||old.order_key!==next.order_key||old.sender_id!==next.sender_id||old.type!==next.type||old.text!==next.text||old.attachment_id!==next.attachment_id))throw new Error('INVALID_WIRE');const merged=old?{...next,receipt:next.receipt?mergeReceipt(old.receipt,next.receipt):old.receipt}:next;return [...messages.filter(m=>m.id!==next.id),merged].sort(compareMessage);}
export function settleIntent(state:Partition,c1:string,messageId:string,canonical=false):void {const intent=state.intents[c1];if(!intent)return;if(intent.messageId&&intent.messageId!==messageId)throw new Error('INVALID_WIRE');intent.messageId=messageId;intent.status='persisted';if(canonical){intent.observed=true;intent.error=null;}else if(intent.error!=='MEMBERSHIP_RECHECK_REQUIRED')intent.error=null;intent.retryAt=null;}
export function withdrawConversation(state:Partition,id:string):void {
 if(!state.denied.includes(id))state.denied.push(id);delete state.messages[id];delete state.conversations[id];delete state.details[id];delete state.drafts[id];delete state.anchors[id];
 if(state.historyWindow?.conversationId===id)state.historyWindow=null;
 for(const intent of Object.values(state.intents))if(intent.conversationId===id&&intent.status!=='persisted'){intent.status='rejected';intent.error='MEMBERSHIP_RECHECK_REQUIRED';}
 for(const [key,value] of Object.entries(state.receipts))if(value.conversationId===id)delete state.receipts[key];
 for(const [key,value] of Object.entries(state.statuses))if(!Object.values(state.messages).some(items=>items.some(m=>m.id===value.message_id)))delete state.statuses[key];
}
export function rejoinConversation(state:Partition,detail:ConversationDetail,boundaryVersion=detail.membership_version??1):void {
 const id=detail.id,previous=state.messages[id]??[],removed=new Set(previous.map(message=>message.event_id));state.seen=state.seen.filter(eventId=>!removed.has(eventId));
 delete state.messages[id];delete state.anchors[id];delete state.drafts[id];state.denied=state.denied.filter(value=>value!==id);
 if(state.historyWindow?.conversationId===id)state.historyWindow=null;
 for(const message of previous)delete state.statuses[message.id];for(const [key,value] of Object.entries(state.receipts))if(value.conversationId===id)delete state.receipts[key];
 for(const intent of Object.values(state.intents))if(intent.conversationId===id&&!intent.observed&&(intent.authorizationVersion??0)<boundaryVersion)intent.error='MEMBERSHIP_RECHECK_REQUIRED';
 state.details[id]=detail;state.conversations[id]={id,type:detail.type,title:detail.title,unread_count:detail.unread_count};
}
export function storeMessage(state:Partition,message:MessageView,userId:string):void {
 if(state.denied.includes(message.conversation_id))return;
 if(message.client_message_id){const intent=state.intents[message.client_message_id];if(intent&&(message.sender_id!==userId||intent.conversationId!==message.conversation_id||intent.payload.type!==message.type||(intent.payload.type==='text'?intent.payload.text!==message.text:intent.payload.attachment_id!==message.attachment_id)))throw new Error('INVALID_WIRE');}
 const projection=state.statuses[message.id];const group=state.conversations[message.conversation_id]?.type==='group';
 const next={...message,receipt:group?null:projection?mergeReceipt(message.receipt,projection):message.receipt};
 state.messages[next.conversation_id]=mergeMessage(state.messages[next.conversation_id]??[],next);
 if(next.client_message_id)settleIntent(state,next.client_message_id,next.id,true);
 if(next.sender_id!==userId&&!state.receipts[next.id])state.receipts[next.id]={messageId:next.id,conversationId:next.conversation_id,desired:'delivered',confirmed:null,error:null,retryAt:null,blocked:false,autoRetryStopped:false};
 else if(state.receipts[next.id]?.error==='MEMBERSHIP_RECHECK_REQUIRED'){state.receipts[next.id].blocked=false;state.receipts[next.id].error=null;}
}
export function applyEvents(state:Partition,events:WireEvent[],userId:string,authorizedJoins:Record<string,ConversationDetail>={}):void {
 const priorJoinIds:Record<string,string[]>={};for(const [eventId,detail] of Object.entries(authorizedJoins))priorJoinIds[eventId]=(state.messages[detail.id]??[]).map(message=>message.event_id);
 for(const e of events){
  const selfBoundary=(e.event==='conversation.member_added'||e.event==='conversation.member_removed')&&e.payload.member_id===userId;
  const id=e.conversation_id,version=selfBoundary?integer(e.payload.membership_version,1):0;
  if(selfBoundary&&id){
   if(version<=(state.selfMembershipVersions[id]??0))continue;
   if(e.event==='conversation.member_removed'){withdrawConversation(state,id);state.selfMembershipVersions[id]=version;state.seen.push(e.event_id);continue;}
   const joined=authorizedJoins[e.event_id];
   if(!joined){if(state.denied.includes(id)){state.selfMembershipVersions[id]=version;state.seen.push(e.event_id);continue;}throw new RepositoryCancelled();}
   if(joined.id!==id||!joined.members.some(member=>member.user_id===userId))throw new RepositoryCancelled();
   rejoinConversation(state,joined,version);const oldIds=new Set(priorJoinIds[e.event_id]);state.seen=state.seen.filter(eventId=>!oldIds.has(eventId));state.selfMembershipVersions[id]=version;state.seen.push(e.event_id);continue;
  }
  if(state.seen.includes(e.event_id))continue;
  const currentVersion=id?state.details[id]?.membership_version:null;
  if(e.event.startsWith('conversation.')&&currentVersion!==null&&currentVersion!==undefined&&integer(e.payload.membership_version,1)<currentVersion){state.seen.push(e.event_id);continue;}
  if(e.conversation_id&&state.denied.includes(e.conversation_id)&&!(e.event==='conversation.member_added'&&e.payload.member_id===userId))continue;
  if(e.event==='message.created'){
   const p=e.payload;const content=p.type==='text'?{text:p.text}:{attachment_id:p.attachment_id};
   storeMessage(state,parseMessage({id:p.message_id,event_id:e.event_id,conversation_id:e.conversation_id,sender_id:e.sender_id,created_at:e.timestamp,order_key:p.order_key,type:p.type,receipt:null,...content,...(p.client_message_id===undefined?{}:{client_message_id:p.client_message_id})},userId),userId);
  }else if(e.event==='message.status'){
   const projection=parseReceipt(e.payload);state.statuses[projection.message_id]=mergeReceipt(state.statuses[projection.message_id]??null,projection);
   const id=string(e.conversation_id);state.messages[id]=(state.messages[id]??[]).map(m=>m.id===projection.message_id?{...m,receipt:state.conversations[id]?.type==='group'?null:mergeReceipt(m.receipt,projection)}:m);
  }else if(e.event==='conversation.updated'){
   const changes=record(e.payload.changes),id=string(e.conversation_id),detail=state.details[id];
   if(changes.kind==='title'){const title=string(changes.title);if(state.conversations[id])state.conversations[id]={...state.conversations[id],title};if(detail)state.details[id]={...detail,title,membership_version:integer(e.payload.membership_version,1)};}
   else if(detail)state.details[id]={...detail,membership_version:integer(e.payload.membership_version,1),members:detail.members.map(m=>m.user_id===changes.member_id?{...m,role:changes.role==='admin'?'admin':'member'}:m)};
  }else if(e.event==='conversation.member_removed'){
   const id=string(e.conversation_id),detail=state.details[id];if(detail)state.details[id]={...detail,membership_version:integer(e.payload.membership_version,1),members:detail.members.filter(m=>m.user_id!==e.payload.member_id)};
  }
  state.seen.push(e.event_id);
 }
}
export function installSnapshot(state:Partition,staged:Partition,observed:WireEvent[],cursor:string,userId:string,authorities:Record<string,ConversationDetail>={}):void {
 if(observed.some(event=>event.event==='conversation.member_removed'&&event.payload.member_id===userId))throw new RepositoryCancelled();
 const oldMessages=state.messages,oldConversations=state.conversations,liveIds=new Set(observed.filter(event=>event.event==='message.created').map(event=>event.event_id));
 const joinedIds=new Set(observed.filter(event=>event.event==='conversation.member_added'&&event.payload.member_id===userId).map(event=>event.conversation_id));
 const groupIds=new Set([...Object.values(oldConversations),...Object.values(staged.conversations)].filter(conversation=>conversation.type==='group').map(conversation=>conversation.id));
 for(const id of groupIds){
  const messageIds=new Set((oldMessages[id]??[]).map(message=>message.id));for(const messageId of messageIds)delete state.statuses[messageId];
  delete state.anchors[id];delete state.details[id];
  if(state.historyWindow?.conversationId===id)state.historyWindow=null;
  for(const receipt of Object.values(state.receipts))if(receipt.conversationId===id){if(receipt.confirmed===receipt.desired)delete state.receipts[receipt.messageId];else{receipt.blocked=true;receipt.error='MEMBERSHIP_RECHECK_REQUIRED';}}
  for(const intent of Object.values(state.intents))if(intent.conversationId===id)intent.error='MEMBERSHIP_RECHECK_REQUIRED';
 }
 state.messages={};state.conversations={...staged.conversations};state.denied=state.denied.filter(id=>!staged.conversations[id]);
 for(const [id,conversation] of Object.entries(state.conversations)){
  if(!joinedIds.has(id))for(const message of staged.messages[id]??[])storeMessage(state,message,userId);
  for(const message of oldMessages[id]??[])if(conversation.type==='direct'||liveIds.has(message.event_id))storeMessage(state,message,userId);
 }
 for(const event of observed){const id=event.conversation_id;if(!id||state.denied.includes(id))continue;if(oldConversations[id])state.conversations[id]=oldConversations[id];for(const message of oldMessages[id]??[])if(liveIds.has(message.event_id))storeMessage(state,message,userId);}
 for(const id of Object.keys(state.details))if(!state.conversations[id])delete state.details[id];
 const observedIds=new Set(observed.map(event=>event.event_id));state.seen=state.seen.filter(id=>!observedIds.has(id));
 for(const event of observed)if(event.event==='message.created'||event.event==='message.status'||event.payload.member_id!==userId)applyEvents(state,[event],userId);
 for(const [id,detail] of Object.entries(authorities)){state.details[id]=detail;state.selfMembershipVersions[id]=Math.max(state.selfMembershipVersions[id]??0,detail.membership_version??0);}
 // This floor is installed only with a reset projection and fresh current-authority A12/A19, never by an ordinary metadata refresh.
 state.cursor=cursor;boundedPartition(state);
}
function requestValue<T>(request:IDBRequest<T>):Promise<T>{return new Promise<T>((resolve,reject)=>{request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(new StorageFault());});}
export class ChatRepository {
 private database:IDBDatabase|null=null;
 private queue:Promise<unknown>=Promise.resolve();
 private readonly key:string;
 constructor(readonly userId:string,readonly deviceId:string){this.key=JSON.stringify([userId,deviceId]);}
 async open():Promise<Partition>{
  try{
   const opening=indexedDB.open('hine-chat-v1',3);
   opening.onupgradeneeded=()=>{
    const database=opening.result,transaction=opening.transaction;
    if(!transaction)throw new StorageFault();
    if(!database.objectStoreNames.contains('partitions'))database.createObjectStore('partitions');
    for(const name of ['drafts','anchors'])if(!database.objectStoreNames.contains(name)){const store=database.createObjectStore(name);store.createIndex('partition','partition');}
    const request=transaction.objectStore('partitions').openCursor();
    request.onsuccess=()=>{
     const cursor=request.result;if(!cursor)return;
     try{
      const root=record(cursor.value),partition=string(cursor.primaryKey);
      if(root.schema===1){
       for(const name of ['drafts','anchors'])for(const [conversation,value] of Object.entries(record(root[name])))transaction.objectStore(name).put({partition,conversation,value},JSON.stringify([partition,conversation]));
       delete root.drafts;delete root.anchors;root.schema=2;root.selfMembershipVersions={};
       for(const value of Object.values(record(root.receipts)))record(value).autoRetryStopped=false;
      }
      if(root.schema===2){root.schema=3;root.historyWindow=null;cursor.update(root);}
      else if(root.schema!==3)throw new StorageFault();
      cursor.continue();
     }catch{transaction.abort();}
    };
   };
   opening.onblocked=()=>opening.onerror?.(new Event('error'));
   this.database=await requestValue(opening);
   this.database.onversionchange=()=>{this.database?.close();this.database=null;};
   return await this.update(state=>{
    for(const [id,messages] of Object.entries(state.messages)){if(!Array.isArray(messages))throw new StorageFault();state.messages[id]=messages.map(value=>{const parsed=parseMessage(value,this.userId);if(parsed.conversation_id!==id)throw new StorageFault();return parsed;});}
    for(const intent of Object.values(state.intents)){uuid(intent.clientMessageId);entity(intent.conversationId);timestamp(intent.createdAt);if(!['pending','unknown','persisted','rejected'].includes(intent.status))throw new StorageFault();if(intent.payload.type==='text')string(intent.payload.text);else{if(intent.payload.type!=='image'&&intent.payload.type!=='file')throw new StorageFault();entity(intent.payload.attachment_id);}}
    for(const receipt of Object.values(state.receipts)){uuid(receipt.messageId);entity(receipt.conversationId);status(receipt.desired);boolean(receipt.autoRetryStopped);if(receipt.confirmed!==null)status(receipt.confirmed);}
   });
  }catch{this.database?.close();this.database=null;throw new StorageFault();}
 }
 update(change:(state:Partition)=>void,valid:()=>boolean=()=>true):Promise<Partition>{
  const run=():Promise<Partition>=>new Promise<Partition>((resolve,reject)=>{
   if(!valid()){reject(new RepositoryCancelled());return;}
   if(!this.database){reject(new StorageFault());return;}
   let transaction:IDBTransaction,result:Partition,cause:unknown;
   try{transaction=this.database.transaction(['partitions','drafts','anchors'],'readwrite',{durability:'strict'});}catch{reject(new StorageFault());return;}
   transaction.onabort=()=>reject(cause??new StorageFault());transaction.onerror=()=>reject(new StorageFault());
   const store=transaction.objectStore('partitions'),requests=[store.get(this.key),transaction.objectStore('drafts').index('partition').getAll(this.key),transaction.objectStore('anchors').index('partition').getAll(this.key)];
   let outstanding=requests.length;
   for(const request of requests)request.onsuccess=()=>{
    if(--outstanding!==0)return;
    try{
     if(!valid())throw new RepositoryCancelled();
     const stored:unknown=requests[0].result;
     if(stored!==undefined){const root=record(stored);fields(root,['schema','cursor','messages','conversations','details','intents','receipts','statuses','denied','seen','selfMembershipVersions','historyWindow']);if(root.schema!==3||!Array.isArray(root.denied)||!Array.isArray(root.seen))throw new StorageFault();if(root.cursor!==null)string(root.cursor);if(root.historyWindow!==null){const window=record(root.historyWindow);entity(window.conversationId);uuid(window.firstMessageId);uuid(window.lastMessageId);}for(const key of ['messages','conversations','details','intents','receipts','statuses','selfMembershipVersions'])record(root[key]);}
     result=stored===undefined?emptyPartition():{...record(stored),drafts:{},anchors:{}} as Partition;
     for(const value of requests[1].result as unknown[]){const row=record(value);if(row.partition!==this.key||typeof row.value!=='string')throw new StorageFault();result.drafts[entity(row.conversation)]=row.value;}
     for(const value of requests[2].result as unknown[]){const row=record(value),anchor=record(row.value);if(row.partition!==this.key||typeof anchor.offset!=='number'||!Number.isFinite(anchor.offset))throw new StorageFault();result.anchors[entity(row.conversation)]={messageId:uuid(anchor.messageId),offset:anchor.offset,atLatest:boolean(anchor.atLatest)};}
     const oldDrafts={...result.drafts},oldAnchors={...result.anchors};
     change(result);boundedPartition(result);
     if(!valid())throw new RepositoryCancelled();
     const {drafts,anchors,...projection}=result;store.put(projection,this.key);
     for(const id of new Set([...Object.keys(oldDrafts),...Object.keys(drafts)])){const key=JSON.stringify([this.key,id]);if(drafts[id]===undefined)transaction.objectStore('drafts').delete(key);else if(drafts[id]!==oldDrafts[id])transaction.objectStore('drafts').put({partition:this.key,conversation:id,value:drafts[id]},key);}
     for(const id of new Set([...Object.keys(oldAnchors),...Object.keys(anchors)])){const key=JSON.stringify([this.key,id]),value=anchors[id],old=oldAnchors[id];if(!value)transaction.objectStore('anchors').delete(key);else if(!old||old.messageId!==value.messageId||old.offset!==value.offset||old.atLatest!==value.atLatest)transaction.objectStore('anchors').put({partition:this.key,conversation:id,value},key);}
    }catch(error){cause=error;transaction.abort();}
   };
   transaction.oncomplete=()=>resolve(result);
  });
  const next=this.queue.then(run,run);this.queue=next.catch(()=>{});return next;
 }
 writeDraft(conversationId:string,text:string,valid:()=>boolean):Promise<void>{return this.writeLocal('drafts',conversationId,text,valid);}
 writeAnchor(conversationId:string,anchor:ScrollAnchor,valid:()=>boolean):Promise<void>{uuid(anchor.messageId);if(!Number.isFinite(anchor.offset))return Promise.reject(new StorageFault());return this.writeLocal('anchors',conversationId,anchor,valid);}
 private writeLocal(name:'drafts'|'anchors',conversationId:string,value:string|ScrollAnchor,valid:()=>boolean):Promise<void>{
  const run=():Promise<void>=>new Promise<void>((resolve,reject)=>{
   if(!valid()){reject(new RepositoryCancelled());return;}if(!this.database){reject(new StorageFault());return;}
   let transaction:IDBTransaction;let cause:unknown;
   try{transaction=this.database.transaction(name,'readwrite',{durability:'strict'});}catch{reject(new StorageFault());return;}
   transaction.onabort=()=>reject(cause??new StorageFault());transaction.onerror=()=>reject(new StorageFault());transaction.oncomplete=()=>resolve();
   const store=transaction.objectStore(name),key=JSON.stringify([this.key,conversationId]),request=store.get(key);
   request.onsuccess=()=>{try{if(!valid())throw new RepositoryCancelled();const old=request.result===undefined?null:record(request.result);const oldValue=old?.value;let changed=oldValue!==value;if(typeof value!=='string'&&oldValue){const anchor=record(oldValue);changed=anchor.messageId!==value.messageId||anchor.offset!==value.offset||anchor.atLatest!==value.atLatest;}if(changed)store.put({partition:this.key,conversation:conversationId,value},key);}catch(error){cause=error;transaction.abort();}};
  });
  const next=this.queue.then(run,run);this.queue=next.catch(()=>{});return next;
 }
 async close():Promise<void>{await this.queue;this.database?.close();this.database=null;}
}
