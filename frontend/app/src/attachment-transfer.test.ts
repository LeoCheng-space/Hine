import { expect, test } from 'bun:test';
import { AttachmentTransferError, canResumeUpload, uploadAttachment, validateUploadGrant } from './attachment-transfer';
import type { SessionController } from './session';
const grant={attachment_id:'a',upload_attempt_id:'attempt',upload_url:'https://storage.googleapis.com/private/object?X-Goog-SignedHeaders=cache-control%3Bcontent-type%3Bhost%3Bx-goog-if-generation-match',expires_at:'2099-01-01T00:00:00Z',required_headers:{'Content-Type':'image/png','x-goog-if-generation-match':'0','Cache-Control':'no-transform'}};
test('requires signed immutable generation and no-transform headers',()=>{
 expect(()=>validateUploadGrant({...grant,required_headers:{'Content-Type':'image/png'}},'image/png')).toThrow();
 expect(()=>validateUploadGrant({...grant,required_headers:{...grant.required_headers,'x-goog-if-generation-match':'1'}},'image/png')).toThrow();
});
test('refuses credentials injected by grant and mismatched MIME',()=>{
 expect(()=>validateUploadGrant({...grant,required_headers:{...grant.required_headers,Authorization:'Bearer token'}},'image/png')).toThrow();
 expect(()=>validateUploadGrant(grant,'application/pdf')).toThrow();
});
test('preserves exact signed header values for a valid immutable grant',()=>{
 expect(validateUploadGrant(grant,'image/png').required_headers).toEqual({'Content-Type':'image/png','x-goog-if-generation-match':'0','Cache-Control':'no-transform'});
});
test('same owner and device refresh can resume but another account or device cannot',()=>{
 const owner={user_id:'me',device_id:'device'};
 const refreshed={state:'authenticated' as const,user_id:'me',device_id:'device',access_token:'new access token',expires_at:'2099-01-01T00:00:00Z',session_generation:7};
 expect(canResumeUpload(refreshed,owner)).toBe(true);
 expect(canResumeUpload({...refreshed,user_id:'other'},owner)).toBe(false);
 expect(canResumeUpload({...refreshed,device_id:'other'},owner)).toBe(false);
 expect(canResumeUpload({state:'refreshing',user_id:'me',device_id:'device',access_token:null,expires_at:null,session_generation:7},owner)).toBe(false);
});

test('a refused PUT can retry the original immutable upload after A21 confirms absence', async () => {
 const file = new File([Uint8Array.from([137, 80, 78, 71])], 'tiny.png', { type: 'image/png' });
 const sha256 = new Bun.CryptoHasher('sha256').update(await file.arrayBuffer()).digest('hex');
 const context = { state: 'authenticated', user_id: 'me', device_id: 'device', expires_at: '2099-01-01T00:00:00Z' };
 const sequence: string[] = [];
 let present = false, grants = 0;
 const session = {
  getSnapshot: () => ({ context }),
  async request(path: string, options: { json?: Record<string, unknown> }) {
   if (path === '/uploads') { grants++; return { data: grant }; }
   expect(path).toBe('/uploads/a/complete');
   expect(options.json?.upload_attempt_id).toBe('attempt');
   sequence.push(present ? 'complete:ready' : 'complete:absent');
   if (!present) throw Object.assign(new Error('object absent'), { code: 'UPLOAD_NOT_READY' });
   return { data: { id: 'a', scope: 'avatar', uploader_id: 'me', kind: 'image', filename: file.name, content_type: file.type, size_bytes: file.size, sha256, state: 'ready', created_at: '2026-10-06T00:00:00Z', conversation_id: null } };
  },
 } as unknown as SessionController;
 const originalFetch = globalThis.fetch;
 const puts: { url: string; headers: Headers; bytes: Uint8Array }[] = [];
 globalThis.fetch = (async (url: string | URL | Request, options?: RequestInit) => {
  expect(options?.method).toBe('PUT');
  const bytes = new Uint8Array(await (options?.body as File).arrayBuffer());
  puts.push({ url: String(url), headers: new Headers(options?.headers), bytes });
  if (puts.length === 1) { sequence.push('put:503'); return new Response(null, { status: 503 }); }
  expect(puts[1]).toEqual(puts[0]);
  present = true; sequence.push('put:200');
  return new Response(null, { status: 200 });
 }) as typeof fetch;
 try {
  const error = await uploadAttachment(session, file, 'avatar', null).catch(error => error);
  expect(error).toBeInstanceOf(AttachmentTransferError);
  expect(error.code).toBe('UPLOAD_NOT_READY');
  expect(error.retryable).toBe(true);
  const ready = await error.retry();
  expect(ready.state).toBe('ready');
  expect(sequence).toEqual(['put:503', 'complete:absent', 'put:200', 'complete:ready']);
  expect(grants).toBe(1);
  expect(puts[1].headers.get('x-goog-if-generation-match')).toBe('0');
 } finally { globalThis.fetch = originalFetch; }
});
