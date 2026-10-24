// Loads the static JSON snapshot written by `python -m football_elo export`.
import { useEffect, useState } from 'react';

const BASE = import.meta.env.BASE_URL + 'data/';
const cache = new Map<string, Promise<unknown>>();

export function fetchJSON<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    // Revalidate every file with the server (a 304 when unchanged): club ids are positions in clubs.json,
    // so a cached clubs.json from before a deploy mixed with fresh tables would mislabel clubs.
    cache.set(path, fetch(BASE + path, { cache: 'no-cache' }).then((r) => {
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json();
    }).catch((e) => { cache.delete(path); throw e; }));
  }
  return cache.get(path) as Promise<T>;
}

export type Rows = { cols: string[]; rows: unknown[][] };

/** Column-array rows -> objects. */
export function objects<T>(t: Rows): T[] {
  return t.rows.map((r) => Object.fromEntries(t.cols.map((c, i) => [c, r[i]])) as T);
}

export type State<T> = { data?: T; error?: string };

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): State<T> {
  const [s, setS] = useState<State<T>>({});
  useEffect(() => {
    let live = true;
    setS({});
    fn().then((data) => live && setS({ data }), (e) => live && setS({ error: String(e) }));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return s;
}

export const useJSON = <T,>(path: string | null) =>
  useAsync<T | undefined>(() => (path ? fetchJSON<T>(path) : Promise.resolve(undefined)), [path]);

// ---------------------------------------------------------------- clubs
export type Club = {
  id: number; slug: string; name: string; country: string | null; league_club: boolean; has_page: boolean;
  top_flight_seasons: number | null; first_season: number | null; last_season: number | null;
  peak_elo: number | null; peak_season: number | null; seasons_at_1: number | null; seasons_top10: number | null;
  best_rank: number | null; best_decade: number | null;
  seasons_at_1_perf: number | null; seasons_top10_perf: number | null; best_rank_perf: number | null; best_decade_perf: number | null;
  logo: string | null; primary: string | null; secondary: string | null;
};

export type ClubIndex = { list: Club[]; byId: Club[]; byName: Map<string, Club>; bySlug: Map<string, Club>; pages: Club[] };

let clubsP: Promise<ClubIndex> | null = null;
export function loadClubs(): Promise<ClubIndex> {
  clubsP ??= fetchJSON<Rows>('clubs.json').then((t) => {
    const list = objects<Club>(t);
    const byId: Club[] = [];
    list.forEach((c) => { byId[c.id] = c; });
    return {
      list, byId,
      byName: new Map(list.map((c) => [c.name, c])),
      bySlug: new Map(list.map((c) => [c.slug, c])),
      pages: list.filter((c) => c.has_page).sort((a, b) => a.name.localeCompare(b.name)),
    };
  });
  return clubsP;
}
export const useClubs = () => useAsync(loadClubs, []);

export type Meta = {
  run_id: number; finished_at: string; last_match_date: string;
  competitions: Record<string, { name: string; type: string; country: string | null }>;
};
export const useMeta = () => useJSON<Meta>('meta.json');

// ---------------------------------------------------------------- one club
export type Match = {
  date: string; comp: number; opp: number; venue: 'h' | 'a' | 'n'; gf: number; ga: number;
  pf: number | null; pa: number | null; elo: number; opp_elo: number; exp: number; delta: number;
};
export type Season = {
  season: number; tier: number; elo_end: number; elo_peak: number; above_field: number;
  world_rank: number; league_rank: number;
  perf: number | null; above_perf: number | null; world_rank_perf: number | null; league_rank_perf: number | null;
};
export type ClubFile = { id: number; months: [string, number][]; seasons: Season[]; matches: Match[] };

export function loadClub(slug: string): Promise<ClubFile> {
  return fetchJSON<{ id: number; months: [string, number][]; seasons: Rows; matches: Rows }>(`club/${slug}.json`)
    .then((f) => ({ id: f.id, months: f.months, seasons: objects<Season>(f.seasons), matches: objects<Match>(f.matches) }));
}

export const useCompetitions = () => useJSON<string[]>('competitions.json');

// ---------------------------------------------------------------- month-end tables
export type TableRow = { club: number; elo: number; tier: number; rank: number };
export function loadYear(year: number): Promise<Record<string, TableRow[]>> {
  return fetchJSON<{ cols: string[]; months: Record<string, number[][]> }>(`tables/${year}.json`).then((f) =>
    Object.fromEntries(Object.entries(f.months).map(([m, rows]) =>
      [m, rows.map(([club, elo, tier, rank]) => ({ club, elo, tier, rank }))])));
}

export function viewRows<T>(name: string): Promise<T[]> {
  return fetchJSON<Rows>(`${name}.json`).then((t) => objects<T>(t));
}
export const useView = <T,>(name: string) => useAsync(() => viewRows<T>(name), [name]);
