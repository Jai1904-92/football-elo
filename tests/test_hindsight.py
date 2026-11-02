import numpy as np
import pandas as pd

from football_elo import hindsight


def _europe(seasons, a_wins_share):
    """European games between countries A and B, rated level, where A wins
    `a_wins_share` of them (rest B wins)."""
    rows = []
    for s in seasons:
        for i in range(40):
            a_won = i < a_wins_share * 40
            home_a = i % 2 == 0
            hg, ag = ((1, 0) if a_won else (0, 1)) if home_a else ((0, 1) if a_won else (1, 0))
            rows.append({"season": s, "comp_type": "europe", "home_club": "a" if home_a else "b",
                         "away_club": "b" if home_a else "a", "home_country": "A" if home_a else "B",
                         "away_country": "B" if home_a else "A", "home_goals": hg, "away_goals": ag,
                         "home_win_exp": 0.5})
    return pd.DataFrame(rows)


SPEC = {"window": 2, "ridge": 10, "full_until": 2005, "fade_until": 2005}


def test_a_country_beating_predictions_is_lifted():
    out = hindsight.corrections(_europe(range(2000, 2006), 0.7), ["A", "B"], SPEC)
    c = out.pivot(index="season", columns="country", values="correction")
    assert (c["A"] > 50).all() and (c["B"] < -50).all()


def test_a_gap_steps_evenly_between_its_neighbours():
    spec = dict(SPEC, gaps={"A": [2002, 2003]})
    out = hindsight.corrections(_europe(range(2000, 2006), 0.7), ["A", "B"], spec)
    a = out[out.country == "A"].set_index("season")["correction"]
    assert np.isclose(a[2002] - a[2001], a[2004] - a[2003], atol=0.2)
    assert np.isclose(a[2003] - a[2002], a[2004] - a[2003], atol=0.2)


def test_a_gap_can_aim_at_the_average_of_the_seasons_after_it():
    e = pd.concat([_europe(range(2000, 2002), 0.5), _europe(range(2004, 2008), 0.8)])
    spec = dict(SPEC, full_until=2007, fade_until=2007, gaps={"A": [2002, 2003]}, gap_after=3)
    a = hindsight.corrections(e, ["A", "B"], spec).query("country == 'A'").set_index("season")["correction"]
    a = a.reindex(range(2000, 2008), fill_value=0.0)
    target = a[[2004, 2005, 2006]].mean()
    assert np.isclose(a[2003] - a[2001], 2 * (target - a[2001]) / 3, atol=0.3)


def _league(country, seasons, offset):
    """One league match per season for `country`, its clubs at forward offset `offset[season]`."""
    return pd.DataFrame([{"season": s, "comp_type": "league", "home_club": "x", "away_club": "y",
                          "home_country": country, "away_country": country, "home_goals": 1, "away_goals": 0,
                          "home_win_exp": 0.5, "home_offset": offset[s], "away_offset": offset[s]}
                         for s in seasons])


def test_a_new_country_without_european_games_takes_the_level_after():
    # A has a league from 2002 but plays in Europe only from 2004; pooling then
    # lowers its forward offset from 0 to -40
    e = _europe(range(2004, 2008), 0.5)
    e[["home_offset", "away_offset"]] = 0.0
    off = {2002: 0.0, 2003: 0.0, 2004: -40.0, 2005: -40.0, 2006: -40.0, 2007: -40.0}
    rated = pd.concat([e, _league("A", range(2002, 2008), off), _league("B", range(2002, 2008), dict.fromkeys(off, 0.0))])
    spec = dict(SPEC, full_until=2007, fade_until=2007, auto_gaps=True, gap_after=2)
    a = hindsight.corrections(rated, ["A", "B"], spec).query("country == 'A'").set_index("season")["correction"]
    after = (a.get(2004, 0.0) + a.get(2005, 0.0)) / 2 - 40
    assert np.isclose(a[2002], after, atol=0.2) and np.isclose(a[2003], after, atol=0.2)
    assert a[2002] < -30


def test_gap_runs_find_seasons_without_european_games():
    e = _europe([2000, 2003], 0.5)
    rated = pd.concat([e, _league("A", range(2000, 2004), dict.fromkeys(range(2000, 2004), 0.0))])
    runs = hindsight.gap_runs(rated, ["A"], dict(SPEC, auto_gaps=True))
    assert runs == {"A": [(2001, 2002)]}
