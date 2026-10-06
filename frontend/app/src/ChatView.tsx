import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { FormEvent } from 'react';
import type { ChatController } from './chat';
import type { SessionController } from './session';
import type { AttachmentView, UserSummary } from './types';
import type { ScrollAnchor } from './repository';
import { uploadAttachment } from './attachment-transfer';
import { AttachmentRecovery, AttachmentTile, AttachmentViewer } from './AttachmentViewer';
import { GroupInfoDialog } from './GroupsPage';
import { hardwareKeyboardAvailable, ReadObserver, shouldSubmitEnter } from './read-observer';
import './Chat.css';

const CONNECTION_LABEL:Record<string,string>={stopped:'未連線',connecting:'正在連線',authenticating:'正在驗證',ready:'即時連線',offline:'離線 · 原傳送意圖已保存',blocked:'聊天已停止'};
export function Chat({session,chat,conversationId,onNavigate}:{session:SessionController;chat:ChatController;conversationId:string|null;onNavigate:(path:string)=>void}) {
 const snapshot=useSyncExternalStore(chat.subscribe,chat.getSnapshot),sessionSnapshot=useSyncExternalStore(session.subscribe,session.getSnapshot);
 const root=useRef<HTMLElement>(null),scroller=useRef<HTMLDivElement>(null),heading=useRef<HTMLHeadingElement>(null),composer=useRef<HTMLTextAreaElement>(null),fileInput=useRef<HTMLInputElement>(null);
 const composition=useRef(false),anchor=useRef<ScrollAnchor|null>(null),restoring=useRef(false),previousIds=useRef<string[]>([]),loadedDraft=useRef<string|null>(null);
 const [draft,setDraft]=useState(''),[error,setError]=useState<string|null>(null),[sending,setSending]=useState(false),[loadingHistory,setLoadingHistory]=useState(false),[newCount,setNewCount]=useState(0),[preview,setPreview]=useState<string|null>(null),[uploading,setUploading]=useState(false),[names,setNames]=useState<Record<string,string>>({});
 const [groupInfoOpen,setGroupInfoOpen]=useState(false),groupInfoButton=useRef<HTMLButtonElement>(null),groupInfoEpoch=useRef(0);
 const historyEpoch=useRef(0);
 const context=sessionSnapshot.context,me=context.user_id;const detail=conversationId?snapshot.details[conversationId]:undefined;
 const transfer=conversationId?chat.getAttachmentTransfer(conversationId):null;
 const authorized=conversationId!==null&&snapshot.currentConversation===conversationId&&!!detail&&!snapshot.denied.includes(conversationId)&&context.state==='authenticated';
 const messages=authorized?snapshot.messages[conversationId]??[]:[];
 const pending=authorized?Object.values(snapshot.intents).filter(intent=>intent.conversationId===conversationId&&intent.error!=='MEMBERSHIP_RECHECK_REQUIRED'&&(intent.status!=='persisted'||!intent.observed)&&!messages.some(message=>message.id===intent.messageId||message.client_message_id===intent.clientMessageId)):[];
 const quarantined=authorized?Object.values(snapshot.intents).filter(intent=>intent.conversationId===conversationId&&intent.error==='MEMBERSHIP_RECHECK_REQUIRED'&&intent.status!=='persisted'):[];
 const pausedReceipts=authorized&&Object.values(snapshot.receipts).some(receipt=>receipt.conversationId===conversationId&&receipt.autoRetryStopped&&!receipt.blocked&&receipt.confirmed!==receipt.desired);
 const closePreview=useCallback(()=>setPreview(null),[]);
 const closeGroupInfo=useCallback(()=>setGroupInfoOpen(false),[]);
 const restoreGroupInfoFocus=useCallback(()=>groupInfoButton.current?.focus(),[]);
 useEffect(()=>{
  setError(null);setPreview(null);setNewCount(0);setDraft('');setNames({});loadedDraft.current=null;anchor.current=null;previousIds.current=[];
  setLoadingHistory(false);
  ++historyEpoch.current;
  ++groupInfoEpoch.current;setGroupInfoOpen(false);
  if(conversationId&&context.state==='authenticated')void chat.openChat(conversationId).catch(()=>setError('無法開啟對話。請返回聊天清單核對權限。'));else chat.closeChat();
  return()=>{++groupInfoEpoch.current;++historyEpoch.current;chat.closeChat();};
 },[conversationId,context.state,context.user_id,context.device_id,context.session_generation,context.access_token,chat]);
 useEffect(()=>{if(conversationId&&snapshot.denied.includes(conversationId)){setGroupInfoOpen(false);setPreview(null);setDraft('');onNavigate('/chats');}},[conversationId,snapshot.denied,onNavigate]);
 useEffect(()=>{setUploading(transfer?.phase==='uploading');},[transfer]);
 useEffect(()=>{
  if(!authorized)return;
  const restorePreview=():void=>{const value:unknown=history.state;if(!value||typeof value!=='object'||!('hinePreview' in value)){setPreview(null);return;}const entry=value.hinePreview;if(!entry||typeof entry!=='object'||!('attachmentId' in entry)||!('path' in entry)||typeof entry.attachmentId!=='string'||entry.path!==location.pathname||!messages.some(message=>message.type!=='text'&&message.attachment_id===entry.attachmentId)){setPreview(null);return;}setPreview(entry.attachmentId);};
  restorePreview();window.addEventListener('popstate',restorePreview);return()=>window.removeEventListener('popstate',restorePreview);
 },[authorized,conversationId,messages]);
 useEffect(()=>{if(!authorized||!conversationId||loadedDraft.current===conversationId)return;loadedDraft.current=conversationId;setDraft(snapshot.drafts[conversationId]??'');anchor.current=snapshot.anchors[conversationId]??null;heading.current?.focus();},[authorized,conversationId,snapshot.drafts,snapshot.anchors]);
 useEffect(()=>{if(!authorized||!detail)return;let active=true;const ids=detail.members.map(member=>member.user_id);void Promise.all(ids.map(async id=>{try{const response=await session.request<UserSummary>(`/users/${encodeURIComponent(id)}`);return [id,response.data.display_name] as const;}catch{return [id,id] as const;}})).then(items=>{if(active)setNames(Object.fromEntries(items));});return()=>{active=false;};},[authorized,detail?.membership_version,conversationId,session]);
 const captureAnchor=useCallback((persist=true):void=>{
  const container=scroller.current;if(!container||!conversationId||!authorized||restoring.current)return;const bounds=container.getBoundingClientRect();
  const bubble=[...container.querySelectorAll<HTMLElement>('[data-message-id]')].find(node=>node.getBoundingClientRect().bottom>bounds.top);
  if(!bubble?.dataset.messageId)return;const next={messageId:bubble.dataset.messageId,offset:bubble.getBoundingClientRect().top-bounds.top,atLatest:container.scrollHeight-container.clientHeight-container.scrollTop<=48};
  const old=anchor.current;anchor.current=next;if(next.atLatest)setNewCount(0);
  if(persist&&(!old||old.messageId!==next.messageId||Math.abs(old.offset-next.offset)>0.5||old.atLatest!==next.atLatest))void chat.saveAnchor(conversationId,next).catch(()=>setError('閱讀位置無法保存，聊天已停止。'));
 },[authorized,conversationId,chat]);
 const restoreAnchor=useCallback(():void=>{
  const container=scroller.current;if(!container)return;restoring.current=true;const saved=anchor.current;
  if(!saved||saved.atLatest)container.scrollTop=container.scrollHeight;else{const bubble=[...container.querySelectorAll<HTMLElement>('[data-message-id]')].find(node=>node.dataset.messageId===saved.messageId);if(bubble)container.scrollTop+=bubble.getBoundingClientRect().top-container.getBoundingClientRect().top-saved.offset;}
  restoring.current=false;
 },[]);
 useLayoutEffect(()=>{
  if(!authorized)return;const ids=messages.map(message=>message.id),old=previousIds.current;
  if(old.length&&anchor.current&&!anchor.current.atLatest){const previousLast=old[old.length-1],index=ids.indexOf(previousLast);if(index>=0){const added=ids.slice(index+1).filter(id=>!old.includes(id)).length;if(added)setNewCount(count=>count+added);}}
  restoreAnchor();previousIds.current=ids;
 },[messages,authorized,restoreAnchor]);
 useEffect(()=>{
  if(!authorized||!root.current||!scroller.current)return;
  const resize=():void=>{const element=root.current;if(!element)return;const viewport=window.visualViewport,available=Math.max(0,(viewport?.offsetTop??0)+(viewport?.height??window.innerHeight)-element.getBoundingClientRect().top);element.style.setProperty('--chat-available-height',`${available}px`);element.classList.toggle('compact-viewport',available<300);restoreAnchor();};
  resize();const observer=new ResizeObserver(()=>restoreAnchor());observer.observe(scroller.current);for(const node of scroller.current.querySelectorAll<HTMLElement>('[data-message-id]'))observer.observe(node);
  window.addEventListener('resize',resize);window.addEventListener('orientationchange',resize);window.addEventListener('hine-bubble-resize',restoreAnchor);window.visualViewport?.addEventListener('resize',resize);window.visualViewport?.addEventListener('scroll',resize);
  return()=>{observer.disconnect();window.removeEventListener('resize',resize);window.removeEventListener('orientationchange',resize);window.removeEventListener('hine-bubble-resize',restoreAnchor);window.visualViewport?.removeEventListener('resize',resize);window.visualViewport?.removeEventListener('scroll',resize);};
 },[authorized,conversationId,restoreAnchor,messages.length]);
 useEffect(()=>{
  if(!authorized||!scroller.current||!conversationId)return;const id=conversationId;
  const observer=new ReadObserver(scroller.current,()=>chat.getSnapshot().currentConversation===id&&session.getSnapshot().context.state==='authenticated',async messageId=>{if(chat.getSnapshot().currentConversation!==id)return;await chat.receipt(messageId,id,'read');});
  return()=>observer.dispose();
 },[authorized,conversationId,chat,session]);
 async function submit(event?:FormEvent<HTMLFormElement>):Promise<void>{event?.preventDefault();if(composition.current||!authorized||!conversationId||sending||draft.length===0)return;
  const text=draft;setSending(true);setError(null);try{await chat.sendText(conversationId,text);setDraft(current=>current===text?'':current);composer.current?.focus();}catch{setError('訊息尚未加入傳送佇列。請核對文字與本機儲存狀態。');}finally{setSending(false);}}
 async function historyPage():Promise<void>{if(!conversationId||loadingHistory)return;captureAnchor();if(anchor.current)anchor.current={...anchor.current,atLatest:false};setLoadingHistory(true);setError(null);try{if(anchor.current)await chat.saveAnchor(conversationId,anchor.current);await chat.loadHistory(conversationId);}catch{setError('較早訊息尚未載入；可重試，不會重設同步游標。');}finally{setLoadingHistory(false);}}
 async function latest():Promise<void>{
  if(!conversationId||loadingHistory)return;
  const id=conversationId,owner=session.getSnapshot().context,saved=anchor.current,epoch=++historyEpoch.current;
  const current=():boolean=>{const value=session.getSnapshot().context;return epoch===historyEpoch.current&&value.state==='authenticated'&&value.user_id===owner.user_id&&value.device_id===owner.device_id&&value.session_generation===owner.session_generation&&chat.getSnapshot().currentConversation===id;};
  setLoadingHistory(true);setError(null);anchor.current=null;
  try{await chat.jumpLatest(id);if(current()){setNewCount(0);requestAnimationFrame(()=>{if(!current()||!scroller.current)return;scroller.current.scrollTop=scroller.current.scrollHeight;captureAnchor();});}}
  catch{if(current()){anchor.current=saved;restoreAnchor();setError('最新訊息尚未取得；請重試。');}}
  finally{if(epoch===historyEpoch.current)setLoadingHistory(false);}
 }
 async function finishUpload(work:()=>Promise<AttachmentView>,id:string):Promise<void>{setUploading(true);setError(null);try{await chat.transferAttachment(id,work);}catch{const current=session.getSnapshot().context;if(current.state==='authenticated'&&current.user_id===context.user_id&&current.device_id===context.device_id&&chat.getSnapshot().currentConversation===id)setError(chat.getAttachmentTransfer(id)?.error??'附件尚未傳送，請核對對話權限與儲存狀態。');}finally{const current=session.getSnapshot().context;if(current.state==='authenticated'&&current.user_id===context.user_id&&current.device_id===context.device_id&&chat.getSnapshot().currentConversation===id){setUploading(chat.getAttachmentTransfer(id)?.phase==='uploading');if(fileInput.current)fileInput.current.value='';}}}
 async function openGroupInfo():Promise<void>{
  if(!authorized||!conversationId||detail?.type!=='group')return;
  const id=conversationId,epoch=++groupInfoEpoch.current,owner=session.getSnapshot().context;
  const currentOwner=():boolean=>{const current=session.getSnapshot().context;return epoch===groupInfoEpoch.current&&current.state==='authenticated'&&current.user_id===owner.user_id&&current.device_id===owner.device_id&&current.session_generation===owner.session_generation;};
  try{await chat.refreshConversation(id);if(currentOwner()&&chat.getSnapshot().currentConversation===id&&!chat.getSnapshot().denied.includes(id))setGroupInfoOpen(true);}
  catch{if(currentOwner())setError('群組資訊尚未取得；請重試並核對權限。');}
 }
 if(!conversationId)return <section className="chat-empty empty-state"><span className="empty-symbol" aria-hidden="true">◌</span><h2>選擇一段對話</h2><p>從聊天清單繼續，或到聯絡人開啟新的對話。</p><button type="button" onClick={()=>onNavigate('/contacts')}>前往聯絡人</button></section>;
 if(!authorized)return <section className="chat-loading"><h2 tabIndex={-1}>正在確認對話</h2><p role="status">{snapshot.connection==='blocked'?'聊天已停止，請重新載入。':'正在取得目前的對話權限…'}</p>{(error||snapshot.error)&&<p role="alert">{error??snapshot.error}</p>}<button type="button" onClick={()=>onNavigate('/chats')}>返回聊天清單</button></section>;
 const title=detail.type==='group'?detail.title:detail.members.filter(member=>member.user_id!==me).map(member=>names[member.user_id]??member.user_id).join('、');
 return <section ref={root} className="chat-room" aria-labelledby="chat-title"><header className="chat-header" data-read-occlusion><div><p className="eyebrow">{detail.type==='group'?'GROUP CONVERSATION':'DIRECT CONVERSATION'}</p><h1 ref={heading} id="chat-title" tabIndex={-1}>{title??'對話'}</h1><small role="status">{CONNECTION_LABEL[snapshot.connection]}</small></div>{detail.type==='group'&&<button ref={groupInfoButton} type="button" aria-haspopup="dialog" aria-controls="group-info-dialog" aria-expanded={groupInfoOpen} onClick={() => { void openGroupInfo(); }}>群組資訊</button>}</header>{<>{(error || snapshot.error) && <div className="chat-notice notice error" role="alert" data-read-occlusion>{error ?? snapshot.error}</div>}<>{groupInfoOpen && detail.type === 'group' && <GroupInfoDialog detail={detail} names={names} onClose={closeGroupInfo} returnFocus={restoreGroupInfoFocus} onManage={() => { setGroupInfoOpen(false); onNavigate(`/groups/${encodeURIComponent(conversationId)}/manage`); }} />}<AttachmentRecovery transfer={transfer} onRetry={() => { void chat.retryAttachment(conversationId).catch(() => setError(chat.getAttachmentTransfer(conversationId)?.error ?? '原附件嘗試尚未完成。')); }} /></>{pausedReceipts && <div className="chat-notice notice" role="status" data-read-occlusion><p>回條操作遭限速，已停止自動重試；已知等待截止仍會保留。</p><button type="button" onClick={() => { void chat.retryReceipts(conversationId).catch(() => setError('回條操作尚未重試。')); }}>手動重試回條</button></div>}{quarantined.length > 0 && <div className="chat-notice notice" role="status" data-read-occlusion><p>先前成員資格的傳送意圖保留原內容與識別碼，但不顯示舊本文。可在目前權限下核對原結果。</p>{quarantined.map(intent => <button type="button" key={intent.clientMessageId} disabled={snapshot.connection !== 'ready' || intent.retryAt !== null && intent.retryAt > Date.now()} onClick={() => { void chat.retryIntent(intent.clientMessageId).catch(() => setError('保留的原傳送意圖尚未核對。')); }}>以原意圖核對</button>)}</div>}</>}<div ref={scroller} className="message-scroller" role="region" aria-label="訊息對話串" tabIndex={0} onScroll={()=>captureAnchor()}><div className="history-control">{snapshot.historyMore[conversationId]!==false&&<button type="button" disabled={loadingHistory} onClick={()=>{void historyPage();}}>{loadingHistory?'正在載入…':'載入較早訊息'}</button>}<button type="button" className="jump-latest" disabled={loadingHistory} onClick={() => { void latest(); }}>跳至最新</button></div>{!messages.length&&!pending.length&&<p className="chat-start muted">這裡還沒有訊息。傳送第一則訊息開始對話。</p>}<ol className="message-list">{messages.map(message=>{const own=message.sender_id===me;return <li key={message.id} className={`message-row ${own?'own':'peer'}`}><article className="message-bubble" data-message-id={message.id} data-read-eligible={!own&&snapshot.receipts[message.id]?.desired!=='read'?'true':'false'} aria-label={`${own?'你':names[message.sender_id]??message.sender_id}的訊息`}>{detail.type==='group'&&!own&&<strong className="message-sender">{names[message.sender_id]??message.sender_id}</strong>}{message.type==='text'?<p className="message-text">{message.text}</p>:<AttachmentTile session={session} attachmentId={message.attachment_id} kind={message.type} onPreview={setPreview}/>}<footer className="message-meta"><time dateTime={message.created_at}>{new Intl.DateTimeFormat('zh-TW',{hour:'2-digit',minute:'2-digit'}).format(new Date(message.created_at))}</time>{own&&<span>{detail.type==='direct'&&message.receipt?message.receipt.status==='read'?'已讀':'已送達':'已持久保存'}</span>}</footer></article></li>;})}{pending.map(intent=><li key={intent.clientMessageId} className="message-row own"><article className={`message-bubble pending-message ${intent.status==='rejected'?'rejected-message':''}`} aria-label="你的待確認訊息">{intent.payload.type==='text'?<p className="message-text">{intent.payload.text}</p>:<p>{intent.payload.type==='image'?'圖片附件':'PDF 附件'} · 已核驗</p>}<footer className="message-meta"><span>{intent.status==='persisted'?'已持久保存，正在核對訊息':intent.status==='rejected'?'未傳送':intent.status==='unknown'?'結果尚未確認':'等待傳送'}</span></footer>{intent.error&&<p className="intent-error">{intent.error==='RATE_LIMITED'?'傳送速度受限，請等待後重試。':intent.error==='FORBIDDEN'?'對話權限已變更。':'此傳送意圖尚未完成，原內容及識別碼已保留。'}</p>}{intent.status!=='persisted'&&<button type="button" disabled={snapshot.connection!=='ready'||intent.retryAt!==null&&intent.retryAt>Date.now()} onClick={()=>{void chat.retryIntent(intent.clientMessageId).catch(()=>setError('原傳送意圖尚未重試。'));}}>以原意圖重試</button>}</article></li>)}</ol></div>{newCount>0&&<div className="new-message-prompt" role="status" data-read-occlusion><span>{newCount} 則新訊息 · 不代表未讀數</span><button type="button" onClick={latest}>跳至最新</button></div>}<form className="chat-composer" onSubmit={event=>{void submit(event);}} data-read-occlusion><label htmlFor="chat-draft">撰寫訊息</label><div className="composer-controls"><button type="button" className="attachment-button" disabled={uploading||snapshot.connection==='blocked'} onClick={()=>fileInput.current?.click()} aria-label="選取 JPEG、PNG 或 PDF 附件">＋</button><input ref={fileInput} className="visually-hidden" type="file" accept="image/jpeg,image/png,application/pdf" aria-label="選取附件，最大 10 MiB" onChange={event=>{const file=event.target.files?.[0];if(!file)return;void finishUpload(()=>uploadAttachment(session,file,'conversation',conversationId),conversationId);}}/><textarea ref={composer} id="chat-draft" placeholder="輸入訊息…" value={draft} rows={1} aria-describedby="composer-help" disabled={snapshot.connection==='blocked'} onChange={event=>{const text=event.target.value;setDraft(text);void chat.setDraft(conversationId,text).catch(()=>setError('草稿無法持久保存，聊天已停止。'));}} onCompositionStart={()=>{composition.current=true;}} onCompositionEnd={()=>{composition.current=false;}} onKeyDown={event=>{if(composition.current||event.nativeEvent.isComposing||event.keyCode===229)return;if(shouldSubmitEnter({key:event.key,isComposing:event.nativeEvent.isComposing,keyCode:event.keyCode,shiftKey:event.shiftKey,ctrlKey:event.ctrlKey,metaKey:event.metaKey},hardwareKeyboardAvailable())){event.preventDefault();void submit();}}}/><button className="primary send-button" type="submit" disabled={sending||draft.length===0||snapshot.connection==='blocked'}>{sending?'保存中…':'傳送'}</button></div><div className="composer-help" id="composer-help"><span>{uploading?'正在上傳與核驗附件；未就緒不傳送。':'Ctrl / ⌘ + Enter 傳送；組字中不會送出。'}</span><span>{[...draft].length} / 4096</span></div></form>{preview&&<AttachmentViewer session={session} attachmentId={preview} onClose={closePreview}/>}</section>;
}
export default Chat;
