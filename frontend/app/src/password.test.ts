import { describe, expect, test } from 'bun:test';
import { passwordProblems } from './password';

// Same vectors as tests/product/test_auth.py: the register page must refuse exactly what A01 refuses (SEC-01).
const email = 'pwa1b2c3d4@product.test';
describe('registration password policy', () => {
  test('each weak password names the rule it breaks', () => {
    const cases: [string, string][] = [
      ['Zx9-qpr', '至少 8 個字元'],
      ['Zx9-'.repeat(32) + 'Q', '最多 128 個字元'],
      ['qwertyzxcvpo', '至少 2 種'],
      ['Zx9-pwa1b2c3d4-q', '電子郵件 @ 前面的帳號名稱'],
      ['Zx9-PWA1B2C3D4-q', '電子郵件 @ 前面的帳號名稱'],
      ['Zx9-aaaa-qp', '連續或重複'],
      ['Zx9-AaAa-qp', '連續或重複'],
      ['Zx9-1234-qp', '連續或重複'],
      ['Zx9-dcba-qp', '連續或重複'],
      ['Zx9-qp\u0007rt', '控制字元'],
    ];
    for (const [password, rule] of cases) {
      const problems = passwordProblems(password, email);
      expect(problems.some(problem => problem.includes(rule))).toBe(true);
    }
  });
  test('boundary, passphrase, three-character runs and non-ASCII passwords are accepted', () => {
    for (const password of ['Zx9-qprt', 'Zx9-'.repeat(32), 'correct horse battery staple', 'abc1abc1', '密碼很長很安全ok']) {
      expect(passwordProblems(password, email)).toEqual([]);
    }
  });
  test('length counts characters, not UTF-16 units, and short account names are not matched', () => {
    expect(passwordProblems('😀😀😀😀abcd', email)).toEqual(['不能包含 4 個以上連續或重複的字元（例如 aaaa、1234、abcd）。']);
    expect(passwordProblems('😀😁😂🤣😃😄😅a', email)).toEqual([]);
    expect(passwordProblems('ab-Zx9-qp', 'ab@product.test')).toEqual([]);
  });
});
