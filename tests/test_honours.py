import pandas as pd

from football_elo import honours


def _m(rows, comp, ctype, season=2010, tier=None, source="x"):
    out = []
    for i, (date, h, a, hg, ag, *pens) in enumerate(rows):
        out.append(dict(match_id=f"{comp}{season}{i}", match_date=pd.Timestamp(date), season=season, competition=comp,
                        comp_type=ctype, tier=tier, round="", home_club=h, away_club=a, home_goals=hg, away_goals=ag,
                        home_pens=pens[0] if pens else None, away_pens=pens[1] if pens else None, source=source))
    return pd.DataFrame(out)


def test_league_table_puts_the_listed_champion_first_and_counts_points():
    m = _m([("2010-09-01", "A", "B", 2, 0), ("2010-10-01", "B", "C", 1, 0), ("2010-11-01", "C", "A", 0, 0),
            ("2011-01-01", "B", "A", 3, 0)], "ENG-L", "league", tier=1)
    t = honours.league_tables(m, {"ENG-L": "ENG"}, pd.DataFrame(columns=["competition", "season", "club"]))
    t = t.set_index("club")
    assert t.loc["B", "pos"] == 1 and t.loc["B", "pts"] == 6 and t.loc["A", "pts"] == 4
    champs = pd.DataFrame([{"competition": "ENG-L", "season": 2010, "club": "A"}])
    t = honours.league_tables(m, {"ENG-L": "ENG"}, champs).set_index("club")
    assert t.loc["A", "pos"] == 1 and t.loc["B", "pos"] == 2 and t.loc["C", "n"] == 3


def test_two_points_for_a_win_before_the_change():
    assert honours.win_points("ENG", 1980) == 2 and honours.win_points("ENG", 1981) == 3
    assert honours.win_points("ITA", 1993) == 2 and honours.win_points("ESP", 1994) == 2


def _cup():
    # eight clubs: quarter-finals, semi-finals, final (level, settled on penalties)
    return _m([("2011-03-01", "A", "B", 2, 0), ("2011-03-01", "C", "D", 1, 0), ("2011-03-01", "E", "F", 0, 1),
               ("2011-03-01", "G", "H", 3, 1), ("2011-04-01", "A", "C", 1, 0), ("2011-04-01", "F", "G", 2, 2, 4, 3),
               ("2011-05-20", "A", "F", 1, 1, 3, 5)], "ENG-FAC", "cup")


def test_cup_runs_take_the_winner_from_trophies_and_place_the_rest_by_clubs_left():
    trophies = pd.DataFrame([{"competition": "ENG-FAC", "season": 2010, "winner": "F", "runner_up": "A"}])
    r = honours.runs(_cup(), trophies, current=2026).set_index("club")
    assert r.loc["F", "stage"] == "W" and r.loc["A", "stage"] == "F" and r.loc["A", "by"] == "F"
    assert r.loc["C", "stage"] == "SF" and r.loc["C", "by"] == "A" and r.loc["B", "stage"] == "QF"


def test_an_unsettled_final_leaves_both_clubs_as_finalists():
    r = honours.runs(_cup(), pd.DataFrame(columns=["competition", "season", "winner", "runner_up"]), 2026)
    r = r.set_index("club")
    assert r.loc["A", "stage"] == "F" and r.loc["F", "stage"] == "F" and "W" not in set(r["stage"])


def test_in_the_current_season_a_cup_side_is_still_in_until_it_loses():
    m = _m([("2026-09-01", "A", "B", 2, 0), ("2026-09-01", "C", "D", 0, 1)], "ENG-LC", "cup", season=2026)
    r = honours.runs(m, pd.DataFrame(columns=["competition", "season", "winner", "runner_up"]), 2026).set_index("club")
    assert r.loc["A", "stage"] == "in" and r.loc["D", "stage"] == "in" and r.loc["B", "stage"] != "in"


def test_strip_slots():
    comps = pd.DataFrame([{"competition": "ENG-FAC", "comp_type": "cup", "country": "ENG"},
                          {"competition": "ENG-LC", "comp_type": "cup", "country": "ENG"},
                          {"competition": "UCL", "comp_type": "europe", "country": None},
                          {"competition": "UEL", "comp_type": "europe", "country": None}])
    run = pd.DataFrame([("ENG-FAC", 2010, "A", "F", "F"), ("UCL", 2010, "A", "out", "X"), ("UEL", 2010, "A", "QF", "Y"),
                        ("ENG-FAC", 2010, "B", "W", None)], columns=["competition", "season", "club", "stage", "by"])
    tables = pd.DataFrame(columns=["competition", "tier", "season", "club", "pos", "n", "p", "w", "d", "l", "gf", "ga", "pts"])
    want = pd.DataFrame([("A", 2010, "ENG"), ("B", 2010, "ENG"), ("C", 2010, "ESP"), ("D", 1955, "ENG")],
                        columns=["club", "season", "country"])
    s = honours.strip(want, tables, run, comps).set_index("club")
    assert s.loc["A", "cup"] == ["ENG-FAC", "F", "F"] and s.loc["A", "europe"] == ["UEL", "QF", "Y"]
    assert s.loc["A", "lcup"] is None            # no League Cup matches held for 2010/11 here
    assert s.loc["B", "europe"] == "-" and s.loc["C", "lcup"] == "na" and s.loc["C", "cup"] is None
    assert s.loc["D", "lcup"] == "na"            # before the League Cup began


def test_a_club_missing_from_a_partial_cup_season_went_out_early():
    comps = pd.DataFrame([{"competition": "ESP-L", "comp_type": "league", "country": "ESP"},
                          {"competition": "ESP-CDR", "comp_type": "cup", "country": "ESP"}])
    top = [f"T{i}" for i in range(8)]
    tables = pd.DataFrame([dict(competition="ESP-L", tier=1, season=2000, club=c, pos=i + 1, n=8, p=0, w=0, d=0, l=0,
                                gf=0, ga=0, pts=0) for i, c in enumerate(top)])
    want = pd.DataFrame([("T0", 2000, "ESP")], columns=["club", "season", "country"])
    part = pd.DataFrame([("ESP-CDR", 2000, c, "QF", None) for c in top[1:4]], columns=["competition", "season", "club", "stage", "by"])
    assert honours.strip(want, tables, part, comps).iloc[0]["cup"] == "early"
    full = pd.DataFrame([("ESP-CDR", 2000, c, "out", None) for c in top[1:]], columns=part.columns)
    assert honours.strip(want, tables, full, comps).iloc[0]["cup"] == "-"
