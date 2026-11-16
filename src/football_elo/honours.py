"""Where a club finished each season: league place, domestic cups, Europe.

For the honours strip on the site's world top 100 (export.season_honours).

League places are rebuilt from the results we hold: points (3 for a win from
THREE_POINTS, 2 before), then goal difference, then goals scored. The champion
in config/league_champions.csv is put first (it can differ from the table on
results alone: head-to-head rules, play-off rounds, points deductions). Other
places can be a place out where a league split, halved points or deducted
points, or settled ties on head-to-head.

Cup and European runs: the winner and runner-up come from gold.mv_trophies
(which settles finals and holds the hand-entered fixes); every other club is
placed by how many clubs were still playing when it played its last match in
that competition: semi-final with four or fewer, quarter-final with eight,
last 16 with sixteen, otherwise an earlier round. Third-place matches are left
out. In the season still being played a club is still in a domestic cup
unless it lost its last match, and still in Europe if its last match is within
STILL_IN_DAYS of the competition's latest match.
"""
from __future__ import annotations

import re

import pandas as pd

THREE_POINTS = {"ENG": 1981, "ESP": 1995, "GER": 1995, "NED": 1995, "POR": 1995}   # others 1994
STAGES = ["W", "F", "SF", "QF", "R16", "in", "out"]
RANK = {"W": 7, "F": 6, "SF": 5, "QF": 4, "R16": 3, "in": 2.5, "out": 1}
EUROPE_ORDER = {"UCL": 4, "UEL": 3, "UCWC": 3, "FAIRS": 2, "UECL": 1}
# League cups the strip gives a slot: country -> (first season, last season, competition or None if not held)
LEAGUE_CUPS = {"ENG": (1960, 9999, "ENG-LC"), "POR": (2007, 9999, "POR-TL"),
               "SCO": (1946, 9999, None), "FRA": (1994, 2019, None)}
NOT_A_RUN = r"^3pp$|third place|3rd place|uefa cup playoff"
STILL_IN_DAYS = 14
FINAL = re.compile(r"^\s*finals?\s*$", re.I)   # Wikipedia pages: the last match is the final only if so named


def win_points(country: str | None, season: int) -> int:
    return 3 if season >= THREE_POINTS.get(country or "", 1994) else 2


def league_tables(matches: pd.DataFrame, country_of: dict[str, str], champions: pd.DataFrame) -> pd.DataFrame:
    """One row per club per league season: competition, tier, pos, n, p, w, d, l, gf, ga, pts."""
    lg = matches[(matches["comp_type"] == "league") & matches["tier"].notna()]
    sides = []
    for me, gf, ga in (("home_club", "home_goals", "away_goals"), ("away_club", "away_goals", "home_goals")):
        sides.append(pd.DataFrame({"competition": lg["competition"], "tier": lg["tier"].astype(int),
                                   "season": lg["season"], "club": lg[me], "gf": lg[gf], "ga": lg[ga]}))
    x = pd.concat(sides, ignore_index=True)
    x["w"] = (x["gf"] > x["ga"]).astype(int)
    x["d"] = (x["gf"] == x["ga"]).astype(int)
    x["l"] = (x["gf"] < x["ga"]).astype(int)
    t = x.groupby(["competition", "tier", "season", "club"], as_index=False)[["gf", "ga", "w", "d", "l"]].sum()
    t["p"] = t["w"] + t["d"] + t["l"]
    wp = [win_points(country_of.get(c), s) for c, s in zip(t["competition"], t["season"])]
    t["pts"] = t["w"] * pd.Series(wp, index=t.index) + t["d"]
    champ = set(zip(champions["competition"], champions["season"], champions["club"]))
    t["champ"] = [(c, s, k) in champ and tier == 1
                  for c, s, k, tier in zip(t["competition"], t["season"], t["club"], t["tier"])]
    t["gd"] = t["gf"] - t["ga"]
    t = t.sort_values(["competition", "tier", "season", "champ", "pts", "gd", "gf"],
                      ascending=[True, True, True, False, False, False, False])
    g = t.groupby(["competition", "tier", "season"])
    t["pos"] = g.cumcount() + 1
    t["n"] = g["club"].transform("size")
    return t.drop(columns=["champ", "gd"]).reset_index(drop=True)


def runs(matches: pd.DataFrame, trophies: pd.DataFrame, current: int) -> pd.DataFrame:
    """One row per club per cup or European competition season: competition, season, club, stage, by
    (the club that knocked it out, or beat it in the final)."""
    m = matches[matches["comp_type"].isin(["cup", "europe"]) & (matches["competition"] != "USC")]
    m = m[~m["round"].fillna("").astype(str).str.contains(NOT_A_RUN, case=False)]
    m = m.sort_values(["match_date", "match_id"])
    final = {(r.competition, r.season): (r.winner, r.runner_up) for r in trophies.itertuples()}
    out = []
    for (comp, season), g in m.groupby(["competition", "season"], sort=False):
        long = pd.concat([
            pd.DataFrame({"club": g["home_club"], "opp": g["away_club"], "date": g["match_date"],
                          "gf": g["home_goals"], "ga": g["away_goals"], "pf": g["home_pens"], "pa": g["away_pens"]}),
            pd.DataFrame({"club": g["away_club"], "opp": g["home_club"], "date": g["match_date"],
                          "gf": g["away_goals"], "ga": g["home_goals"], "pf": g["away_pens"], "pa": g["home_pens"]}),
        ]).sort_values("date", kind="stable")
        last = long.groupby("club").tail(1).set_index("club")
        alive = last["date"].map(lambda d: int((last["date"] >= d).sum()))
        winner, runner_up = final.get((comp, season), (None, None))
        a = b = None
        end = g.iloc[-1]
        if winner is None and season < current and (end.source != "wikipedia" or FINAL.match(str(end["round"]))):
            a, b = end.home_club, end.away_club   # a final the data can't settle: both are finalists
        latest = g["match_date"].max()
        cup = g["comp_type"].iloc[0] == "cup"
        for club, r in last.iterrows():
            n = alive[club]
            if club == winner:
                stage, by = "W", None
            elif club in (runner_up, a, b):
                stage, by = "F", (winner if club == runner_up else (b if club == a else a))
            else:
                lost = r.gf < r.ga or (r.gf == r.ga and pd.notna(r.pf) and r.pf < r.pa)
                if season >= current and (not lost if cup else r.date >= latest - pd.Timedelta(days=STILL_IN_DAYS)):
                    stage, by = "in", None
                else:
                    stage = "SF" if n <= 4 else "QF" if n <= 8 else "R16" if n <= 16 else "out"
                    by = r.opp
            out.append((comp, season, club, stage, by))
    return pd.DataFrame(out, columns=["competition", "season", "club", "stage", "by"])


def strip(club_seasons: pd.DataFrame, tables: pd.DataFrame, run: pd.DataFrame,
          comps: pd.DataFrame) -> pd.DataFrame:
    """The four honours slots for each (club, country, season) asked for.

    league: table row or None. cup / lcup: a run, "-" (not in the rounds we
    hold), None (no data for that cup season) or, lcup only, "na" (no league
    cup). europe: the best European run or "-". runs: every cup and European
    run, for the detail card."""
    held = set(zip(run["competition"], run["season"]))
    cups = comps[comps["comp_type"] == "cup"]
    league_cups = {v[2] for v in LEAGUE_CUPS.values() if v[2]}
    main_cup = {c: k for k, c in zip(cups["competition"], cups["country"]) if k not in league_cups}
    europe = set(comps.loc[comps["comp_type"] == "europe", "competition"])
    tab = {(r.club, r.season): r for r in tables.sort_values("tier", ascending=False).itertuples()}
    by_cs: dict = {}
    for r in run.itertuples():
        by_cs.setdefault((r.club, r.season), []).append((r.competition, r.stage, r.by))

    def slot(comp, rs, season):
        if comp is None or (comp, season) not in held:
            return None
        got = [x for x in rs if x[0] == comp]
        return list(got[0]) if got else "-"

    rows = []
    for c in club_seasons.itertuples():
        rs = by_cs.get((c.club, c.season), [])
        t = tab.get((c.club, c.season))
        league = None if t is None else [t.competition, int(t.tier), int(t.pos), int(t.n), int(t.p), int(t.w),
                                         int(t.d), int(t.l), int(t.gf), int(t.ga), int(t.pts)]
        lc = LEAGUE_CUPS.get(c.country)
        lcup = "na" if not lc or not lc[0] <= c.season <= lc[1] else slot(lc[2], rs, c.season)
        eu = sorted((x for x in rs if x[0] in europe), key=lambda x: (RANK[x[1]], EUROPE_ORDER.get(x[0], 0)))
        rows.append((c.club, int(c.season), league, slot(main_cup.get(c.country), rs, c.season), lcup,
                     list(eu[-1]) if eu else "-", [list(x) for x in rs]))
    return pd.DataFrame(rows, columns=["club", "season", "league", "cup", "lcup", "europe", "runs"], dtype=object)
