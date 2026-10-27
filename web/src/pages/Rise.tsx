import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { loadClub, useAsync, useView, type ClubIndex } from '../lib/data';
import { Card, ClubName, ClubPicker, Seg, Status, Table } from '../components/ui';
import LineChart, { type Marker, type Series } from '../components/LineChart';
import { clubLines } from '../lib/color';
import { EUROPEAN, int, seasonLabel, signed } from '../lib/format';
import { careerFigures, MeasureNote, seasonFigures, useMeasure } from '../lib/measure';

const PRESETS: Record<string, [string, string[]]> = {
  europe: ['European royalty', ['Real Madrid', 'Barcelona', 'Bayern Munich', 'AC Milan', 'Liverpool', 'Juventus']],
  england: ["England's giants", ['Manchester United', 'Liverpool', 'Arsenal', 'Chelsea', 'Manchester City', 'Tottenham Hotspur']],
  spain: ["Spain's giants", ['Real Madrid', 'Barcelona', 'Atletico Madrid', 'Valencia CF', 'Athletic Bilbao', 'Sevilla']],
  italy: ["Italy's giants", ['Juventus', 'AC Milan', 'Internazionale', 'AS Roma', 'SSC Napoli', 'Lazio']],
  germany: ["Germany's giants", ['Bayern Munich', 'Borussia Dortmund', 'Hamburger SV', 'Borussia Monchengladbach', 'Werder Bremen', 'Bayer Leverkusen']],
  france: ["France's giants", ['Paris Saint-Germain', 'Olympique Marseille', 'Olympique Lyon', 'AS Monaco', 'AS Saint-Etienne', 'Girondins Bordeaux']],
  lowlands: ['Portugal and the Netherlands', ['AFC Ajax', 'PSV Eindhoven', 'Feyenoord', 'SL Benfica', 'FC Porto', 'Sporting CP']],
};
type Measure = 'elo' | 'above' | 'rank';
type Trophy = { competition: string; season: number; winner: number };

export default function Rise({ clubs }: { clubs: ClubIndex }) {
  const [params, setParams] = useSearchParams();
  const slugs = (params.get('clubs') ?? 'real-madrid,barcelona,bayern-munich,ac-milan,liverpool,juventus').split(',').filter((s) => clubs.bySlug.get(s)?.has_page).slice(0, 8);
  const measure = (params.get('m') as Measure) || 'elo';
  const set = (s: string[], m = measure) => setParams({ clubs: s.join(','), m }, { replace: true });
  const [preset, setPreset] = useState('');
  const { measure: sm } = useMeasure();

  const files = useAsync(() => Promise.all(slugs.map(loadClub)), [slugs.join(',')]);
  const trophies = useView<Trophy>('trophies');
  const sel = slugs.map((s) => clubs.bySlug.get(s)!);
  const lines = useMemo(() => clubLines(sel), [slugs.join(',')]); // eslint-disable-line react-hooks/exhaustive-deps
  const colors = lines.map((l) => l.color);

  const { series, markers } = useMemo(() => {
    if (!files.data) return { series: [] as Series[], markers: [] as Marker[] };
    const series: Series[] = files.data.map((f, i) => ({
      key: sel[i].slug, label: sel[i].name, color: colors[i], dash: lines[i].dash,
      points: measure === 'elo'
        ? f.months.map(([m, v]) => ({ x: new Date(m + '-15T00:00:00Z'), y: v }))
        : f.seasons.map((s) => { const v = seasonFigures(s, sm); return { x: new Date(Date.UTC(s.season + 1, 4, 31)), y: measure === 'above' ? v.above : v.world }; }),
    }));
    const markers: Marker[] = [];
    (trophies.data ?? []).forEach((t) => {
      const i = sel.findIndex((c) => c.id === t.winner);
      if (i < 0 || !(t.competition === 'UCL' || EUROPEAN.includes(t.competition))) return;
      const x = new Date(Date.UTC(t.season + 1, 4, 31));
      const pts = series[i].points;
      const near = pts.reduce((b, p) => (Math.abs(+p.x - +x) < Math.abs(+b.x - +x) ? p : b), pts[0]);
      if (!near) return;
      markers.push({ key: `${t.competition}${t.season}${i}`, x: near.x, y: near.y, color: colors[i],
        shape: t.competition === 'UCL' ? 'diamond' : 'ring', label: `${sel[i].name} — ${t.competition} ${seasonLabel(t.season)}` });
    });
    return { series, markers };
  }, [files.data, trophies.data, measure, lines, sm]); // eslint-disable-line react-hooks/exhaustive-deps

  const counts = (id: number) => {
    const won = (trophies.data ?? []).filter((t) => t.winner === id);
    return { ec: won.filter((t) => t.competition === 'UCL').length, oe: won.filter((t) => EUROPEAN.includes(t.competition)).length };
  };

  return (
    <div className="page">
      <Card title="Compare clubs over time" note="Pick up to eight clubs. Rating is the Elo rating month by month. Above average is the end-of-season rating minus the average top-flight club across the eleven leagues that season, which makes eras comparable. Rank is the position among every club in the eleven leagues at season end.">
        <div className="controls">
          <ClubPicker id="rise-add" clubs={clubs} placeholder="Add a club" onPick={(c) => !slugs.includes(c.slug) && set([...slugs, c.slug].slice(-8))} />
          <select className="select" value={preset} aria-label="Quick picks" onChange={(e) => {
            const p = PRESETS[e.target.value]; setPreset('');
            if (p) set(p[1].map((n) => clubs.byName.get(n)?.slug).filter(Boolean) as string[]);
          }}>
            <option value="">Quick picks</option>
            {Object.entries(PRESETS).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
          </select>
          <Seg label="Measure" value={measure} onChange={(m) => set(slugs, m)}
               options={[['elo', 'Rating'], ['above', 'Above average'], ['rank', 'Rank']]} />
        </div>
        <div className="chips" style={{ marginBottom: 10 }}>
          {sel.map((c, i) => (
            <span className="chip" key={c.slug}>
              <svg className="chip-line" viewBox="0 0 22 10" aria-hidden="true"><line x1="1" y1="5" x2="21" y2="5" stroke={colors[i]} strokeWidth="2.5" strokeDasharray={lines[i].dash ?? undefined} /></svg><ClubName club={c} size={20} />
              <button aria-label={`Remove ${c.name}`} onClick={() => set(slugs.filter((s) => s !== c.slug))}>×</button></span>))}
        </div>
        {measure !== 'elo' && <MeasureNote />}
        {files.data ? (
          <LineChart series={series} markers={markers} invert={measure === 'rank'} log={measure === 'rank'} zero={measure === 'above'}
                     gapDays={measure === 'elo' ? 200 : 400} shadeBefore={new Date(Date.UTC(1965, 6, 1))}
                     yLabel={measure === 'elo' ? 'Rating' : measure === 'above' ? 'Above average' : 'Rank'}
                     format={measure === 'above' ? signed : int} height={420}
                     xFormat={measure === 'elo' ? undefined : (d) => 'Season ' + seasonLabel(d.getUTCFullYear() - 1)} />
        ) : <Status error={files.error} />}
        <p className="note">Diamonds mark European Cup wins and rings other European trophies. Shaded: 1955–64, the burn-in decade while starting ratings settle. Gaps are summers and seasons outside the modelled leagues. Each line is in its club's colour; clubs that share a colour are told apart by dashes.</p>
      </Card>

      <Card title="Head to head" note="Career numbers since 1965/66.">
        <MeasureNote />
        <Table rowKey={(c) => c.id} rows={sel} initial={['peak_elo', 'desc']} cols={[
          { key: 'name', label: 'Club', render: (c) => <ClubName club={c} /> },
          { key: 'peak_elo', label: 'Peak', num: true, render: (c) => int(c.peak_elo) },
          { key: 'peak_season', label: 'Peak season', num: true, render: (c) => (c.peak_season ? seasonLabel(c.peak_season) : '—') },
          { key: 'at1', label: 'At #1', num: true, sort: (c) => careerFigures(c, sm).at1, render: (c) => careerFigures(c, sm).at1 ?? 0 },
          { key: 'top10', label: 'Top 10', num: true, sort: (c) => careerFigures(c, sm).top10, render: (c) => careerFigures(c, sm).top10 ?? 0 },
          { key: 'best', label: 'Best rank', num: true, sort: (c) => careerFigures(c, sm).best, render: (c) => careerFigures(c, sm).best ?? '—' },
          { key: 'ec', label: 'European Cups', num: true, sort: (c) => counts(c.id).ec, render: (c) => counts(c.id).ec },
          { key: 'oe', label: 'Other European', num: true, sort: (c) => counts(c.id).oe, render: (c) => counts(c.id).oe },
          { key: 'top_flight_seasons', label: 'Top-flight seasons', num: true, hideSm: true },
          { key: 'decade', label: 'Best decade', num: true, hideSm: true, sort: (c) => careerFigures(c, sm).decade, render: (c) => { const d = careerFigures(c, sm).decade; return d ? `${d}s` : '—'; } },
        ]} />
      </Card>
    </div>
  );
}
