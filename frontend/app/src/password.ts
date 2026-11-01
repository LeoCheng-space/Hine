// SEC-01 registration password policy. Mirrors password_acceptable in backend/api/src/hine_api/auth.py; the API
// remains the authority and answers INVALID_ARGUMENT for anything this check misses.

/** Each flag is a violation of one rule; the register form shows them as a live checklist. */
export interface PasswordViolations { tooShort: boolean; tooLong: boolean; control: boolean; fewClasses: boolean; containsAccount: boolean; run: boolean }

export function passwordViolations(password: string, email: string): PasswordViolations {
  const characters = Array.from(password);
  const classes = new Set(characters.map(c => (c >= 'A' && c <= 'Z' ? 'upper' : c >= 'a' && c <= 'z' ? 'lower' : c >= '0' && c <= '9' ? 'digit' : 'symbol')));
  const lowered = Array.from(password.toLowerCase());
  const account = email.slice(0, Math.max(0, email.lastIndexOf('@'))).toLowerCase();
  let run = false;
  for (let start = 0; start + 4 <= lowered.length && !run; start++) {
    const chunk = lowered.slice(start, start + 4);
    const steps = new Set(chunk.slice(1).map((character, index) => character.codePointAt(0)! - chunk[index].codePointAt(0)!));
    const sameKind = chunk.every(c => c >= '0' && c <= '9') || chunk.every(c => c >= 'a' && c <= 'z');
    run = (steps.size === 1 && steps.has(0)) || (steps.size === 1 && (steps.has(1) || steps.has(-1)) && sameKind);
  }
  return {
    tooShort: characters.length < 8,
    tooLong: characters.length > 128,
    control: characters.some(character => /\p{Cc}/u.test(character)),
    fewClasses: classes.size < 2,
    containsAccount: Array.from(account).length >= 3 && lowered.join('').includes(account),
    run,
  };
}

export function passwordProblems(password: string, email: string): string[] {
  const violations = passwordViolations(password, email);
  const problems: string[] = [];
  if (violations.tooShort) problems.push('密碼至少 8 個字元。');
  if (violations.tooLong) problems.push('密碼最多 128 個字元。');
  if (violations.control) problems.push('密碼不能包含控制字元。');
  if (violations.fewClasses) problems.push('需包含大寫字母、小寫字母、數字、符號（含空格）其中至少 2 種。');
  if (violations.containsAccount) problems.push('不能包含電子郵件 @ 前面的帳號名稱。');
  if (violations.run) problems.push('不能包含 4 個以上連續或重複的字元（例如 aaaa、1234、abcd）。');
  return problems;
}
