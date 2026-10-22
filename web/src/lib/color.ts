// Club colours on a dark background: pick a shade that reads, and keep
// several clubs on one chart apart from each other.
import type { CSSProperties } from 'react';
import type { Club } from './data';

const BG = [7, 11, 20];
const FALLBACK = ['#3fd0ff', '#ffd166', '#ff6b6b', '#4ade80', '#a78bfa', '#fb923c', '#f472b6', '#e2e8f0'];

const rgb = (hex: string) => {
  const h = hex.replace('#', '');
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
};
const toHex = (c: number[]) => '#' + c.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('');
const lum = (c: number[]) => {
  const [r, g, b] = c.map((v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a: number[], b: number[]) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const mix = (a: number[], b: number[], t: number) => a.map((v, i) => v + (b[i] - v) * t);
const dist = (a: number[], b: number[]) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

/** A readable version of a colour on the dark background (lightened if needed). */
export function readable(hex: string | null | undefined): string | null {
  if (!hex || !/^#?[0-9a-f]{6}$/i.test(hex)) return null;
  let c = rgb(hex);
  for (let i = 0; i < 6 && contrast(c, BG) < 3.2; i++) c = mix(c, [255, 255, 255], 0.22);
  return toHex(c);
}

/** The club's accent and second colour for the dark theme. */
export function clubColors(club: Pick<Club, 'primary' | 'secondary'> | undefined) {
  const p = club?.primary, s = club?.secondary;
  // a black or white primary reads as "no colour": lead with the secondary instead
  const plain = (h?: string | null) => !h || /^#?(000000|ffffff|111111|fefefe)$/i.test(h);
  const [a, b] = plain(p) && !plain(s) ? [s, p] : [p, s];
  const accent = readable(a) ?? '#3fd0ff';
  const second = readable(b) ?? '#e2e8f0';
  return { accent, second, raw: a ?? null };
}

/** One distinct line colour per club, preferring each club's own colours. */
export function seriesColors(clubs: (Club | undefined)[]): string[] {
  const out: string[] = [];
  clubs.forEach((c, i) => {
    const { accent, second } = clubColors(c);
    const free = (h: string) => out.every((o) => dist(rgb(o), rgb(h)) > 90);
    const pick = [accent, second].find(free) ?? FALLBACK.find((f) => free(f)) ?? FALLBACK[i % FALLBACK.length];
    out.push(pick);
  });
  return out;
}

export function clubStyle(club: Club | undefined): CSSProperties {
  const { accent, second } = clubColors(club);
  return { ['--club' as string]: accent, ['--club-2' as string]: second };
}
