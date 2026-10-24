from pathlib import Path

import pandas as pd

from football_elo import sources, wikicups

PAGE = """The '''1975–76 Cup''' began on 1 August 1975 and ended on 26 June 1976.

==Matches==
===First round===
{| class="wikitable"
!Home team !! Score !! Away team
|- style=font-size:90%
| align=right| [[ASV Landau]]
| align=center| '''1 – 7'''
| '''[[Hannover 96]]'''
|-
| [[Hamburger SV|HSV]] (1) || 2–2 || [[FC Bayern Munich|Bayern]] (1) || ''([[Extra time|AET]])''
|-
| [[VfL Bochum]] || w/o || [[Arminia Bielefeld]]
|}
====Replays====
{{OneLegResult|'''[[FC Bayern Munich|Bayern]]'''||0–1 {{aet}}|{{nobold|[[Hamburger SV]] (1)}}}}

==Quarter-finals==
{{TwoLegResult|[[Algeciras CF]] || 1–3 | '''[[UP Langreo]]''' || 0–0 | 1–3 |winner=2}}
{{TwoLegResult|'''[[Samsunspor]]'''||([[Away goals rule|a]]) 2–2|[[Trabzonspor]]||0–1|2–1 (4–3 p)}}

==Final==
{{football box
|date = 26 June 1976
|team1 = [[Hamburger SV]]
|score = 2–0
|team2 = [[1. FC Kaiserslautern]]
|stadium = [[Waldstadion]]
}}

==Bracket==
{{4TeamBracket
| RD1=Semi-finals
| RD2=Final
| RD1-team1 = [[Hamburger SV|Hamburg]]
| RD1-score1 = 3
| RD1-team2 = [[Rot-Weiss Essen|RW Essen]]
| RD1-score2 = 1 (4)
| RD2-team1 = '''[[Hamburger SV|Hamburg]]'''
| RD2-score1 = 2
| RD2-team2 = [[1. FC Kaiserslautern|Kaiserslautern]]
| RD2-score2 = 0
}}
"""


def _parsed():
    return {(m["home"], m["away"]): m for m in wikicups.parse_page(PAGE, 1975)}


def test_tables_read_cells_with_attributes_and_skip_walkovers():
    ms = _parsed()
    m = ms[("ASV Landau", "Hannover 96")]
    assert (m["hg"], m["ag"], m["fmt"], m["round"]) == (1, 7, "table", "First round")
    assert ms[("Hamburger SV", "FC Bayern Munich")]["aet"]
    assert ("VfL Bochum", "Arminia Bielefeld") not in ms


def test_replays_get_their_own_slot_and_wrapped_names_survive():
    m = _parsed()[("FC Bayern Munich", "Hamburger SV")]
    assert (m["hg"], m["ag"], m["aet"], m["fmt"]) == (0, 1, True, "oneleg")
    assert m["round"] == "First round" and m["slot"] == "First round / Replays"


def test_two_leg_rows_swap_the_second_leg_and_its_shootout():
    ms = _parsed()
    first, second = ms[("Algeciras CF", "UP Langreo")], ms[("UP Langreo", "Algeciras CF")]
    assert (first["leg"], first["hg"], first["ag"]) == (1, 0, 0)
    assert (second["leg"], second["hg"], second["ag"]) == (2, 3, 1)
    ret = ms[("Trabzonspor", "Samsunspor")]
    assert (ret["hg"], ret["ag"], ret["pens"], ret["aet"]) == (1, 2, (3, 4), True)


def test_box_wins_over_bracket_and_bracket_only_ties_are_kept():
    ms = _parsed()
    final = ms[("Hamburger SV", "1. FC Kaiserslautern")]
    assert final["fmt"] == "box" and final["date"] == pd.Timestamp("1976-06-26")
    assert sum(m["fmt"] == "bracket" for m in ms.values()) == 1        # the final appears once
    semi = ms[("Hamburger SV", "Rot-Weiss Essen")]
    assert (semi["fmt"], semi["hg"], semi["ag"], semi["neutral"]) == ("bracket", 3, 1, True)


def test_expand_uses_onlyinclude(tmp_path: Path):
    (tmp_path / wikicups.cache_name("1976 Cup Final")).write_text(
        "Lead text 9–9.\n<onlyinclude>{{football box|team1=[[A]]|score=1–0|team2=[[B]]}}</onlyinclude>",
        encoding="utf-8")
    text = wikicups.expand("==Final==\n{{:1976 Cup Final}}\n", tmp_path)
    assert wikicups.transcluded("{{:1976 Cup Final}}") == ["1976 Cup Final"]
    assert "9–9" not in text and "football box" in text


def test_reader_dates_rounds_in_order_and_makes_single_finals_neutral(tmp_path: Path):
    (tmp_path / "1975.txt").write_text(PAGE, encoding="utf-8")
    df = sources.wikipedia_cup(tmp_path, "GER-DFB", "GER")
    by = df.set_index(["home_club", "away_club"])
    first = by.loc[("ASV Landau", "Hannover 96"), "match_date"]
    replay = by.loc[("FC Bayern Munich", "Hamburger SV"), "match_date"]
    qf1, qf2 = by.loc[("Algeciras CF", "UP Langreo"), "match_date"], by.loc[("UP Langreo", "Algeciras CF"), "match_date"]
    assert pd.Timestamp("1975-08-01") <= first < replay < qf1 < pd.Timestamp("1976-06-26")
    assert qf2 - qf1 == pd.Timedelta(days=14)
    assert by.loc[("Hamburger SV", "1. FC Kaiserslautern"), "neutral"]
    assert not by.loc[("ASV Landau", "Hannover 96"), "neutral"]
    assert by.loc[("Trabzonspor", "Samsunspor"), "home_pens"] == 3


def test_expand_reads_labelled_sections(tmp_path: Path):
    (tmp_path / wikicups.cache_name("1986 Cup final")).write_text(
        "Intro 7–7\n<section begin=firstleg />{{football box|team1=[[A]]|score=1–0|team2=[[B]]}}"
        "<section end=firstleg />\n<section begin=\"secondleg\"/>{{football box|team1=[[B]]|score=2–2|team2=[[A]]}}"
        "<section end=\"secondleg\"/>", encoding="utf-8")
    text = wikicups.expand("==Final==\n===First leg===\n{{#lst:1986 Cup final|firstleg}}\n"
                           "===Second leg===\n{{#lst:1986 Cup final|secondleg}}\n", tmp_path)
    ms = wikicups.parse_page(text, 1985)
    assert [(m["home"], m["hg"], m["ag"], m["leg"]) for m in ms] == [("A", 1, 0, None), ("B", 2, 2, 2)]
    assert "7–7" not in text


def test_unlinked_names_and_reserve_sides_get_their_own_keys():
    assert wikicups.club("[[PSV Eindhoven|Jong PSV]]") == ("PSV Eindhoven [Jong PSV]", "Jong PSV")
    assert wikicups.club("[[Real Madrid Castilla|Castilla]]") == ("Real Madrid Castilla", "Castilla")
    assert wikicups.club("'''Schijndel''' (A)") == ("~Schijndel", "Schijndel")
