import { expect, test } from 'bun:test';
import { GROUP_OTHER_MEMBER_LIMIT, addMember, removeMember } from './group-selection';

test('adding ignores self and duplicates and keeps insertion order', () => {
  let selected: string[] = [];
  expect(addMember(selected, 'me', 'me').result).toBe('self');
  ({ selected } = addMember(selected, 'a', 'me'));
  expect(addMember(selected, 'a', 'me').result).toBe('duplicate');
  ({ selected } = addMember(selected, 'b', 'me'));
  expect(selected).toEqual(['a', 'b']);
});
test('selection stops at forty-nine other members and frees a slot on removal', () => {
  let selected: string[] = [];
  for (let i = 0; i < GROUP_OTHER_MEMBER_LIMIT; i++) ({ selected } = addMember(selected, `u${i}`, 'me'));
  expect(addMember(selected, 'extra', 'me').result).toBe('full');
  selected = removeMember(selected, 'u0');
  expect(addMember(selected, 'extra', 'me').result).toBe('added');
});
test('adding returns a new array so React state updates', () => {
  const before = ['a'];
  const { selected } = addMember(before, 'b', 'me');
  expect(selected).not.toBe(before);
  expect(before).toEqual(['a']);
});
