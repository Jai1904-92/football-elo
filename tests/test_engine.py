import numpy as np
import pandas as pd
import pytest

from football_elo import engine, silver


def _matches(rows):
    df = pd.DataFrame(rows, columns=["match_date", "season", "tier", "home_club", "away_club",
                                     "home_goals", "away_goals"])
    df["match_date"] = pd.to_datetime(df["match_date"])
    df["match_id"] = df["match_date"].dt.strftime("%Y%m%d") + "_" + df["home_club"] + "_" + df["away_club"]
    return df


SAMPLE = _matches([
    ("2020-08-01", 2020, 1, "A", "B", 2, 0),
    ("2020-08-01", 2020, 2, "C", "D", 1, 1),
    ("2020-08-08", 2020, 1, "B", "A", 3, 1),
    ("2020-08-08", 2020, 2, "D", "C", 0, 4),
    ("2020-08-15", 2020, 1, "A", "C", 1, 0),
    ("2021-08-01", 2021, 1, "A", "B", 0, 0),
    ("2021-08-01", 2021, 2, "C", "E", 2, 1),
])
P = engine.EloParams(k=20, hfa=70, countries={"ENG": {"start_ratings": {1: 1600, 2: 1450, 3: 1300, 4: 1150},
                                                     "nonleague": 1000}})


def test_zero_sum_and_expectation():
    rated, final = engine.run(SAMPLE, P)
    assert np.allclose(rated.home_elo_post + rated.away_elo_post, rated.home_elo_pre + rated.away_elo_pre)
    first = rated.iloc[0]
    assert first.home_elo_pre == 1600 and first.away_elo_pre == 1600
    assert first.home_win_exp == pytest.approx(1 / (10 ** (-70 / 400) + 1))
    # 2-0 win: K * sqrt(2) * (1 - We)
    assert first.elo_delta == pytest.approx(20 * 2 ** 0.5 * (1 - first.home_win_exp))


def test_draw_moves_towards_underdog():
    rated, _ = engine.run(SAMPLE, P)
    draw = rated[(rated.home_club == "C") & (rated.away_club == "D")].iloc[0]
    assert draw.elo_delta < 0  # home side was expected to win thanks to HFA


def test_ratings_carry_across_tiers():
    rated, final = engine.run(SAMPLE, P)
    # C (tier 2) plays A in tier 1 and keeps its rating rather than resetting
    c_vs_a = rated[(rated.home_club == "A") & (rated.away_club == "C")].iloc[0]
    c_prev = rated[(rated.home_club == "D") & (rated.away_club == "C")].iloc[0]
    assert c_vs_a.away_elo_pre == pytest.approx(c_prev.away_elo_post)


def test_new_club_starts_at_tier_rating():
    rated, _ = engine.run(SAMPLE, P)
    e = rated[rated.away_club == "E"].iloc[0]
    assert e.away_elo_pre == 1450


@pytest.mark.parametrize("method,expected", [
    ("none", [1, 1, 1, 1]), ("sqrt", [1, 1, 2 ** 0.5, 3 ** 0.5]),
])
def test_margin_lookup(method, expected):
    p = engine.EloParams(margin_method=method)
    assert np.allclose(p.margin_lookup(3), expected)


def test_margin_table():
    p = engine.EloParams(margin_method="table", margin_table=[1, 1, 1.5, 1.75])
    assert list(p.margin_lookup(5)) == [1, 1, 1.5, 1.75, 1.75, 1.75]


def test_incremental_equals_full():
    full, _ = engine.run(SAMPLE, P)
    cut = pd.Timestamp("2020-08-08")
    first, state = engine.run(SAMPLE[SAMPLE.match_date < cut], P)
    rest, _ = engine.run(SAMPLE[SAMPLE.match_date >= cut], P, initial=state)
    both = pd.concat([first, rest]).set_index("match_id").sort_index()
    pd.testing.assert_frame_equal(both[["home_elo_post", "away_elo_post"]],
                                  full.set_index("match_id").sort_index()[["home_elo_post", "away_elo_post"]])


def test_periods():
    rated, _ = engine.run(SAMPLE, P)
    per = engine.periods(rated)
    a = per[per.club == "A"].reset_index(drop=True)
    assert a.valid_from.tolist() == list(pd.to_datetime(["2020-08-02", "2020-08-09", "2020-08-16", "2021-08-02"]))
    assert a.valid_to.iloc[0] == pd.Timestamp("2020-08-08")   # next match day
    assert pd.isna(a.valid_to.iloc[-1])                        # still in the league
    d = per[per.club == "D"].reset_index(drop=True)          # D not in 2021: closed at season end
    assert d.valid_to.iloc[-1] == pd.Timestamp("2020-08-15")
    on = engine.ratings_on(per, "2020-08-10")
    assert set(on.club) == {"A", "B", "C", "D"}


def _cup_sample():
    m = SAMPLE.assign(competition="ENG-L", comp_type="league", neutral=False)
    extra = _matches([("2020-08-20", 2020, None, "A", "Z", 1, 1),       # cup v non-league
                      ("2020-08-22", 2020, None, "C", "Real", 0, 2)])    # European v foreign
    extra = extra.assign(competition=["ENG-FAC", "UCL"], comp_type=["cup", "europe"], neutral=[True, False])
    return pd.concat([m, extra], ignore_index=True)


def test_start_ratings_by_country_and_tier():
    m = _cup_sample()
    p = engine.EloParams(k=20, hfa=70, countries=P.countries, foreign_start={"default": 1500, "ESP": 1700},
                         k_multiplier={"league": 1, "playoff": 1, "cup": 0.5, "europe": 1})
    country = pd.Series({c: "ENG" for c in "ABCDEZ"} | {"Real": "ESP"})
    rated, _ = engine.run(m, p, club_country=country)
    cup = rated[rated.competition == "ENG-FAC"].iloc[0]
    assert cup.away_elo_pre == 1000          # non-league club of a modelled country
    assert not cup.hfa_on                    # neutral venue
    assert cup.home_win_exp == pytest.approx(1 / (10 ** (-(cup.home_elo_pre - 1000) / 400) + 1))
    assert cup.elo_delta == pytest.approx(20 * 0.5 * (0.5 - cup.home_win_exp))
    eu = rated[rated.competition == "UCL"].iloc[0]
    assert eu.away_elo_pre == 1700           # foreign club, country-specific start
    assert eu.home_tier == 2 and pd.isna(eu.away_tier)


def test_periods_tier_null_outside_league():
    m = _cup_sample()
    country = pd.Series({c: "ENG" for c in "ABCDEZ"} | {"Real": "ESP"})
    rated, _ = engine.run(m, P, club_country=country)
    per = engine.periods(rated)
    assert per.loc[per.club == "Real", "tier"].isna().all()
    assert (per.loc[per.club == "Real", "country"] == "ESP").all()


def test_apply_aliases_fails_on_unknown_names():
    aliases = pd.DataFrame({"source": ["football_data"], "source_name": ["Man City"], "club": ["Manchester City"]})
    df = pd.DataFrame({"home_club": ["Man City"], "away_club": ["Wolves"],
                       "home_name": ["Man City"], "away_name": ["Wolves"]})
    with pytest.raises(ValueError, match="Wolves"):
        silver.apply_aliases(df, aliases, "football_data")


def test_apply_aliases_auto_registers_new_clubs():
    aliases = pd.DataFrame({"source": ["espn", "espn"], "source_name": ["1", "2"], "club": ["Arsenal", "Chelsea"]})
    df = pd.DataFrame({"home_club": ["1", "99"], "away_club": ["2", "1"], "home_name": ["Arsenal", "Arsenal"],
                       "away_name": ["Chelsea", "Arsenal"], "home_country": [None, None], "away_country": [None, None]})
    new = []
    out = silver.apply_aliases(df, aliases, "espn", auto_new=new)
    # display name clashes with an existing club, so it gets a suffix
    assert new == [{"source": "espn", "source_name": "99", "club": "Arsenal (espn)"}]
    assert out.home_club.tolist() == ["Arsenal", "Arsenal (espn)"]


def test_check_matches_reports_double_booking():
    df = SAMPLE.assign(competition="ENG-L", source="x")
    df.loc[1, ["home_club"]] = "A"   # A plays twice on 2020-08-01
    df["match_id"] = df.index.astype(str)
    report = silver.check_matches(df)
    assert set(report.club) == {"A"}


def test_check_matches_rejects_self_match():
    df = SAMPLE.assign(competition="ENG-L", source="x", match_id=SAMPLE.index.astype(str))
    df.loc[0, "away_club"] = "A"
    with pytest.raises(ValueError, match="itself"):
        silver.check_matches(df)


def test_newcomer_from_below_starts_one_tier_down():
    # country's first season 2020: A, B, C, D are founders; E joins tier 2 (the
    # lowest modelled tier) in 2021, so it starts at the tier-3 rating
    m = SAMPLE.copy()
    m = pd.concat([m, _matches([("2021-08-08", 2021, 2, "E", "D", 0, 0)])], ignore_index=True)
    p = engine.EloParams(k=20, hfa=70, countries={"ENG": {"start_ratings": {1: 1600, 2: 1450, 3: 1300},
                                                         "nonleague": 1000}}, newcomer_from_below=True)
    rated, _ = engine.run(m, p)
    first_e = rated[(rated.home_club == "E") | (rated.away_club == "E")].iloc[0]
    e_pre = first_e.home_elo_pre if first_e.home_club == "E" else first_e.away_elo_pre
    assert e_pre == 1300
    founders = rated.iloc[0]
    assert founders.home_elo_pre == 1600     # first season: tier start, no newcomer drop


def test_source_corrections_apply_to_one_season(tmp_path):
    class Fake(silver.SourceReader):
        def _read(self, source, competition):
            return SAMPLE.assign(competition=competition)
    cfg = {"paths": {"bronze": tmp_path}, "corrections": [
        {"source": "engsoccerdata", "competition": "ENG-L", "season": 2021, "club": "A", "to": "A2"}]}
    df = Fake(cfg).read("engsoccerdata", "ENG-L")
    assert set(df.loc[df.season == 2021, "home_club"]) == {"A2", "C"}
    assert "A" in set(df.loc[df.season == 2020, "home_club"])


def _two_country_sample():
    m = _matches([
        ("2020-08-01", 2020, 1, "A", "B", 1, 0),
        ("2020-08-01", 2020, 1, "X", "Y", 2, 2),
        ("2020-09-15", 2020, None, "A", "X", 0, 3),     # European tie
        ("2020-09-20", 2020, 1, "B", "A", 1, 1),
        ("2020-09-20", 2020, 1, "Y", "X", 0, 1),
        ("2020-09-29", 2020, None, "Y", "B", 2, 0),     # European tie
        ("2020-10-04", 2020, 1, "A", "B", 3, 1),
        ("2020-10-04", 2020, 1, "X", "Y", 1, 0),
    ])
    m["competition"] = ["ENG-L", "ESP-L", "UCL", "ENG-L", "ESP-L", "UCL", "ENG-L", "ESP-L"]
    m["comp_type"] = ["league", "league", "europe", "league", "league", "europe", "league", "league"]
    m["neutral"] = False
    country = pd.Series({"A": "ENG", "B": "ENG", "X": "ESP", "Y": "ESP"})
    p = engine.EloParams(k=20, hfa=70, league_pool=0.3, countries={
        "ENG": {"start_ratings": {1: 1600}, "nonleague": 1400},
        "ESP": {"start_ratings": {1: 1600}, "nonleague": 1400}})
    return m, country, p


def test_league_pool_moves_whole_country():
    m, country, p = _two_country_sample()
    rated, _ = engine.run(m, p, club_country=country)
    tie = rated[rated.match_id.str.contains("_A_X")].iloc[0]
    # X won in Europe: Spain's offset rises, so Y (who did not play) gains too
    assert tie.away_offset == pytest.approx(0.3 * -tie.elo_delta)
    nxt = rated[rated.match_id.str.contains("_Y_X")].iloc[0]
    y_before = rated[rated.match_id.str.contains("_X_Y")].iloc[0].away_elo_post
    assert nxt.home_elo_pre == pytest.approx(y_before + tie.away_offset)
    offs = engine.league_offsets(rated)
    assert set(offs.country) == {"ENG", "ESP"}


def test_league_pool_incremental_equals_full():
    m, country, p = _two_country_sample()
    full, _ = engine.run(m, p, club_country=country)
    cut = pd.Timestamp("2020-09-20")
    first, _ = engine.run(m[m.match_date < cut], p, club_country=country,
                          membership=engine.league_membership(m))
    offsets = dict(engine.run.last_offsets)
    per = engine.periods(first)
    last = per.sort_values("valid_from").groupby("club").tail(1)
    base = dict(zip(last.club, last.elo - last.country_offset))
    rest, _ = engine.run(m[m.match_date >= cut], p, club_country=country, offsets=offsets, initial_base=base,
                         membership=engine.league_membership(m))
    both = pd.concat([first, rest]).set_index("match_id").sort_index()
    pd.testing.assert_series_equal(both.home_elo_post, full.set_index("match_id").sort_index().home_elo_post)
    pd.testing.assert_series_equal(both.away_elo_post, full.set_index("match_id").sort_index().away_elo_post)


def test_all_features_incremental_equals_full():
    # pooling, provisional K and dynamic home advantage, split mid-way and
    # resumed from stored state, must match one full run exactly
    m, country, p = _two_country_sample()
    from dataclasses import replace
    p = replace(p, provisional_matches=3, provisional_k=2.0, hfa_eta=5.0, hfa_start=100.0)
    full, _ = engine.run(m, p, club_country=country)
    cut = pd.Timestamp("2020-09-20")
    mem = engine.league_membership(m)
    first, _ = engine.run(m[m.match_date < cut], p, club_country=country, membership=mem)
    offsets, played, hfa = dict(engine.run.last_offsets), dict(engine.run.last_played), dict(engine.run.last_hfa)
    levels = engine.hfa_levels(first)
    assert hfa == levels.groupby("hfa_key")["hfa"].last().to_dict()
    per = engine.periods(first)
    last = per.sort_values("valid_from").groupby("club").tail(1)
    base = dict(zip(last.club, last.elo - last.country_offset))
    rest, _ = engine.run(m[m.match_date >= cut], p, club_country=country, offsets=offsets, initial_base=base,
                         played=played, hfa_state=hfa, membership=mem)
    both = pd.concat([first, rest]).set_index("match_id").sort_index()
    ref = full.set_index("match_id").sort_index()
    pd.testing.assert_series_equal(both.home_elo_post, ref.home_elo_post)
    pd.testing.assert_series_equal(both.hfa_used, ref.hfa_used)


def test_a_club_changing_country_keeps_its_rating():
    # A wins in Europe for country X, which lifts X's pooled level; when A moves to
    # country Y (a union league breaking up) its rating carries over unchanged
    m = _matches([
        ("2000-09-01", 2000, 1, "A", "F", 3, 0),
        ("2001-09-01", 2001, 1, "A", "B", 1, 1),
    ]).assign(comp_type=["europe", "league"])
    p = engine.EloParams(k=20, hfa=0, league_pool=0.5, countries={"X": {"start_ratings": {1: 1500}, "nonleague": 1300},
                                                                   "Y": {"start_ratings": {1: 1500}, "nonleague": 1300}})
    country = pd.Series({("A", 2000): "X", ("F", 2000): "Z", ("A", 2001): "Y", ("B", 2001): "Y"})
    rated, _ = engine.run(m, p, club_country=country)
    first, second = rated.iloc[0], rated.iloc[1]
    assert first.home_offset > 0                              # X lifted by A's European win
    assert second.home_country == "Y" and second.home_offset == 0
    assert second.home_elo_pre == pytest.approx(first.home_elo_post)


def test_country_seasons_follow_the_league():
    cfg = {"competitions": {"U-L": {"type": "league", "country": "URS"}, "K-L": {"type": "league", "country": "UKR"},
                            "UCL": {"type": "europe"}}}
    df = pd.DataFrame({
        "season": [1990, 1990, 1991, 1992, 1992, 1993],
        "competition": ["U-L", "UCL", "UCL", "K-L", "UCL", "UCL"],
        "comp_type": ["league", "europe", "europe", "league", "europe", "europe"],
        "home_club": ["Kyiv", "Kyiv", "Tbilisi", "Kyiv", "Kyiv", "Tbilisi"],
        "away_club": ["Tbilisi", "Ajax", "Ajax", "Dnipro", "Ajax", "Ajax"],
        "home_country": ["URS", "URS", "GEO", "UKR", "UKR", "GEO"],
        "away_country": ["URS", "NED", "NED", "UKR", "NED", "NED"]})
    cs = silver.country_seasons(df, cfg)
    assert cs[("Kyiv", 1990)] == "URS" and cs[("Kyiv", 1992)] == "UKR"
    assert cs[("Tbilisi", 1990)] == "URS" and cs[("Tbilisi", 1993)] == "GEO"
