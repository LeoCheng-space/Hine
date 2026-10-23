// Issue #17: browser entry that exposes the frontend's native chat-list review scenarios to browser acceptance.
// It is built after the production bundle (so it is not part of production asset provenance), served from
// /review-shell/ on the same owned HTTPS origin, and driven by tests/browser/browser_acceptance.py.
import {
  SessionController,
  nativeShellCases,
  nativeShellDiagnostic,
  runNativeCasefoldDevicePartition,
  runNativeChatListBurstRace,
  runNativeChatListChanges,
  runNativeChatListOwnerRace,
  runNativeChatListPaging,
  verifyNativeDeviceIdentityAfterReload,
} from '../../frontend/app/tests/review-shell-native';

declare global {
  interface Window { hineReviewShell: unknown }
}

window.hineReviewShell = Object.freeze({
  SessionController,
  nativeShellCases,
  nativeShellDiagnostic,
  runNativeCasefoldDevicePartition,
  runNativeChatListBurstRace,
  runNativeChatListChanges,
  runNativeChatListOwnerRace,
  runNativeChatListPaging,
  verifyNativeDeviceIdentityAfterReload,
});
