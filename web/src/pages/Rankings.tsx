import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { loadYear, useAsync, useJSON, type ClubIndex } from '../lib/data';
import { Card, ClubName, Status, Table } from '../components/ui';
import { COUNTRIES, dateLong, int, signed } from '../lib/format';

const JUMPS: [string, string][] = [['1970-05', 'May 1970'], ['1980-05', 'May 1980'], ['1990-05', 'May 1990'], ['1999-05', 'May 1999'],
  ['2010-05', 'May 2010'], ['2020-08', 'August 2020']];

export default function Rankings({ clubs }: { clubs: ClubIndex }) {
  const field = useJSON<Record<string, number>>('field.json');
  const months = useMemo(() => Object.keys(field.data ?? {}).sort(), [field.data]);
  const [p, setP] = useSearchParams();
  const month = p.get('on') ?? months.at(-1) ?? null;
  const [country, setCountry] = useState('');
  const [tier, setTier] = useState('');
  const [q, setQ] = useState('');

  const data = useAsync(async () => {
    if (!month) return null;
    const y = +month.slice(0, 4);
    const [now, before] = await Promise.all([loadYear(y), loadYear(y - 1).catch(() => ({} as Record<string, never[]>))]);
    const rows = now[month] ?? [];
    const prev = new Map((before[`${y - 1}${month.slice(4)}`] ?? []).map((r: { club: number; elo: number }) => [r.club, r.elo]));
    return rows.map((r) => ({ ...r, change: prev.has(r.club) ? r.elo - (prev.get(r.club) as number) : null }));
  }, [month]);

  const rows = useMemo(() => (data.data ?? []).filter((r) => {
    const c = clubs.byId[r.club];
    return (!country || c.country === country) && (!tier || r.tier === +tier) && (!q || c.name.toLowerCase().includes(q.toLowerCase()));
  }), [data.data, country, tier, q, clubs]);

  const go = (m: string) => setP({ on: m }, { replace: true });
  return (
    <div className="page">
      <Card title={month ? `Ranking · ${dateLong(month)}` : 'Ranking'} note="Every club in the seven modelled leagues at the end of the month, by Elo rating. Change is against the same month a year before.">
        <div className="controls">
          <input className="input" type="month" aria-label="Month" value={month ?? ''} min={months[0]} max={months.at(-1)}
                 onChange={(e) => e.target.value && months.includes(e.target.value) && go(e.target.value)} />
          <select className="select" aria-label="Jump to a date" value="" onChange={(e) => e.target.value && go(e.target.value)}>
            <option value="">Jump to…</option>{JUMPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button className="btn" type="button" onClick={() => months.length && go(months.at(-1)!)}>Latest</button>
          <select className="select" aria-label="Country" value={country} onChange={(e) => setCountry(e.target.value)}>
            <option value="">All countries</option>{Object.entries(COUNTRIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="select" aria-label="Tier" value={tier} onChange={(e) => setTier(e.target.value)}>
            <option value="">All tiers</option><option value="1">Top flight</option><option value="2">Second tier</option><option value="3">Third tier</option><option value="4">Fourth tier</option>
          </select>
          <input className="input" type="search" placeholder="Search clubs" aria-label="Search clubs" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {data.data ? <Table rowKey={(r) => r.club} rows={rows} limit={300} cols={[
          { key: 'rank', label: '#', num: true, render: (r) => <span className="rank">{r.rank}</span> },
          { key: 'club', label: 'Club', sort: (r) => clubs.byId[r.club].name, render: (r) => <ClubName club={clubs.byId[r.club]} /> },
          { key: 'country', label: 'Country', hideSm: true, sort: (r) => clubs.byId[r.club].country, render: (r) => COUNTRIES[clubs.byId[r.club].country ?? ''] ?? '' },
          { key: 'tier', label: 'Tier', num: true },
          { key: 'elo', label: 'Rating', num: true, render: (r) => int(r.elo) },
          { key: 'change', label: '12 months', num: true, render: (r) => <span className={(r.change ?? 0) >= 0 ? 'win' : 'loss'}>{signed(r.change)}</span> },
        ]} /> : <Status error={data.error ?? field.error} />}
      </Card>
    </div>
  );
}
