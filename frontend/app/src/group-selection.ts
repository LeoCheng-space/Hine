import type { GroupCreatePayload } from './GroupsPage';

/** A group holds at most 50 members including the creator. */
export const GROUP_OTHER_MEMBER_LIMIT = 49;
export type AddResult = 'added' | 'duplicate' | 'self' | 'full';

/** Pure selection step on an immutable list so React state always receives a new array. */
export function addMember(selected: readonly string[], id: string, self: string): { selected: string[]; result: AddResult } {
  if (id === self) return { selected: [...selected], result: 'self' };
  if (selected.includes(id)) return { selected: [...selected], result: 'duplicate' };
  if (selected.length >= GROUP_OTHER_MEMBER_LIMIT) return { selected: [...selected], result: 'full' };
  return { selected: [...selected, id], result: 'added' };
}
export function removeMember(selected: readonly string[], id: string): string[] { return selected.filter(item => item !== id); }
export function groupPayload(title: string, selected: readonly string[]): GroupCreatePayload { return { title, member_ids: [...selected] }; }
