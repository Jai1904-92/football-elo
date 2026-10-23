"""Whole-season strength: a performance rating per league club per season.

The season-end rating says where a club finished; this says how good it was
over the whole season. For each club-season it is the one constant rating
that best explains every result that season (expected score summed over the
matches = actual score), against the opponents as they were rated at kick-off,
with home advantage and league offsets as in the Elo run. Matches count with
their K multiplier (cups half). A few virtual draws against a side of the
club's season-average rating pull short or freak seasons towards it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VIRTUAL_DRAWS = 8
LN10_400 = np.log(10) / 400


def season_average(periods: pd.DataFrame) -> pd.Series:
    """(club, season) -> mean rating at the August to May month ends of that
    season, read on the same dates for every club (league periods only)."""
    r = periods[periods["tier"].notna()].copy()
    r["valid_from"] = pd.to_datetime(r["valid_from"])
    r["valid_to"] = pd.to_datetime(r["valid_to"]).fillna(pd.Timestamp("2200-01-01"))
    keys = r[["club", "season"]].drop_duplicates()
    ends = pd.DataFrame({"m": range(10)})   # Aug .. May
    grid = keys.merge(ends, how="cross")
    # 1 August + n month ends = the end of August, September, ...
    grid["d"] = [pd.Timestamp(int(s), 8, 1) + pd.offsets.MonthEnd(int(m) + 1)
                 for s, m in zip(grid["season"], grid["m"])]
    grid = grid.sort_values("d")
    hit = pd.merge_asof(grid, r.sort_values("valid_from")[["club", "season", "valid_from", "valid_to", "elo"]]
                        .rename(columns={"season": "p_season"}),
                        left_on="d", right_on="valid_from", by="club", direction="backward")
    hit = hit[(hit["p_season"] == hit["season"]) & (hit["d"] <= hit["valid_to"])]
    return hit.groupby(["club", "season"])["elo"].mean()


def club_sides(rated: pd.DataFrame) -> pd.DataFrame:
    """One row per club per match: own pre-match rating, own expected score,
    actual score and weight."""
    score_h = np.where(rated["home_goals"] > rated["away_goals"], 1.0,
                       np.where(rated["home_goals"] == rated["away_goals"], 0.5, 0.0))
    w = rated["k_mult"].astype(float) if "k_mult" in rated else 1.0
    h = pd.DataFrame({"club": rated["home_club"], "season": rated["season"], "pre": rated["home_elo_pre"],
                      "p": rated["home_win_exp"], "score": score_h, "w": w})
    a = pd.DataFrame({"club": rated["away_club"], "season": rated["season"], "pre": rated["away_elo_pre"],
                      "p": 1 - rated["home_win_exp"], "score": 1 - score_h, "w": w})
    return pd.concat([h, a], ignore_index=True)


def season_performance(rated: pd.DataFrame, periods: pd.DataFrame,
                       virtual: float = VIRTUAL_DRAWS) -> pd.DataFrame:
    """club, season, elo_perf, elo_avg, matches for every league club-season."""
    avg = season_average(periods)
    sides = club_sides(rated)
    sides = sides.join(avg.rename("prior"), on=["club", "season"], how="inner")
    p = sides["p"].clip(1e-6, 1 - 1e-6)
    # rating gap the match was played at, less the club's own rating: g + R is the gap at rating R
    sides["g"] = 400 * np.log10(p / (1 - p)) - sides["pre"]
    key = pd.MultiIndex.from_frame(sides[["club", "season"]])
    codes, uniq = pd.factorize(key)
    n = len(uniq)
    w, g, s = sides["w"].to_numpy(), sides["g"].to_numpy(), sides["score"].to_numpy()
    prior = sides.groupby(codes)["prior"].first().to_numpy()
    target = np.bincount(codes, weights=w * s, minlength=n) + virtual * 0.5
    R = prior.copy()
    for _ in range(50):   # Newton steps; the objective is monotone and smooth
        e = 1 / (1 + 10 ** (-(g + R[codes]) / 400))
        ev = 1 / (1 + 10 ** (-(R - prior) / 400))
        f = np.bincount(codes, weights=w * e, minlength=n) + virtual * ev - target
        df = LN10_400 * (np.bincount(codes, weights=w * e * (1 - e), minlength=n) + virtual * ev * (1 - ev))
        step = np.clip(f / df, -200, 200)
        R -= step
        if np.abs(step).max() < 0.01:
            break
    out = pd.DataFrame({"club": uniq.get_level_values(0), "season": uniq.get_level_values(1).astype(int),
                        "elo_perf": R, "elo_avg": prior,
                        "matches": np.bincount(codes, minlength=n)})
    return out.sort_values(["season", "club"]).reset_index(drop=True)
