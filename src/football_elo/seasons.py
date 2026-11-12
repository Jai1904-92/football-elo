"""Whole-season strength: a performance rating per league club per season.

The season-end rating says where a club finished; this says how good it was
over the whole season. For each club-season it is the one constant rating
that best explains every result that season (expected score summed over the
matches = actual score), against the opponents as they were rated at kick-off,
with home advantage and league offsets as in the Elo run. Matches count with
their K multiplier, a little more for bigger wins. A few virtual draws against a side of the
club's season-average rating pull short or freak seasons towards it, and a few more against
the club's level in the surrounding seasons pull a season that is out of line with the club's
history back towards it (a one-off title run more than a dynasty's tenth).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Chosen 2026-10-23 by how well a season predicts the next (README "Judging a
# season"): 8 overrated the strongest promoted sides (-1.6pp the next season),
# 25+ removed that but dragged late-surging seasons back towards the lagging
# season average. 15 splits it: promoted clubs +1.1pp overall, top quarter -0.9pp.
VIRTUAL_DRAWS = 15
# A match's weight grows with the goal margin: 1-0 x1, 2-0 x1.19, 3-0 x1.32,
# 4-0 x1.41 (draws x1). Adopted 2026-11-07 with the halfway pull for promoted
# and relegated clubs: next-season log loss 0.63417 -> 0.63393, promoted clubs
# +1.5pp -> +1.0pp (strongest quarter +0.5 -> +0.1); half strength (0.5) predicted
# worse and changed five #1s.
MARGIN_EXPONENT = 0.25
# Club-history pull (2026-11-12): HISTORY_DRAWS virtual draws against the club's
# whole-season rating (the measure without this pull) in the surrounding seasons, the
# nearer counting double (HISTORY_WEIGHTS: season offset -> weight). Fit on half of each
# season's matches and scored on the other half: log loss -0.00097 (1965-94) and -0.00107
# (1995-2025); 20 draws a little better but changes 11 world #1s, 10 changes 3 (all near-ties).
# Freak seasons drop ~20 points (Leicester 2015/16 9th -> 11th); peak seasons of great
# sides ~10. Uses later seasons too, so a season moves a little as the next two arrive.
HISTORY_DRAWS = 10
HISTORY_WEIGHTS = {-2: 0.5, -1: 1.0, 1: 1.0, 2: 0.5}
LN10_400 = np.log(10) / 400


def season_average(periods: pd.DataFrame) -> pd.Series:
    """(club, season) -> mean rating at the August to May month ends of that
    season, read on the same dates for every club (league periods only)."""
    r = periods[periods["tier"].notna()].copy()
    # one resolution for every date: parquet and the database return different ones
    r["valid_from"] = pd.to_datetime(r["valid_from"]).astype("datetime64[ns]")
    r["valid_to"] = pd.to_datetime(r["valid_to"]).fillna(pd.Timestamp("2200-01-01")).astype("datetime64[ns]")
    keys = r[["club", "season"]].drop_duplicates()
    ends = pd.DataFrame({"m": range(10)})   # Aug .. May
    grid = keys.merge(ends, how="cross")
    # 1 August + n month ends = the end of August, September, ...
    grid["d"] = pd.to_datetime([pd.Timestamp(int(s), 8, 1) + pd.offsets.MonthEnd(int(m) + 1)
                                for s, m in zip(grid["season"], grid["m"])]).astype("datetime64[ns]")
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
    w = w * np.maximum((rated["home_goals"] - rated["away_goals"]).abs(), 1) ** MARGIN_EXPONENT
    h = pd.DataFrame({"club": rated["home_club"], "season": rated["season"], "pre": rated["home_elo_pre"],
                      "p": rated["home_win_exp"], "score": score_h, "w": w})
    a = pd.DataFrame({"club": rated["away_club"], "season": rated["season"], "pre": rated["away_elo_pre"],
                      "p": 1 - rated["home_win_exp"], "score": 1 - score_h, "w": w})
    return pd.concat([h, a], ignore_index=True)


def club_history(club: np.ndarray, season: np.ndarray, perf: np.ndarray,
                 weights: dict[int, float] = HISTORY_WEIGHTS) -> np.ndarray:
    """Weighted mean of each club's `perf` in its other seasons at the offsets in
    `weights` (only those present); NaN for a club with none."""
    look = pd.Series(perf, index=pd.MultiIndex.from_arrays([club, season]))
    num = np.zeros(len(perf)); den = np.zeros(len(perf))
    for k, w in weights.items():
        v = look.reindex(pd.MultiIndex.from_arrays([club, season + k])).to_numpy()
        ok = ~np.isnan(v)
        num[ok] += w * v[ok]
        den[ok] += w
    return np.where(den > 0, num / np.maximum(den, 1e-12), np.nan)


def _fit(codes, w, g, s, n, prior, virtual, hist=None, hist_draws=0.0):
    """Newton solve for each club-season's constant rating: expected = actual over its
    matches plus `virtual` draws at `prior` and `hist_draws` draws at `hist` (none where NaN)."""
    h = np.zeros(n) if hist is None else np.nan_to_num(hist, nan=0.0)
    v2 = np.zeros(n) if hist is None else np.where(np.isnan(hist), 0.0, hist_draws)
    target = np.bincount(codes, weights=w * s, minlength=n) + (virtual + v2) * 0.5
    R = prior.copy()
    for _ in range(60):   # Newton steps; the objective is monotone and smooth
        e = 1 / (1 + 10 ** (-(g + R[codes]) / 400))
        e1 = 1 / (1 + 10 ** (-(R - prior) / 400))
        e2 = 1 / (1 + 10 ** (-(R - h) / 400))
        f = np.bincount(codes, weights=w * e, minlength=n) + virtual * e1 + v2 * e2 - target
        df = LN10_400 * (np.bincount(codes, weights=w * e * (1 - e), minlength=n)
                         + virtual * e1 * (1 - e1) + v2 * e2 * (1 - e2))
        step = np.clip(f / df, -200, 200)
        R -= step
        if np.abs(step).max() < 0.01:
            break
    return R


def season_performance(rated: pd.DataFrame, periods: pd.DataFrame,
                       virtual: float = VIRTUAL_DRAWS, history: float = HISTORY_DRAWS) -> pd.DataFrame:
    """club, season, elo_perf, elo_avg, matches for every league club-season.
    The history pull reads the club's other seasons in the input, so give it two
    seasons either side of those you keep."""
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
    R = _fit(codes, w, g, s, n, prior, virtual)
    if history:
        club = np.asarray(uniq.get_level_values(0))
        season = np.asarray(uniq.get_level_values(1)).astype(int)
        R = _fit(codes, w, g, s, n, prior, virtual, club_history(club, season, R), history)
    out = pd.DataFrame({"club": uniq.get_level_values(0), "season": uniq.get_level_values(1).astype(int),
                        "elo_perf": R, "elo_avg": prior,
                        "matches": np.bincount(codes, minlength=n)})
    return out.sort_values(["season", "club"]).reset_index(drop=True)
