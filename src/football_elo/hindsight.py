"""Hindsight country levels for the season views.

Ratings are computed forwards in time, so a country's level in a season only
reflects European results up to then. With few European games per season
(before the mid-1990s) levels drifted: Serie A was rated 30-40 points too low
around 1985-91 and England too high on its return from the 1985-90 ban. For
historical rankings, later results can be used too: for each season, the
country offsets that best explain European results in the seasons around it
(before and after), on top of the forward ratings.

The correction is added to season ratings only (season views, both measures),
in full up to `full_until`, fading to nothing by `fade_until`; afterwards the
forward ratings are already well levelled. Seasons in which a country played no
European football (`gaps`, England's ban; with `auto_gaps` every such run) are
filled from the country's level either side of the gap (see fill_gaps).

Checked on seasons left out of the fit (each predicted from its neighbours only):
European log loss 1958-74 0.5480 -> 0.5404, 1975-94 0.5498 -> 0.5476.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def europe_frame(rated: pd.DataFrame, countries: list[str]) -> pd.DataFrame:
    e = rated[rated["comp_type"] == "europe"].copy()
    p = e["home_win_exp"].clip(1e-6, 1 - 1e-6)
    e["gap"] = 400 * np.log10(p / (1 - p))
    e["s"] = np.where(e["home_goals"] > e["away_goals"], 1.0, np.where(e["home_goals"] == e["away_goals"], 0.5, 0.0))
    hc, ac = e["home_country"], e["away_country"]       # each club's country that season
    e["hc"] = np.where(hc.isin(countries), hc, "other")
    e["ac"] = np.where(ac.isin(countries), ac, "other")
    return e[["season", "gap", "s", "hc", "ac"]]


def fit(e: pd.DataFrame, weights: np.ndarray, countries: list[str], ridge: float) -> dict[str, float]:
    """Offsets per country ("other" included) maximising the weighted likelihood
    of the European results, with a ridge worth `ridge` average games pulling
    each to 0; the games-weighted mean over `countries` is pinned at 0."""
    keys = countries + ["other"]
    n, ix = len(keys), {k: i for i, k in enumerate(keys)}
    h, a = e["hc"].map(ix).to_numpy(), e["ac"].map(ix).to_numpy()
    g, s, w = e["gap"].to_numpy(), e["s"].to_numpy(), weights
    k = np.log(10) / 400
    lam = ridge * k * k * 0.25
    games = np.bincount(h, weights=w, minlength=n) + np.bincount(a, weights=w, minlength=n)
    c = np.zeros(n)
    for _ in range(60):
        p = 1 / (1 + np.exp(-k * (g + c[h] - c[a])))
        r, v = w * (s - p), w * p * (1 - p)
        grad = k * (np.bincount(h, weights=r, minlength=n) - np.bincount(a, weights=r, minlength=n)) - lam * c
        # full Newton step: the offsets are coupled (one country's rise is its opponents' fall)
        hess = np.zeros((n, n))
        np.add.at(hess, (h, h), v); np.add.at(hess, (a, a), v)
        np.add.at(hess, (h, a), -v); np.add.at(hess, (a, h), -v)
        step = np.linalg.solve(k * k * hess + lam * np.eye(n), grad)
        c += step
        c -= np.average(c[:len(countries)], weights=np.maximum(games[:len(countries)], 1e-9))
        if np.abs(step).max() < 0.01:
            break
    return dict(zip(keys, c))


def corrections(rated: pd.DataFrame, countries: list[str], spec: dict) -> pd.DataFrame:
    """country, season, correction (rating points) for the modelled countries."""
    e = europe_frame(rated, countries)
    half, ridge = int(spec.get("window", 3)), float(spec.get("ridge", 60))
    full_until, fade_until = int(spec["full_until"]), int(spec["fade_until"])
    rows = []
    for s in range(int(e["season"].min()), fade_until + 1):
        d = (e["season"] - s).abs().to_numpy()
        w = np.where(d <= half, (half + 1 - d) / (half + 1), 0.0)
        c = fit(e[w > 0], w[w > 0], countries, ridge)
        scale = 1.0 if s <= full_until else (fade_until + 1 - s) / (fade_until + 1 - full_until)
        rows += [{"country": k, "season": s, "correction": c[k] * scale} for k in countries]
    out = pd.DataFrame(rows)
    out = fill_gaps(out, rated, countries, spec)
    out["correction"] = out["correction"].round(1)
    return out[out["correction"] != 0].reset_index(drop=True)


def gap_runs(rated: pd.DataFrame, countries: list[str], spec: dict) -> dict[str, list[tuple[int, int]]]:
    """country -> runs of league seasons (first, last) to fill: the configured
    `gaps`, plus with `auto_gaps` every run of seasons in which the country's
    clubs played no European games (sanctions, a new country, a league before
    its clubs entered Europe)."""
    runs = {c: [tuple(g)] for c, g in spec.get("gaps", {}).items()}
    if not spec.get("auto_gaps"):
        return runs
    lg = rated[rated["comp_type"] == "league"]
    leagues = set(zip(lg["home_country"], lg["season"])) | set(zip(lg["away_country"], lg["season"]))
    e = rated[rated["comp_type"] == "europe"]
    played = set(zip(e["home_country"], e["season"])) | set(zip(e["away_country"], e["season"]))
    for c in countries:
        quiet = sorted(s for (cc, s) in leagues if cc == c and (c, s) not in played and s <= int(spec["fade_until"]))
        for s in quiet:
            if any(a <= s <= b for a, b in runs.get(c, [])):
                continue
            if runs.get(c) and runs[c][-1][1] == s - 1 and (c, s - 1) not in played:
                runs[c][-1] = (runs[c][-1][0], s)
            else:
                runs.setdefault(c, []).append((s, s))
    return runs


def fill_gaps(out: pd.DataFrame, rated: pd.DataFrame, countries: list[str], spec: dict) -> pd.DataFrame:
    """Corrections for seasons a country sat out of Europe, from its level
    (forward league offset + correction) either side of the gap: the average
    over the first `gap_after` seasons back (default 1), and the season before.
    With a season before, the level steps evenly from one to the other
    (England's ban); without one (a new country such as Serbia in 1992, or the
    USSR before its clubs entered Europe) the level after applies throughout.
    Counting the forward offset matters: after a gap, pooling moves a country's
    offset for several seasons, and that change belongs to the gap years too."""
    n_after = int(spec.get("gap_after", 1))
    lg = rated[rated["comp_type"] == "league"]
    off = (pd.concat([lg[["home_country", "season", "home_offset"]].set_axis(["country", "season", "off"], axis=1),
                      lg[["away_country", "season", "away_offset"]].set_axis(["country", "season", "off"], axis=1)]
                     ).groupby(["country", "season"])["off"].mean()
           if "home_offset" in rated else pd.Series(dtype=float))   # no pooling: offsets all 0
    leagues = set(zip(lg["home_country"], lg["season"])) | set(zip(lg["away_country"], lg["season"]))
    out = out.copy()
    for country, runs in gap_runs(rated, countries, spec).items():
        sel = out["country"] == country
        corr = out[sel].set_index("season")["correction"]
        # seasons the country had a league (all of them when the matches carry no league rows)
        level = {s: off.get((country, s), 0.0) + corr[s] for s in corr.index
                 if not leagues or (country, s) in leagues}
        for first, last in runs:
            back = [level[s] for s in range(last + 1, last + 1 + n_after) if s in level]
            if not back:
                continue
            after, before = sum(back) / len(back), level.get(first - 1)
            for s in range(first, last + 1):
                target = after if before is None else before + (after - before) * (s - first + 1) / (last - first + 2)
                row = (out["country"] == country) & (out["season"] == s)
                if row.any():
                    out.loc[row, "correction"] = target - off.get((country, s), 0.0)
                else:   # a gap before the first season with any European games
                    out.loc[len(out)] = {"country": country, "season": s,
                                         "correction": target - off.get((country, s), 0.0)}
    return out
