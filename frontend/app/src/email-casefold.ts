import { FULL_CASEFOLD } from './email-casefold-data';

// Match Python 3.12 email.casefold() exactly, independent of the browser's Unicode
// version. In particular, preserve expansions and Cherokee's uppercase fold;
// unchanged codepoints must not fall back to JavaScript lowercase/normalization.
export function emailCasefold(value: string): string {
  let folded = '';
  for (const character of value) folded += FULL_CASEFOLD[character] ?? character;
  return folded;
}
