export const COUNTRIES: Record<string, string> = {
  ENG: 'England', ESP: 'Spain', GER: 'Germany', ITA: 'Italy', FRA: 'France', POR: 'Portugal', NED: 'Netherlands',
  SCO: 'Scotland', BEL: 'Belgium', TUR: 'Turkey', GRE: 'Greece',
};
export const COUNTRY_ORDER = Object.keys(COUNTRIES);

// Country series colours, tuned for the dark background.
export const COUNTRY_COLOR: Record<string, string> = {
  ENG: '#5ab8ff', ESP: '#ff6b6b', GER: '#ffd166', ITA: '#4ade80', FRA: '#a78bfa', POR: '#f472b6', NED: '#fb923c',
  SCO: '#2dd4bf', BEL: '#e879f9', TUR: '#f87171', GRE: '#93c5fd',
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
  'ENG-FAC': 'FA Cup', 'ENG-LC': 'League Cup', 'ENG-PO': 'Play-off', UCL: 'European Cup', UEL: 'UEFA Cup', UECL: 'Conference League',
  UCWC: "Cup Winners' Cup", FAIRS: 'Fairs Cup', USC: 'Super Cup', 'ESP-CDR': 'Copa del Rey', 'GER-DFB': 'DFB-Pokal',
  'ITA-CI': 'Coppa Italia', 'FRA-CDF': 'Coupe de France', 'NED-KNVB': 'KNVB Cup', 'POR-TP': 'Taça',
  'SCO-SC': 'Scottish Cup', 'BEL-BC': 'Belgian Cup', 'TUR-TC': 'Turkish Cup', 'GRE-GC': 'Greek Cup',
};
export const EUROPEAN = ['UEL', 'UCWC', 'FAIRS', 'UECL'];
export const DOMESTIC_CUPS = ['ENG-FAC', 'ENG-LC', 'ESP-CDR', 'GER-DFB', 'ITA-CI', 'FRA-CDF', 'NED-KNVB', 'POR-TP',
  'SCO-SC', 'BEL-BC', 'TUR-TC', 'GRE-GC'];

export const initials = (name: string) =>
  name.replace(/\b(FC|AC|AS|SC|CF|CD|SL|SV|VfB|VfL|US|SSC|AFC|RC|UD|SD|1\.)\b/g, '').trim().split(/[\s-]+/)
    .filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || name.slice(0, 2).toUpperCase();
