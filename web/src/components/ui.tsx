import { useMemo, useState, type CSSProperties, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { Club, ClubIndex } from '../lib/data';
import { clubColors, clubStyle } from '../lib/color';
import { initials } from '../lib/format';

const HEX = (r: number) =>
  Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 3) * i - Math.PI / 2;
    return `${50 + r * Math.cos(a)},${50 + r * Math.sin(a)}`;
  }).join(' ');

/** Club crest in a hexagon frame in the club's colours; a monogram when there is no crest. */
export function Badge({ club, size = 28, glow = false }: { club?: Club; size?: number; glow?: boolean }) {
  const [broken, setBroken] = useState(false);
  const { accent, second } = clubColors(club);
  const showImg = club?.logo && !broken;
  return (
    <span className="badge" style={{ width: size, height: size * 1.1 }} title={club?.name}>
      <svg viewBox="0 0 100 100" width={size} height={size * 1.1} preserveAspectRatio="none"
           style={glow ? { filter: `drop-shadow(0 0 6px ${accent})` } : undefined}>
        <polygon points={HEX(48)} fill={showImg ? '#0b1426' : accent} fillOpacity={showImg ? 0.9 : 0.9} stroke={accent} strokeWidth={4} />
        {!showImg && <polygon points={HEX(36)} fill="none" stroke={second} strokeOpacity={0.5} strokeWidth={2} />}
        {!showImg && club && (
          <text x="50" y="58" textAnchor="middle" fontFamily="Rajdhani, sans-serif" fontWeight={700}
                fontSize={initials(club.name).length > 1 ? 30 : 36} fill={second === accent ? '#03101c' : second}>{initials(club.name)}</text>
        )}
      </svg>
      {showImg && <img src={club!.logo!} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)} />}
    </span>
  );
}

/** Crest + name, linked to the club page when there is one. */
export function ClubName({ club, size = 22 }: { club?: Club; size?: number }) {
  if (!club) return <span className="muted">—</span>;
  const inner = <span className="clubcell"><Badge club={club} size={size} />{club.name}</span>;
  return club.has_page ? <Link to={`/club/${club.slug}`} style={{ color: 'inherit' }}>{inner}</Link> : inner;
}

export function Card({ title, note, children, club, style }: { title?: ReactNode; note?: ReactNode; children: ReactNode; club?: Club; style?: CSSProperties }) {
  return (
    <section className="card" style={{ ...(club ? clubStyle(club) : {}), ...style }}>
      <div className="card-in">
        {title && <h2>{title}</h2>}
        {note && <p className="note">{note}</p>}
        {children}
      </div>
    </section>
  );
}

export function Status({ error }: { error?: string }) {
  return <div className={'status' + (error ? ' err' : '')}>{error ? `Could not load data — ${error}` : 'Loading…'}</div>;
}

export function Seg<T extends string | number>({ value, options, onChange, label }:
  { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={String(v)} type="button" aria-pressed={v === value} onClick={() => onChange(v)}>{text}</button>
      ))}
    </div>
  );
}

/** Text input with suggestions from the clubs that have pages. */
export function ClubPicker({ clubs, onPick, placeholder = 'Choose a club', value, id }:
  { clubs: ClubIndex; onPick: (c: Club) => void; placeholder?: string; value?: string; id: string }) {
  const [text, setText] = useState(value ?? '');
  const commit = (v: string) => {
    const c = clubs.byName.get(v);
    if (c && c.has_page) { onPick(c); if (value === undefined) setText(''); }
  };
  return (
    <input className="input" id={id} list="clubs-list" placeholder={placeholder} value={text} autoComplete="off"
           aria-label={placeholder}
           onChange={(e) => { setText(e.target.value); commit(e.target.value); }}
           onKeyDown={(e) => { if (e.key === 'Enter') commit(text); }} />
  );
}

/** The suggestion list every ClubPicker uses; rendered once by the app shell. */
export function ClubDatalist({ clubs }: { clubs: ClubIndex }) {
  const opts = useMemo(() => clubs.pages.map((c) => <option key={c.id} value={c.name} />), [clubs]);
  return <datalist id="clubs-list">{opts}</datalist>;
}

export type Col<T> = { key: string; label: string; num?: boolean; hideSm?: boolean; render?: (r: T) => ReactNode; sort?: (r: T) => number | string | null };

/** Sortable table. */
export function Table<T>({ rows, cols, initial, limit, rowKey }:
  { rows: T[]; cols: Col<T>[]; initial?: [string, 'asc' | 'desc']; limit?: number; rowKey: (r: T, i: number) => string | number }) {
  const [sort, setSort] = useState<[string, 'asc' | 'desc'] | undefined>(initial);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = cols.find((c) => c.key === sort[0]);
    const get = col?.sort ?? ((r: T) => (r as Record<string, unknown>)[sort[0]] as number | string | null);
    const dir = sort[1] === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = get(a), y = get(b);
      if (x == null) return 1; if (y == null) return -1;
      return (x < y ? -1 : x > y ? 1 : 0) * dir;
    });
  }, [rows, sort, cols]);
  const shown = limit ? sorted.slice(0, limit) : sorted;
  return (
    <div className="tablewrap">
      <table className="t">
        <thead><tr>{cols.map((c) => (
          <th key={c.key} className={(c.num ? 'num ' : '') + (c.hideSm ? 'hide-sm' : '')}
              aria-sort={sort?.[0] === c.key ? (sort[1] === 'asc' ? 'ascending' : 'descending') : undefined}
              onClick={() => setSort(sort?.[0] === c.key ? [c.key, sort[1] === 'asc' ? 'desc' : 'asc'] : [c.key, c.num ? 'desc' : 'asc'])}>
            {c.label}</th>))}</tr></thead>
        <tbody>{shown.map((r, i) => (
          <tr key={rowKey(r, i)}>{cols.map((c) => (
            <td key={c.key} className={(c.num ? 'num ' : '') + (c.hideSm ? 'hide-sm' : '')}>
              {c.render ? c.render(r) : String((r as Record<string, unknown>)[c.key] ?? '—')}</td>))}</tr>))}
        </tbody>
      </table>
    </div>
  );
}

/** Circular gauge in the style of the HUD: value against a min-max range. */
export function Ring({ value, min = 1300, max = 2200, label, sub, size = 260, color = 'var(--club)' }:
  { value: number; min?: number; max?: number; label: string; sub?: string; size?: number; color?: string }) {
  const f = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const R = 40, C = 2 * Math.PI * R;
  const ticks = Array.from({ length: 60 }, (_, i) => i);
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} role="img" aria-label={`${label}: ${Math.round(value)}`} style={{ maxWidth: '100%', height: 'auto' }}>
      <defs>
        <radialGradient id="rg-core"><stop offset="0" stopColor={color} stopOpacity=".55" /><stop offset=".55" stopColor={color} stopOpacity=".06" /><stop offset="1" stopColor={color} stopOpacity="0" /></radialGradient>
      </defs>
      <polygon points={HEX(49)} fill="none" stroke="rgba(63,208,255,.25)" strokeWidth=".4" />
      <circle cx="50" cy="50" r="30" fill="url(#rg-core)" />
      <g className="ring-spin">{ticks.map((i) => (
        <line key={i} x1="50" y1="3.5" x2="50" y2={i % 5 ? 5 : 6.5} stroke={color} strokeOpacity={i % 5 ? .35 : .8} strokeWidth=".5" transform={`rotate(${i * 6} 50 50)`} />))}
      </g>
      <circle className="ring-spin rev" cx="50" cy="50" r="45" fill="none" stroke={color} strokeOpacity=".35" strokeWidth=".4" strokeDasharray="1 2.2" />
      <circle cx="50" cy="50" r={R} fill="none" stroke="rgba(63,208,255,.12)" strokeWidth="3" />
      <circle cx="50" cy="50" r={R} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round"
              strokeDasharray={`${C * f} ${C}`} transform="rotate(-90 50 50)" style={{ filter: `drop-shadow(0 0 2px ${color})` }} />
      <text x="50" y="50" textAnchor="middle" fill="#f1f8ff" fontFamily="Rajdhani, sans-serif" fontWeight="700" fontSize="15">{Math.round(value)}</text>
      <text x="50" y="59" textAnchor="middle" fill="#7d8fa9" fontFamily="Rajdhani, sans-serif" fontSize="4.6" letterSpacing=".6">{label.toUpperCase()}</text>
      {sub && <text x="50" y="65" textAnchor="middle" fill={color} fontFamily="Rajdhani, sans-serif" fontSize="4.2" letterSpacing=".4">{sub}</text>}
    </svg>
  );
}
