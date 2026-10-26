# football-elo

Club Elo-style ratings for English football (tiers 1–4), Spain, Germany, Italy, France and the Netherlands
(tiers 1–2), and the top flights of Portugal, Scotland, Belgium, Turkey, Greece, Austria, Switzerland,
Sweden, Denmark, Romania, Hungary, the Soviet Union, Yugoslavia, Czechoslovakia and East Germany (and their
successors Russia, Ukraine, Czechia, Slovakia, Serbia and Croatia), from 1955 to now, kept
current weekly in Supabase. Ratings include the FA Cup, League Cup, EFL play-offs,
the other countries' domestic cups from 2012/13, and the European club competitions. The Supabase project is
`football-elo` (ref `mukyuvlvwozeihsrjjis`, Sydney).

## Quick start

```
pip install -e .[dev]
cp .env.example .env                  # add the database password
python -m football_elo build          # fetch sources, build silver + gold locally, score calibration
python -m football_elo load           # full rebuild into Supabase
python -m football_elo update         # weekly incremental update
python -m football_elo validate       # league source overlap check (1993-2025)
python -m football_elo calibrate --fit k_cup k_europe foreign
python tools/derive_aliases.py        # map club names for new sources (review the output)
python tools/link_league_names.py ESP # link a new country's league names to existing clubs
python tools/link_grid_names.py rsssf ITA-L NED-L   # link names from date-less sources (RSSSF, Wikipedia)
python tools/clubelo_names.py         # map Club Elo names (calibration)
pytest
```

**Config files**
- [config/elo.yaml](config/elo.yaml) holds all rating parameters, the sources, and which source covers which
  competition and years.
- [config/club_aliases.csv](config/club_aliases.csv) maps each source's club names or IDs to one canonical name.

## Competitions and sources

| Competition | Code | Sources (priority order) |
|---|---|---|
| England, tiers 1–4 | `ENG-L` | engsoccerdata to 2024/25 → football-data.co.uk (2022/23 gap, and 2025/26 on) |
| Spain, tiers 1–2 | `ESP-L` | engsoccerdata (tier 1) to 2024/25 → football-data (tier 2 from 1996/97; all from 2025/26) → Wikipedia grids (tier 2 1955/56–1995/96, and the partial 2001/02–2003/04) |
| Germany, tiers 1–2 | `GER-L` | engsoccerdata (from 1963; tier 2 from 1974) to 2024/25 → football-data |
| Italy, tiers 1–2 | `ITA-L` | engsoccerdata (tier 1) to 2024/25 → RSSSF (tier 2 1955/56–1996/97, and the partial 2002/03 and 2004/05) → football-data (tier 2 from 1997/98) |
| Portugal, tier 1 | `POR-L` | RSSSF results grids 1955/56–1993/94 (dates assigned) → engsoccerdata 1994/95–2024/25 → football-data |
| Scotland, Belgium, Turkey, Greece (tier 1) | `SCO-L`, `BEL-L`, `TUR-L`, `GRE-L` | Wikipedia results grids 1955/56–1993/94 (dates assigned; Turkey from 1958/59, Greece's 1956–58 Panhellenic final rounds) → engsoccerdata 1994/95–2024/25 → football-data |
| Austria, Switzerland, Sweden, Denmark, Romania, Hungary (tier 1) | `AUT-L`, `SUI-L`, `SWE-L`, `DEN-L`, `ROU-L`, `HUN-L` | Wikipedia results grids 1955/56–2025/26 (dates assigned; calendar-year seasons from April) → 2026/27 (Sweden's 2026) dated: ESPN (Austria, Sweden, Denmark), football-data's extra leagues (Switzerland, Romania); Hungary none yet |
| Soviet Union, Yugoslavia, Czechoslovakia, East Germany (tier 1) | `URS-L`, `YUG-L`, `TCH-L`, `GDR-L` | Wikipedia results grids 1955–1991 (1992/93 Czechoslovakia, 1990/91 East Germany) |
| Russia, Ukraine, Czechia, Slovakia, Serbia, Croatia (tier 1) | `RUS-L`, `UKR-L`, `CZE-L`, `SVK-L`, `SRB-L`, `CRO-L` | Wikipedia results grids from the split (1992 or 1993/94) to 2025/26; Serbia's includes Montenegro to 2005/06 → 2026/27 dated from ESPN (Russia only; the others have no free dated source yet) |
| German championship final round | `GER-CH` | RSSSF 1955/56–1962/63 (qualifiers, groups and final between the Oberliga champions) |
| Netherlands, tiers 1–2 | `NED-L` | engsoccerdata (tier 1) 1956/57–2024/25 → RSSSF (tier 2 1956/57–2024/25) → football-data (tier 1) |
| France, tiers 1–2 | `FRA-L` | engsoccerdata (tier 1; 1993/94 missing) to 2024/25 → football-data (tier 2 from 1996/97) → RSSSF (the partial 2003/04) → Wikipedia grid (the partial 2002/03) |
| Play-offs | `ENG-PO` | engsoccerdata to 2015/16 → ESPN |
| FA Cup (Round 1 on) | `ENG-FAC` | engsoccerdata to 2018/19 → Transfermarkt to 2025/26 → ESPN |
| League Cup | `ENG-LC` | engsoccerdata to 2018/19 → ESPN |
| Copa del Rey, DFB-Pokal, Coppa Italia, KNVB Cup | `ESP-CDR`, `GER-DFB`, `ITA-CI`, `NED-KNVB` | Transfermarkt 2012/13–2025/26 → ESPN |
| Taça de Portugal | `POR-TP` | Transfermarkt 2012/13–2025/26 (some seasons from the last 8 only) → ESPN (2021/22 on, and 2026/27) |
| Coupe de France (last 64 on) | `FRA-CDF` | ESPN from 2015/16 |
| European Cup / Champions League | `UCL` | engsoccerdata to 2017/18 → Transfermarkt → ESPN |
| UEFA Cup / Europa League | `UEL` | DataRozhlas to 2011/12 → Transfermarkt → ESPN |
| Conference League | `UECL` | Transfermarkt → ESPN |
| Cup Winners' Cup | `UCWC` | DataRozhlas (1960–99) |
| Fairs Cup | `FAIRS` | DataRozhlas (1955–71) |
| UEFA Super Cup | `USC` | Transfermarkt → ESPN |

How sources combine:
- Each competition lists its sources in priority order. A later source only fills (season, tier) blocks
  that an earlier one lacks, so overlaps are never double counted. All source rows are still kept in bronze,
  so the overlaps can be checked.
- Two window options: `replace_partial: x` lets a later source take over a block where the earlier sources
  hold under x times its match count (football-data's partial Segunda 2001/02–2003/04), and `tiers` limits a
  window to some tiers (RSSSF and Wikipedia tier-1 sections are read only to link club names).
- Transfermarkt is [dcaribou/transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets). Its
  updates stopped in July 2026, so the 2026/27 season onward comes from ESPN's public scoreboard API. That API
  is unofficial and undocumented, so expect occasional breakage.
- DataRozhlas is Wikipedia data, scraped by
  [DataRozhlas/evropske-pohary](https://github.com/DataRozhlas/evropske-pohary). Credit Wikipedia (CC BY-SA)
  if any of it is published.

**Known gaps and data quality**
- **Date-less sources:** Portugal before 1994/95, Serie B before 1997/98, the Segunda before 1996/97 and the
  Eerste Divisie before 2004/05 come from results grids or round lists without (full) dates, as does
  Ligue 2 2002/03 (`src/football_elo/grids.py`, `sources._schedule`). Dates are printed ones where the page
  has them (Eerste Divisie from 2004/05, some Serie B seasons, Serie B 2002/03 and 2004/05, Ligue 2 2003/04), else one round a week from the round order (Serie B from
  1961/62), else a synthetic double round-robin on Sundays from September. So the order of matches within
  those seasons is approximate. Their club names are linked by fixtures within a season instead of by date
  (`tools/link_grid_names.py`, which also holds a short list of hand links).
  Credits: RSSSF (Portugal: Jorge Miguel Teixeira; Italy: Maurizio Mariani, Serie B stages via Sorin
  Arotaritei; Netherlands: Karel Stokkermans and others) and Wikipedia (CC BY-SA, results cited to BDFutbol).
- **Source slips handled in the parsers:** letter O for zero, run-together cells, blank cells for withdrawn
  clubs (placed by column), abandoned matches, and a grid with two clubs' rows swapped (Serie B 1966/67,
  where the round list wins).
- **Second tiers still missing:** France before 1996/97 (no free match-level source found: RSSSF and
  Wikipedia have final tables only), Portugal (no tier 2 at all), and the Eerste Divisie from 2025/26 (RSSSF has only the table so far).
  Football-data's partial Serie B and Ligue 2 files of 2002–04 are filled from RSSSF and Wikipedia. Promoted clubs from a
  missing tier start at the rating below the top flight.
- **Reserve teams** (Real Madrid Castilla, Barcelona B, Jong Ajax, ...) play in the Segunda and Eerste
  Divisie and are rated as clubs of their own.
- **Wrong files from football-data:** some early files hold another league's data. For example, 1993/94 `P1`
  and three early `SP2` files contain La Liga. The reader keeps only rows labelled with the requested
  division.
- **Thin seasons:** the build warns about any competition season with under half its usual match count, so a
  partial source can't silently block a complete one. That is how the 2016/17–2017/18 Champions League bug
  was caught.
- **Big-5 coverage:**
  - The Bundesliga starts in 1963. Before that, German clubs are rated from the national championship final
    rounds (`GER-CH`) and European matches: the regional Oberligen have no free match-level source (RSSSF and
    Wikipedia have final tables only). Final-round clubs start at the top-flight rating (`start_tier` in
    config), but get no league season, so they appear in season rankings only from 1963/64.
  - Scotland, Belgium, Turkey and Greece: top flight only, like Portugal. Their starting levels are lower
    than the big seven's (Scotland −125, Belgium −100, Turkey and Greece −250): starting level left Turkish
    and Greek clubs 25–30pp worse in Europe than predicted in the 1960s. Cypriot champions played in the
    Greek league 1967/68–1973/74; `club_countries` in config keeps them Cypriot.
  - The sixteen leagues added 2026-10-24 (the other countries whose clubs won or reached European finals)
    are also top flight only, from Wikipedia's season grids throughout: no source has their current season
    yet (2026/27, Sweden's 2026), so they stop at 2025/26 for now. Championship and relegation groups count;
    promotion and qualification groups (and the Nationalliga B rounds on the Swiss pages) don't. Starting
    levels were tuned on European bias over each league's first two decades: Soviet Union 1551 (−10 on the
    big seven), Czechoslovakia 1529, Hungary and Yugoslavia 1472, Romania 1460, East Germany 1450, Sweden
    1391, Switzerland 1401, Austria 1362, Denmark 1359. A successor league's level only sets clubs new to the
    top flight after the split; the rest carry their rating over.
  - **A club's country can change.** Each club has a country per season, the country of the league it played
    in (`silver.country_seasons`): Dynamo Kyiv pools with the Soviet Union to 1991 and Ukraine after, Dynamo
    Dresden with East Germany to 1990/91 and Germany after. A season without league games takes the country
    of its other matches (a cup's, or the association a European source names), so Dinamo Tbilisi is Georgian
    after the Soviet league and Budućnost Montenegrin after the Serbian one. On a change the club's rating
    carries over; only its pooled part moves to the new country. The club registry holds each club's latest
    country (used by the weekly update). Before this, East German clubs counted as German and their European
    results lifted West Germany's level (+190 by 1970).
  - Second tiers in Spain and Italy start in 1955 and the Netherlands in 1956; France's in 1996/97, when
    football-data begins.
  - A few football-data files are empty (Ligue 2 1993–96, Serie B 1993–97), and some 2002–04 files are partial
    (filled from other sources, above).
  - Domestic cups outside England start in 2012/13 (the Coupe de France in 2015/16); earlier seasons have no
    source yet. The Taça de Portugal 2020/21 has only its last 8 (Transfermarkt; ESPN starts a season later).
- **engsoccerdata naming:** it names some clubs differently across seasons (e.g. "TSV 1860 Munchen" vs
  "1860 Munchen", "SV Bayer 04 Leverkusen" vs "Bayer Leverkusen"). These are merged through `engsoccerdata`
  alias rows. Successor clubs are kept separate, e.g. ESTAC Troyes vs Troyes AF.
- **Season-specific fixes:** a plain alias can't fix an error that only applies to some seasons, so these go
  in `corrections` in config. Example: engsoccerdata files Gazélec Ajaccio's 2015/16 Ligue 1 season under
  AC Ajaccio.
- **DataRozhlas holes:** the Fairs Cup 1963–66 is thin, and the 1980/81 Cup Winners' Cup first round is
  missing.
- **Undated legs:** DataRozhlas gives both legs of an undated tie the same date. The pipeline spaces them 14
  days apart, and which leg came first is a guess.
- **UEFA qualifiers:** since 2020, ESPN carries them only from the current season. Transfermarkt covers
  2012–2025 in full.
- **Source date errors:** 210 club-days have two matches on the same date, all from wrong dates in the sources.
  They are listed in `data/silver/data_quality.csv` and only affect the order matches are rated in.
- **Club names:**
  - 1,229 clubs exist only in European data. They are named after the shortest source name available
    (ESPN, then Wikipedia, then Transfermarkt).
  - engsoccerdata's cup files spell a few clubs differently from its league file (e.g. "Yeovil Town" vs
    "Yeovil"). Those are mapped through `engsoccerdata` alias rows.
  - Genuinely different clubs with near-identical names are kept apart: Wimbledon vs AFC Wimbledon,
    Bohemians (IRL) vs Bohemians (TCH).

## Layers

| Layer | Local | Supabase |
|---|---|---|
| Bronze | `data/bronze/` raw files | `bronze.source_files`, `bronze.source_matches` (every source row, with the source's own club keys) |
| Silver | `data/silver/*.parquet` | `silver.matches`, `silver.clubs`, `silver.club_aliases`, `silver.competitions` |
| Gold | `data/gold/*.parquet` | `gold.match_ratings`, `gold.club_ratings`, `gold.current_ratings` (view), `gold.ratings_on(date, league_only)`, `gold.runs`, `gold.calibration_scores` |

**`gold.club_ratings`** has the Club Elo From/To grain:
- `valid_from` is the day after a match, and `valid_to` is the club's next match day.
- `valid_to` is null for clubs that played in the latest season. For clubs that have since dropped out, it is
  the last match day of their final season.
- `tier` is the club's league tier that season. It is null for non-league and foreign clubs.
- The current-table view and `ratings_on` list league clubs by default.

### Serving layer (for the dashboard)

Each full load and weekly update ends by calling `gold.refresh_serving()`. That rebuilds the materialized
views below from the new ratings, which takes about 30 seconds:
- `gold.mv_club_seasons`: one row per club per season, with rating, rating above the average top-flight club,
  rank across the five leagues and rank in its league.
- `gold.mv_club_months`: each club's rating at the end of every month it played.
- `gold.mv_club_summary`: one row per club, with its career numbers.
- `gold.mv_number_ones`, `gold.mv_decade_kings`, `gold.mv_league_strength`, `gold.mv_greatest_seasons`,
  `gold.mv_dynasties`, `gold.mv_alltime_parts`, `gold.mv_upsets` and `gold.mv_trophies`: the dashboard's era
  and ranking views.

The dashboard reads only these views, plus `gold.ratings_on(date)` and per-club match lookups. A page query is
then an indexed lookup in milliseconds rather than a 6-second rebuild over every rating period, and page speed
doesn't change as leagues are added. `gold.ratings_on` uses a GiST index on each period's date range.

## Elo engine

```
We = 1 / (10^(-(elo_home - elo_away + HFA) / 400) + 1)     HFA = 0 at neutral venues
Δ  = K · k_mult(type) · √(goal diff) · (R − We)             R = 1 / 0.5 / 0
```

**Match rules**
- Results count after extra time. A penalty shoot-out counts as a draw.
- Two-legged ties are rated as two separate matches.

**Three improvements over plain Club Elo** (all in `config/elo.yaml`; each can be switched off)
- **Dynamic home advantage:** each country's home advantage, and one shared European home advantage, starts
  at 120 in 1955. After every match it moves by `eta` × (result − expected). It learns that home advantage
  was far bigger in the past:

  | Decade | England league | Spain league | European ties |
  |---|---|---|---|
  | 1960s | 112 | 191 | 158 |
  | 1980s | 95 | 160 | 200 |
  | 2020s | 43 | 70 | 72 |

- **League pooling:** 30% of every European rating change also moves the club's whole country (more for a
  country whose clubs played few European games the season before: 0.3 × √(50 / games), at most 60%; since
  2026-10-26, `pool_evidence` in config). A league
  that over- or under-performs in Europe is re-levelled within seasons rather than decades. A club's rating
  is its own part plus its country's level; the level history is in `gold.league_offsets`.
- **Provisional ratings:** a club's first 40 rated matches use K × 2. A foreign club on its European debut,
  or a newly promoted club, reaches its level quickly. New clubs also inherit their country's current level.

**Starting ratings**
- **All five countries start level in 1955** with the same tier gap. European results then set their
  levels, so the model doesn't depend on a judgment about which league was strongest.
- **League clubs** start at their tier's rating. Ratings then carry across tiers and competitions with no
  reset.
- **Newcomers from below:** a club joining a country's lowest modelled tier after its first season starts
  one tier down.
- **Non-league clubs** met in the cups start at the non-league rating. Transfermarkt and ESPN give no
  country for most amateur sides, so a domestic cup's clubs take the cup's country.
- **Foreign clubs** from unmodelled countries start at the foreign rating plus their country's pooled
  level. They are rated only through European matches.

| Parameter | Value |
|---|---|
| K | 15 |
| K multiplier | league 1.0, play-off 1.0, cup 0.5, Europe 1.0 |
| Home advantage | dynamic, from 120 in 1955, eta 1.0, Europe shared |
| League pooling | 0.3 |
| Provisional | first 40 matches at K × 2 |
| Start ratings, every country | tier 1 1585, tier 2 1421 (England also 1257 / 1093), below 1257 (England 929) |
| Foreign start | 1335 |

## Early-era calibration

**The problem.** The first models fitted country starting levels to Club Elo snapshots from 2008 on. That
left the 1960s–80s skewed: Spain rated far too high, Italy too low. The diagnosis, from matches between the
five leagues:
- A fixed 70-point home advantage badly underestimated old-era home advantage. In the 1960s–80s home sides
  in European ties scored 0.69–0.71 against an expected 0.57.
- Strong clubs' away results therefore looked like failures. Spanish clubs scored exactly as expected at
  home but 0.42 against an expected 0.73 away.
- League levels only moved through a handful of European games, so a wrong level persisted for decades.

**Results.** Bias is a country's average result minus expected in European matches between the five
leagues, by decade.

| | Before | After |
|---|---|---|
| Bias between the five leagues, RMS | 6.6 pts | **2.5 pts** |
| 1960s bias, worst country | Germany +19, Spain −17 | all within ±3 |
| European log loss, 1965+ | 0.614 | **0.584** |
| League log loss, 1965+ | 0.6469 | **0.6431** |
| Spearman vs Club Elo | 0.985 | **0.991** |
| RMSE vs Club Elo | 24.6 | 27.5 |

RMSE against Club Elo rises because Club Elo has a fixed home advantage and no pooling, so its country
levels carry the drift this removes. The average Premier League club is now 1838 against Club Elo's 1839.

**Effect on eras.**
- **Top-rated club each season:** Leeds in 1968–69, Mönchengladbach and Bayern through the 70s, Liverpool,
  Hamburg in 1982–84, Milan for 1991–96, then Juventus.
- **1960s decade:** led by Real Madrid, Leeds and Inter, where it used to be four Spanish clubs.

Reproduce with `tools/pool_experiment.py` (bias by country and decade) and `tools/fit_pool.py`.

## Calibration against Club Elo (phases 1–3)

The history below is before the early-era work above.

The targets are every English, Spanish, German, Italian and French club in Tony Elhabr's Club Elo snapshots
(2023-03 to 2026-01). They also include the same countries in Wayback captures of api.clubelo.com (full tables
from 2008, 2017, 2024 and 2025) and Aston Villa's history from 1965. That makes 8,692 club-date comparisons.
The Ipswich capture is empty.

| | England only (phase 1) | + cups, Europe (phase 2) | + big-5 leagues (phase 3) |
|---|---|---|---|
| RMSE, all targets | 28.3 | 25.8 | **24.6** (5 countries) |
| RMSE, England | 28.3 | 25.8 | 26.8 |
| Spearman (rank correlation) | 0.992 | 0.990 | 0.985 |
| League log loss, 1965+ | 0.6563 | 0.6546 | **0.6469** |

**Phase 3 by country**

| Country | RMSE | Bias | Spearman |
|---|---|---|---|
| ENG | 26.8 | −5.8 | 0.990 |
| ESP | 28.3 | +4.0 | 0.990 |
| GER | 20.1 | +2.4 | 0.995 |
| ITA | 24.3 | +0.1 | 0.983 |
| FRA | 20.8 | +2.2 | 0.992 |

**Phase 3 by snapshot**

| Snapshot | RMSE |
|---|---|
| Elhabr 2023–26 | 21.8 |
| 2024-09 | 20.6 |
| 2025-01 | 21.8 |
| 2017-01 | 40.4 |
| 2008 | 48–51 (England and Italy run about 36 low there) |

How the parameters were chosen:
- **K, HFA and the England tier gap** come from the league-only fit. Club Elo's own per-match changes imply
  K≈8.4, HFA≈71, but its ratings also move on matches outside the league; with league matches alone, K≈15
  tracked its rating spread best.
- **Cup K multiplier:** first set to 0.5 on a grid: full weight predicted league games marginally better but
  pulled ratings away from Club Elo. Retested 2026-10-23, with all eight domestic cups and judging on
  prediction, full weight (1.0) won:

  | Cup weight | League | Europe | Cups | Club Elo RMSE |
  |---|---|---|---|---|
  | 0.5 | 0.63172 | 0.58228 | 0.62696 | 29.6 |
  | 1.0 | 0.63144 | 0.58222 | 0.62085 | 32.9 |

  The first three columns are log loss. The bias between leagues is unchanged. Top-50 seasons move by 0.9
  places on average, and six end-of-season #1s change, mostly towards double and treble winners
  (Manchester United 1998/99, Arsenal 2001/02, Celtic 1968/69). English cups go back to 1955 but the
  others only to 2012, so before 2012 English clubs gain a little more from cups.
- **Country start levels, tier gaps and foreign start:** fitted on RMSE. With the other countries' leagues
  in, the four new countries' biases fell from −13…+24 to −6…+4, and league log loss improved.
- **Overfitting:** letting every parameter float overfits. An earlier run gave cups near-zero K and a
  443-point tier gap, so K, HFA and England's gaps stay fixed.
- **Remaining error:** mostly the older snapshots. In 2008 Club Elo rated England and Italy about 35 points
  higher relative to the rest than we do. The likely causes are Club Elo's other leagues and the domestic
  cups before 2012, which aren't modelled here.
- **Domestic cups (2026-10-23):** adding the six countries' cups from 2012/13 left league and European log
  loss and the bias between leagues unchanged, but lifted every rating about 3 points against Club Elo
  (bias −0.7 → +2.7, RMSE 26.2 → 27.0): amateur sides start at the non-league rating and lose points to
  the clubs they meet. Starting them one tier lower made every measure worse, so the setting stays.

## Weekly update

`python -m football_elo update` runs these steps:
1. **Refresh sources.** Re-downloads the live files: football-data's current season and its extra-league files
   (Switzerland, Romania), plus ESPN's current and previous year.
2. **Store changed files** in bronze.
3. **Add matches.** Upserts new or corrected matches from the last two seasons into silver.
4. **Re-rate.** Re-rates from the earliest changed match date, starting from the stored ratings just before
   it.

Clubs ESPN or football-data's extra leagues haven't seen before, such as a new European opponent or a promoted
club, are added automatically under the source's display name (`tools/link_live_leagues.py` links the league
sources' keys to existing clubs by season and score, since the Wikipedia grids before them have no real dates). The job logs a warning and appends them to `config/club_aliases.csv` for review. If the rating
parameters or competition list in config change, the job does a full rebuild instead.

It runs every Monday at 20:00 UTC (Tuesday morning in Australia) as `.github/workflows/weekly-update.yml`,
using the `SUPABASE_DB_URL` repository secret. Source files are kept in an Actions cache between runs. When
it succeeds, the site workflow exports and redeploys. `scripts/weekly_update.ps1` with Windows Task Scheduler
is the local alternative.

Tested against the live database on 2026-10-23:
- A routine run picked up 45 new or changed matches.
- A forced replay removed seven months of matches (3,691, from 1 April 2026) and let the update re-add and
  re-rate them.
- In both cases every match rating, the latest club ratings and the whole-season ratings matched a full
  rebuild exactly.

The update leaves the hindsight country levels alone: they only cover seasons before 2000.

## Website

`web/` is the public site: a Vite + React + D3 app on GitHub Pages, reading a static JSON snapshot instead of
querying Supabase, so no database keys reach the browser.
- **Snapshot:** `python -m football_elo export` reads the serving views, ratings and matches from Supabase
  and writes `web/public/data/` (about 60 MB, not committed): `clubs.json`, one file per summary view, one
  file per league club (`club/<slug>.json`: monthly ratings, seasons, every match) and month-end rankings
  per year (`tables/<year>.json`).
- **Crests and colours:** `python tools/club_branding.py` writes `config/club_branding.csv` from ESPN team
  records (crest, primary and alternate colour), falling back to Transfermarkt crests and to colours taken
  from the crest. Crests are linked from those sites, not stored in the repo. Clubs without one get a
  monogram badge.
- **Local:** `npm --prefix web install`, export, then `npm --prefix web run dev`
  (http://localhost:5173/football-elo/).
- **Deploy:** `.github/workflows/site.yml` exports, builds and publishes on every push to `main` that
  touches the site, weekly on Tuesdays, and on demand. It needs the `SUPABASE_DB_URL` repository secret.

## Judging a season: end of season or whole season

Every season-based figure exists in two versions, chosen on the site by the "Season view" toggle (stored as
`measure` in the `gold.mv_*` season views). This covers world and league rank, above average, #1 per season,
decade kings, greatest seasons, dynasties, league strength and the all-time ranking.
- **End (`end`):** the rating after the club's last match of the season, i.e. where it finished. Good for
  current standing. It undervalues a strong start: a club that slumps late is judged on the slump.
- **Whole (`perf`):** a performance rating (`src/football_elo/seasons.py`, stored in
  `gold.club_season_perf`). It's the one constant rating that best explains every result of the season,
  against each opponent as rated at kick-off, with home advantage and league offsets as in the Elo run.
  - Every match counts equally whatever its date, cups included, as in the ratings.
  - Fifteen virtual draws against a side of the club's season-average rating (August–May month ends) pull
    every season towards that average, so a run of luck in one season isn't taken at face value.
  - Unlike a season-average rating, it doesn't lag behind form, since last season isn't carried in.
- **Choosing the pull and leaving out goal margin (2026-10-23):** tested by predicting each club's next
  season from this one, especially for promoted clubs.
  - With 8 draws, the strongest quarter of promoted clubs did 1.6pp worse the next season than predicted,
    i.e. dominant second-tier seasons (Fulham 2000/01) were overrated.
  - Counting goal margin made that worse (−3.0pp), though it predicted slightly better overall.
  - 25 draws or more nearly removed the bias but dragged late-surging seasons back towards the lagging
    season average.
  - 15 draws splits it (promoted clubs +1.1pp overall, strongest quarter −0.9pp) and predicts better than
    8.
  - Margin was retested with the pull tuned to the same split. Half-strength margin (gd^0.25) with 25
    draws predicted a little better (log loss 0.64564 against 0.64633) and changed the #1 in six seasons,
    Ajax 1972/73 among them. Full margin needed 40 draws, which dragged late-surging seasons down. Both
    were judged not worth it; the measure stays margin-free.
- **Example:** Aston Villa finished 7th in 2022/23 after a strong spring, then 4th in 2023/24 after a weak
  finish. Season end ranks them 22nd and 31st in Europe; whole season ranks them 23rd and 17th.
- **How much it matters:** since 1965/66 the two rank orders correlate at 0.99, but the European #1 differs
  in 14 of 61 seasons.
- **Where it doesn't apply:** the monthly rating charts and the Rankings tab are point-in-time and unchanged.

### Hindsight country levels (season and date views before 2000)

Ratings run forwards, so a country's level in a season reflects only European results up to then. With few
European games a season before the mid-1990s, levels drifted. Serie A was rated 30–40 points too low around
1985–91: Italian clubs did about 5pp better in Europe than predicted. England stayed at its early-1980s level
through the 1985–90 ban and came back about 25 points too high.
- **Method (`src/football_elo/hindsight.py`, stored in `gold.country_hindsight`):** for each season, the
  country offsets that best explain European results in the three seasons either side, weighted towards the
  nearest. A ridge worth 60 games pulls each towards 0, and the average over the modelled countries stays
  put. They're added to season ratings under both measures: in full to 1994/95, fading out by 1999/2000.
- **Gaps:** seasons a country sat out of Europe step evenly from the level before to the level after, the
  average of the first four seasons back (`gap_after`; since 2026-10-24, when Alex asked for a gentle slide
  given English clubs' underperformance in 1991–96). England 1985/86–1990/91 now reads +4, −2, −7, −13, −19,
  −25 (was +6, +1, −3, −8, −12, −17 towards 1991/92 alone); predictions are unaffected. That's
  England 1985/86–1990/91, counting 1990/91 when only Manchester United and Aston Villa were back (Liverpool returned in 1991/92). England returns at the
  lower level instead of jumping to it.
- **Tested on left-out seasons** (each predicted from its neighbours only), European log loss:

  | Period | Forward only | With hindsight |
  |---|---|---|
  | 1958–74 | 0.5480 | 0.5404 |
  | 1975–94 | 0.5498 | 0.5476 |
  | 1995–2025 | 0.5964 | 0.5970 (slightly worse, hence the fade) |

  Bias spread by 5-year block: 3.62 → 2.46pp.
- **Effect:** Milan 1988/89 rises from 10th to about 7th, and 1989/90 and 1990/91 from 4th to 3rd.
  Liverpool and Arsenal stay ahead in 1988–90, because the ban gives no European evidence to correct
  England against during those years.
- **Where it applies on the site:** season views, and since 2026-10-24 also the date views (monthly club
  ratings, the Rankings tab's month-end tables and the field average), added in `export.py` per rating period
  by its country and season. Match ratings (the pre-match ratings and win chances) stay forward-only, and so do
  the database's `gold.mv_club_months` and `gold.ratings_on`. With the sixteen leagues of run 22, end of May
  1990 reads Liverpool 1910, Milan 1908 (Milan 4th → 2nd, Bayern 2nd → 4th); Liverpool falls from 3rd to 7th
  at the end of 1990/91.

## Useful queries

```sql
select * from gold.current_ratings;                          -- league clubs, latest
select * from gold.ratings_on('1999-05-27');                 -- league table on a date
select * from gold.ratings_on('1999-05-27', false) limit 20; -- including foreign clubs
select m.*, r.* from silver.matches m join gold.match_ratings r using (match_id)
 where m.competition = 'UCL' and (m.home_club = 'Liverpool' or m.away_club = 'Liverpool')
 order by m.match_date desc;
```
