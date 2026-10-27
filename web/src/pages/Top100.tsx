import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useView, type ClubIndex } from '../lib/data';
import { Card, ClubName, Seg, Status, Table } from '../components/ui';
import { COUNTRIES, int, seasonLabel, signed } from '../lib/format';
import { MeasureNote, useMeasure, type Measure } from '../lib/measure';

type Row = { measure: Measure; season: number; rank: number; club: number; rating: number; above: number;
  tier: number; league_rank: number; prev_rank: number | null };

const SUFFIX = ['th', 'st', 'nd', 'rd'];
const ordinal = (n: number) => { const v = n % 100; return n + (SUFFIX[(v - 20) % 10] ?? SUFFIX[v] ?? 'th'); };

export default function Top100({ clubs }: { clubs: ClubIndex }) {
  const view = useView<Row>('season_top100');
  const { measure, setMeasure } = useMeasure();
  const other: Measure = measure === 'end' ? 'perf' : 'end';
  const seasons = useMemo(() => [...new Set((view.data ?? []).map((r) => r.season))].sort((a, b) => a - b), [view.data]);
  const [p, setP] = useSearchParams();
  const season = p.has('season') ? +p.get('season')! : seasons.at(-2) ?? null;   // the last finished season
  const go = (s: number) => setP({ season: String(s) }, { replace: true });
  const [country, setCountry] = useState('');

  const rows = useMemo(() => {
    const all = (view.data ?? []).filter((r) => r.season === season);
    const otherRank = new Map(all.filter((r) => r.measure === other).map((r) => [r.club, r.rank]));
    return all.filter((r) => r.measure === measure && (!country || clubs.byId[r.club].country === country))
      .map((r) => ({ ...r, move: r.prev_rank == null ? null : r.prev_rank - r.rank, other: otherRank.get(r.club) ?? null }));
  }, [view.data, season, measure, other, country, clubs]);

  const byCountry = useMemo(() => {
    const n: Record<string, number> = {};
    rows.forEach((r) => { const c = clubs.byId[r.club].country ?? ''; n[c] = (n[c] ?? 0) + 1; });
    return Object.entries(n).sort((a, b) => b[1] - a[1]);
  }, [rows, clubs]);

  const i = season == null ? -1 : seasons.indexOf(season);
  return (
    <div className="page">
      <Card title={season == null ? 'World top 100' : `World top 100 · ${seasonLabel(season)}`}
            note="The 100 highest-rated clubs across every modelled league that season. Move is against the club's world rank the season before; Other view is its rank under the other season measure.">
        <div className="controls">
          <button className="btn" type="button" disabled={i <= 0} onClick={() => go(seasons[i - 1])} aria-label="Previous season">‹</button>
          <select className="select" aria-label="Season" value={season ?? ''} onChange={(e) => go(+e.target.value)}>
            {[...seasons].reverse().map((s) => <option key={s} value={s}>{seasonLabel(s)}</option>)}
          </select>
          <button className="btn" type="button" disabled={i < 0 || i >= seasons.length - 1} onClick={() => go(seasons[i + 1])} aria-label="Next season">›</button>
          <Seg<Measure> label="Judge seasons by" value={measure} onChange={setMeasure} options={[['end', 'End of season'], ['perf', 'Whole season']]} />
          <select className="select" aria-label="Country" value={country} onChange={(e) => setCountry(e.target.value)}>
            <option value="">All countries</option>{Object.entries(COUNTRIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <MeasureNote />
        {!country && byCountry.length > 0 && (
          <p className="note">{byCountry.map(([c, n]) => `${COUNTRIES[c] ?? c} ${n}`).join(' · ')}</p>
        )}
        {season === seasons.at(-1) && <p className="note">{seasonLabel(season)} is still being played: these are the standings so far.</p>}
        {view.data ? <Table rowKey={(r) => r.club} rows={rows} cols={[
          { key: 'rank', label: '#', num: true, render: (r) => <span className="rank">{r.rank}</span> },
          { key: 'move', label: 'Move', num: true, sort: (r) => r.move ?? -999,
            render: (r) => r.move == null ? <span className="muted">new</span>
              : <span className={r.move >= 0 ? 'win' : 'loss'}>{r.move === 0 ? '=' : signed(r.move)}</span> },
          { key: 'club', label: 'Club', sort: (r) => clubs.byId[r.club].name, render: (r) => <ClubName club={clubs.byId[r.club]} /> },
          { key: 'country', label: 'Country', hideSm: true, sort: (r) => clubs.byId[r.club].country, render: (r) => COUNTRIES[clubs.byId[r.club].country ?? ''] ?? '' },
          { key: 'league_rank', label: 'In league', num: true, hideSm: true,
            render: (r) => `${ordinal(r.league_rank)}${r.tier > 1 ? ` (tier ${r.tier})` : ''}` },
          { key: 'rating', label: 'Rating', num: true, render: (r) => int(r.rating) },
          { key: 'above', label: 'Above average', num: true, hideSm: true, render: (r) => signed(r.above) },
          { key: 'other', label: 'Other view', num: true, hideSm: true, sort: (r) => r.other ?? 999, render: (r) => r.other ?? '>100' },
        ]} /> : <Status error={view.error} />}
      </Card>
    </div>
  );
}
