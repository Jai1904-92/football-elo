import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { objects, useJSON, useView, type ClubIndex, type Rows } from '../lib/data';
import { Card, ClubName, Seg, Status, Table } from '../components/ui';
import { champion, HonoursCell, Legend, ordinal, StripHead, wonSomething, type Honours } from '../components/Honours';
import { COUNTRIES, int, seasonLabel, signed } from '../lib/format';
import { MeasureNote, useMeasure, type Measure } from '../lib/measure';

type Row = { measure: Measure; season: number; rank: number; club: number; rating: number; above: number;
  tier: number; league_rank: number; prev_rank: number | null };

type Filter = 'all' | 'champ' | 'notchamp' | 'trophy';

export default function Top100({ clubs }: { clubs: ClubIndex }) {
  const view = useView<Row>('season_top100');
  const { measure, setMeasure } = useMeasure();
  const other: Measure = measure === 'end' ? 'perf' : 'end';
  const seasons = useMemo(() => [...new Set((view.data ?? []).map((r) => r.season))].sort((a, b) => a - b), [view.data]);
  const [p, setP] = useSearchParams();
  const season = p.has('season') ? +p.get('season')! : seasons.at(-2) ?? null;   // the last finished season
  const go = (s: number) => setP({ season: String(s) }, { replace: true });
  const [country, setCountry] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const honoursFile = useJSON<Rows>('season_honours.json');
  const honours = useMemo(() => new Map(objects<Honours>(honoursFile.data ?? { cols: [], rows: [] })
    .map((h) => [`${h.club}-${h.season}`, h])), [honoursFile.data]);
  const hon = (club: number) => honours.get(`${club}-${season}`);

  const rows = useMemo(() => {
    const all = (view.data ?? []).filter((r) => r.season === season);
    const otherRank = new Map(all.filter((r) => r.measure === other).map((r) => [r.club, r.rank]));
    return all.filter((r) => r.measure === measure && (!country || clubs.byId[r.club].country === country))
      .map((r) => ({ ...r, move: r.prev_rank == null ? null : r.prev_rank - r.rank, other: otherRank.get(r.club) ?? null }));
  }, [view.data, season, measure, other, country, clubs]);
  const shown = useMemo(() => filter === 'all' || !honoursFile.data ? rows : rows.filter((r) => {
    const h = honours.get(`${r.club}-${r.season}`);
    return filter === 'champ' ? champion(h) : filter === 'notchamp' ? !champion(h) : wonSomething(h);
  }), [rows, filter, honours, honoursFile.data]);
  const champs = rows.filter((r) => champion(honours.get(`${r.club}-${r.season}`))).length;
  const winners = rows.filter((r) => wonSomething(honours.get(`${r.club}-${r.season}`))).length;

  const byCountry = useMemo(() => {
    const n: Record<string, number> = {};
    rows.forEach((r) => { const c = clubs.byId[r.club].country ?? ''; n[c] = (n[c] ?? 0) + 1; });
    return Object.entries(n).sort((a, b) => b[1] - a[1]);
  }, [rows, clubs]);

  const facts = (r: Row & { other: number | null }) => [
    COUNTRIES[clubs.byId[r.club].country ?? ''],
    `${ordinal(r.league_rank)} by rating in its league${r.tier > 1 ? ` (tier ${r.tier})` : ''}`,
    `${signed(r.above)} above average`,
    `${other === 'end' ? 'end-of-season' : 'whole-season'} rank ${r.other ?? '>100'}`,
  ].filter(Boolean).join(' · ');
  const cell = (r: Row & { other: number | null }) => <HonoursCell h={hon(r.club)} rank={r.rank} rating={r.rating} clubs={clubs}
    current={season === seasons.at(-1)} facts={facts(r)} />;
  const i = season == null ? -1 : seasons.indexOf(season);
  return (
    <div className="page top100">
      <Card title={season == null ? 'World top 100' : `World top 100 · ${seasonLabel(season)}`}
            note="The 100 highest-rated clubs across every modelled league that season. Move is against the club's world rank the season before. The season strip shows where each club actually finished: league place, domestic cup, league cup and best European run. Tap a strip for the detail, including the club's rank under the other season measure.">
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
        <div className="controls">
          <Seg<Filter> label="Show" value={filter} onChange={setFilter}
                       options={[['all', 'All'], ['champ', 'League champions'], ['notchamp', "Didn't win the league"], ['trophy', 'Won something']]} />
        </div>
        <Legend />
        <MeasureNote />
        {!country && byCountry.length > 0 && (
          <p className="note">{byCountry.map(([c, n]) => `${COUNTRIES[c] ?? c} ${n}`).join(' · ')}</p>
        )}
        {honoursFile.data && rows.length > 0 && season !== seasons.at(-1) && (
          <p className="note">{champs} of these {rows.length} clubs won their league; {winners} won at least one trophy.</p>
        )}
        {season === seasons.at(-1) && <p className="note">{seasonLabel(season)} is still being played: these are the standings so far.</p>}
        {view.data ? <Table rowKey={(r) => r.club} rows={shown} cols={[
          { key: 'rank', label: '#', num: true, render: (r) => <span className="rank">{r.rank}</span> },
          { key: 'move', label: 'Move', num: true, hideSm: true, sort: (r) => r.move ?? -999,
            render: (r) => r.move == null ? <span className="muted">new</span>
              : <span className={r.move >= 0 ? 'win' : 'loss'}>{r.move === 0 ? '=' : signed(r.move)}</span> },
          { key: 'club', label: 'Club', sort: (r) => clubs.byId[r.club].name, render: (r) => <>
            <ClubName club={clubs.byId[r.club]} />
            <div className="show-sm">{cell(r)}</div>
          </> },
          { key: 'honours', label: <StripHead />, hideSm: true, sort: (r) => { const l = hon(r.club)?.league; return l ? -(l[1] * 100 + l[2]) : null; },
            render: cell },
          { key: 'rating', label: 'Rating', num: true, render: (r) => int(r.rating) },
        ]} /> : <Status error={view.error} />}
      </Card>
    </div>
  );
}
