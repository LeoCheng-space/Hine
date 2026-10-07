import type { SessionController } from './session';
import type { AttachmentView, DownloadGrant, SessionContext, UploadGrant } from './types';
import { entity, fields, integer, record, string, timestamp } from './repository';

export class AttachmentTransferError extends Error {
 constructor(readonly code:string,readonly retryable:boolean,readonly retry:(()=>Promise<AttachmentView>)|null=null){super(code==='UPLOAD_NOT_READY'?'附件尚未完成核驗，請核對原上傳嘗試。':code==='UPLOAD_EXPIRED'?'上傳授權已過期，請重新選取檔案建立新嘗試。':'附件傳輸失敗，尚未傳送訊息。');this.name='AttachmentTransferError';}
}
export interface UploadOwner {user_id:string;device_id:string}
export function canResumeUpload(context:SessionContext,owner:UploadOwner):boolean {return context.state==='authenticated'&&context.user_id===owner.user_id&&context.device_id===owner.device_id&&Date.parse(context.expires_at)>Date.now();}
const MIME_KIND:Record<string,'image'|'file'>={'image/jpeg':'image','image/png':'image','application/pdf':'file'};
function storageURL(value:unknown):URL {
 const url=new URL(string(value));if(url.protocol!=='https:'||url.username||url.password||!(url.hostname==='storage.googleapis.com'||url.hostname.endsWith('.storage.googleapis.com')))throw new AttachmentTransferError('INVALID_STORAGE_GRANT',false);
 return url;
}
export function validateUploadGrant(value:unknown,mime:string):UploadGrant {
 const p=record(value);fields(p,['attachment_id','upload_attempt_id','upload_url','expires_at','required_headers']);
 const headers=record(p.required_headers),normalized:Record<string,string>={};
 for(const [name,value] of Object.entries(headers)){
  const lower=name.toLowerCase();if(normalized[lower]!==undefined||(!['content-type','cache-control','x-goog-if-generation-match'].includes(lower)&&!lower.startsWith('x-goog-meta-')))throw new AttachmentTransferError('INVALID_STORAGE_GRANT',false);
  normalized[lower]=string(value);
 }
 if(normalized['content-type']!==mime||normalized['x-goog-if-generation-match']!=='0'||normalized['cache-control']!=='no-transform')throw new AttachmentTransferError('INVALID_STORAGE_GRANT',false);
 const url=storageURL(p.upload_url),signed=url.searchParams.get('X-Goog-SignedHeaders')?.toLowerCase().split(';');
 if(!signed||Object.keys(normalized).some(name=>!signed.includes(name)))throw new AttachmentTransferError('INVALID_STORAGE_GRANT',false);
 const expiry=timestamp(p.expires_at);if(Date.parse(expiry)<=Date.now())throw new AttachmentTransferError('UPLOAD_EXPIRED',false);
 return {attachment_id:entity(p.attachment_id),upload_attempt_id:entity(p.upload_attempt_id),upload_url:url.href,expires_at:expiry,required_headers:Object.fromEntries(Object.entries(headers).map(([name,value])=>[name,string(value)]))};
}
function readyAttachment(value:unknown,grant:UploadGrant,scope:'avatar'|'conversation',conversationId:string|null,file:File,sha256:string,userId:string):AttachmentView {
 const p=record(value);fields(p,['id','scope','uploader_id','kind','filename','content_type','size_bytes','sha256','state','created_at','conversation_id']);
 if(p.id!==grant.attachment_id||p.scope!==scope||p.uploader_id!==userId||p.conversation_id!==conversationId||p.kind!==MIME_KIND[file.type]||p.filename!==file.name||p.content_type!==file.type||p.size_bytes!==file.size||p.sha256!==sha256)throw new AttachmentTransferError('ATTACHMENT_MISMATCH',false);
 if(p.state!=='ready')throw new AttachmentTransferError('UPLOAD_NOT_READY',true);
 return {id:entity(p.id),scope,uploader_id:userId,kind:MIME_KIND[file.type],filename:file.name,content_type:file.type,size_bytes:file.size,sha256,state:'ready',created_at:timestamp(p.created_at),conversation_id:conversationId};
}
export async function uploadAttachment(session:SessionController,file:File,scope:'avatar'|'conversation',conversationId:string|null):Promise<AttachmentView> {
 if(!(file instanceof File)||!MIME_KIND[file.type]||file.size<=0||file.size>10_485_760||[...file.name].length<1||[...file.name].length>255||(scope==='avatar'&&(conversationId!==null||MIME_KIND[file.type]!=='image'))||(scope==='conversation'&&conversationId===null))throw new AttachmentTransferError('INVALID_ATTACHMENT',false);
 const context=session.getSnapshot().context;if(context.state!=='authenticated')throw new AttachmentTransferError('UNAUTHENTICATED',false);
 const binding:UploadOwner={user_id:context.user_id,device_id:context.device_id};
 const valid=():boolean=>canResumeUpload(session.getSnapshot().context,binding);
 const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());const sha256=Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,'0')).join('');
 const idempotencyKey=crypto.randomUUID();let grant:UploadGrant|null=null;let putAttempted=false;let putUnconfirmed=false;
 const attempt=async():Promise<AttachmentView>=>{
  try{
   if(!valid())throw new AttachmentTransferError('UNAUTHENTICATED',false);
   if(!grant){const response=await session.request<unknown>('/uploads',{method:'POST',idempotencyKey,json:{scope,conversation_id:conversationId,filename:file.name,content_type:file.type,size_bytes:file.size,sha256}});if(!valid())throw new AttachmentTransferError('UNAUTHENTICATED',false);grant=validateUploadGrant(response.data,file.type);}
   if(!putAttempted&&Date.parse(grant.expires_at)>Date.now()){
    putAttempted=true;putUnconfirmed=true;
    try{const response=await fetch(grant.upload_url,{method:'PUT',body:file,headers:grant.required_headers,credentials:'omit',redirect:'error',referrerPolicy:'no-referrer',cache:'no-store',signal:AbortSignal.timeout(60_000)});putUnconfirmed=!response.ok;}
    catch{/* Unknown PUT outcome is reconciled only by the original A21 attempt. */}
   }
   if(!valid())throw new AttachmentTransferError('UNAUTHENTICATED',false);
   const response=await session.request<unknown>(`/uploads/${encodeURIComponent(grant.attachment_id)}/complete`,{method:'POST',json:{upload_attempt_id:grant.upload_attempt_id,sha256}});
   if(!valid())throw new AttachmentTransferError('UNAUTHENTICATED',false);return readyAttachment(response.data,grant,scope,conversationId,file,sha256,binding.user_id);
  }catch(error){
   const current=session.getSnapshot().context;
   if(error instanceof Error&&'code' in error&&error.code==='UNAUTHENTICATED'&&current.state!=='logged_out'&&current.user_id===binding.user_id&&current.device_id===binding.device_id)throw new AttachmentTransferError('AUTH_REFRESH_PENDING',true,attempt);
   if(error instanceof AttachmentTransferError&&error.code!=='UPLOAD_NOT_READY')throw error;
   const fault=error instanceof Error&&'code' in error?String(error.code):'TRANSFER_UNCONFIRMED';
   if(fault==='UPLOAD_NOT_READY'){
    if(grant&&Date.parse(grant.expires_at)<=Date.now())throw new AttachmentTransferError('UPLOAD_EXPIRED',false);
    if(putUnconfirmed)putAttempted=false;
   }
   const retryable=!['FORBIDDEN','NOT_FOUND','INVALID_ARGUMENT','CONFLICT','UNSUPPORTED_MEDIA_TYPE','PAYLOAD_TOO_LARGE','UNAUTHENTICATED','IDEMPOTENCY_CONFLICT'].includes(fault);
   throw new AttachmentTransferError(fault,retryable,retryable?attempt:null);
  }
 };
 return attempt();
}
export async function downloadAttachment(session:SessionController,attachmentId:string):Promise<DownloadGrant> {
 const context=session.getSnapshot().context;if(context.state!=='authenticated')throw new AttachmentTransferError('UNAUTHENTICATED',false);
 const response=await session.request<unknown>(`/attachments/${encodeURIComponent(attachmentId)}/download`);const now=session.getSnapshot().context;
 if(now.state!=='authenticated'||now.access_token!==context.access_token)throw new AttachmentTransferError('UNAUTHENTICATED',false);
 return validateDownloadGrant(response.data);
}
export function validateDownloadGrant(value:unknown):DownloadGrant {
 const p=record(value);fields(p,['download_url','expires_at','content_type','filename','size_bytes']);
 const url=storageURL(p.download_url);if(!url.searchParams.has('generation'))throw new AttachmentTransferError('INVALID_STORAGE_GRANT',false);
 const expiry=timestamp(p.expires_at),mime=string(p.content_type);if(!MIME_KIND[mime]||Date.parse(expiry)<=Date.now())throw new AttachmentTransferError('INVALID_STORAGE_GRANT',false);
 return {download_url:url.href,expires_at:expiry,content_type:mime,filename:string(p.filename),size_bytes:integer(p.size_bytes,1)};
}
