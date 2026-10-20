# Handover: state of the project and the gap backlog

Written 2026-10-20 at the end of a long build session, so a fresh session can pick up from here. The README
covers how everything works; this note covers where things stand and what's next.

## Where things stand

- **Pipeline:** `python -m football_elo build | load | update | validate | calibrate`.
  - Coverage: England tiers 1–4, Spain, Germany, Italy and France tiers 1–2, Portugal and the Netherlands tier 1.
    Also English cups and play-offs, and the UEFA competitions, all from 1955.
  - Size: 379,075 matches and 2,162 clubs.
  - Tests: 20, all passing (`pytest`).
- **Supabase:** project `football-elo`, ref `mukyuvlvwozeihsrjjis`. The last full load was run 5 on
  2026-10-20.
  - Loads use `SUPABASE_DB_URL` from `.env` (psycopg) and take about 4 minutes.
  - Every run ends with `gold.refresh_serving()`, which rebuilds the `gold.mv_*` views the dashboard reads.
- **Model:** K 15, cup K × 0.5, √goal-difference margin. On top of plain Club Elo it adds dynamic home
  advantage, league pooling 0.3, and provisional K × 2 for a club's first 40 matches. All countries start
  level in 1955. The README sections "Elo engine" and "Early-era calibration" give the reasoning.
  - Judge model changes with `tools/pool_experiment.py`: log loss, and bias between the modelled leagues by
    decade.
  - Use the Club Elo fit (RMSE 26.9, Spearman 0.991) only as a secondary check, because Club Elo has no
    pooling and a fixed home advantage.
- **Dashboard:** https://claude.ai/artifact/6ZBJ8NoziTLrGuX6PDNexe (Dashboard artifact type). It runs live
  queries on the Supabase connector, with tabs that load lazily.
  - The page and its queries are mirrored in `dashboard/index.html` and `dashboard/queries.json`.
  - The live copy is in the artifact's store (`files/index.html`, `datasets/*`). Edit the repo copy, then
    write it to the store.
  - Keep queries on the `gold.mv_*` views. A raw rebuild over `gold.club_ratings` costs about 6 seconds per
    query.

## Not done yet

- The weekly update isn't scheduled. Options: `.github/workflows/weekly-update.yml` (needs a GitHub repo
  plus the `SUPABASE_DB_URL` secret) or `scripts/weekly_update.ps1` with Task Scheduler.
- The update's re-rating path is covered by unit tests but hasn't run against the live database yet. The
  first weekly run after new matches is the real test: compare it with a full rebuild.
- Git is local only: everything up to this note is committed on `master`, and there is no remote yet.

## Gap backlog, biggest effect on rankings first

Work through these one at a time. For each: find a source, check its coverage, map club names
(`tools/derive_aliases.py`, `tools/link_league_names.py`), validate, re-check calibration, reload, then
update the dashboard.

1. **Second tiers before the mid-1990s.**
   - Spain, France and Italy start in 1996–97. Portugal and the Netherlands have none.
   - Spain, France and Italy also have partial football-data files for 2002–04.
   - RSSSF has Dutch Eerste Divisie results grids for 1956–2004; 2004–2020 is patchy; openfootball has
     2020 onward. Portugal's second tier has almost nothing free before about 2005.
   - Check RSSSF for Spanish, French and Italian second-tier grids.
   - Same approach as Portugal: parse the results grids and give them a synthetic round-robin schedule.
2. **Domestic cups outside England.**
   - Transfermarkt has the Copa del Rey (`CDR`), DFB-Pokal (`DFB`), Coppa Italia (`CIT`), KNVB Cup (`NLP`)
     and probably the Taça (`POCP`) from 2012. The Coupe de France isn't in its list.
   - Before 2012 a source is needed (RSSSF or Wikipedia).
   - Cups use K × 0.5.
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

- A partial season from one source blocks a complete one from a later source. Watch the "thin season"
  warnings in the build log.
- football-data sometimes serves the wrong league in a file. The reader checks the `Div` column.
- engsoccerdata names clubs differently across files and seasons. Fix with `engsoccerdata` alias rows, or
  with `corrections` in `config/elo.yaml` when the error only applies to some seasons.
- Watch for duplicate canonical clubs when a new source's names don't match existing ones. Run the
  near-duplicate scan in `tools/derive_aliases.py`, and check the overlap report from
  `python -m football_elo validate`.
