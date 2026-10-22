import { useMemo, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { loadClub, useAsync, useCompetitions, useJSON, type Club, type ClubIndex } from '../lib/data';
import { Badge, Card, ClubPicker, Status, Table } from '../components/ui';
import { clubColors, seriesColors } from '../lib/color';
import { COMP_SHORT, dateLong, int, pct, seasonLabel, signed } from '../lib/format';

/** Value at a month, or the latest one in the 12 months before it. */
function atMonth(series: Map<string, number>, month: string): [string, number] | null {
  let [y, m] = month.split('-').map(Number);
  for (let i = 0; i < 13; i++) {
    const k = `${y}-${String(m).padStart(2, '0')}`;
    if (series.has(k)) return [k, series.get(k)!];
    m -= 1; if (m === 0) { m = 12; y -= 1; }
  }
  return null;
}
const expect = (gap: number) => 1 / (1 + 10 ** (-gap / 400));

function Side({ club, children }: { club: Club; children?: ReactNode }) {
  return <div style={{ display: 'grid', justifyItems: 'center', gap: 8 }}><Badge club={club} size={70} glow /><b style={{ fontFamily: 'var(--head)', fontSize: '1.2rem' }}>{club.name}</b>{children}</div>;
}

export default function Matchups({ clubs }: { clubs: ClubIndex }) {
  const [p, setP] = useSearchParams();
  const get = (k: string, d: string) => clubs.bySlug.get(p.get(k) ?? d) ?? clubs.bySlug.get(d)!;
  const a = get('a', 'liverpool'), b = get('b', 'manchester-united');
  const wa = get('wa', 'manchester-united'), wb = get('wb', 'barcelona');
  const da = p.get('da') ?? '1999-05', db = p.get('db') ?? '2011-05';
  const upd = (k: string, v: string) => { const n = new URLSearchParams(p); n.set(k, v); setP(n, { replace: true }); };

  const comps = useCompetitions();
  const fa = useAsync(() => loadClub(a.slug), [a.slug]);
  const meetings = useMemo(() => (fa.data?.matches ?? []).filter((m) => m.opp === b.id).reverse(), [fa.data, b.id]);
  const rec = meetings.reduce((r, m) => (m.gf > m.ga ? { ...r, w: r.w + 1 } : m.gf < m.ga ? { ...r, l: r.l + 1 } : { ...r, d: r.d + 1 }), { w: 0, d: 0, l: 0 });
  const [ca, cb] = seriesColors([a, b]);

  const field = useJSON<Record<string, number>>('field.json');
  const wi = useAsync(() => Promise.all([loadClub(wa.slug), loadClub(wb.slug)]), [wa.slug, wb.slug]);
  const whatif = useMemo(() => {
    if (!wi.data || !field.data) return null;
    const f = new Map(Object.entries(field.data));
    const one = (file: { months: [string, number][] }, month: string) => {
      const e = atMonth(new Map(file.months), month), fv = atMonth(f, month);
      return e && fv ? { month: e[0], elo: e[1], above: e[1] - fv[1] } : null;
    };
    const x = one(wi.data[0], da), y = one(wi.data[1], db);
    if (!x || !y) return { x, y };
    const gap = x.above - y.above;
    return { x, y, raw: x.elo - y.elo, gap, neutral: expect(gap), home: expect(gap + 70), away: expect(gap - 70) };
  }, [wi.data, field.data, da, db]);

  const total = meetings.length || 1;
  return (
    <div className="page">
      <Card title="Head-to-head record" note="Every meeting in the rated data, newest first. Ratings are as each match kicked off.">
        <div className="controls">
          <ClubPicker id="h2h-a" clubs={clubs} placeholder={a.name} onPick={(c) => upd('a', c.slug)} />
          <span className="muted">v</span>
          <ClubPicker id="h2h-b" clubs={clubs} placeholder={b.name} onPick={(c) => upd('b', c.slug)} />
        </div>
        <div className="versus">
          <Side club={a}><span className="big" style={{ color: ca }}>{rec.w}</span></Side>
          <div><span className="big muted">{rec.d}</span><div className="muted">draws · {meetings.length} games</div></div>
          <Side club={b}><span className="big" style={{ color: cb }}>{rec.l}</span></Side>
        </div>
        <div className="bar3" aria-hidden="true">
          <i style={{ width: `${(100 * rec.w) / total}%`, background: ca }} /><i style={{ width: `${(100 * rec.d) / total}%`, background: '#44556f' }} /><i style={{ width: `${(100 * rec.l) / total}%`, background: cb }} />
        </div>
        {fa.data ? <Table rowKey={(m) => m.date} rows={meetings} limit={60} cols={[
          { key: 'date', label: 'Date', render: (m) => m.date },
          { key: 'comp', label: 'Competition', render: (m) => COMP_SHORT[comps.data?.[m.comp] ?? ''] ?? '' },
          { key: 'venue', label: 'Venue', render: (m) => ({ h: a.name, a: b.name, n: 'Neutral' })[m.venue] },
          { key: 'score', label: `${a.name} score`, render: (m) => <span className={m.gf > m.ga ? 'win' : m.gf < m.ga ? 'loss' : ''}>{m.gf}–{m.ga}</span> },
          { key: 'elo', label: 'Ratings', num: true, hideSm: true, render: (m) => `${int(m.elo)} v ${int(m.opp_elo)}` },
          { key: 'exp', label: `${a.name} expected`, num: true, render: (m) => pct(m.exp) },
          { key: 'delta', label: 'Change', num: true, hideSm: true, render: (m) => signed(m.delta) },
        ]} /> : <Status error={fa.error} />}
      </Card>

      <Card title="What if they met?" note="Each club at a chosen month, measured against the average top-flight club of its own time, so different eras compare fairly. Expected score: win probability plus half the draw chance, at a neutral ground and with 70 points of home advantage.">
        <div className="controls">
          <ClubPicker id="wi-a" clubs={clubs} placeholder={wa.name} onPick={(c) => upd('wa', c.slug)} />
          <input className="input" type="month" value={da} min="1965-07" aria-label={`${wa.name} month`} onChange={(e) => e.target.value && upd('da', e.target.value)} />
          <span className="muted">v</span>
          <ClubPicker id="wi-b" clubs={clubs} placeholder={wb.name} onPick={(c) => upd('wb', c.slug)} />
          <input className="input" type="month" value={db} min="1965-07" aria-label={`${wb.name} month`} onChange={(e) => e.target.value && upd('db', e.target.value)} />
        </div>
        {!whatif ? <Status error={wi.error ?? field.error} /> : !whatif.x || !whatif.y ? (
          <p className="muted">{!whatif.x ? wa.name : wb.name} has no rating within a year before that month.</p>
        ) : (
          <>
            <div className="versus">
              <Side club={wa}><span className="muted">{dateLong(whatif.x.month)} · {int(whatif.x.elo)}</span><span className="big" style={{ color: clubColors(wa).accent }}>{signed(whatif.x.above)}</span></Side>
              <div><div className="big">{pct(whatif.neutral!)}</div><div className="muted">{wa.name} expected, neutral</div></div>
              <Side club={wb}><span className="muted">{dateLong(whatif.y.month)} · {int(whatif.y.elo)}</span><span className="big" style={{ color: clubColors(wb).accent }}>{signed(whatif.y.above)}</span></Side>
            </div>
            <div className="tiles" style={{ marginTop: 16 }}>
              <div className="tile"><b>{signed(whatif.gap)}</b><span>Era-adjusted gap</span></div>
              <div className="tile"><b>{signed(whatif.raw)}</b><span>Raw rating gap</span></div>
              <div className="tile"><b>{pct(whatif.home!)}</b><span>{wa.name} at home</span></div>
              <div className="tile"><b>{pct(whatif.away!)}</b><span>{wa.name} away</span></div>
            </div>
            <p className="note">Above average is the rating minus the average top-flight club that month ({seasonLabel(+whatif.x.month.slice(0, 4) - (+whatif.x.month.slice(5) < 7 ? 1 : 0))} v {seasonLabel(+whatif.y.month.slice(0, 4) - (+whatif.y.month.slice(5) < 7 ? 1 : 0))}).</p>
          </>
        )}
      </Card>
    </div>
  );
}
