import type { ThemeName } from '../theme';

export function navPillClass(theme: ThemeName, active = false): string {
  if (theme === 'folder') {
    return active ? 'tab tab-ghost tab-active' : 'tab tab-ghost';
  }
  return active
    ? 'rounded-full border border-mint bg-mint px-3 py-2 text-sm font-medium text-white transition'
    : 'rounded-full border border-[#ead8c6] bg-[#fffdf8] px-3 py-2 text-sm font-medium text-[#241c15] transition hover:bg-[#fff5e9]';
}

export function userChipClass(theme: ThemeName): string {
  return theme === 'folder'
    ? 'tab user-chip'
    : 'flex items-center gap-3 rounded-full border border-[#ead8c6] bg-[#fffdf8] px-4 py-2 ml-2';
}
