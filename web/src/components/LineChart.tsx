import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

export type Point = { x: Date; y: number };
export type Series = { key: string; label: string; color: string; points: Point[] };
export type Marker = { key: string; x: Date; y: number; color: string; shape: 'diamond' | 'ring' | 'square'; label: string };

type Props = {
  series: Series[];
  markers?: Marker[];
  height?: number;
  invert?: boolean;          // rank: 1 at the top
  log?: boolean;
  zero?: boolean;            // draw the y = 0 line
  gapDays?: number;          // break a line across gaps longer than this
  shadeBefore?: Date;        // burn-in shading
  yLabel?: string;
  format?: (v: number) => string;
  xFormat?: (d: Date) => string;
};

export default function LineChart({ series, markers = [], height = 380, invert, log, zero, gapDays = 200,
  shadeBefore, yLabel, format = (v) => String(Math.round(v)), xFormat = d3.utcFormat('%b %Y') }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const draw = () => {
      el.querySelector('svg')?.remove();
      el.querySelector('.tip')?.remove();
      const width = el.clientWidth || 800;
      const m = { t: 14, r: 16, b: 28, l: 48 };
      const sorted = series.map((s) => ({ ...s, points: [...s.points].sort((a, b) => +a.x - +b.x) }));
      const all = sorted.flatMap((s) => s.points);
      if (!all.length) return;
      const x = d3.scaleUtc().domain(d3.extent(all, (p) => p.x) as [Date, Date]).range([m.l, width - m.r]);
      const [lo, hi] = d3.extent(all, (p) => p.y) as [number, number];
      const y = log
        ? d3.scaleLog().domain([Math.max(1, lo), Math.max(hi, 2)]).range(invert ? [m.t, height - m.b] : [height - m.b, m.t]).nice()
        : d3.scaleLinear().domain(zero ? [Math.min(lo, 0), Math.max(hi, 0)] : [lo, hi]).nice().range(invert ? [m.t, height - m.b] : [height - m.b, m.t]);

      const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${width} ${height}`).attr('role', 'img')
        .attr('aria-label', `${yLabel ?? 'Values'} over time for ${series.map((s) => s.label).join(', ')}`);
      const defs = svg.append('defs');
      const glow = defs.append('filter').attr('id', 'glow').attr('x', '-20%').attr('y', '-20%').attr('width', '140%').attr('height', '140%');
      glow.append('feGaussianBlur').attr('stdDeviation', 2.2).attr('result', 'b');
      const merge = glow.append('feMerge'); merge.append('feMergeNode').attr('in', 'b'); merge.append('feMergeNode').attr('in', 'SourceGraphic');

      if (shadeBefore && x.domain()[0] < shadeBefore) {
        svg.append('rect').attr('x', m.l).attr('y', m.t).attr('width', Math.max(0, x(shadeBefore) - m.l)).attr('height', height - m.t - m.b)
          .attr('fill', 'rgba(63,208,255,.04)');
        svg.append('text').attr('x', m.l + 6).attr('y', m.t + 12).attr('fill', '#44556f').attr('font-size', 10).text('BURN-IN');
      }
      svg.append('g').attr('class', 'gridline').attr('transform', `translate(${m.l},0)`)
        .call(d3.axisLeft(y).ticks(6, log ? '~s' : undefined).tickSize(-(width - m.l - m.r)).tickFormat(() => ''))
        .call((g) => g.select('.domain').remove());
      svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${height - m.b})`).call(d3.axisBottom(x).ticks(width / 90));
      svg.append('g').attr('class', 'axis').attr('transform', `translate(${m.l},0)`)
        .call(log ? d3.axisLeft(y).ticks(6, '~s') : d3.axisLeft(y).ticks(6).tickFormat((v) => format(+v)));
      if (zero && !log) svg.append('line').attr('x1', m.l).attr('x2', width - m.r).attr('y1', y(0)).attr('y2', y(0))
        .attr('stroke', 'rgba(63,208,255,.35)').attr('stroke-dasharray', '3 4');

      const gap = gapDays * 864e5;
      const line = d3.line<Point>().x((p) => x(p.x)).y((p) => y(p.y)).curve(d3.curveMonotoneX);
      sorted.forEach((s) => {
        // split into runs at gaps
        const runs: Point[][] = [];
        s.points.forEach((p, i) => {
          if (i === 0 || +p.x - +s.points[i - 1].x > gap) runs.push([]);
          runs[runs.length - 1].push(p);
        });
        const g = svg.append('g');
        runs.forEach((r) => {
          if (r.length === 1) g.append('circle').attr('cx', x(r[0].x)).attr('cy', y(r[0].y)).attr('r', 2).attr('fill', s.color);
          else g.append('path').attr('d', line(r)).attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', 2)
            .attr('filter', 'url(#glow)').attr('stroke-linejoin', 'round');
        });
      });
      markers.forEach((mk) => {
        const cx = x(mk.x), cy = y(mk.y);
        const g = svg.append('g').attr('transform', `translate(${cx},${cy})`);
        g.append('title').text(mk.label);
        if (mk.shape === 'diamond') g.append('rect').attr('x', -4.5).attr('y', -4.5).attr('width', 9).attr('height', 9)
          .attr('transform', 'rotate(45)').attr('fill', mk.color).attr('stroke', '#05080f').attr('stroke-width', 1.5);
        else if (mk.shape === 'square') g.append('rect').attr('x', -3.5).attr('y', -3.5).attr('width', 7).attr('height', 7)
          .attr('fill', mk.color).attr('stroke', '#05080f').attr('stroke-width', 1.5);
        else g.append('circle').attr('r', 4.5).attr('fill', '#05080f').attr('stroke', mk.color).attr('stroke-width', 2);
      });

      // hover readout
      const tip = d3.select(el).append('div').attr('class', 'tip').style('display', 'none');
      const rule = svg.append('line').attr('y1', m.t).attr('y2', height - m.b).attr('stroke', 'rgba(63,208,255,.5)').style('display', 'none');
      const dots = svg.append('g');
      const bis = d3.bisector<Point, Date>((p) => p.x).center;
      svg.append('rect').attr('x', m.l).attr('y', m.t).attr('width', width - m.l - m.r).attr('height', height - m.t - m.b)
        .attr('fill', 'transparent')
        .on('mousemove', (ev) => {
          const [px] = d3.pointer(ev);
          const at = x.invert(px);
          const hits = sorted.map((s) => {
            const p = s.points[bis(s.points, at)];
            return p && Math.abs(+p.x - +at) < gap / 2 ? { s, p } : null;
          }).filter(Boolean) as { s: Series; p: Point }[];
          if (!hits.length) { tip.style('display', 'none'); rule.style('display', 'none'); dots.selectAll('*').remove(); return; }
          rule.style('display', null).attr('x1', px).attr('x2', px);
          dots.selectAll('*').remove();
          hits.forEach(({ s, p }) => dots.append('circle').attr('cx', x(p.x)).attr('cy', y(p.y)).attr('r', 4).attr('fill', s.color).attr('stroke', '#05080f'));
          hits.sort((a, b) => (invert ? a.p.y - b.p.y : b.p.y - a.p.y));
          tip.style('display', null).html(`<b>${xFormat(hits[0].p.x)}</b>` + hits.map(({ s, p }) =>
            `<div><span style="color:${s.color}">${s.label}</span><span>${format(p.y)}</span></div>`).join(''));
          const w = (tip.node() as HTMLDivElement).offsetWidth;
          tip.style('left', `${px + 14 + w > width ? px - w - 14 : px + 14}px`).style('top', `${m.t + 8}px`);
        })
        .on('mouseleave', () => { tip.style('display', 'none'); rule.style('display', 'none'); dots.selectAll('*').remove(); });
    };
    draw();
    const ro = new ResizeObserver(() => draw());
    ro.observe(el);
    return () => ro.disconnect();
  }, [series, markers, height, invert, log, zero, gapDays, shadeBefore, yLabel, format, xFormat]);

  return <div className="chart" ref={ref} style={{ minHeight: height * 0.5 }} />;
}
