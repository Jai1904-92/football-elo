import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { loadClub, useAsync, useCompetitions, useView, type ClubIndex, type Match } from '../lib/data';
import { Badge, Card, ClubName, ClubPicker, Ring, Status, Table } from '../components/ui';
import LineChart, { type Marker } from '../components/LineChart';
import { clubColors, clubStyle } from '../lib/color';
import { COMP_SHORT, COUNTRIES, DOMESTIC_CUPS, EUROPEAN, int, pct, seasonLabel, signed } from '../lib/format';
import { careerFigures, MeasureNote, seasonFigures, useMeasure } from '../lib/measure';

type Trophy = { competition: string; season: number; winner: number; runner_up: number };
const HONOURS: [string, string][] = [
  ['UCL', 'European Cup'], ['UEL', 'UEFA Cup / Europa League'], ['UCWC', "Cup Winners' Cup"], ['FAIRS', 'Fairs Cup'],
  ['UECL', 'Conference League'], ...DOMESTIC_CUPS.map((c) => [c, COMP_SHORT[c]] as [string, string]),
];

export default function ClubPage({ clubs }: { clubs: ClubIndex }) {
  const { slug = 'liverpool' } = useParams();
  const nav = useNavigate();
  const club = clubs.bySlug.get(slug);
  const file = useAsync(() => (club?.has_page ? loadClub(slug) : Promise.reject(new Error('no such club'))), [slug]);
  const comps = useCompetitions();
  const trophies = useView<Trophy>('trophies');
  const colors = clubColors(club);
  const { measure } = useMeasure();

  const won = useMemo(() => (trophies.data ?? []).filter((t) => t.winner === club?.id), [trophies.data, club]);
  const results = useMemo(() => {
    const ms = file.data?.matches ?? [];
    const by = [...ms].sort((a, b) => b.delta - a.delta);
    return { best: by.slice(0, 10), worst: by.slice(-10).reverse() };
  }, [file.data]);

  const markers: Marker[] = useMemo(() => {
    if (!file.data) return [];
    const months = new Map(file.data.months);
    return won.filter((t) => t.competition === 'UCL' || EUROPEAN.includes(t.competition)).map((t) => {
      const key = `${t.season + 1}-05`;
      const y = months.get(key) ?? months.get(`${t.season + 1}-04`) ?? months.get(`${t.season + 1}-06`);
      return y == null ? null : { key: t.competition + t.season, x: new Date(key + '-15T00:00:00Z'), y, color: colors.second,
        shape: t.competition === 'UCL' ? 'diamond' : 'ring', label: `${COMP_SHORT[t.competition]} ${seasonLabel(t.season)}` } as Marker;
    }).filter(Boolean) as Marker[];
  }, [won, file.data, colors.second]);

  if (!club) return <Status error={`no club "${slug}"`} />;
  const latest = file.data?.months.at(-1);
  const career = careerFigures(club, measure);
  const resultCols = [
    { key: 'date', label: 'Date', render: (m: Match) => m.date },
    { key: 'comp', label: 'Competition', hideSm: true, render: (m: Match) => COMP_SHORT[comps.data?.[m.comp] ?? ''] ?? '' },
    { key: 'opp', label: 'Opponent', render: (m: Match) => <ClubName club={clubs.byId[m.opp]} size={18} /> },
    { key: 'venue', label: '', render: (m: Match) => ({ h: 'H', a: 'A', n: 'N' })[m.venue] },
    { key: 'score', label: 'Score', render: (m: Match) => <span className={m.gf > m.ga ? 'win' : m.gf < m.ga ? 'loss' : ''}>{m.gf}–{m.ga}{m.pf != null ? ` (${m.pf}–${m.pa}p)` : ''}</span> },
    { key: 'exp', label: 'Expected', num: true, hideSm: true, render: (m: Match) => pct(m.exp) },
    { key: 'delta', label: 'Change', num: true, render: (m: Match) => signed(m.delta) },
  ];

  return (
    <div className="page" style={clubStyle(club)}>
      <Card club={club}>
        <div className="controls" style={{ marginTop: 0 }}>
          <ClubPicker id="club-pick" clubs={clubs} onPick={(c) => nav(`/club/${c.slug}`)} />
        </div>
        <div className="hero">
          <div style={{ display: 'grid', placeItems: 'center' }}>
            {latest ? <Ring value={club.peak_elo ?? latest[1]} label="Peak rating" sub={club.peak_season ? seasonLabel(club.peak_season) : undefined} color={colors.accent} size={300} />
                    : <Status error={file.error} />}
          </div>
          <div style={{ display: 'grid', gap: 14 }}>
            <div className="profile-head">
              <Badge club={club} size={84} glow />
              <div>
                <h1>{club.name}</h1>
                <div className="muted" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  {COUNTRIES[club.country ?? ''] ?? club.country}
                  {club.first_season != null && <> · {seasonLabel(club.first_season)} – {seasonLabel(club.last_season!)}</>}
                  <span className="swatch" aria-label="Club colours"><i style={{ background: colors.accent }} /><i style={{ background: colors.second }} /></span>
                </div>
              </div>
            </div>
            <div className="tiles">
              <div className="tile"><b>{latest ? int(latest[1]) : '—'}</b><span>Latest rating</span></div>
              <div className="tile"><b>{career.at1 ?? 0}</b><span>Seasons at #1</span></div>
              <div className="tile"><b>{career.top10 ?? 0}</b><span>Seasons in top 10</span></div>
              <div className="tile"><b>{career.best ?? '—'}</b><span>Best rank</span></div>
              <div className="tile"><b>{club.top_flight_seasons ?? 0}</b><span>Top-flight seasons</span></div>
              <div className="tile"><b>{career.decade ? `${career.decade}s` : '—'}</b><span>Best decade</span></div>
            </div>
          </div>
        </div>
      </Card>

      <Card club={club} title="Rating history" note="Month-end Elo rating. Diamonds mark European Cup wins and rings other European trophies.">
        {file.data ? <LineChart height={340} markers={markers} shadeBefore={new Date(Date.UTC(1965, 6, 1))}
          series={[{ key: club.slug, label: club.name, color: colors.accent, points: file.data.months.map(([m, v]) => ({ x: new Date(m + '-15T00:00:00Z'), y: v })) }]} />
          : <Status error={file.error} />}
      </Card>

      <Card club={club} title="Honours" note="Worked out from the finals in the rated data. Domestic cups outside England from 2012/13.">
        {won.length ? (
          <div className="honours">{HONOURS.map(([code, name]) => {
            const list = won.filter((t) => t.competition === code);
            return list.length ? <div className="honour" key={code}><b>{list.length}</b>{name}<small>{list.map((t) => seasonLabel(t.season)).join(', ')}</small></div> : null;
          })}</div>
        ) : <p className="muted">No European trophies or domestic cups in the rated data.</p>}
      </Card>

      <div className="grid2">
        <Card club={club} title="Best results" note="Biggest rating gains in a single match.">
          {file.data ? <Table rowKey={(m) => m.date + m.opp} rows={results.best} cols={resultCols} /> : <Status error={file.error} />}
        </Card>
        <Card club={club} title="Worst results" note="Biggest rating losses in a single match.">
          {file.data ? <Table rowKey={(m) => m.date + m.opp} rows={results.worst} cols={resultCols} /> : <Status error={file.error} />}
        </Card>
      </div>

      <Card club={club} title="Season by season" note="End rating is where the club finished the season; season rating is the whole-season performance rating. Above average, world rank and league rank follow the season view chosen at the top: against the average top-flight club, among every club in the seven leagues, and within the club's own league.">
        <MeasureNote />
        {file.data ? <Table rowKey={(s) => s.season} rows={[...file.data.seasons].reverse()} cols={[
          { key: 'season', label: 'Season', render: (s) => seasonLabel(s.season) },
          { key: 'tier', label: 'Tier', num: true },
          { key: 'league', label: 'League rank', num: true, sort: (s) => seasonFigures(s, measure).league, render: (s) => seasonFigures(s, measure).league },
          { key: 'elo_end', label: 'End rating', num: true, render: (s) => int(s.elo_end) },
          { key: 'perf', label: 'Season rating', num: true, render: (s) => int(s.perf) },
          { key: 'elo_peak', label: 'Peak', num: true, hideSm: true, render: (s) => int(s.elo_peak) },
          { key: 'above', label: 'Above average', num: true, sort: (s) => seasonFigures(s, measure).above, render: (s) => signed(seasonFigures(s, measure).above) },
          { key: 'world', label: 'World rank', num: true, sort: (s) => seasonFigures(s, measure).world, render: (s) => seasonFigures(s, measure).world },
        ]} /> : <Status error={file.error} />}
      </Card>
    </div>
  );
}
