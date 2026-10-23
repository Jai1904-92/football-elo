import { useMemo, useState } from 'react';
import { useView, type ClubIndex } from '../lib/data';
import { Card, ClubName, Status, Table } from '../components/ui';
import { clubColors } from '../lib/color';
import { MeasureNote, useMeasure } from '../lib/measure';

type Part = { measure: string; club: number; country: string; peak_above: number; best5_above: number; seasons_at_1: number;
  seasons_top10: number; top_flight_seasons: number; s_peak: number; s_sus: number; s_at1: number; s_top10: number };

const WEIGHTS: [keyof W, string][] = [['peak', 'Peak'], ['sustain', 'Sustained'], ['top', 'At #1'], ['long', 'Top 10']];
type W = { peak: number; sustain: number; top: number; long: number };

export default function AllTime({ clubs }: { clubs: ClubIndex }) {
  const parts = useView<Part>('alltime_parts');
  const [w, setW] = useState<W>({ peak: 25, sustain: 35, top: 20, long: 20 });
  const { measure } = useMeasure();
  const rows = useMemo(() => {
    const tot = w.peak + w.sustain + w.top + w.long || 1;
    return (parts.data ?? []).filter((p) => p.measure === measure).map((p) => ({
      ...p, score: Math.round(1000 * (w.peak * p.s_peak + w.sustain * p.s_sus + w.top * p.s_at1 + w.long * p.s_top10) / tot) / 10,
    })).sort((a, b) => b.score - a.score).slice(0, 60).map((r, i) => ({ ...r, pos: i + 1 }));
  }, [parts.data, w, measure]);

  return (
    <div className="page">
      <Card title="All-time ranking" note="A weighted blend of four things since 1965/66: peak (best season above the top-flight average), sustained (best five-season average), seasons ranked #1 and seasons in the top 10. Each is scaled 0–1 against the best club. Move the weights to change the order.">
        <MeasureNote />
        <div className="controls">
          {WEIGHTS.map(([k, label]) => (
            <label className="slider" key={k}>{label}
              <input type="range" min={0} max={100} step={5} value={w[k]} onChange={(e) => setW({ ...w, [k]: +e.target.value })} />
              <output>{w[k]}</output></label>))}
        </div>
        {parts.data ? (
          <Table rowKey={(r) => r.club} rows={rows} cols={[
            { key: 'pos', label: '#', num: true, render: (r) => <span className="rank">{r.pos}</span> },
            { key: 'club', label: 'Club', render: (r) => <ClubName club={clubs.byId[r.club]} /> },
            { key: 'score', label: 'Score', num: true, render: (r) => (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <i style={{ display: 'inline-block', height: 6, width: Math.max(4, r.score * 1.2), background: clubColors(clubs.byId[r.club]).accent, boxShadow: `0 0 8px ${clubColors(clubs.byId[r.club]).accent}` }} />
                {r.score.toFixed(1)}</span>) },
            { key: 'peak_above', label: 'Peak above avg', num: true, render: (r) => Math.round(r.peak_above) },
            { key: 'best5_above', label: 'Best 5 seasons', num: true, hideSm: true, render: (r) => Math.round(r.best5_above) },
            { key: 'seasons_at_1', label: 'At #1', num: true },
            { key: 'seasons_top10', label: 'Top 10', num: true },
            { key: 'top_flight_seasons', label: 'Top-flight seasons', num: true, hideSm: true },
          ]} />
        ) : <Status error={parts.error} />}
      </Card>
    </div>
  );
}
