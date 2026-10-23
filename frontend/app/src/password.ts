// SEC-01 registration password policy. Mirrors password_acceptable in backend/api/src/hine_api/auth.py; the API
// remains the authority and answers INVALID_ARGUMENT for anything this check misses.
export function passwordProblems(password: string, email: string): string[] {
  const characters = Array.from(password);
  const problems: string[] = [];
  if (characters.length < 8) problems.push('密碼至少 8 個字元。');
  if (characters.length > 128) problems.push('密碼最多 128 個字元。');
  if (characters.some(character => /\p{Cc}/u.test(character))) problems.push('密碼不能包含控制字元。');
  const classes = new Set(characters.map(c => (c >= 'A' && c <= 'Z' ? 'upper' : c >= 'a' && c <= 'z' ? 'lower' : c >= '0' && c <= '9' ? 'digit' : 'symbol')));
  if (classes.size < 2) problems.push('需包含大寫字母、小寫字母、數字、符號（含空格）其中至少 2 種。');
  const lowered = Array.from(password.toLowerCase());
  const account = email.slice(0, Math.max(0, email.lastIndexOf('@'))).toLowerCase();
  if (Array.from(account).length >= 3 && lowered.join('').includes(account)) problems.push('不能包含電子郵件 @ 前面的帳號名稱。');
  for (let start = 0; start + 4 <= lowered.length; start++) {
    const run = lowered.slice(start, start + 4);
    const steps = new Set(run.slice(1).map((character, index) => character.codePointAt(0)! - run[index].codePointAt(0)!));
    const sameKind = run.every(c => c >= '0' && c <= '9') || run.every(c => c >= 'a' && c <= 'z');
    if ((steps.size === 1 && steps.has(0)) || (steps.size === 1 && (steps.has(1) || steps.has(-1)) && sameKind)) {
      problems.push('不能包含 4 個以上連續或重複的字元（例如 aaaa、1234、abcd）。');
      break;
    }
  }
  return problems;
}
