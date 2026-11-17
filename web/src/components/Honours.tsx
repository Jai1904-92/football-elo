// Honours strip for the world top 100: league place, main cup, league cup, best European run.
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import type { ClubIndex } from '../lib/data';
import { seasonLabel } from '../lib/format';

export type Stage = 'W' | 'F' | 'SF' | 'QF' | 'R16' | 'in' | 'out';
export type Run = [comp: string, stage: Stage, by: number | null];
/** competition, tier, place, clubs, played, won, drawn, lost, for, against, points */
export type League = [string, number, number, number, number, number, number, number, number, number, number];
/** A run, '-' (not in the rounds we hold), null (no data for that cup season) or 'na' (the country has no league cup). */
/** ... 'early' (missing from a cup season we hold only from its later rounds: out before them). */
export type Slot = Run | '-' | 'early' | 'na' | null;
export type Honours = { club: number; season: number; league: League | null; cup: Slot; lcup: Slot; europe: Run | '-'; runs: Run[] };

const LEAGUE_CUPS = new Set(['ENG-LC', 'POR-TL', 'SCO-LC', 'FRA-CDL']);
const EUROPE = new Set(['UCL', 'UEL', 'UCWC', 'FAIRS', 'UECL']);
const SHORT: Record<string, string> = { UCL: 'CL', UEL: 'EL', UCWC: 'CW', FAIRS: 'FC', UECL: 'CO' };
const STAGE: Record<Stage, string> = { W: 'Won', F: 'Final', SF: 'Semi-final', QF: 'Quarter-final', R16: 'Last 16', in: 'Still in', out: 'Earlier round' };
const LC_NAME: Record<string, string> = { ENG: 'League Cup', POR: 'Taça da Liga', SCO: 'League Cup', FRA: 'Coupe de la Ligue' };

export const compName = (c: string, s: number) => ({
  UCL: s >= 1992 ? 'Champions League' : 'European Cup', UEL: s >= 2009 ? 'Europa League' : 'UEFA Cup',
  UCWC: "Cup Winners' Cup", FAIRS: 'Fairs Cup', UECL: 'Conference League',
  'ENG-FAC': 'FA Cup', 'ENG-LC': 'League Cup', 'POR-TL': 'Taça da Liga', 'ESP-CDR': 'Copa del Rey', 'GER-DFB': 'DFB-Pokal',
  'ITA-CI': 'Coppa Italia', 'FRA-CDF': 'Coupe de France', 'NED-KNVB': 'KNVB Cup', 'POR-TP': 'Taça de Portugal',
  'SCO-SC': 'Scottish Cup', 'SCO-LC': 'Scottish League Cup', 'FRA-CDL': 'Coupe de la Ligue', 'BEL-BC': 'Belgian Cup', 'GRE-GC': 'Greek Cup', 'TUR-TC': 'Turkish Cup',
} as Record<string, string>)[c] ?? c;

const SUFFIX = ['th', 'st', 'nd', 'rd'];
export const ordinal = (n: number) => { const v = n % 100; return n + (SUFFIX[(v - 20) % 10] ?? SUFFIX[v] ?? 'th'); };

const medal = (s: Stage) => (s === 'W' ? 'g' : s === 'F' ? 's' : s === 'SF' ? 'b' : s === 'in' ? 'live' : 'x');
const stageText = (s: Stage) => (s === 'out' ? '·' : s === 'in' ? '•' : s);

export const champion = (h?: Honours) => !!h?.league && h.league[1] === 1 && h.league[2] === 1;
export const wonSomething = (h?: Honours) => champion(h) || !!h?.runs.some((r) => r[1] === 'W');

function LeaguePip({ l }: { l: League | null }) {
  if (!l) return <span className="pip n" title="No data">?</span>;
  const [, tier, pos] = l;
  const c = tier > 1 ? 'x' : pos === 1 ? 'g' : pos === 2 ? 's' : pos === 3 ? 'b' : 'x';
  return <span className={`pip ${c}`}>{pos}{tier > 1 && <small>T{tier}</small>}</span>;
}

function SlotPip({ v, europe }: { v: Slot; europe?: boolean }) {
  if (v === 'na') return <span className="pip na" />;
  if (v === null) return <span className="pip n">–</span>;
  if (v === '-') return <span className="pip h">–</span>;
  if (v === 'early') return <span className="pip x">·</span>;
  return <span className={`pip ${medal(v[1])}`}>{stageText(v[1])}{europe && <small>{SHORT[v[0]]}</small>}</span>;
}

export function Strip({ h }: { h?: Honours }) {
  if (!h) return <span className="strip"><span className="pip n">?</span><span className="pip n">?</span><span className="pip n">?</span><span className="pip n">?</span></span>;
  return <span className="strip"><LeaguePip l={h.league} /><SlotPip v={h.cup} /><SlotPip v={h.lcup} /><SlotPip v={h.europe} europe /></span>;
}

export const StripHead = () => (
  <span className="strip strip-head"><span>League</span><span>Cup</span><span>League cup</span><span>Europe</span></span>
);

export function Legend() {
  const item = (c: string, t: string) => <span><i className={`pip ${c}`} />{t}</span>;
  return (
    <p className="honours-legend">
      {item('g', 'Won / 1st')}{item('s', 'Final / 2nd')}{item('b', 'Semi-final / 3rd')}{item('x', 'Further back')}
      {item('h', 'Not in it')}{item('n', 'No data')}
    </p>
  );
}

function Line({ pip, k, children }: { pip: ReactNode; k: string; children: ReactNode }) {
  return <div className="hd-line">{pip}<div><div className="hd-k">{k}</div>{children}</div></div>;
}

function Detail({ h, rank, rating, clubs, country, current, facts }:
  { h: Honours; rank: number; rating: number; clubs: ClubIndex; country: string; current: boolean; facts?: string }) {
  const name = (id: number | null) => (id == null ? '' : clubs.byId[id]?.name ?? '');
  const run = (r: Run, key?: string) => (
    <Line key={key ?? r[0]} pip={<SlotPip v={r} />} k={compName(r[0], h.season)}>
      {STAGE[r[1]]}{r[2] != null && <> · {r[1] === 'F' ? 'lost to' : 'out to'} {name(r[2])}</>}
    </Line>
  );
  const l = h.league;
  const cups = h.runs.filter((r) => !EUROPE.has(r[0]) && !LEAGUE_CUPS.has(r[0]));
  const europe = h.runs.filter((r) => EUROPE.has(r[0]));
  return (
    <>
      <h4>{clubs.byId[h.club].name}</h4>
      <div className="hd-meta">{seasonLabel(h.season)} · world #{rank} · rating {rating}{facts && <><br />{facts}</>}</div>
      {l ? (
        <Line pip={<LeaguePip l={l} />} k={`League${l[1] > 1 ? ` (tier ${l[1]})` : ''}`}>
          {ordinal(l[2])} of {l[3]} · {l[10]} pts{current && ' so far'}
          <div className="muted">P{l[4]} W{l[5]} D{l[6]} L{l[7]} · {l[8]}–{l[9]}</div>
        </Line>
      ) : <Line pip={<LeaguePip l={null} />} k="League">No table for this season</Line>}
      {h.cup === null && <Line pip={<SlotPip v={null} />} k="Domestic cup">No data for this cup season</Line>}
      {h.cup === '-' && <Line pip={<SlotPip v="-" />} k="Domestic cup">{current ? 'Not played yet' : "Didn't take part"}</Line>}
      {h.cup === 'early' && <Line pip={<SlotPip v="early" />} k="Domestic cup">{current ? 'Not played yet' : 'Out before the rounds we hold'}</Line>}
      {cups.map((r) => run(r))}
      {h.lcup === null && <Line pip={<SlotPip v={null} />} k={LC_NAME[country] ?? 'League cup'}>No data yet</Line>}
      {h.lcup === '-' && <Line pip={<SlotPip v="-" />} k={LC_NAME[country] ?? 'League cup'}>{current ? 'Not played yet' : "Didn't take part"}</Line>}
      {h.lcup === 'early' && <Line pip={<SlotPip v="early" />} k={LC_NAME[country] ?? 'League cup'}>{current ? 'Not played yet' : 'Out before the rounds we hold'}</Line>}
      {Array.isArray(h.lcup) && run(h.lcup, 'lcup')}
      {europe.length ? europe.map((r) => run(r)) : <Line pip={<SlotPip v="-" />} k="Europe">Not in Europe</Line>}
    </>
  );
}

/** The strip as a button; tapping it opens the detail card beside it. */
export function HonoursCell(props: { h?: Honours; rank: number; rating: number; clubs: ClubIndex; current: boolean; facts?: string }) {
  const { h, clubs } = props;
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    if (!open || !btn.current || !card.current) return;
    const b = btn.current.getBoundingClientRect(), w = card.current.offsetWidth, ht = card.current.offsetHeight;
    const left = Math.max(8, Math.min(window.innerWidth - w - 8, b.left));
    const below = b.bottom + 6;
    setPos({ left, top: below + ht > window.innerHeight - 8 ? Math.max(8, b.top - ht - 6) : below });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e.type === 'keydown' && (e as KeyboardEvent).key !== 'Escape') return;
      if (e.type === 'pointerdown' && (card.current?.contains(e.target as Node) || btn.current?.contains(e.target as Node))) return;
      setOpen(false); setPos(null);
    };
    const opts = { capture: true, passive: true };
    document.addEventListener('pointerdown', close, true);
    document.addEventListener('keydown', close);
    window.addEventListener('scroll', close, opts);
    window.addEventListener('resize', close);
    return () => {
      document.removeEventListener('pointerdown', close, true);
      document.removeEventListener('keydown', close);
      window.removeEventListener('scroll', close, opts);
      window.removeEventListener('resize', close);
    };
  }, [open]);

  if (!h) return <Strip />;
  return (
    <>
      <button ref={btn} type="button" className="strip-btn" aria-expanded={open} aria-label={`Season detail for ${clubs.byId[h.club].name}`}
              onClick={() => { setOpen((o) => !o); setPos(null); }}>
        <Strip h={h} />
      </button>
      {open && createPortal(   // on <body>: the card panels' clip-path would make it fixed to the panel
        <div ref={card} className="honours-card" role="dialog" style={pos ? { left: pos.left, top: pos.top } : { visibility: 'hidden' }}>
          <Detail {...props} h={h} country={clubs.byId[h.club].country ?? ''} />
        </div>, document.body)}
    </>
  );
}
