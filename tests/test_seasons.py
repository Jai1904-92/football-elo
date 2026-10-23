import pandas as pd
import pytest

from football_elo import seasons


def _season(results, pre=1600.0, opp=1600.0):
    """One club's league season against equal opponents at neutral venues."""
    n = len(results)
    rated = pd.DataFrame({
        "season": 2000, "home_club": "A", "away_club": [f"O{i}" for i in range(n)],
        "home_goals": [r[0] for r in results], "away_goals": [r[1] for r in results],
        "home_elo_pre": pre, "away_elo_pre": opp, "home_win_exp": 1 / (1 + 10 ** (-(pre - opp) / 400)),
        "k_mult": 1.0})
    periods = pd.DataFrame({"club": "A", "season": 2000, "tier": 1, "elo": pre,
                            "valid_from": [pd.Timestamp("2000-08-01")], "valid_to": [pd.Timestamp("2001-06-30")]})
    return seasons.season_performance(rated, periods).set_index("club").loc["A"]


def test_even_record_against_equals_rates_at_their_level():
    r = _season([(1, 0), (0, 1)] * 10)
    assert r["elo_perf"] == pytest.approx(1600, abs=0.5)
    assert r["elo_avg"] == pytest.approx(1600)


def test_winning_record_rates_above_and_is_pulled_towards_the_average():
    strong = _season([(2, 0)] * 15 + [(1, 1)] * 5)
    assert strong["elo_perf"] > 1750
    # fewer matches, same win rate: the virtual draws pull it closer to 1600
    short = _season([(2, 0)] * 3 + [(1, 1)])
    assert 1600 < short["elo_perf"] < strong["elo_perf"]


def test_strong_start_and_strong_finish_count_the_same():
    start = _season([(1, 0)] * 10 + [(0, 1)] * 5)
    finish = _season([(0, 1)] * 5 + [(1, 0)] * 10)
    assert start["elo_perf"] == pytest.approx(finish["elo_perf"])


def test_dates_as_the_database_returns_them():
    # the update path reads periods from Postgres: plain dates, not timestamps
    import datetime as dt
    rated = pd.DataFrame({"season": 2000, "home_club": "A", "away_club": ["B", "C"], "home_goals": [1, 0],
                          "away_goals": [0, 1], "home_elo_pre": 1600.0, "away_elo_pre": 1600.0, "home_win_exp": 0.5,
                          "k_mult": 1.0})
    periods = pd.DataFrame({"club": "A", "season": 2000, "tier": 1, "elo": 1600.0,
                            "valid_from": [dt.date(2000, 8, 1)], "valid_to": [dt.date(2001, 6, 30)]})
    out = seasons.season_performance(rated, periods)
    assert out.loc[0, "elo_perf"] == pytest.approx(1600, abs=0.5)
