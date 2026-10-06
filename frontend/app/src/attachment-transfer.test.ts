import { expect, test } from 'bun:test';
import { canResumeUpload, validateUploadGrant } from './attachment-transfer';
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
