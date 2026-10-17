import { expect, test } from 'bun:test';
import { AttachmentTransferError } from './attachment-transfer';
import { AvatarSaveRecovery } from './ProfilePage';
import type { AttachmentView } from './types';

const file = new File([Uint8Array.from([137, 80, 78, 71])], 'avatar.png', { type: 'image/png' });
const neverRetried = (): Promise<AttachmentView> => { throw new Error('the test must not run the retry'); };

test('a refusal before any upload attempt exists does not claim an original attempt was kept', async () => {
 const recovery = new AvatarSaveRecovery();
 recovery.select(file);
 const refusal = new AttachmentTransferError('DEPENDENCY_UNAVAILABLE', true, neverRetried, { scope: 'avatar', attemptCreated: false });
 await recovery.attachment(() => Promise.reject(refusal)).catch(() => undefined);
 expect(recovery.retry).not.toBeNull();
 expect(recovery.getSnapshot().attemptRetained).toBe(false);
});

test('a failure after the upload attempt was created keeps the original-attempt notice', async () => {
 const recovery = new AvatarSaveRecovery();
 recovery.select(file);
 const pending = new AttachmentTransferError('UPLOAD_NOT_READY', true, neverRetried, { scope: 'avatar', attemptCreated: true });
 await recovery.attachment(() => Promise.reject(pending)).catch(() => undefined);
 expect(recovery.getSnapshot().attemptRetained).toBe(true);
 recovery.select(null);
 expect(recovery.getSnapshot().attemptRetained).toBe(false);
});
