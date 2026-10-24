export const COUNTRIES: Record<string, string> = {
  ENG: 'England', ESP: 'Spain', GER: 'Germany', ITA: 'Italy', FRA: 'France', POR: 'Portugal', NED: 'Netherlands',
  SCO: 'Scotland', BEL: 'Belgium', TUR: 'Turkey', GRE: 'Greece',
  AUT: 'Austria', SUI: 'Switzerland', SWE: 'Sweden', DEN: 'Denmark', ROU: 'Romania', HUN: 'Hungary',
  URS: 'Soviet Union', YUG: 'Yugoslavia', TCH: 'Czechoslovakia', GDR: 'East Germany',
  RUS: 'Russia', UKR: 'Ukraine', CZE: 'Czechia', SVK: 'Slovakia', SRB: 'Serbia', CRO: 'Croatia',
};
export const COUNTRY_ORDER = Object.keys(COUNTRIES);

// Country series colours, tuned for the dark background.
export const COUNTRY_COLOR: Record<string, string> = {
  ENG: '#5ab8ff', ESP: '#ff6b6b', GER: '#ffd166', ITA: '#4ade80', FRA: '#a78bfa', POR: '#f472b6', NED: '#fb923c',
  SCO: '#2dd4bf', BEL: '#e879f9', TUR: '#f87171', GRE: '#93c5fd',
  AUT: '#fca5a5', SUI: '#fecaca', SWE: '#fde047', DEN: '#fb7185', ROU: '#facc15', HUN: '#86efac',
  URS: '#ef4444', YUG: '#60a5fa', TCH: '#38bdf8', GDR: '#c4b5fd',
  RUS: '#f97316', UKR: '#eab308', CZE: '#0ea5e9', SVK: '#7dd3fc', SRB: '#3b82f6', CRO: '#f43f5e',
};
export const countryColor = (c: string | null | undefined) => (c && COUNTRY_COLOR[c]) || '#6b7a90';

export const seasonLabel = (s: number) => `${s}/${String((s + 1) % 100).padStart(2, '0')}`;
export const int = (v: number | null | undefined) => (v == null ? '—' : Math.round(v).toLocaleString('en-GB'));
export const signed = (v: number | null | undefined) => (v == null ? '—' : (v > 0 ? '+' : '') + Math.round(v));
export const pct = (v: number) => `${Math.round(v * 100)}%`;
export const dateLong = (d: string) =>
  new Date(d + (d.length === 7 ? '-01' : '') + 'T00:00:00Z').toLocaleDateString('en-GB', { day: d.length > 7 ? 'numeric' : undefined, month: 'short', year: 'numeric', timeZone: 'UTC' });

export const COMP_SHORT: Record<string, string> = {
  'ENG-L': 'League', 'ESP-L': 'League', 'GER-L': 'League', 'ITA-L': 'League', 'FRA-L': 'League', 'NED-L': 'League', 'POR-L': 'League',
  'SCO-L': 'League', 'BEL-L': 'League', 'TUR-L': 'League', 'GRE-L': 'League', 'GER-CH': 'German final round',
  'AUT-L': 'League', 'SUI-L': 'League', 'SWE-L': 'League', 'DEN-L': 'League', 'ROU-L': 'League', 'HUN-L': 'League',
  'URS-L': 'Soviet league', 'YUG-L': 'Yugoslav league', 'TCH-L': 'Czechoslovak league', 'GDR-L': 'DDR-Oberliga',
  'RUS-L': 'League', 'UKR-L': 'League', 'CZE-L': 'League', 'SVK-L': 'League', 'SRB-L': 'League', 'CRO-L': 'League',
  'ENG-FAC': 'FA Cup', 'ENG-LC': 'League Cup', 'ENG-PO': 'Play-off', UCL: 'European Cup', UEL: 'UEFA Cup', UECL: 'Conference League',
  UCWC: "Cup Winners' Cup", FAIRS: 'Fairs Cup', USC: 'Super Cup', 'ESP-CDR': 'Copa del Rey', 'GER-DFB': 'DFB-Pokal',
  'ITA-CI': 'Coppa Italia', 'FRA-CDF': 'Coupe de France', 'NED-KNVB': 'KNVB Cup', 'POR-TP': 'Taça',
  'SCO-SC': 'Scottish Cup', 'BEL-BC': 'Belgian Cup', 'TUR-TC': 'Turkish Cup', 'GRE-GC': 'Greek Cup',
};
export const EUROPEAN = ['UEL', 'UCWC', 'FAIRS', 'UECL'];
// League titles (config/league_champions.csv), in country order: competition -> honours label.
const DEMONYM: Record<string, string> = {
  ENG: 'English', ESP: 'Spanish', GER: 'German', ITA: 'Italian', FRA: 'French', POR: 'Portuguese', NED: 'Dutch',
  SCO: 'Scottish', BEL: 'Belgian', TUR: 'Turkish', GRE: 'Greek', AUT: 'Austrian', SUI: 'Swiss', SWE: 'Swedish',
  DEN: 'Danish', ROU: 'Romanian', HUN: 'Hungarian', URS: 'Soviet', YUG: 'Yugoslav', TCH: 'Czechoslovak',
  GDR: 'East German', RUS: 'Russian', UKR: 'Ukrainian', CZE: 'Czech', SVK: 'Slovak', SRB: 'Serbian', CRO: 'Croatian',
};
export const LEAGUE_TITLES: [string, string][] = COUNTRY_ORDER.map((c) => [`${c}-L`, `${DEMONYM[c]} champions`]);
export const DOMESTIC_CUPS = ['ENG-FAC', 'ENG-LC', 'ESP-CDR', 'GER-DFB', 'ITA-CI', 'FRA-CDF', 'NED-KNVB', 'POR-TP',
  'SCO-SC', 'BEL-BC', 'TUR-TC', 'GRE-GC'];

export const initials = (name: string) =>
  name.replace(/\b(FC|AC|AS|SC|CF|CD|SL|SV|VfB|VfL|US|SSC|AFC|RC|UD|SD|1\.)\b/g, '').trim().split(/[\s-]+/)
    .filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || name.slice(0, 2).toUpperCase();
