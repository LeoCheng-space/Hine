import { useEffect, useRef, useState } from 'react';
import type { SessionController } from './session';
import type { DownloadGrant } from './types';
import type { AttachmentSendState } from './chat';
import { downloadAttachment } from './attachment-transfer';
interface AttachmentMetadata {filename:string;content_type:string;size_bytes:number}
export function AttachmentRecovery({transfer,onRetry}:{transfer:AttachmentSendState|null;onRetry:()=>void}) {
 if(!transfer)return null;
 return <div className="chat-notice notice" data-read-occlusion role="status" aria-label="附件傳送狀態"><p>{transfer.phase==='uploading'?'正在上傳與核驗附件；未就緒不會傳送訊息。':transfer.phase==='ready'?'附件已完成核驗，尚未加入傳送佇列。':'原附件上傳嘗試尚未完成，請核對原嘗試。'}</p>{transfer.error&&<p>{transfer.error}</p>}{transfer.retryable&&transfer.phase!=='uploading'&&<button type="button" onClick={onRetry}>{transfer.phase==='ready'?'傳送已核驗附件':'核對原上傳嘗試'}</button>}</div>;
}

async function attachmentBytes(session:SessionController,id:string):Promise<{grant:DownloadGrant;blob:Blob}> {
 const before=session.getSnapshot().context;const grant=await downloadAttachment(session,id);
 const response=await fetch(grant.download_url,{credentials:'omit',redirect:'error',referrerPolicy:'no-referrer',cache:'no-store',signal:AbortSignal.timeout(30_000)});
 if(!response.ok)throw new Error('附件版本無法下載，請重新取得授權。');const blob=await response.blob();
 const current=session.getSnapshot().context;if(before.state!=='authenticated'||current.state!=='authenticated'||before.access_token!==current.access_token||blob.size!==grant.size_bytes)throw new Error('附件版本或工作階段已變更。');
 return {grant,blob};
}
export function AttachmentTile({session,attachmentId,kind,onPreview}:{session:SessionController;attachmentId:string;kind:'image'|'file';onPreview:(id:string)=>void}) {
 const [grant,setGrant]=useState<AttachmentMetadata|null>(null),[image,setImage]=useState<string|null>(null),[error,setError]=useState<string|null>(null),[loading,setLoading]=useState(false),[revision,setRevision]=useState(0);
 useEffect(()=>{let active=true,objectURL:string|null=null;setError(null);setGrant(null);setImage(null);setLoading(true);
  const load=async():Promise<void>=>{if(kind==='file'){const result=await downloadAttachment(session,attachmentId);if(active)setGrant({filename:result.filename,content_type:result.content_type,size_bytes:result.size_bytes});return;}const result=await attachmentBytes(session,attachmentId);if(!active)return;if(result.grant.content_type==='application/pdf')throw new Error('ATTACHMENT_KIND_MISMATCH');setGrant({filename:result.grant.filename,content_type:result.grant.content_type,size_bytes:result.grant.size_bytes});objectURL=URL.createObjectURL(result.blob);setImage(objectURL);};
  void load().catch(()=>{if(active)setError('附件無法載入。請重新取得下載授權。');}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;if(objectURL)URL.revokeObjectURL(objectURL);};
 },[session,attachmentId,kind,revision]);
 async function download():Promise<void>{setLoading(true);setError(null);try{const result=await attachmentBytes(session,attachmentId),url=URL.createObjectURL(result.blob),anchor=document.createElement('a');anchor.href=url;anchor.download=result.grant.filename;anchor.rel='noopener';document.body.append(anchor);anchor.click();anchor.remove();window.setTimeout(()=>URL.revokeObjectURL(url),1000);}catch{setError('下載失敗，請重新取得附件授權。');}finally{setLoading(false);}}
 return <div className="attachment-tile">{kind==='image'&&image&&<button type="button" className="image-preview-button" onClick={()=>onPreview(attachmentId)} aria-label={`開啟圖片：${grant?.filename??'附件'}`}><img src={image} alt={grant?.filename??'圖片附件'} onLoad={()=>window.dispatchEvent(new Event('hine-bubble-resize'))}/></button>}<div className="attachment-info"><strong>{grant?.filename??(kind==='image'?'圖片附件':'PDF 附件')}</strong>{grant&&<small>{(grant.size_bytes/1024).toFixed(1)} KB · {grant.content_type}</small>}</div>{loading&&<small role="status">正在取得附件…</small>}{error&&<><p role="alert">{error}</p><button type="button" onClick={()=>setRevision(value=>value+1)}>重新載入附件</button></>}{grant&&<button type="button" disabled={loading} onClick={()=>{void download();}}>下載{kind==='file'?' PDF':'原始圖片'}</button>}</div>;
}
export function AttachmentViewer({session,attachmentId,onClose}:{session:SessionController;attachmentId:string;onClose:()=>void}) {
 const dialog=useRef<HTMLDialogElement>(null),closeButton=useRef<HTMLButtonElement>(null),trigger=useRef<HTMLElement|null>(document.activeElement instanceof HTMLElement?document.activeElement:null);
 const [grant,setGrant]=useState<AttachmentMetadata|null>(null),[url,setURL]=useState<string|null>(null),[error,setError]=useState<string|null>(null),[loading,setLoading]=useState(true),[revision,setRevision]=useState(0),[details,setDetails]=useState(false);
 const previous=history.state?.hinePreview;const marker=useRef(typeof previous?.marker==='string'&&previous.attachmentId===attachmentId&&previous.path===location.pathname?previous.marker:crypto.randomUUID());
 useEffect(()=>{
  const element=dialog.current;if(!element)return;element.showModal();closeButton.current?.focus();window.dispatchEvent(new Event('hine-overlay-change'));
  if(history.state?.hinePreview?.marker!==marker.current)history.pushState({...history.state,hinePreview:{marker:marker.current,attachmentId,path:location.pathname}},'',location.href);
  const back=():void=>{if(history.state?.hinePreview?.marker!==marker.current)onClose();};window.addEventListener('popstate',back);
  return()=>{window.removeEventListener('popstate',back);element.close();window.dispatchEvent(new Event('hine-overlay-change'));if(trigger.current?.isConnected)trigger.current.focus();};
 },[onClose]);
 useEffect(()=>{let active=true,objectURL:string|null=null;setLoading(true);setError(null);setURL(null);
  void attachmentBytes(session,attachmentId).then(result=>{if(!active)return;setGrant({filename:result.grant.filename,content_type:result.grant.content_type,size_bytes:result.grant.size_bytes});objectURL=URL.createObjectURL(result.blob);setURL(objectURL);}).catch(()=>{if(active)setError('這個固定版本無法載入。請重新取得下載授權。');}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;if(objectURL)URL.revokeObjectURL(objectURL);};
 },[session,attachmentId,revision]);
 function close():void{if(history.state?.hinePreview?.marker===marker.current)history.back();onClose();}
 return <dialog ref={dialog} className="attachment-modal" aria-modal="true" aria-labelledby="attachment-title" onCancel={event=>{event.preventDefault();close();}} onKeyDown={event=>{if(event.key!=='Tab'||!dialog.current)return;const focusable=[...dialog.current.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],[tabindex="0"]')];const first=focusable[0],last=focusable[focusable.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}}><header className="attachment-modal-header"><h2 id="attachment-title">{grant?.filename??'圖片檢視器'}</h2><button ref={closeButton} type="button" onClick={close} aria-label="關閉附件預覽">關閉</button></header>{loading&&<p role="status">正在核對下載權限…</p>}{error&&<div role="alert"><p>{error}</p><button type="button" onClick={()=>setRevision(value=>value+1)}>重新取得附件</button></div>}{url&&grant&&<>{grant.content_type==='application/pdf'?<div className="pdf-download-only"><p>PDF 僅提供下載，不內嵌預覽。</p><a href={url} download={grant.filename}>下載 PDF</a></div>:<img className="attachment-full-image" src={url} alt={grant.filename}/>}<footer><button type="button" onClick={()=>setDetails(value=>!value)} aria-expanded={details}>附件詳細資料</button><a className="button-link" href={url} download={grant.filename}>下載原始檔案</a>{details&&<dl><dt>檔名</dt><dd>{grant.filename}</dd><dt>類型</dt><dd>{grant.content_type}</dd><dt>大小</dt><dd>{grant.size_bytes.toLocaleString()} bytes</dd></dl>}</footer></>}</dialog>;
}
export default AttachmentViewer;
