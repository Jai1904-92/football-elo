import { useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';
import { useView, type ClubIndex } from '../lib/data';
import { Badge, Card, ClubName, Seg, Status, Table } from '../components/ui';
import LineChart, { type Series } from '../components/LineChart';
import { COUNTRIES, COUNTRY_ORDER, countryColor, int, seasonLabel } from '../lib/format';
import { MeasureNote, useMeasure } from '../lib/measure';

type One = { measure: string; season: number; club: number; country: string; rating: number; elo_end: number; margin: number; runner_up: number };
type King = { measure: string; decade: number; pos: number; club: number; country: string; seasons: number; avg_above_field: number; best_rank: number; seasons_at_1: number };
type Strength = { measure: string; season: number; country: string; avg_top_flight: number; best: number };
type Dyn = { measure: string; top_n: number; club: number; country: string; from_season: number; to_season: number; span: string; seasons: number; avg_rank: number; seasons_at_1: number; pos: number };

function OnesChart({ rows, clubs }: { rows: One[]; clubs: ClubIndex }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const draw = () => {
      el.replaceChildren();
      const width = el.clientWidth || 800, height = 220, m = { t: 10, r: 10, b: 26, l: 40 };
      const x = d3.scaleBand<number>().domain(rows.map((r) => r.season)).range([m.l, width - m.r]).padding(0.18);
      const y = d3.scaleLinear().domain([0, d3.max(rows, (r) => r.margin) ?? 1]).nice().range([height - m.b, m.t]);
      const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${width} ${height}`).attr('role', 'img').attr('aria-label', 'Top-rated club at each season end');
      svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${height - m.b})`)
        .call(d3.axisBottom(x).tickValues(rows.map((r) => r.season).filter((s) => s % 10 === 0)).tickFormat((s) => String(s)));
      svg.append('g').attr('class', 'axis').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4));
      const tip = d3.select(el).append('div').attr('class', 'tip').style('display', 'none');
      svg.append('g').selectAll('polygon').data(rows).join('polygon')
        .attr('points', (r) => { const x0 = x(r.season)!, w = x.bandwidth(), y0 = y(r.margin), b = height - m.b, c = Math.min(w / 2, 4);
          return `${x0},${b} ${x0},${y0 + c} ${x0 + w / 2},${y0} ${x0 + w},${y0 + c} ${x0 + w},${b}`; })
        .attr('fill', (r) => countryColor(r.country)).attr('fill-opacity', 0.85)
        .on('mousemove', (ev, r) => {
          const [px, py] = d3.pointer(ev, el);
          tip.style('display', null).style('left', `${Math.min(px + 12, width - 200)}px`).style('top', `${py - 60}px`)
            .html(`<b>${seasonLabel(r.season)}</b><div><span>${clubs.byId[r.club]?.name}</span><span>${int(r.rating)}</span></div><div><span class="muted">Margin over ${clubs.byId[r.runner_up]?.name ?? '—'}</span><span>${r.margin}</span></div>`);
        })
        .on('mouseleave', () => tip.style('display', 'none'));
    };
    draw();
    const ro = new ResizeObserver(draw); ro.observe(el); return () => ro.disconnect();
  }, [rows, clubs]);
  return <div className="chart" ref={ref} />;
}

export default function Eras({ clubs }: { clubs: ClubIndex }) {
  const { measure } = useMeasure();
  const ones0 = useView<One>('number_ones');
  const kings0 = useView<King>('decade_kings');
  const strength0 = useView<Strength>('league_strength');
  const dyn0 = useView<Dyn>('dynasties');
  const pick = <T extends { measure: string }>(s: { data?: T[]; error?: string }) =>
    ({ data: s.data?.filter((r) => r.measure === measure), error: s.error });
  const ones = useMemo(() => pick(ones0), [ones0, measure]); // eslint-disable-line react-hooks/exhaustive-deps
  const kings = useMemo(() => pick(kings0), [kings0, measure]); // eslint-disable-line react-hooks/exhaustive-deps
  const strength = useMemo(() => pick(strength0), [strength0, measure]); // eslint-disable-line react-hooks/exhaustive-deps
  const dyn = useMemo(() => pick(dyn0), [dyn0, measure]); // eslint-disable-line react-hooks/exhaustive-deps
  const [topN, setTopN] = useState(5);

  const reigns = useMemo(() => {
    const out: { club: number; country: string; from: number; to: number; n: number }[] = [];
    (ones.data ?? []).forEach((r) => {
      const last = out.at(-1);
      if (last && last.club === r.club && last.to === r.season - 1) { last.to = r.season; last.n += 1; }
      else out.push({ club: r.club, country: r.country, from: r.season, to: r.season, n: 1 });
    });
    return out.filter((r) => r.n >= 3).sort((a, b) => b.n - a.n);
  }, [ones.data]);

  const strengthSeries: Series[] = useMemo(() => COUNTRY_ORDER.map((c) => ({
    key: c, label: COUNTRIES[c], color: countryColor(c),
    points: (strength.data ?? []).filter((r) => r.country === c).map((r) => ({ x: new Date(Date.UTC(r.season + 1, 4, 31)), y: r.avg_top_flight })),
  })).filter((s) => s.points.length), [strength.data]);

  const decades = useMemo(() => d3.groups(kings.data ?? [], (k) => k.decade), [kings.data]);

  return (
    <div className="page">
      <Card title="Top-rated club of each season" note="Each bar is a season, coloured by the leader's country; height is the leader's margin over the runner-up. Hover for details.">
        <MeasureNote />
        <div className="legend">{COUNTRY_ORDER.map((c) => <span key={c}><i style={{ background: countryColor(c) }} />{COUNTRIES[c]}</span>)}</div>
        {ones.data ? <OnesChart rows={ones.data} clubs={clubs} /> : <Status error={ones.error} />}
        <div className="reigns">{reigns.map((r) => (
          <span key={`${r.club}${r.from}`} style={{ borderColor: countryColor(r.country) }}>
            {clubs.byId[r.club]?.name} · {seasonLabel(r.from)}–{seasonLabel(r.to)} ({r.n})</span>))}
        </div>
      </Card>

      <Card title="Best clubs of each decade" note={`Average ${measure === 'perf' ? 'whole-season' : 'end-of-season'} rating above the average top-flight club, top-flight seasons only, at least three seasons in the decade. The 1960s cover 1965–69.`}>
        {kings.data ? (
          <div className="decades">{decades.map(([dec, list]) => (
            <div className="decade" key={dec}>
              <h3>{dec}s</h3>
              <ol>{list.map((k) => (
                <li key={k.club}><span className="muted" style={{ width: 16 }}>{k.pos}</span><Badge club={clubs.byId[k.club]} size={18} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{clubs.byId[k.club]?.name}</span>
                  <span className="num">+{Math.round(k.avg_above_field)}</span></li>))}</ol>
            </div>))}
          </div>
        ) : <Status error={kings.error} />}
      </Card>

      <Card title="League strength over time" note={`Average ${measure === 'perf' ? 'whole-season' : 'end-of-season'} rating of each country's top-flight clubs. Leagues rise and fall against each other through European results.`}>
        <div className="legend">{strengthSeries.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}</div>
        {strength.data ? <LineChart series={strengthSeries} gapDays={800} height={360} shadeBefore={new Date(Date.UTC(1965, 6, 1))}
                                    xFormat={(d) => 'Season ' + seasonLabel(d.getUTCFullYear() - 1)} /> : <Status error={strength.error} />}
      </Card>

      <Card title="Dynasties" note={`The longest unbroken runs of ${measure === 'perf' ? 'whole-season ratings' : 'season-end finishes'} in the top places among all clubs in the seven leagues, since 1965.`}>
        <div className="controls"><Seg label="Top places" value={topN} onChange={setTopN} options={[[1, 'Top 1'], [3, 'Top 3'], [5, 'Top 5'], [10, 'Top 10']]} /></div>
        {dyn.data ? (
          <Table rowKey={(r) => `${r.club}-${r.from_season}`} rows={dyn.data.filter((d) => d.top_n === topN)} initial={['seasons', 'desc']} limit={25} cols={[
            { key: 'pos', label: '#', num: true, render: (r) => <span className="rank">{r.pos}</span> },
            { key: 'club', label: 'Club', render: (r) => <ClubName club={clubs.byId[r.club]} /> },
            { key: 'span', label: 'Seasons' },
            { key: 'seasons', label: 'Length', num: true },
            { key: 'avg_rank', label: 'Average rank', num: true, render: (r) => r.avg_rank.toFixed(1) },
            { key: 'seasons_at_1', label: 'At #1', num: true },
          ]} />
        ) : <Status error={dyn.error} />}
      </Card>
    </div>
  );
}
