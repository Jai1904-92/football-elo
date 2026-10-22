# football-elo

Club Elo-style ratings for English football (tiers 1–4), Spain, Germany, Italy, France and the Netherlands
(tiers 1–2), and Portugal (tier 1), from 1955 to now, kept current weekly in Supabase. Ratings include the FA Cup, League Cup, EFL play-offs,
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
  - The Bundesliga starts in 1963. Before that, German clubs are rated only from their European matches.
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

- **League pooling:** 30% of every European rating change also moves the club's whole country. A league
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
- **Cup K multiplier:** chosen on a grid. Full-weight cups predict league games marginally better but pull
  ratings away from Club Elo.
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
1. **Refresh sources.** Re-downloads the live files: football-data's current season, plus ESPN's current and
   previous year.
2. **Store changed files** in bronze.
3. **Add matches.** Upserts new or corrected matches from the last two seasons into silver.
4. **Re-rate.** Re-rates from the earliest changed match date, starting from the stored ratings just before
   it.

Clubs ESPN hasn't seen before, such as a new European opponent, are added automatically under ESPN's display
name. The job logs a warning and appends them to `config/club_aliases.csv` for review. If the rating
parameters or competition list in config change, the job does a full rebuild instead.

To schedule it, use either:
- `.github/workflows/weekly-update.yml`, with the `SUPABASE_DB_URL` repository secret
- `scripts/weekly_update.ps1` with Windows Task Scheduler

## Useful queries

```sql
select * from gold.current_ratings;                          -- league clubs, latest
select * from gold.ratings_on('1999-05-27');                 -- league table on a date
select * from gold.ratings_on('1999-05-27', false) limit 20; -- including foreign clubs
select m.*, r.* from silver.matches m join gold.match_ratings r using (match_id)
 where m.competition = 'UCL' and (m.home_club = 'Liverpool' or m.away_club = 'Liverpool')
 order by m.match_date desc;
```
