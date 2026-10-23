// Which season measure the season-based views show:
//   end  - the rating at the end of the season (where a club finished)
//   perf - the whole-season performance rating (how good it was over the season)
import { createContext, useContext, useState, type ReactNode } from 'react';
import type { Club, Season } from './data';

export type Measure = 'end' | 'perf';
const KEY = 'football-elo:measure';

const Ctx = createContext<{ measure: Measure; setMeasure: (m: Measure) => void }>({ measure: 'end', setMeasure: () => {} });

export function MeasureProvider({ children }: { children: ReactNode }) {
  const [measure, set] = useState<Measure>(() => {
    try { return localStorage.getItem(KEY) === 'perf' ? 'perf' : 'end'; } catch { return 'end'; }
  });
  const setMeasure = (m: Measure) => { set(m); try { localStorage.setItem(KEY, m); } catch { /* private mode */ } };
  return <Ctx.Provider value={{ measure, setMeasure }}>{children}</Ctx.Provider>;
}
export const useMeasure = () => useContext(Ctx);

export const MEASURE_LABEL: Record<Measure, string> = { end: 'End of season', perf: 'Whole season' };
export const MEASURE_NOTE: Record<Measure, string> = {
  end: 'Seasons are judged on the rating at the end of the season: where each club finished.',
  perf: 'Seasons are judged on a whole-season performance rating: the rating that best explains every result that season, so a strong start counts as much as a strong finish.',
};

/** A season row's figures under the chosen measure. */
export function seasonFigures(s: Season, m: Measure) {
  return m === 'perf' && s.perf != null
    ? { rating: s.perf, above: s.above_perf!, world: s.world_rank_perf!, league: s.league_rank_perf! }
    : { rating: s.elo_end, above: s.above_field, world: s.world_rank, league: s.league_rank };
}

/** A club's career figures under the chosen measure. */
export function careerFigures(c: Club, m: Measure) {
  return m === 'perf'
    ? { at1: c.seasons_at_1_perf, top10: c.seasons_top10_perf, best: c.best_rank_perf, decade: c.best_decade_perf }
    : { at1: c.seasons_at_1, top10: c.seasons_top10, best: c.best_rank, decade: c.best_decade };
}

/** One line saying which season measure a card is showing. */
export function MeasureNote() {
  const { measure } = useMeasure();
  return <p className="measure-note"><b>{MEASURE_LABEL[measure]}.</b> {MEASURE_NOTE[measure]}</p>;
}
