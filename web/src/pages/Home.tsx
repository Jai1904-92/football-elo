import { Link } from 'react-router-dom';
import { loadYear, useAsync, useJSON, useMeta, type ClubIndex } from '../lib/data';
import { Badge, Card, ClubName, Ring, Status } from '../components/ui';
import { clubColors, clubStyle } from '../lib/color';
import { COUNTRIES, dateLong, int, signed } from '../lib/format';

export default function Home({ clubs }: { clubs: ClubIndex }) {
  const field = useJSON<Record<string, number>>('field.json');
  const meta = useMeta();
  const month = field.data ? Object.keys(field.data).sort().at(-1)! : null;
  const table = useAsync(async () => {
    if (!month) return null;
    const y = +month.slice(0, 4);
    const [now, before] = await Promise.all([loadYear(y), loadYear(y - 1).catch(() => ({}))]);
    const prev = new Map(((before as Record<string, { club: number; elo: number }[]>)[`${y - 1}${month.slice(4)}`] ?? []).map((r) => [r.club, r.elo]));
    return now[month].map((r) => ({ ...r, change: prev.has(r.club) ? r.elo - prev.get(r.club)! : null }));
  }, [month]);

  if (!table.data) return <Status error={field.error ?? table.error} />;
  const top = table.data.slice(0, 10);
  const one = clubs.byId[top[0].club];
  const { accent } = clubColors(one);
  return (
    <div className="page">
      <Card club={one}>
        <div className="hero" style={clubStyle(one)}>
          <div style={{ position: 'relative', display: 'grid', placeItems: 'center' }}>
            <Ring value={top[0].elo} label="Elo rating" sub={`#1 · ${dateLong(month!)}`} size={340} color={accent} />
          </div>
          <div style={{ display: 'grid', gap: 14 }}>
            <span className="kicker">Top-rated club in Europe</span>
            <div className="profile-head">
              <Badge club={one} size={72} glow />
              <h1>{one.name}</h1>
            </div>
            <p className="note" style={{ margin: 0 }}>
              {top[0].elo - top[1].elo} points clear of {clubs.byId[top[1].club].name}. Ratings follow every league, cup and
              European match since 1955 across England, Spain, Germany, Italy, France, the Netherlands and Portugal.
            </p>
            <div className="controls" style={{ margin: 0 }}>
              <Link className="btn" to={`/club/${one.slug}`}>Club profile</Link>
              <Link className="btn" to="/rise">Compare clubs</Link>
              <Link className="btn" to="/rankings">Full ranking</Link>
            </div>
          </div>
        </div>
      </Card>

      <Card title="Top ten right now" note={`${meta.data?.last_match_date.startsWith(month!) ? 'As of ' + dateLong(meta.data.last_match_date) : 'End of ' + dateLong(month!)}. Change is against the same month a year earlier.`}>
        <div className="tablewrap">
          <table className="t">
            <thead><tr><th className="num">#</th><th>Club</th><th className="hide-sm">League</th><th className="num">Rating</th><th className="num">12 months</th></tr></thead>
            <tbody>{top.map((r) => {
              const c = clubs.byId[r.club];
              return (
                <tr key={r.club}>
                  <td className="num rank">{r.rank}</td>
                  <td><ClubName club={c} size={26} /></td>
                  <td className="hide-sm muted">{COUNTRIES[c.country ?? ''] ?? c.country} · tier {r.tier}</td>
                  <td className="num">{int(r.elo)}</td>
                  <td className={'num ' + ((r.change ?? 0) >= 0 ? 'win' : 'loss')}>{signed(r.change)}</td>
                </tr>);
            })}</tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
