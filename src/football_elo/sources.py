"""Source readers. Each returns matches in the common silver schema, with
club keys as the source names them (aliases are applied later in silver).

Common columns:
  file_name (relative to the bronze root), match_date, season (start year), competition, tier (league only), round,
  leg, home_club, away_club, home_goals, away_goals (after extra time),
  neutral, extra_time, home_pens, away_pens, home_country, away_country,
  home_name, away_name (display names, for alias review), source
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import grids

log = logging.getLogger(__name__)

COLUMNS = ["file_name", "match_date", "season", "competition", "tier", "round", "leg",
           "home_club", "away_club", "home_goals", "away_goals", "neutral", "extra_time",
           "home_pens", "away_pens", "home_country", "away_country", "home_name", "away_name", "source"]


def _frame(source: str, **cols) -> pd.DataFrame:
    df = pd.DataFrame(cols)
    for c in COLUMNS:
        if c not in df:
            df[c] = np.nan
    df["source"] = source
    df["home_name"] = df["home_name"].fillna(df["home_club"])
    df["away_name"] = df["away_name"].fillna(df["away_club"])
    df["neutral"] = df["neutral"].fillna(False).astype(bool)
    df["extra_time"] = df["extra_time"].fillna(False).astype(bool)
    return df[COLUMNS]


def _rel(path: Path) -> str:
    """File name relative to the bronze root, e.g. football_data/2627_E0.csv."""
    return f"{path.parent.name}/{path.name}"


def _pens(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """'4-3' -> (4, 3); anything else -> NaN."""
    parts = series.astype(str).str.strip().str.extract(r"^(\d+)\s*-\s*(\d+)$").astype(float)
    return parts[0], parts[1]


def season_from_date(d: pd.Series) -> pd.Series:
    return np.where(d.dt.month >= 7, d.dt.year, d.dt.year - 1)


# ------------------------------------------------------------ engsoccerdata
def es_league(path: Path, country: str, competition: str, max_tier: int) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df = df[pd.to_numeric(df["tier"], errors="coerce").between(1, max_tier)]
    df = df[df["hgoal"].notna() & df["vgoal"].notna()]   # unplayed / abandoned (some non-English files)
    return _frame("engsoccerdata", file_name=_rel(path),
                  match_date=pd.to_datetime(df["Date"]), season=df["Season"].astype(int),
                  competition=competition, tier=df["tier"].astype(int), round="league",
                  home_club=df["home"].str.strip(), away_club=df["visitor"].str.strip(),
                  home_goals=df["hgoal"].astype(int), away_goals=df["vgoal"].astype(int),
                  home_country=country, away_country=country)


def es_facup(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df = df[df["nonmatch"].isna() & df["hgoal"].notna()]
    hp, ap = df["hp"], df["vp"]
    return _frame("engsoccerdata", file_name=_rel(path),
                  match_date=pd.to_datetime(df["Date"]), season=df["Season"].astype(int),
                  competition="ENG-FAC", round=df["round"].astype(str), leg=df["tie"],
                  home_club=df["home"].str.strip(), away_club=df["visitor"].str.strip(),
                  home_goals=df["hgoal"].astype(int), away_goals=df["vgoal"].astype(int),
                  neutral=df["neutral"].eq("yes"), extra_time=df["aet"].eq("yes"),
                  home_pens=pd.to_numeric(hp, errors="coerce"), away_pens=pd.to_numeric(ap, errors="coerce"),
                  home_country="ENG", away_country="ENG")


def es_leaguecup(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df = df[df["hgoal"].notna()]
    rnd = df["round"].astype(str).str.lower()
    # one-off finals (leg 0) are at Wembley / Cardiff; 1961-66 finals were two-legged
    neutral = rnd.eq("final") & df["leg"].eq(0)
    return _frame("engsoccerdata", file_name=_rel(path),
                  match_date=pd.to_datetime(df["Date"]), season=df["Season"].astype(int),
                  competition="ENG-LC", round=rnd, leg=df["leg"].astype(str),
                  home_club=df["home"].str.strip(), away_club=df["visitor"].str.strip(),
                  home_goals=df["hgoal"].astype(int), away_goals=df["vgoal"].astype(int),
                  neutral=neutral, home_country="ENG", away_country="ENG")


def es_playoffs(path: Path, max_tier: int) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df = df[(df["htier"] <= max_tier) & (df["vtier"] <= max_tier) & (df["Season"] >= 1986)]
    hp, ap = _pens(df["pens"])
    return _frame("engsoccerdata", file_name=_rel(path),
                  match_date=pd.to_datetime(df["Date"]), season=df["Season"].astype(int),
                  competition="ENG-PO", round=df["round"].astype(str), leg=df["tie"],
                  home_club=df["home"].str.strip(), away_club=df["visitor"].str.strip(),
                  home_goals=df["hgoal"].astype(int), away_goals=df["vgoal"].astype(int),
                  neutral=df["neutral"].eq("yes"), extra_time=df["aet"].eq("yes"),
                  home_pens=hp, away_pens=ap, home_country="ENG", away_country="ENG")


def es_champs(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    rnd = df["round"].astype(str)
    hp, ap = _pens(df["pens"])
    return _frame("engsoccerdata", file_name=_rel(path),
                  match_date=pd.to_datetime(df["Date"]), season=df["Season"].astype(int),
                  competition="UCL", round=rnd, leg=df["leg"].astype(str),
                  home_club=df["home"].str.strip(), away_club=df["visitor"].str.strip(),
                  home_goals=df["tothgoal"].astype(int), away_goals=df["totvgoal"].astype(int),
                  neutral=rnd.str.lower().eq("final") | df["leg"].eq("replay"),
                  extra_time=df["aet"].notna(), home_pens=hp, away_pens=ap,
                  home_country=df["hcountry"], away_country=df["vcountry"])


# ------------------------------------------------------------ football-data.co.uk
def football_data_file(path: Path, country: str, tier: int, division: str | None = None) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="latin1", on_bad_lines="skip")
    df.columns = [c.lstrip("﻿").lstrip("ï»¿") for c in df.columns]
    df = df.rename(columns={"HG": "FTHG", "AG": "FTAG", "HT": "HomeTeam", "AT": "AwayTeam"})
    needed = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]
    if not set(needed) <= set(df.columns):
        log.warning("skipping unreadable football-data file %s", path.name)  # some early files are empty
        return _frame("football_data")
    df = df.dropna(subset=needed[1:])
    # some early files hold another league's data (1993/94 P1 is La Liga):
    # keep only rows labelled with the division we asked for
    if division and "Div" in df.columns:
        wrong = df["Div"].astype(str).str.strip() != division
        if wrong.all():
            log.warning("skipping %s: it holds division %s, not %s", path.name, df["Div"].iloc[0], division)
            return _frame("football_data")
        df = df[~wrong]
    code = path.stem.split("_")[0]
    start = int(code[:2])
    return _frame("football_data", file_name=_rel(path),
                  match_date=pd.to_datetime(df["Date"], dayfirst=True, format="mixed"),
                  season=1900 + start if start >= 90 else 2000 + start,
                  competition=f"{country}-L", tier=tier, round="league",
                  home_club=df["HomeTeam"].str.strip(), away_club=df["AwayTeam"].str.strip(),
                  home_goals=df["FTHG"].astype(int), away_goals=df["FTAG"].astype(int),
                  home_country=country, away_country=country)


def football_data(folder: Path, divisions: dict[str, list]) -> pd.DataFrame:
    """`divisions` maps division code (E0, SP1, ...) -> [country, tier].
    Competition codes are '<country>-L'."""
    frames = []
    for p in sorted(folder.glob("*.csv")):
        div = p.stem.split("_")[1]
        if div in divisions:
            country, tier = divisions[div]
            df = football_data_file(p, country, int(tier), div)
            if len(df):
                frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else _frame("football_data")


# ------------------------------------------------------------ transfermarkt-datasets
# Country names (Transfermarkt, DataRozhlas) -> 3-letter codes as used by
# engsoccerdata's champs.csv. Historical states keep their own codes.
COUNTRY = {
    "England": "ENG", "Scotland": "SCO", "Wales": "WAL", "Northern Ireland": "NIR",
    "Republic of Ireland": "IRL", "Spain": "ESP", "Germany": "GER", "West Germany": "GER",
    "East Germany": "GDR", "Saar Protectorate": "SAA", "Italy": "ITA", "France": "FRA",
    "Portugal": "POR", "Netherlands": "NED", "Belgium": "BEL", "Luxembourg": "LUX",
    "Switzerland": "SUI", "Austria": "AUT", "Turkey": "TUR", "Türkiye": "TUR", "Greece": "GRE",
    "Cyprus": "CYP", "Malta": "MLT", "Gibraltar": "GIB", "Denmark": "DEN", "Sweden": "SWE",
    "Norway": "NOR", "Finland": "FIN", "Iceland": "ISL", "Faroe Islands": "FRO",
    "Russia": "RUS", "Soviet Union": "URS", "Commonwealth of Independent States": "CIS",
    "Ukraine": "UKR", "Belarus": "BLR", "Moldova": "MDA", "Poland": "POL",
    "Czech Republic": "CZE", "Czechoslovakia": "TCH", "Slovakia": "SVK", "Hungary": "HUN",
    "Romania": "ROU", "Bulgaria": "BUL", "Serbia": "SRB", "Serbia and Montenegro": "SCG",
    "Federal Republic of Yugoslavia": "SCG", "Socialist Federal Republic of Yugoslavia": "YUG",
    "Croatia": "CRO", "Slovenia": "SVN", "Bosnia and Herzegovina": "BIH", "Montenegro": "MNE",
    "North Macedonia": "MKD", "Albania": "ALB", "Kosovo": "KOS",
    "Israel": "ISR", "Latvia": "LVA", "Lithuania": "LTU", "Estonia": "EST", "Georgia": "GEO",
    "Armenia": "ARM", "Azerbaijan": "AZE", "Kazakhstan": "KAZ", "Andorra": "AND",
    "San Marino": "SMR", "Liechtenstein": "LIE",
}
TM_COUNTRY = COUNTRY


def transfermarkt(folder: Path, competitions: dict[str, str]) -> pd.DataFrame:
    """`competitions` maps Transfermarkt competition_id -> our competition code."""
    g = pd.read_csv(folder / "games.csv.gz")
    g = g[g["competition_id"].isin(competitions) & g["home_club_goals"].notna()]
    clubs = pd.read_csv(folder / "clubs.csv.gz")
    comps = pd.read_csv(folder / "competitions.csv.gz")
    league_country = comps.set_index("competition_id")["country_name"].map(TM_COUNTRY)
    club_country = clubs.set_index("club_id")["domestic_competition_id"].map(league_country)
    comp = g["competition_id"].map(competitions)
    rnd = g["round"].astype(str)
    neutral = (rnd.eq("Final") | g["competition_id"].eq("USC") |
               (comp.eq("ENG-FAC") & rnd.str.contains("Semi", case=False)))
    return _frame("transfermarkt", file_name=_rel(folder / "games.csv.gz"),
                  match_date=pd.to_datetime(g["date"]), season=g["season"].astype(int),
                  competition=comp, round=rnd,
                  home_club=g["home_club_id"].astype(int).astype(str),
                  away_club=g["away_club_id"].astype(int).astype(str),
                  home_goals=g["home_club_goals"].astype(int), away_goals=g["away_club_goals"].astype(int),
                  neutral=neutral,
                  home_country=g["home_club_id"].map(club_country),
                  away_country=g["away_club_id"].map(club_country),
                  home_name=g["home_club_name"], away_name=g["away_club_name"])


# ------------------------------------------------------------ ESPN scoreboard
def espn(folder: Path, slugs: dict[str, str], playoffs_only: bool = True) -> pd.DataFrame:
    """Read cached ESPN scoreboard JSON (one file per slug per year).
    `slugs` maps ESPN league slug -> our competition code. League slugs
    (eng.2 etc.) are only used for their play-off matches."""
    rows = []
    for slug, comp in slugs.items():
        for path in sorted((folder / slug).glob("*.json")):
            for ev in json.loads(path.read_text(encoding="utf-8")).get("events", []):
                if not ev.get("status", {}).get("type", {}).get("completed"):
                    continue                 # unplayed, or no status at all (some cup fixtures)
                stage = (ev.get("season") or {}).get("slug", "")
                # play-off stages: "promotion-semifinals"/"promotion-final" since
                # 2020, plain "semi-finals"/"semifinals"/"final" before
                is_playoff = ("promotion" in stage or "playoff" in stage
                              or stage in ("semi-finals", "semifinals", "final"))
                if comp == "ENG-PO" and playoffs_only and not is_playoff:
                    continue
                c = ev["competitions"][0]
                side = {t["homeAway"]: t for t in c["competitors"]}
                h, a = side["home"], side["away"]
                status = ev["status"]["type"]["name"]
                rows.append({
                    "file_name": f"espn/{slug}/{path.name}",
                    "match_date": pd.Timestamp(ev["date"]).tz_convert("Europe/London").tz_localize(None).normalize(),
                    "competition": comp, "round": stage or None,
                    "home_club": h["team"]["id"], "away_club": a["team"]["id"],
                    "home_name": h["team"]["displayName"], "away_name": a["team"]["displayName"],
                    "home_goals": int(h["score"]), "away_goals": int(a["score"]),
                    # finals are at neutral venues, as are FA Cup semi-finals
                    "neutral": bool(c.get("neutralSite")) or stage.endswith("final")
                               or (comp == "ENG-FAC" and "semi" in stage),
                    "extra_time": status in ("STATUS_FINAL_AET", "STATUS_FINAL_PEN"),
                    "home_pens": h.get("shootoutScore"), "away_pens": a.get("shootoutScore"),
                })
    if not rows:
        return _frame("espn")
    df = pd.DataFrame(rows).drop_duplicates(["match_date", "home_club", "away_club"])
    df["season"] = season_from_date(df["match_date"])
    return _frame("espn", **{c: df[c] for c in df.columns})


# ------------------------------------------------------------ DataRozhlas (Wikipedia)
def datarozhlas(path: Path, competitions: dict[str, str]) -> pd.DataFrame:
    """European club competitions 1955- scraped from Wikipedia by DataRozhlas.
    Club keys are Wikipedia page slugs. Awarded/annulled/unplayed results
    are dropped. A final is neutral when it was a single match."""
    d = pd.read_csv(path)
    d = d[d["competition"].isin(competitions)]
    d = d.drop_duplicates(["competition", "season", "phase", "homeTeam", "awayTeam", "score"])
    score = d["score"].astype(str).str.extract(r"^(\d+)-(\d+)$")
    ok = score[0].notna()
    d = d[ok].assign(hg=score.loc[ok, 0].astype(int), ag=score.loc[ok, 1].astype(int))
    d["when"] = pd.to_datetime(d["date"].fillna(d["estimatedDate"]), errors="coerce")
    d = d[d["when"].notna()]
    # Undated two-legged ties get the same estimated date for both legs; space
    # repeat meetings of a pairing on one date 14 days apart (order unknown).
    pair = d[["homeTeam", "awayTeam"]].astype(str).apply(sorted, axis=1).str.join("|")
    rep = d.groupby([d["competition"], d["season"], pair, d["when"]]).cumcount()
    d["when"] = d["when"] + pd.to_timedelta(rep * 14, unit="D")
    phase = d["phase"].astype(str).str.lower()
    d["finals"] = phase.eq("final").groupby([d["competition"], d["season"]]).transform("sum")
    comp = d["competition"].map(competitions)
    return _frame("datarozhlas", file_name=_rel(path),
                  match_date=d["when"], season=d["season"].str[:4].astype(int),
                  competition=comp, round=phase,
                  home_club=d["homeTeamUrl"].fillna(d["homeTeam"]),
                  away_club=d["awayTeamUrl"].fillna(d["awayTeam"]),
                  home_goals=d["hg"], away_goals=d["ag"],
                  neutral=phase.eq("final") & d["finals"].eq(1),
                  home_country=d["homeTeamCountry"].map(COUNTRY),
                  away_country=d["awayTeamCountry"].map(COUNTRY),
                  home_name=d["homeTeam"], away_name=d["awayTeam"])


# ------------------------------------------------------------ RSSSF results grids
def _round_robin(n: int) -> list[list[tuple[int, int]]]:
    """Circle-method rounds for n teams (a bye is added if n is odd): every
    team plays once per round, every pair meets once."""
    idx = list(range(n)) + ([None] if n % 2 else [])
    m = len(idx)
    rounds = []
    for r in range(m - 1):
        pairs = [(idx[i], idx[m - 1 - i]) for i in range(m // 2)]
        rounds.append([(a, b) if r % 2 == 0 else (b, a) for a, b in pairs if a is not None and b is not None])
        idx = [idx[0]] + [idx[-1]] + idx[1:-1]
    return rounds


def _first_sunday(year: int, month: int = 9, day: int = 1) -> pd.Timestamp:
    d = pd.Timestamp(year, month, day)
    return d + pd.Timedelta(days=(6 - d.weekday()) % 7)


def _schedule(blocks: list[list[dict]], season: int, start: pd.Timestamp | None = None) -> list[dict]:
    """Dates for one season-tier's matches, set in place as "match_date" plus
    a "dating" label. Blocks are the season's grids or sections in page
    order; a block whose clubs overlap an earlier block's (a later phase)
    starts the week after that block ends, a disjoint one (a parallel group)
    at the same time as the first.

      printed (month, day) -> that date ("league")
      round only           -> one round a week from the start, by default the
                              first Sunday of September ("league (date from round)")
      neither (bare grid)  -> a synthetic double round-robin, one match per
                              club a week ("league (date assigned)")"""
    begin = start or _first_sunday(season)
    seen, out = [], []
    for rows in blocks:
        if not rows:
            continue
        clubs = {r["home"] for r in rows} | {r["away"] for r in rows}
        prev = [end for c, end in seen if c & clubs]
        t0 = max(prev) + pd.Timedelta(weeks=1) if prev else begin
        for r in rows:
            if r["md"] is not None:
                mon, day = r["md"]
                try:
                    r["match_date"] = pd.Timestamp(season if mon >= 7 else season + 1, mon, day)
                    r["dating"] = "league"
                except ValueError:          # impossible printed date: fall back to the round
                    r["md"] = None
            if r["md"] is None and r["round"] is not None:
                r["match_date"] = t0 + pd.Timedelta(weeks=r["round"] - 1)
                r["dating"] = "league (date from round)"
        undated = [r for r in rows if r["md"] is None and r["round"] is None]
        busy: dict = {}
        for r in rows:
            if "match_date" in r:
                for c in (r["home"], r["away"]):
                    busy.setdefault(c, set()).add(r["match_date"])
        if undated and busy:
            # a few grid matches missing from the round list: the first week
            # (from the block start) in which neither club plays
            for r in undated:
                when = t0
                while when in busy.get(r["home"], ()) or when in busy.get(r["away"], ()):
                    when += pd.Timedelta(weeks=1)
                r["match_date"], r["dating"] = when, "league (date assigned)"
                for c in (r["home"], r["away"]):
                    busy.setdefault(c, set()).add(when)
        elif undated:
            # clubs in grid order where known, so the schedule is the same on every build
            first_pos: dict = {}
            for r in undated:
                for side, k in (("home", "i"), ("away", "j")):
                    first_pos[r[side]] = min(first_pos.get(r[side], 99), r.get(k, 99))
            names = sorted(first_pos, key=lambda c: (first_pos[c], c))
            idx = {c: k for k, c in enumerate(names)}
            rounds = _round_robin(len(names))
            slot = {}
            for k, rnd in enumerate(rounds + [[(b, a) for a, b in r] for r in rounds]):
                for h, a in rnd:
                    slot[(h, a)] = k
            for r in undated:
                r["match_date"] = t0 + pd.Timedelta(weeks=slot[(idx[r["home"]], idx[r["away"]])])
                r["dating"] = "league (date assigned)"
        seen.append((clubs, max(r["match_date"] for r in rows)))
        out.extend(rows)
    return out


def _league_frame(source: str, rows: list[dict], competition: str, country: str) -> pd.DataFrame:
    if not rows:
        return _frame(source)
    df = pd.DataFrame(rows)
    names = {side: df[f"{side}_name"] if f"{side}_name" in df else df[side] for side in ("home", "away")}
    return _frame(source, file_name=df["file_name"], match_date=df["match_date"], season=df["season"],
                  competition=competition, tier=df["tier"].astype(int), round=df["dating"],
                  home_club=df["home"], away_club=df["away"], home_goals=df["hg"], away_goals=df["ag"],
                  home_country=country, away_country=country,
                  home_name=names["home"], away_name=names["away"])


def _dedupe(rows: list[dict], where: str) -> list[dict]:
    """First listing of each (home, away) in a block; later ones are replays
    or listing slips."""
    seen, out = set(), []
    for r in rows:
        key = (r["home"], r["away"])
        if key in seen:
            log.debug("%s: %s v %s listed twice, keeping the first", where, *key)
            continue
        seen.add(key)
        out.append(r)
    return out


def rsssf_league(folder: Path, competition: str, country: str, tiers: dict) -> pd.DataFrame:
    """RSSSF season pages saved as <start year>.html. `tiers` maps a tier to
    its section headings ({start, end} regexes, see grids.sections), or to
    None when the whole page is that tier's one results grid.

    Within a section a complete results grid gives the results, and round
    lists or stage pairs, when present, their round order and dates; without
    a grid the round lists give the results too. See _schedule for dates."""
    out = []
    for path in sorted(folder.glob("*.html")):
        season = int(path.stem)
        text = grids.page_text(path)
        for tier, sec in tiers.items():
            where = f"{competition} {season} tier {tier}"
            bodies = [text] if sec is None else [b for _, b in grids.sections(text, sec["start"], sec["end"])]
            blocks = []
            for body in bodies:
                ordered, grid = grids.section_matches(body)
                if grid and ordered:
                    grid, clashes = grids.order_grid(ordered, grid)
                    if clashes:
                        log.info("%s: %d results differ between grid and round list (grid kept)", where, clashes)
                    unplaced = sum(r["round"] is None for r in grid)
                    if unplaced:
                        log.info("%s: %d grid matches not in the round list (dates assigned)", where, unplaced)
                if grid:
                    for g in sorted({r["group"] for r in grid}):
                        blocks.append(_dedupe([r for r in grid if r["group"] == g], where))
                elif ordered:
                    blocks.append(_dedupe(ordered, where))
            for r in _schedule(blocks, season):
                out.append(dict(r, season=season, tier=int(tier), file_name=f"rsssf/{folder.name}/{path.name}"))
    return _league_frame("rsssf", out, competition, country)


# ------------------------------------------------------------ RSSSF championship final rounds
_FR_SEASON = re.compile(r"^\s*(\d{4})-(\d{2})\s*$")
_FR_HEADING = re.compile(r"^\s*([A-Z][^:]{0,60}):\s*$")
# "(Berlin)   Borussia Dortmund    4-2 Karlsruher SC   [aet]" - a named venue is neutral
_FR_KNOCKOUT = re.compile(r"^\s*(?:\(([^)]*)\)\s+)?(\S.*?\S)\s+(\d+)-(\d+)\s+(\S.*?\S)\s*(\[[^\]]*\])?\s*$")
# "Schalke 04   -  1. FC Kaiserslautern  3:1   13.5.1956" - group games, home and away
_FR_GROUP = re.compile(r"^\s*(?:\(([^)]*)\)\s+)?(\S.*?\S)\s+-\s+(\S.*?\S)\s+(\d+):(\d+)\s*(\[[^\]]*\])?\s*"
                       r"(\d{1,2})?\.?(\d{1,2})?\.?(\d{4})?\s*$")


def rsssf_final_rounds(path: Path, competition: str, country: str, seasons: tuple[int, int]) -> pd.DataFrame:
    """A national championship's final rounds from one RSSSF history page
    (sections headed "1955-56"): knockout ties at named neutral venues and
    home-and-away groups. Dates come from "[Jun 24]" lines or a trailing
    "13.5.1956"; an undated game takes the last date seen in its season."""
    text = grids.page_text(path)
    out, season, rnd, mode, last = [], None, None, None, None
    for line in text.split("\n"):
        m = _FR_SEASON.match(line)
        if m:
            season, rnd, mode, last = int(m.group(1)), None, None, None
            continue
        if season is None or not seasons[0] <= season <= seasons[1]:
            continue
        m = _FR_HEADING.match(line)
        if m:
            rnd = m.group(1).strip()
            mode = "table" if rnd.lower() == "table" else "games"
            continue
        if mode != "games":
            continue
        s = line.strip()
        if re.fullmatch(r"\[[^\]]*\]", s) and grids._month_day(s):
            mon, day = grids._month_day(s)
            last = pd.Timestamp(season + 1 if mon <= 7 else season, mon, day)
            continue
        m = _FR_GROUP.match(line)
        if m:
            venue, home, away, hg, ag, note, d, mo, y = m.groups()
            if d and mo and y:
                last = pd.Timestamp(int(y), int(mo), int(d))
            out.append({"home": home, "away": away, "hg": int(hg), "ag": int(ag), "date": last,
                        "neutral": venue is not None, "aet": bool(note and "aet" in note.lower()),
                        "round": rnd, "season": season})
            continue
        m = _FR_KNOCKOUT.match(line)
        if m:
            venue, home, hg, ag, away, note = m.groups()
            out.append({"home": home, "away": away, "hg": int(hg), "ag": int(ag), "date": last,
                        "neutral": venue is not None, "aet": bool(note and "aet" in note.lower()),
                        "round": rnd, "season": season})
    df = pd.DataFrame(out)
    if df.empty:
        return _frame("rsssf")
    # knockout ties before the first dated game: early June of the season's end year
    df["date"] = df["date"].fillna(pd.Series([pd.Timestamp(s + 1, 6, 1) for s in df["season"]], index=df.index))
    return _frame("rsssf", file_name=f"rsssf/{path.parent.name}/{path.name}",
                  match_date=pd.to_datetime(df["date"]), season=df["season"], competition=competition,
                  round=df["round"], home_club=df["home"], away_club=df["away"],
                  home_goals=df["hg"], away_goals=df["ag"], neutral=df["neutral"], extra_time=df["aet"],
                  home_country=country, away_country=country)


# ------------------------------------------------------------ Wikipedia results grids
_WP_LINK = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")


def _template(text: str, start: int) -> str:
    """The {{...}} template starting at `start`, nested templates included."""
    depth, i = 0, start
    while i < len(text):
        if text.startswith("{{", i):
            depth, i = depth + 1, i + 2
        elif text.startswith("}}", i):
            depth, i = depth - 1, i + 2
            if depth == 0:
                break
        else:
            i += 1
    return text[start:i]


def wikipedia_grids(text: str) -> list[dict]:
    """Every {{#invoke:Sports results}} grid in a page's wikitext, in page
    order: {"clubs": {code: (key, display name)}, "order": [code, ...],
    "scores": {(home code, away code): (hg, ag)}, "start_date": str | None,
    "section": the level-2 heading above the grid}.
    A club's key is the article its name links to (stable across seasons
    and unique, e.g. "CD Málaga" vs "Málaga CF"), else its plain name."""
    out = []
    heads = [(h.start(), h.group(1).strip()) for h in re.finditer(r"^==([^=\n]+)==\s*$", text, re.M)]
    for m in re.finditer(r"\{\{\s*#invoke:\s*sports results", text, re.I):
        body = _template(text, m.start())
        section = next((h for pos, h in reversed(heads) if pos < m.start()), "")
        params = {}
        for part in re.split(r"\|(?=\s*[\wÀ-ɏ]+\s*=)", body):
            k, eq, v = part.partition("=")
            if eq:
                params[k.strip()] = v.strip()
        order = [params[k] for k in sorted((k for k in params if re.fullmatch(r"team\d+", k)),
                                            key=lambda k: int(k[4:]))]
        if not order and "team_order" in params:
            order = [c.strip() for c in params["team_order"].split(",") if c.strip()]
        clubs = {}
        for code in order:
            raw = re.sub(r"<[^>]*>|'{2,}", "", params.get(f"name_{code}", code)).strip()
            raw = re.sub(r"\{\{[^{}]*\}\}", "", raw).strip()
            link = _WP_LINK.search(raw)
            clubs[code] = ((link.group(1).strip(), (link.group(2) or link.group(1)).strip()) if link
                           else (raw, raw))
        scores = {}
        for k, v in params.items():
            mm = re.fullmatch(r"match_(.+?)_(.+)", k)
            if not mm or mm.group(1) not in clubs or mm.group(2) not in clubs:
                continue
            v = _WP_LINK.sub(lambda x: x.group(2) or x.group(1), v)
            sc = re.match(r"\s*(\d+)\s*[–—-]\s*(\d+)", v)
            if sc:
                scores[(mm.group(1), mm.group(2))] = (int(sc.group(1)), int(sc.group(2)))
        out.append({"clubs": clubs, "order": order, "scores": scores, "start_date": params.get("start_date"),
                    "section": section})
    return out


def wikipedia_league(folder: Path, competition: str, country: str, tier: int) -> pd.DataFrame:
    """Wikipedia season articles saved as <start year>.txt (raw wikitext).
    Every results grid on the page is a block of `tier` (regional groups and
    later phases included), except those under a play-off or qualification
    heading: promotion play-off groups mix in top-flight clubs, and qualifying
    rounds (Greece's Panhellenic Championship) lower-level ones. Dates are synthetic, from the
    page's start_date or else the first Sunday of September; see _schedule."""
    out = []
    for path in sorted(folder.glob("*.txt")):
        season = int(path.stem)
        blocks, start = [], None
        for g, grid in enumerate(wikipedia_grids(path.read_text(encoding="utf-8"))):
            if re.search(r"play-?offs?|qualif", grid["section"], re.I):
                continue
            if start is None and grid["start_date"]:
                start = pd.to_datetime(grid["start_date"], errors="coerce")
                start = None if pd.isna(start) else start
            pos = {c: k for k, c in enumerate(grid["order"])}
            blocks.append([{"round": None, "md": None, "group": g, "i": pos[h], "j": pos[a],
                            "home": grid["clubs"][h][0], "away": grid["clubs"][a][0],
                            "home_name": grid["clubs"][h][1], "away_name": grid["clubs"][a][1],
                            "hg": hg, "ag": ag} for (h, a), (hg, ag) in grid["scores"].items()])
        for r in _schedule(blocks, season, start):
            out.append(dict(r, season=season, tier=tier, file_name=f"wikipedia/{folder.name}/{path.name}"))
    return _league_frame("wikipedia", out, competition, country)
