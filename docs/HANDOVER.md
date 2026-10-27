# Handover: state of the project and the gap backlog

Last updated 2026-10-24 (sixteen more top flights and their current season built locally; last load run 21). The README covers how everything works; this note
covers where things stand and what's next. Alex's working style: tackle gaps one at a time, biggest first;
judge model changes on evidence (next-season / out-of-sample prediction and bias between leagues), not on
Club Elo RMSE; show the effect on familiar clubs and seasons before switching.

## Start here: next jobs (Alex's queue)

Site requests, added 2026-10-27, not started:
- **Rise and fall (`web/src/pages/Eras.tsx`):** the selected line should always be drawn in that team's
  own colour (`config/club_branding.csv`).
- **World top 100 by season:** a new view of the world top 100 for any season, with the end / whole-season
  (`measure` 'end' / 'perf') toggle, so the top 100's standings can be compared year to year.

1. **Domestic cups going way back.** English cups already run from 1955; the other ten countries' cups
   only from 2012/13 (Coupe de France 2015/16; Scotland, Belgium, Turkey and Greece have none yet).
   A survey of English Wikipedia's season articles (one sampled season per decade) showed four formats,
   none covering everything:
   - `{{Football box}}` matches: Scotland and Greece good recently; Copa del Rey from the 1980s; the
     DFB-Pokal only in some years (1984/85 has 66 boxes, 1970/80/90 none).
   - `{{TwoLegResult}}` rows: common for the Copa del Rey (46–101 a season in the 1960s–70s), the Greek
     Cup, some Coppa Italia seasons.
   - Bracket templates (`RD1-team1`, scores in `RD1-score1`): Greek Cup late rounds in every decade, Belgian
     and Italian late rounds from 1990.
   - Plain wikitables: likely where none of the above appear (DFB-Pokal 1970–90, Coupe de France, KNVB
     Cup, Turkish Cup), or late rounds only.
   **Done (2026-10-23/24), loaded as run 21.** 536 season pages (`wikipedia.cups` in
   `elo.yaml`, folders `data/bronze/wikipedia/cup-*`) plus 323 transcluded final articles
   (`cup-*/transcluded`). `src/football_elo/wikicups.py` reads five layouts (Football box, OneLegResult,
   TwoLegResult, brackets, wikitables), expands `{{:Final}}` / `{{#lst:}}` transclusions, and keeps each
   match once (box first, bracket last). `sources.wikipedia_cup` dates undated rounds between the page's
   dated ones (lead dates, else 1 Sep–31 May), spaces a club's matches within a round, and makes
   single-match finals neutral. 41,298 matches; finals found in 526 of 536 seasons.
   - Coverage: `python tools/cup_coverage.py` → `data/silver/cup_coverage.csv` (per cup and season:
     matches per layout, final/semis/quarters found, share dated, Transfermarkt count where it overlaps).
     2012–14 overlap matches Transfermarkt exactly for the Copa, DFB-Pokal, Coppa Italia; Wikipedia has more
     amateur rounds for the KNVB and Taça.
   - Gaps: Coppa Italia 1960s–80s group stages are standings only (no results); Coupe de France before
     1990 has the last 32/64 only; no pages for KNVB before 1969, Taça 1955–61/1969–89 (except 1982),
     Belgian Cup before 1989 (except 1978), Turkish Cup before 1987 (except 1965, 1974). RSSSF next for these.
   - Known residue: reserve sides linked to their first team's article (Jong PSV → PSV, 6 self-matches),
     about 110 same-day clashes from printed dates, and a few results awarded but printed as scores
     (footnoted, e.g. Longuenesse v Caen 2005/06).
   - **Linked and loaded (2026-10-24).** `tools/link_cup_names.py` links cup keys: resolved title →
     existing wikipedia/DataRozhlas alias; name via every known club name (incl. Transfermarkt/ESPN display
     names); fixtures 2012–14; near-identical spellings; else a new club (one per display name per cup).
     Unlinked names are keyed `<country>:<name>`, reserve sides `<article> [<label>]`. Review list:
     `data/silver/cup_alias_review.csv`. 4,883 alias rows written.
   - **Alex's rule: only ties with a league club on one side** (`silver.league_ties`, Wikipedia cup rows
     only; Transfermarkt/ESPN 2012+ cups unchanged). About 8,700 amateur-only matches dropped (Belgium
     3,871: its pages list the amateur rounds from about 2010). Kept: 31,249 Wikipedia cup matches;
     2,614 new clubs (3,383 → 5,996), lower-league and reserve sides that met a league club.
   - New competitions `SCO-SC`, `BEL-BC`, `TUR-TC`, `GRE-GC` (Wikipedia throughout); the six other cups take
     Wikipedia before 2012/13 (Coupe de France before 2015/16). Scottish semi-finals neutral. Trophies:
     migration `20261024000000_cup_history.sql` adds the four cups and, for Wikipedia seasons, only counts a
     last match whose round is the final (10 seasons have no final on the page). The site's `format.ts`
     names the new cups.
   - Weekly update: the current season's cup pages re-download each run; clubs new in later rounds are
     auto-registered like ESPN's (review them with `tools/link_cup_names.py`). CI's first run after the
     push downloads all ~860 pages (cached after).
   - **Effect:** against Club Elo, bias +13.2 → +24.8, RMSE 32.9 → 39.7, but RMSE with bias removed only
     30.1 → 31.1 and Spearman 0.9894 → 0.9890: a level shift at the top, not a reordering. Mean change for
     clubs rated before: −3 (1965), 0 (1980), +5 (1995), +17 (2010), +4 (2025); the big clubs are about
     +12 in 2025. New clubs leak only ~16,000 points in total, so the likely cause is spread: top clubs
     play many more cup ties against weaker sides. **Judged 2026-10-24 with `pool_experiment`'s measures
     (configured pool 0.3, before vs after):** league log loss 0.6314 → 0.6313, European log loss
     0.5822 → 0.5819 (better in the 1960s/70s by 0.002–0.003, 1980s 0.001 worse), European bias RMS
     2.10 → 2.14pp; after re-levelling, Club Elo RMSE 30.14 → 31.05. Prediction is no worse, so no fix:
     the shift is a level change, and Elo predictions depend only on rating differences. If absolute
     numbers should match Club Elo again, lowering every start rating by ~12 (`calibrate.align_level`) is
     purely cosmetic. Individual moves worth a look: Bayern
     +53 and Real Madrid −31 in 1965 (cups 1955–65 now count; the Oberligen still aren't modelled).
   - Gaps left: Coppa Italia group stages 1960s–80s, Coupe de France before 1990 beyond the last 32/64,
     KNVB before 1969, Taça 1955–61/1969–89 (except 1982), Belgian Cup before 1989, Turkish Cup before 1987:
     RSSSF next.
2. **Leagues of the other European trophy winners.** Clubs from unmodelled countries are rated only from
   European games: Steaua and Red Star (European Cup), Dinamo Kyiv, Dinamo Tbilisi, Slovan Bratislava,
   Magdeburg (Cup Winners' Cup), Göteborg, Ferencváros, Dinamo Zagreb, Shakhtar, Zenit (UEFA/Fairs Cup),
   plus finalists like Rapid/Austria Wien and Malmö. Likely set: Romania, Yugoslavia, USSR, Ukraine,
   Russia, Czechoslovakia, GDR, Hungary, Sweden, Austria, Switzerland, Denmark. Use the method from the
   Scotland/Belgium/Turkey/Greece work (Wikipedia grids for the early seasons, link names via overlap years,
   then a duplicate scan against each country's European-only clubs, then starting levels tuned with
   `tools/pool_experiment.py`). Top flight only.
   **Built locally 2026-10-24, not loaded yet (waiting for Alex's go-ahead).** Sixteen leagues, all from
   Wikipedia's season grids 1955/56–2025/26: `AUT-L SUI-L SWE-L DEN-L ROU-L HUN-L`, the unions `URS-L YUG-L
   TCH-L GDR-L`, and their successors `RUS-L UKR-L CZE-L SVK-L SRB-L CRO-L`. About 167,000 matches (718,676
   in all) and 374 new clubs (6,307). Titles come from each league's "seasons" category; 779 pages were
   fetched in bulk through the API (50 a request), later fetches go through `bronze.fetch_wikipedia`.
   - Parser: `legs=2` grids (clubs meeting four times: Denmark, Hungary, Croatia, Slovakia) read as one
     block per leg; `{{nowrap|...}}` names unwrapped; two clubs linked to one article in a grid are keyed
     `<article> [<name>]`. Spec keys: `kind` (calendar-year seasons start in April; spring-only half seasons,
     saved as `<season>s.txt`, in March) and `skip` (these leagues keep their championship/relegation groups).
   - **Country per season** (engine + `silver.country_seasons`, README "Big-5 coverage"): a club's pool follows
     its league (Dynamo Kyiv USSR → Ukraine, Dresden GDR → Germany); its rating carries over on a change.
   - Linking: `tools/link_cup_names.py` now takes league competitions (successor-country sets, same-article
     keys are one club unless they met). Review list `data/silver/league_alias_review.csv`. New
     `tools/merge_clubs.py` merged 63 fragmented European-only clubs first (Sparta Praha/Sparta Prague,
     LASK/Linzer ASK, Rijeka, Copenhagen, Red Star, Petržalka/Artmedia, ...) and Lok Leipzig into VfB Leipzig.
     Hand links: Universitatea Craiova (a `corrections` row for 2021), NK Varaždin (2012) apart from Varteks;
     Vaduz stays Liechtenstein (`club_countries`).
   - Effect against run 21 (same European matches, `pool_experiment`-style alignment): European log loss
     0.5819 → 0.5764; Club Elo RMSE 31.05 → 30.07, Spearman 0.9890 → 0.9892; league log loss (old 11)
     unchanged; European bias RMS old 11 3.31 → 3.11pp, new countries 5.42 → 4.60pp. Against Club Elo the
     new countries' levels since 2008 are within about ±25 (Serbia −24, Austria +28). All ratings sit about
     36 points higher than before against Club Elo (bias +25 → +61): the new countries' pooled levels feed
     back through Europe. Separating East from West Germany took Bayern 1975 from #4 to #12; Steaua 1986
     #118 → #31, Red Star 1991 #24 → #6, Magdeburg 1975 #87 → #23.
   - **Current season, dated (built locally 2026-10-24, not loaded).** 2026/27 (Sweden's 2026) follows the
     grids: ESPN league slugs `aut.1 den.1 rus.1 swe.1` (`sources.espn.leagues`, read in full: tier 1,
     ESPN's season year, fetched from 2025) and football-data.co.uk's extra-league files `new/SWZ.csv`,
     `new/ROU.csv` (new source `football_data_extra`, one file per country, re-downloaded every run). ESPN
     dropped `sui.1` and `rou.1` in late September 2025 (that was the "truncated" look); football-data's
     Russian file stops after two rounds of 2026/27. Windows: `{source: wikipedia}` then the dated source;
     the grids' (season, tier) blocks keep the dated source out of 2025/26 and earlier. 561 matches so far
     (AUT 55, SUI 60, SWE 194, DEN 67, ROU 96, RUS 89).
     - Linking: `tools/link_live_leagues.py` (ESPN ids, football-data names → clubs) seeds from existing
       aliases and same-season names, then votes on season + score with the opponent already linked
       (the grids' dates are synthetic); promoted clubs by country name or unique prefix. 89 aliases
       added; report `data/silver/live_league_links.csv`. New club: Rodina Moscow. Merged a run-22
       duplicate, "Mjällby AIF (SWE)" into "Mjällby AIF".
     - Grid parser fix: an HTML comment after `team_order` was glued to the last club code, dropping
       its games: +30 Liga I 2025/26 (Metaloglobus București, a new club), +30 each Serbian 2024/25 and
       2025/26 (Jedinstvo Ub, new), +10 Danish 2024/25, +30 Segunda 1955/56 (España Industrial = CD Condal).
     - Synthetic-date fix (`sources._schedule`): a single-leg grid (the third round of a Swiss or Hungarian
       season, a championship group) took a double round-robin's weeks, so Swiss seasons ran a full
       year (2025/26 to 13 Sep 2026, among the real 2026/27 games: 17 same-day clashes). Now n − 1
       weeks: Swiss 2025/26 ends 24 May 2026. 72 seasons' dates change (Denmark 21, Hungary 13, Slovakia
       10, Segunda 10, ...).
     - Effect (local build): 719,337 matches, 6,309 clubs, no 2026/27 clashes. Club Elo bias +68.6
       either way (the new rows alone move it by 0.02), debiased RMSE 33.48 → 33.46, Spearman 0.987;
       `pool_experiment 0.3`: European log loss 0.5764 (as run 22), league 0.6259, bias RMS 2.52pp.
     - Still no free dated source for Ukraine, Czechia, Slovakia, Serbia, Croatia, Hungary (ESPN has no
       slugs; TheSportsDB's free key caps at 15 games). Options for Alex: Transfermarkt's
       `gesamtspielplan` pages (dated, club ids, 1 page per league a week, but its terms forbid scraping),
       or the current Wikipedia grid dated by the week a result first appears.
   - Left: Transfermarkt DK1/RU1/UKR1 2012–25 (dated, unused; could replace synthetic dates). Wikipedia keys
     the pre-2016 FC Farul Constanța as Viitorul Constanta (DataRozhlas keeps "Farul Constanța" apart):
     unchecked. Serbian clubs underperform in Europe 1992–2010 (−28/−14pp): Red Star and Partizan
     carry Yugoslav ratings into the sanctions years. Club Elo names for the new countries are mapped by
     name only (121; Zenit, Young Boys, Shakhtar unmapped). Crests/colours for the new clubs not fetched yet
     (`tools/club_branding.py`). The site lists 16 more countries (`web/src/lib/format.ts`); the league
     strength chart may need a filter.

**Model changes 2026-10-26 (runs 26-27).** Evidence-scaled pooling (`pool_evidence`: 0.3 x sqrt(50 / last
season's European games), cap 0.6) and season regression (`season_regress` 0.2 towards last season's league
average). Both tuned on 1965-94 and checked on 1995-2026; regression improved league, cup and European log
loss and removed the dominant-club bias (clubs 300+ above their league were -3.5pp in Europe). Top ratings
are 50-110 points lower; 5 of 61 season #1s changed (e.g. Man Utd 1998/99, Arsenal 2025/26). England's
ban seasons slide towards its 1991-95 average (`gap_after: 4`). Not yet re-checked under these: the
whole-season measure's settings (15 virtual draws), and the starting levels. Re-checked 2026-10-27: starting levels fine (every country's early European bias within ~2 s.e.); goal margin still worse at every draw count; 25 draws would restore the promoted-club balance and predict slightly better (0.63446 vs 0.63557) but changes three #1s (Inter 1988/89 to Real Madrid among them). Alex kept 15.

**League titles in the honours (2026-10-24).** `tools/league_champions.py` writes
`config/league_champions.csv` (1,542 titles, 1955/56–2025/26) from each country's Wikipedia "List of ...
football champions", matched to that season's top-flight clubs and checked against a table from our results
(review: `data/silver/league_champions_review.csv`; about 70 seasons differ, nearly all play-offs, split
seasons or points halving where the list is right). Slovakia and Croatia have no list page: table plus hand
entries (`MANUAL`). Seasons without a title are left out (Ligue 1 1992/93, Serie A 2004/05, Eredivisie 2019/20,
Ukraine 2021/22). `export.py` adds them to `trophies.json`; the club page lists them first. Re-run the tool each
summer when a season ends (CI doesn't).

Known issues to keep in mind: the Accrington cup bug (below), "Keçiörengücü" linked to "Hacettepe"
(unchecked), Cypriot champions in the Greek league kept Cypriot via `club_countries`.

## Where things stand

- **Pipeline:** `python -m football_elo build | load | update | validate | calibrate | export`.
  - Coverage: England tiers 1–4; Spain, Germany, Italy, France, Netherlands tiers 1–2; top flights of
    Portugal, Scotland, Belgium, Turkey, Greece; English cups and play-offs from 1955; the other ten
    countries' cups from 1955 where Wikipedia has them (league-club ties only before 2012/13, see job 1);
    German championship final rounds 1955–63; UEFA competitions from 1955.
  - Size: about 551,000 matches and 5,996 clubs. Tests: 50, all passing (`pytest`).
  - Install with `pip install -e . -c constraints.txt` (pinned versions, see below).
- **Supabase:** project `football-elo`, ref `mukyuvlvwozeihsrjjis`. Last full load: run 21 on 2026-10-24.
  - Loads use `SUPABASE_DB_URL` from `.env` (psycopg) and take about 6–10 minutes; they run in one
    transaction with a 15-minute statement timeout, so a failure rolls back cleanly.
  - The DB connector in Claude sessions is signed in to a different org; use `football_elo.db.connect()`.
  - Every run ends with `gold.refresh_serving()`, which rebuilds the `gold.mv_*` views.
- **Model:** K 15, cups at full weight (since 2026-10-23), √goal-difference margin, dynamic home
  advantage, league pooling 0.3, provisional K × 2 for a club's first 40 matches. The big seven start level
  in 1955; Scotland −125, Belgium −100, Turkey and Greece −250 (README "Big-5 coverage").
  - Season and date views (site export) add hindsight country levels before 2000 (README "Hindsight country levels"; England's ban
    seasons step down evenly).
  - Whole-season rating: performance rating with 15 virtual draws, no goal margin (README "Judging a
    season" records why, including the rejected margin options).
  - Judge model changes with `tools/pool_experiment.py` (log loss, bias between leagues by decade). Its
    input `data/silver/matches_prepared.parquet` is written by `build` (since 2026-10-24, with each club's
    country per season); its `MODS` lists the countries it reports.
- **Website:** https://jai1904-92.github.io/football-elo/ from `web/` (Vite + React + D3, geometric HUD
  design, club crests and colours, a "Season view: End / Whole" toggle). It reads a JSON snapshot
  (`python -m football_elo export`). Crests/colours: `tools/club_branding.py` → `config/club_branding.csv`;
  re-run it after adding clubs. README "Website" covers running and deploying.
- **Weekly update:** GitHub Actions, Mondays 20:00 UTC (`weekly-update.yml`), then the site workflow
  exports and redeploys. Tested live: a seven-month forced replay matched a full rebuild exactly. Failures
  email the repo owner; a local full `load` always restores a clean state.
  - CI and local must use the same library versions (`constraints.txt`, used by both workflows). With
    pandas 3.1, CI built different match ids for clubs with accented names and inserted 326 duplicate
    matches (runs 17 and 19); ids now use an explicit ASCII rule (`silver.match_ids`), and a full reload
    removed the duplicates.
  - After any local full load, the next CI run should report "no new or changed matches" apart from
    genuinely new results; if it re-adds hundreds, something differs between local and CI again.
- **Git:** public repo github.com/Jai1904-92/football-elo, branch `main`. Pushes touching `web/`,
  `export.py` or the branding CSV redeploy the site; otherwise run `gh workflow run site.yml`.
- **Old dashboard:** a claude.ai artifact in Alex's other account (not readable from this one), mirrored
  in `dashboard/`; superseded by the website. Its queries pin `measure = 'end'`.

## Not done yet

- Data bug: engsoccerdata's FA Cup and League Cup files call the modern Accrington Stanley (founded 1968,
  league club "Accrington" from 2006) "Accrington Stanley", so about 75 cup games up to 2018 sit on the old
  club (folded 1962). Fix with `corrections` per season or a dated alias.
- European-source aliases can be badly wrong (West Ham's record was on Reading, Lausanne's on Carlisle until
  2026-10-23). When a club's numbers look odd, scan for aliases whose source name doesn't resemble the club.

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
   - `tools/pool_experiment.py` needs `data/silver/matches_prepared.parquet`; `build` writes it since
     2026-10-24 (before that it had to be regenerated by hand, or the experiment used a stale file).
2. **Domestic cups outside England.** Done from 2012/13 on 2026-10-23, and loaded (run 10):
   - `ESP-CDR`, `GER-DFB`, `ITA-CI`, `NED-KNVB`, `POR-TP` from Transfermarkt 2012/13–2025/26, then ESPN
     (which also fills the Taça's partial Transfermarkt seasons from 2021/22). `FRA-CDF` from ESPN only, last
     64 on, from 2015/16. 6,553 matches; cups count at full weight (K × 0.5 until 2026-10-23). Trophy winners come from the finals
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
3. **Germany before 1963.** Partly done 2026-10-23: the national championship final rounds 1955/56–1962/63
   (`GER-CH`, 176 matches, RSSSF `duithist4763.html`), with final-round clubs starting at top-flight level
   (`start_tier`). The regional Oberligen themselves have no free match-level source: RSSSF and both
   Wikipedias have final tables only; worldfootball.net-type sites have results but scraping them is not
   allowed. German champions 1956–63 now count as trophies.
4. **The rest of Europe.** Done 2026-10-23 for Scotland, Belgium, Turkey and Greece, top flight only (Alex's
   call). Wikipedia grids 1955/56–1993/94, engsoccerdata 1994/95 on, football-data for the current season.
   - Name linking: Wikipedia pages 1994–2004 are read only to link names by fixtures. About 80 pre-1994-only
     clubs were added; about 60 duplicates were merged, mostly the clubs' European-only names against the
     engsoccerdata ones ("RSC Anderlecht"/"Anderlecht", "AEK Athens"/"AEK") plus spelling variants
     ("Kasimpasa"/"Kasımpaşa"). Waregem is split (KSV Waregem to 2001, Zulte-Waregem from 2005, via
     `corrections`). "Clyde F.C." was mislinked to Clydebank and is fixed.
     Unchecked: "Keçiörengücü" is linked to "Hacettepe".
   - Starting levels lowered (see README "Big-5 coverage"); European bias RMS 2.47 → 2.10pp.
   - The same work merged 16 older European-only duplicates in the big seven (Zaragoza, Bologna, Karlsruhe,
     Alavés, Palermo, Genoa, ...). That removed a pooling artefact that had inflated Spain and Italy:
     European log loss 0.5839 → 0.5826.
   - Countries still rated only from European games: everyone else (Austria, Switzerland, the
     Scandinavian countries, Eastern Europe).
5. **Smaller items:**
   - Trophies: the 11 unresolved European finals are hand-entered in the trophies view since 2026-10-24
     (migration `20261024010000_european_finals.sql`: away goals, shoot-outs the source lacks, a 35-day
     final). Two data gaps found there change ratings, so they wait for the next reload: the Fairs Cup
     1966/67 semi-finals and final (Dinamo Zagreb v Eintracht Frankfurt, Leeds v Kilmarnock, Dinamo v
     Leeds) are missing from DataRozhlas, and its Juventus v Leeds 0–0 of 26 May 1971 was abandoned and
     replayed, so it shouldn't be rated.
   - Play-offs: 2019/20 has only 5 of 15 matches.
   - Dates: 3,784 club-days with two matches since run 21 (210 before): cup rounds without a printed date
    often land on a league matchday. Only match order is affected; moving estimated cup dates to the
    nearest Wednesday would clear most. Listed in `data/silver/data_quality.csv`.
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
