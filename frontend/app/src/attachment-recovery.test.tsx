import { expect, test } from 'bun:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { AttachmentRecovery } from './AttachmentViewer';
const retry=():void=>{throw new Error('render must not execute a transfer');};
const storageDown='附件儲存服務目前無法使用，請稍後再試；若持續發生，請聯絡管理員確認儲存服務設定。尚未傳送訊息。';
test('waiting original-attempt recovery renders without any unrelated chat error',()=>{
 const html=renderToStaticMarkup(<AttachmentRecovery transfer={{phase:'waiting',error:null,retryable:true,attemptCreated:true}} onRetry={retry}/>);
 expect(html).toContain('原本的附件上傳尚未完成');expect(html).toContain('重新確認原上傳');expect(html).toContain('<button');expect(html).not.toContain('disabled');
});
test('an upload refused before any attempt exists states the cause once and offers a fresh upload',()=>{
 const html=renderToStaticMarkup(<AttachmentRecovery transfer={{phase:'waiting',error:storageDown,retryable:true,attemptCreated:false}} onRetry={retry}/>);
 expect(html).not.toContain('原本的附件上傳');expect(html).not.toContain('重新確認原上傳');
 expect(html.split(storageDown).length-1).toBe(1);
 expect(html).toContain('重新上傳');
});
test('ready-stage recovery remains available without repeating A20 or A21',()=>{
 const html=renderToStaticMarkup(<AttachmentRecovery transfer={{phase:'ready',error:null,retryable:true,attemptCreated:true}} onRetry={retry}/>);
 expect(html).toContain('傳送已檢查的附件');expect(html).toContain('<button');
});
test('active upload has status but cannot start a second transfer',()=>{
 const html=renderToStaticMarkup(<AttachmentRecovery transfer={{phase:'uploading',error:null,retryable:false,attemptCreated:false}} onRetry={retry}/>);
 expect(html).toContain('正在上傳');expect(html).not.toContain('<button');
});
