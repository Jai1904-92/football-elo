import pandas as pd

from football_elo import grids, silver, sources

GRID = """
Eerste divisie     1977-1978

                  Amf  DBos Camb Dord
   SC Amersfoort  ***  1-1  0-0  0-3
   FC Den Bosch   0-1  ***  2-2  4-1
   Spcl. Cambuur  3-1  O-0  ***  2-0
   FC Dordrecht   1-0  2-2  1-1  ***
"""


def test_grid_parses_rows_and_fixes_typos():
    (g,) = grids.grids(GRID, min_teams=4)
    assert g["teams"] == ["SC Amersfoort", "FC Den Bosch", "Spcl. Cambuur", "FC Dordrecht"]
    assert g["scores"][(0, 3)] == (0, 3)
    assert g["scores"][(2, 1)] == (0, 0)          # letter O read as zero
    assert len(g["scores"]) == 12


def test_grid_with_blank_cells_places_scores_by_column():
    text = """
   Ajax       ***  1-0  2-0  3-0
   PSV        0-1  ***  1-1  2-2
   Twente          2-1  ***  1-0
   Utrecht    1-1  0-0  0-1  ***
"""
    (g,) = grids.grids(text, min_teams=4)
    assert (2, 0) not in g["scores"]               # not played
    assert g["scores"][(2, 1)] == (2, 1) and g["scores"][(2, 3)] == (1, 0)


def test_stage_pairs_return_leg_is_printed_from_first_clubs_side():
    text = """Stages 1-20   13.09.  07.02.
Avellino        -  Ascoli          =  0 - 0  *  0 - 1
"""
    first, ret = grids.stage_pairs(text)
    assert (first["round"], first["home"], first["hg"], first["ag"]) == (1, "Avellino", 0, 0)
    assert (ret["round"], ret["home"], ret["away"], ret["hg"], ret["ag"]) == (20, "Ascoli", "Avellino", 1, 0)
    assert first["md"] == (9, 13) and ret["md"] == (2, 7)


def test_round_lists_read_dates_and_skip_abandoned_and_table_rows():
    text = """Round 1
[Aug 13]
Helmond Sport            2-2 Sparta Rotterdam
  [Sergio van Dijk 8; Danny Koevermans 1]
Achilles '29             1-0 FC Oss
[Aug 14]
Eindhoven            abd Helmond Sport             [abandoned at 1-1 in 35']
 1.Heracles Almelo              36 23  6  7  67-34  75  Promoted
Round 2 (August 20)
Cesena - Pistoiese                 1-0
"""
    ms = grids.round_lists(text)
    assert [(m["home"], m["away"], m["hg"], m["ag"], m["md"]) for m in ms] == [
        ("Helmond Sport", "Sparta Rotterdam", 2, 2, (8, 13)),
        ("Achilles '29", "FC Oss", 1, 0, (8, 13)),
        ("Cesena", "Pistoiese", 1, 0, (8, 20))]


def test_round_lists_read_a_leading_full_date():
    # Serie B 2004/05: "[dd/mm/yyyy] Home  3-1 Away", scorers on the next line
    text = """Round 1
[10/09/2004] Torino Calcio S.p.A.          3-1 Verona Hellas Football Club S.p.A.
13' Massimo Marazzina (1-0); 81' Andrea Cossu (3-1)

[11/09/2004] A.C. Cesena S.p.A.            1-0 U. S. Triestina Calcio S.r.l.
"""
    ms = grids.round_lists(text)
    assert [(m["home"], m["away"], m["hg"], m["ag"], m["md"]) for m in ms] == [
        ("Torino Calcio S.p.A.", "Verona Hellas Football Club S.p.A.", 3, 1, (9, 10)),
        ("A.C. Cesena S.p.A.", "U. S. Triestina Calcio S.r.l.", 1, 0, (9, 11))]


def test_order_grid_prefers_round_list_for_a_misplaced_grid_row():
    # the grid has club X's results under club Y and vice versa: every fixture
    # of X and Y disagrees, so the round list wins for them
    teams = [f"C{i}" for i in range(12)]
    ordered = [{"round": 1, "md": None, "home": h, "away": a, "hg": 1, "ag": 0, "note": ""}
               for h in teams for a in teams if h != a]
    grid = [dict(o, hg=0 if "C0" in (o["home"], o["away"]) else 1, group=0) for o in ordered]
    out, clashes = grids.order_grid(ordered, grid)
    assert clashes == 0 and all((g["hg"], g["ag"]) == (1, 0) for g in out)


def test_schedule_dates_rounds_and_grids():
    dated = [{"round": 1, "md": (8, 27), "home": "A", "away": "B", "hg": 1, "ag": 0},
             {"round": 20, "md": None, "home": "B", "away": "A", "hg": 0, "ag": 0}]
    out = sources._schedule([dated], 1995)
    assert out[0]["match_date"] == pd.Timestamp("1995-08-27") and out[0]["dating"] == "league"
    assert out[1]["match_date"] == pd.Timestamp("1995-09-03") + pd.Timedelta(weeks=19)
    # a bare grid: synthetic double round robin, one match per club per week
    grid = [{"round": None, "md": None, "home": h, "away": a, "i": i, "j": j, "hg": 0, "ag": 0}
            for i, h in enumerate("ABCD") for j, a in enumerate("ABCD") if h != a]
    out = sources._schedule([grid], 1960)
    days = pd.DataFrame([(r["match_date"], c) for r in out for c in (r["home"], r["away"])])
    assert not days.duplicated().any() and days[0].nunique() == 6


WIKI = """==Group North==
===Results===
{{#invoke:sports results|main
| team1= ALA | team2= MGA
|name_ALA = [[Deportivo Alavés|Alavés]]
|name_MGA = [[CD Málaga|Málaga]]
| match_ALA_MGA = 2–0
| match_MGA_ALA = [[x|1–1]]
}}
==Promotion playoffs==
{{#invoke:sports results|main
| team1= ALA | team2= BET
|name_BET = [[Real Betis]]
| match_ALA_BET = 1–1
}}
"""


def test_wikipedia_grids_key_clubs_by_article(tmp_path):
    (tmp_path / "1955.txt").write_text(WIKI, encoding="utf-8")
    df = sources.wikipedia_league(tmp_path, "ESP-L", "ESP", 2)
    assert sorted(zip(df["home_club"], df["away_club"], df["home_goals"], df["away_goals"])) == [
        ("CD Málaga", "Deportivo Alavés", 1, 1), ("Deportivo Alavés", "CD Málaga", 2, 0)]
    assert set(df["home_name"]) == {"Alavés", "Málaga"}      # play-off grid skipped


class _Reader:
    def __init__(self, frames):
        self.frames = frames

    def read(self, source, competition):
        return self.frames[source].copy()


def test_replace_partial_takes_over_thin_seasons_only():
    def frame(source, season, n):
        return pd.DataFrame({"season": season, "tier": 2, "match_date": pd.Timestamp(season, 10, 1),
                             "competition": "X", "source": source, "home_club": range(n), "away_club": range(n)})
    cfg = {"competitions": {"X": {"windows": [{"source": "a"}, {"source": "b", "replace_partial": 0.9}]}}}
    reader = _Reader({"a": pd.concat([frame("a", 2000, 380), frame("a", 2001, 159)]),
                      "b": pd.concat([frame("b", 2000, 380), frame("b", 2001, 380), frame("b", 1990, 380)])})
    out = silver.combine_windows(cfg, "X", reader)
    assert out.groupby("season")["source"].agg(set).to_dict() == {1990: {"b"}, 2000: {"a"}, 2001: {"b"}}


def test_match_ids_drop_accented_letters_whatever_the_pandas_version():
    df = pd.DataFrame({"match_date": pd.to_datetime(["2025-09-28"]), "home_club": ["Kayserispor"],
                       "away_club": ["Gençlerbirliği"]})
    assert silver.match_ids(df).tolist() == ["20250928_Kayserispor_Genlerbirlii"]


WIKI_LEGS = """==Results==
{{#invoke:sports results|main|legs=2
|team1=DIN|team2=HAJ|team3=ADM|team4=MOD
|name_DIN=[[GNK Dinamo Zagreb|Dinamo Zagreb]]
|name_HAJ={{nowrap|[[HNK Hajduk Split|Hajduk Split]]}}
|name_ADM=[[FC Admira Wacker Mödling|Admira/Wacker]]
|name_MOD=[[FC Admira Wacker Mödling|VfB Mödling]]
|match1_DIN_HAJ=1–1
|match2_DIN_HAJ=2–0
|match1_ADM_MOD=3–2
}}
"""


def test_wikipedia_grids_read_legs_and_tell_shared_articles_apart():
    grids_ = sources.wikipedia_grids(WIKI_LEGS)
    assert [g["scores"] for g in grids_] == [{("DIN", "HAJ"): (1, 1), ("ADM", "MOD"): (3, 2)}, {("DIN", "HAJ"): (2, 0)}]
    clubs = grids_[0]["clubs"]
    assert clubs["HAJ"] == ("HNK Hajduk Split", "Hajduk Split")
    assert clubs["ADM"][0] == "FC Admira Wacker Mödling [Admira/Wacker]" != clubs["MOD"][0]
