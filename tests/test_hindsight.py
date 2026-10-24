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
