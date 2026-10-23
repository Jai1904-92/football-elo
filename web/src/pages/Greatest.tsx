import { useState } from 'react';
import { useView, type ClubIndex } from '../lib/data';
import { Card, ClubName, Status, Table } from '../components/ui';
import { COMP_SHORT, COUNTRIES, int, pct, seasonLabel, signed } from '../lib/format';
import { MeasureNote, useMeasure } from '../lib/measure';

type GSeason = { measure: string; rating: number; club: number; country: string; season: number; season_label: string; elo_end: number; elo_peak: number; above_field: number; world_rank: number };
type Upset = { match_id: string; match_date: string; competition: string; comp_type: string; home_club: number; away_club: number;
  score: string; winner: number; loser: number; home_elo: number; away_elo: number; winner_chance: number };

export default function Greatest({ clubs }: { clubs: ClubIndex }) {
  const seasons = useView<GSeason>('greatest_seasons');
  const upsets = useView<Upset>('upsets');
  const [country, setCountry] = useState('');
  const { measure } = useMeasure();
  const [type, setType] = useState('');
  return (
    <div className="page">
      <Card title="Greatest single seasons" note="Rating above the average top-flight club that season, since 1965/66.">
        <MeasureNote />
        <div className="controls">
          <select className="select" aria-label="Country" value={country} onChange={(e) => setCountry(e.target.value)}>
            <option value="">All countries</option>{Object.entries(COUNTRIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        {seasons.data ? <Table rowKey={(r) => `${r.club}-${r.season}`} limit={50} initial={['above_field', 'desc']}
          rows={seasons.data.filter((r) => r.measure === measure && (!country || r.country === country))} cols={[
            { key: 'club', label: 'Club', sort: (r) => clubs.byId[r.club]?.name, render: (r) => <ClubName club={clubs.byId[r.club]} /> },
            { key: 'season', label: 'Season', render: (r) => seasonLabel(r.season) },
            { key: 'above_field', label: 'Above average', num: true, render: (r) => signed(r.above_field) },
            { key: 'rating', label: measure === 'perf' ? 'Season rating' : 'End rating', num: true, render: (r) => int(r.rating) },
            ...(measure === 'perf' ? [{ key: 'elo_end', label: 'End rating', num: true, hideSm: true, render: (r: GSeason) => int(r.elo_end) }] : []),
            { key: 'elo_peak', label: 'Peak', num: true, hideSm: true, render: (r) => int(r.elo_peak) },
            { key: 'world_rank', label: 'Rank', num: true },
          ]} /> : <Status error={seasons.error} />}
      </Card>

      <Card title="Biggest upsets" note="Wins by the side the ratings gave the smallest chance, since 1965/66.">
        <div className="controls">
          <select className="select" aria-label="Competition type" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All competitions</option><option value="league">League</option><option value="cup">Cups</option><option value="europe">Europe</option><option value="playoff">Play-offs</option>
          </select>
        </div>
        {upsets.data ? <Table rowKey={(r) => r.match_id} limit={50} initial={['winner_chance', 'asc']}
          rows={upsets.data.filter((r) => !type || r.comp_type === type)} cols={[
            { key: 'match_date', label: 'Date' },
            { key: 'competition', label: 'Competition', hideSm: true, render: (r) => COMP_SHORT[r.competition] ?? r.competition },
            { key: 'winner', label: 'Winner', sort: (r) => clubs.byId[r.winner]?.name, render: (r) => <ClubName club={clubs.byId[r.winner]} /> },
            { key: 'loser', label: 'Beat', sort: (r) => clubs.byId[r.loser]?.name, render: (r) => <ClubName club={clubs.byId[r.loser]} /> },
            { key: 'score', label: 'Score', render: (r) => <span title={`${clubs.byId[r.home_club]?.name} v ${clubs.byId[r.away_club]?.name}`}>{r.score}</span> },
            { key: 'ratings', label: 'Ratings', num: true, hideSm: true, sort: (r) => r.home_elo - r.away_elo, render: (r) => `${int(r.home_elo)} v ${int(r.away_elo)}` },
            { key: 'winner_chance', label: 'Chance', num: true, render: (r) => pct(r.winner_chance) },
          ]} /> : <Status error={upsets.error} />}
      </Card>
    </div>
  );
}
