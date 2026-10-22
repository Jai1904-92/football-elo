# Handover: state of the project and the gap backlog

Written 2026-10-20 at the end of a long build session, so a fresh session can pick up from here. The README
covers how everything works; this note covers where things stand and what's next.

## Where things stand

- **Pipeline:** `python -m football_elo build | load | update | validate | calibrate`.
  - Coverage: England tiers 1–4, Spain, Germany, Italy, France and the Netherlands tiers 1–2, Portugal tier 1.
    Also English cups and play-offs, and the UEFA competitions, all from 1955.
  - Size: 444,608 matches and 3,266 clubs (2026-10-23; about 1,000 of them cup-only).
  - Tests: 29, all passing (`pytest`).
- **Supabase:** project `football-elo`, ref `mukyuvlvwozeihsrjjis`. The last full load was run 10 on
  2026-10-23.
  - Loads use `SUPABASE_DB_URL` from `.env` (psycopg) and take about 4 minutes.
  - Every run ends with `gold.refresh_serving()`, which rebuilds the `gold.mv_*` views the dashboard reads.
- **Model:** K 15, cup K × 0.5, √goal-difference margin. On top of plain Club Elo it adds dynamic home
  advantage, league pooling 0.3, and provisional K × 2 for a club's first 40 matches. All countries start
  level in 1955. The README sections "Elo engine" and "Early-era calibration" give the reasoning.
  - Judge model changes with `tools/pool_experiment.py`: log loss, and bias between the modelled leagues by
    decade.
  - Use the Club Elo fit (RMSE 26.9, Spearman 0.991) only as a secondary check, because Club Elo has no
    pooling and a fixed home advantage.
- **Website (from 2026-10-23):** `web/`, a Vite + React + D3 site for GitHub Pages with a geometric HUD
  design, club crests and per-club colours. It reads a static JSON snapshot (`python -m football_elo
  export`) instead of querying Supabase. Crests/colours: `tools/club_branding.py` → `config/club_branding.csv`.
  README "Website" covers running and deploying it. It has the old dashboard's seven tabs plus a home page.
- **Old dashboard:** https://claude.ai/artifact/6ZBJ8NoziTLrGuX6PDNexe (Dashboard artifact type, in Alex's
  other claude.ai account; not readable from this one). Mirrored in `dashboard/index.html` and
  `dashboard/queries.json`; superseded by the website.
  - Keep queries on the `gold.mv_*` views. A raw rebuild over `gold.club_ratings` costs about 6 seconds per
    query.

## Not done yet

- The weekly update isn't scheduled. Options: `.github/workflows/weekly-update.yml` (needs a GitHub repo
  plus the `SUPABASE_DB_URL` secret) or `scripts/weekly_update.ps1` with Task Scheduler.
- The update's re-rating path is covered by unit tests but hasn't run against the live database yet. The
  first weekly run after new matches is the real test: compare it with a full rebuild. Its GitHub workflow
  is manual-only until then.
- Data bug: engsoccerdata's FA Cup and League Cup files call the modern Accrington Stanley (founded 1968,
  league club "Accrington" from 2006) "Accrington Stanley", so about 75 cup games up to 2018 sit on the old
  club (folded 1962). Fix with `corrections` per season or a dated alias.
- Git is local only: everything up to this note is committed on `master`, and there is no remote yet.

## Gap backlog, biggest effect on rankings first

Work through these one at a time. For each: find a source, check its coverage, map club names
(`tools/derive_aliases.py`, `tools/link_league_names.py`), validate, re-check calibration, reload, then
update the dashboard.

1. **Second tiers before the mid-1990s.** Mostly done 2026-10-21/23, and loaded (run 9):
   - Done: Serie B 1955/56–1996/97 (RSSSF), Segunda 1955/56–1995/96 plus the partial 2001/02–2003/04
     (Wikipedia grids), Eerste Divisie 1956/57–2024/25 (RSSSF; 2020/21 onwards added 2026-10-22, which took
     Club Elo RMSE from 26.90 to 26.15 and Spearman to 0.992 with European log loss unchanged). Parsers in `src/football_elo/grids.py`, readers
     in `sources.py`, name linking in `tools/link_grid_names.py` (fixture matching within a season, plus a
     `MANUAL` table of hand links). README "Date-less sources" has the details.
   - Calibration after (before): Club Elo RMSE 26.86 (26.88), Spearman 0.991 (0.991), European log loss
     0.5839 (0.5838), European bias RMS 1.80pp (1.72pp). The Netherlands' 1960s–70s European bias got worse
     (−9.8 / −4.0pp, was −6.8 / −1.5): Dutch clubs now underperform their ratings in Europe a little more.
     Possible lever: NED's tier gap or starting levels. Not tuned yet.
   - Left: the Eerste Divisie 2025/26 (RSSSF has only the table so far; extend `seasons` in `elo.yaml` when
     the rounds appear, or use openfootball), France before 1996/97 (no free match-level source
     found: RSSSF `fran2hist` and both Wikipedias have final tables only), and Portugal's second tier.
   - Football-data's partial seasons were filled 2026-10-23: Serie B 2002/03 (RSSSF `ital03`) and 2004/05
     (`ital2-05`, via `extra_pages`), Ligue 2 2003/04 (RSSSF `fran04`, dated) and 2002/03 (Wikipedia grid,
     synthetic dates: RSSSF has no Ligue 2 that year). Scores agree with football-data wherever both have the
     match, except Clermont v Niort 2002/03 (football-data 1–1, Wikipedia 0–1). Calibration barely moved
     (RMSE 26.15, European log loss 0.5839). The same work fixed two duplicate clubs: RSSSF's 2002/03
     "Messina" (now FC Messina, by a correction), and a European-only "Sedan" (now CS Sedan, and UA
     Sedan-Torcy for 1961/62).
   - `tools/pool_experiment.py` needs `data/silver/matches_prepared.parquet`, which nothing in the pipeline
     writes: regenerate it with `engine.prepare(matches, params, club_country=clubs.country)` first, or the
     experiment silently uses a stale file.
2. **Domestic cups outside England.** Done from 2012/13 on 2026-10-23, and loaded (run 10):
   - `ESP-CDR`, `GER-DFB`, `ITA-CI`, `NED-KNVB`, `POR-TP` from Transfermarkt 2012/13–2025/26, then ESPN
     (which also fills the Taça's partial Transfermarkt seasons from 2021/22). `FRA-CDF` from ESPN only, last
     64 on, from 2015/16. 6,553 matches; cups use K × 0.5. Trophy winners come from the finals
     (migration `20261023000000_domestic_cups.sql`).
   - About 1,000 cup-only clubs were added (amateur and lower-league sides); they take the cup's country
     (`silver.build`), so they start at the country's non-league rating. Linking: `tools/derive_aliases.py`,
     then a name screen of every new club against the existing clubs of its country, with about 100
     duplicates merged by hand (e.g. "SG Dynamo Dresden", "TSV 1860 Munich", "MVV Maastricht"). Refounded
     clubs stay separate where the league data keeps them apart (Sestao River, Salamanca UDS, Xerez
     Deportivo, Union Brescia, AVS). The screen also caught a 2026 ESPN duplicate, "Torreense".
   - Calibration: league and European log loss and the bias between leagues unchanged; every rating about 3
     points higher against Club Elo (bias +2.7, RMSE 27.0). Lowering the amateur start rating made things
     worse (README, "Early-era calibration").
   - Left: cups before 2012. RSSSF's season pages don't carry them (Italy's 2002/03 page aside). Wikipedia
     season articles ("1984–85 DFB-Pokal") do, in `{{Football box}}` templates, but coverage varies:
     the DFB-Pokal and Copa del Rey are well covered from the 1980s; the Coppa Italia is in tables; the
     Coupe de France and KNVB Cup have only the late rounds; the Taça has nothing. That needs a new parser.
     The Taça 2020/21 has only its last 8.
3. **Germany before 1963.** The regional Oberligen ran from 1955 to 1963. Check RSSSF for results grids;
   until then German clubs are rated only from European games.
4. **The rest of Europe.** engsoccerdata has `scotland`, `belgium`, `turkey` and `greece`, the same format as
   the other countries. Each addition is mostly config plus name mapping, like Portugal and the Netherlands.
   Clubs from other countries are rated only from European games.
5. **Smaller items:**
   - Trophies: 11 unresolved two-legged European finals (UEL 7, FAIRS 3, UCWC 1). They need an away-goals
     rule, or a hand-entered list of winners.
   - Play-offs: 2019/20 has only 5 of 15 matches.
   - Dates: 210 clashes in the sources, listed in `data/silver/data_quality.csv`.
   - ESPN, the live source for cups and Europe, is unofficial.

## Things that bit us (check these when adding data)

- Date-less sources can't be linked on dates. Link on (season, opponent, venue, score) instead, and require
  a name seed to be in the same season *and tier*: otherwise reserve teams ("Athletic Bilbao B") link to
  their first team.
- engsoccerdata's names can hide mergers (its 1956–58 "DWS Amsterdam" is BVC Amsterdam), and European-only
  aliases can duplicate a league club (Roda/Roda JC, NEC/NEC Nijmegen, FC Den Haag/ADO Den Haag were split
  until 2026-10-21). Same-day clashes between a source's tier-2 rows and another's tier-1 rows show these up.
- RSSSF Italian stage lists print both legs' scores from the first club's side.
- A partial season from one source blocks a complete one from a later source. Watch the "thin season"
  warnings in the build log.
- football-data sometimes serves the wrong league in a file. The reader checks the `Div` column.
- engsoccerdata names clubs differently across files and seasons. Fix with `engsoccerdata` alias rows, or
  with `corrections` in `config/elo.yaml` when the error only applies to some seasons.
- Watch for duplicate canonical clubs when a new source's names don't match existing ones. Run the
  near-duplicate scan in `tools/derive_aliases.py`, and check the overlap report from
  `python -m football_elo validate`.
