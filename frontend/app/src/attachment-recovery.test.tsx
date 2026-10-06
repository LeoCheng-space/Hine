import { expect, test } from 'bun:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { AttachmentRecovery } from './AttachmentViewer';
const retry=():void=>{throw new Error('render must not execute a transfer');};
test('waiting original-attempt recovery renders without any unrelated chat error',()=>{
 const html=renderToStaticMarkup(<AttachmentRecovery transfer={{phase:'waiting',error:null,retryable:true}} onRetry={retry}/>);
 expect(html).toContain('核對原上傳嘗試');expect(html).toContain('<button');expect(html).not.toContain('disabled');
});
test('ready-stage recovery remains available without repeating A20 or A21',()=>{
 const html=renderToStaticMarkup(<AttachmentRecovery transfer={{phase:'ready',error:null,retryable:true}} onRetry={retry}/>);
 expect(html).toContain('傳送已核驗附件');expect(html).toContain('<button');
});
test('active upload has status but cannot start a second transfer',()=>{
 const html=renderToStaticMarkup(<AttachmentRecovery transfer={{phase:'uploading',error:null,retryable:false}} onRetry={retry}/>);
 expect(html).toContain('正在上傳');expect(html).not.toContain('<button');
});
