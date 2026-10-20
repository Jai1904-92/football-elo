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
from pathlib import Path

import numpy as np
import pandas as pd

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
                if not ev["status"]["type"].get("completed"):
                    continue
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


def rsssf_crosstable(path: Path) -> tuple[list[str], dict[tuple[int, int], tuple[int, int]]]:
    """Teams (in row order) and scores {(home_i, away_j): (hg, ag)} from an
    RSSSF season page's results grid. Columns follow row order; the printed
    row numbers are ignored (1977/78 prints two of them swapped)."""
    import html as _html
    import re as _re
    raw = path.read_text(encoding="latin-1")
    txt = _html.unescape(_re.sub(r"<[^>]+>", "", raw))
    rows = []
    for line in txt.splitlines():
        m = _re.match(r"^\s*(\d{1,2})\s+(.+?)\s{2,}((?:X|\d+-\d+|\s)+)$", line)
        if m and "X" in m.group(3):
            cells = _re.findall(r"X|\d+-\d+", m.group(3))
            rows.append((m.group(2).strip(), cells))
    n = len(rows)
    if not n or any(len(c) != n for _, c in rows):
        raise ValueError(f"{path.name}: results grid not parsed cleanly ({n} rows)")
    scores = {}
    for i, (_, cells) in enumerate(rows):
        for j, c in enumerate(cells):
            if c != "X":
                hg, ag = c.split("-")
                scores[(i, j)] = (int(hg), int(ag))
    return [name for name, _ in rows], scores


def rsssf_league(folder: Path, competition: str, country: str) -> pd.DataFrame:
    """Season pages saved as <start year>.html. Each season gets a synthetic
    double round-robin schedule (one match per club per Sunday from the first
    Sunday of September), since the grids carry no dates."""
    out = []
    for path in sorted(folder.glob("*.html")):
        season = int(path.stem)
        teams, scores = rsssf_crosstable(path)
        first = pd.Timestamp(season, 9, 1)
        first += pd.Timedelta(days=(6 - first.weekday()) % 7)
        rounds = _round_robin(len(teams))
        schedule = rounds + [[(b, a) for a, b in r] for r in rounds]
        for k, rnd in enumerate(schedule):
            when = first + pd.Timedelta(weeks=k)
            for h, a in rnd:
                if (h, a) not in scores:
                    continue
                hg, ag = scores[(h, a)]
                out.append({"match_date": when, "season": season, "home_club": teams[h], "away_club": teams[a],
                            "home_goals": hg, "away_goals": ag, "file_name": f"rsssf/{path.parent.name}/{path.name}"})
    if not out:
        return _frame("rsssf")
    df = pd.DataFrame(out)
    return _frame("rsssf", file_name=df["file_name"], match_date=df["match_date"], season=df["season"],
                  competition=competition, tier=1, round="league (date assigned)",
                  home_club=df["home_club"], away_club=df["away_club"],
                  home_goals=df["home_goals"], away_goals=df["away_goals"],
                  home_country=country, away_country=country)
