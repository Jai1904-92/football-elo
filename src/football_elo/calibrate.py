"""Calibration against published Club Elo ratings.

Targets (clubs of every modelled country, mapped to canonical names via the
aliases file):
  - Tony Elhabr's Club Elo snapshots (2023-03 .. 2026-01), sampled monthly
  - Wayback captures of api.clubelo.com: full tables (2008, 2017, 2024, 2025)
    and the Aston Villa history (sampled once per month, after burn-in)
"""
from __future__ import annotations

import copy
import logging
from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from . import engine

log = logging.getLogger(__name__)


def _clubelo_aliases(cfg: dict) -> pd.Series:
    a = pd.read_csv(cfg["aliases"])
    return a[a["source"] == "clubelo"].set_index("source_name")["club"]


def load_targets(cfg: dict, burn_in_until: str | None = None) -> pd.DataFrame:
    """Club Elo ratings as (date, club, clubelo_elo, source) rows."""
    cal = cfg["paths"]["calibration"]
    alias = _clubelo_aliases(cfg)
    frames = []

    eh = pd.read_csv(cal / "clubelo-club-rankings.csv", usecols=["Club", "Country", "Elo", "date"])
    countries = list(cfg["elo"]["countries"])
    eh = eh[eh["Country"].isin(countries)]
    eh["date"] = pd.to_datetime(eh["date"])
    keep = eh["date"].drop_duplicates().sort_values()
    keep = keep[keep.dt.to_period("M").duplicated() == False]  # first snapshot of each month  # noqa: E712
    eh = eh[eh["date"].isin(keep)]
    frames.append(pd.DataFrame({"date": eh["date"], "club": eh["Club"].map(alias), "country": eh["Country"],
                                "clubelo_elo": eh["Elo"], "source": "elhabr"}))

    for path in sorted((cal / "wayback").glob("table_*.csv")):
        t = pd.read_csv(path)
        t = t[t["Country"].isin(countries)]
        when = pd.Timestamp(path.stem.removeprefix("table_"))
        frames.append(pd.DataFrame({"date": when, "club": t["Club"].map(alias), "country": t["Country"],
                                    "clubelo_elo": t["Elo"], "source": f"wayback_{when.date()}"}))

    for path in sorted((cal / "wayback").glob("club_*.csv")):
        h = pd.read_csv(path, parse_dates=["From", "To"])
        if h.empty:
            log.warning("empty club history capture: %s", path.name)
            continue
        h = h[h["Country"].isin(countries)]
        h["month"] = h["To"].dt.to_period("M")
        h = h.drop_duplicates("month", keep="last")
        frames.append(pd.DataFrame({"date": h["To"], "club": h["Club"].map(alias), "country": h["Country"],
                                    "clubelo_elo": h["Elo"], "source": "wayback_" + path.stem}))

    t = pd.concat(frames, ignore_index=True).dropna(subset=["club"])
    if burn_in_until:
        t = t[t["date"] >= pd.Timestamp(burn_in_until)]
    return t.reset_index(drop=True)


def attach_ours(targets: pd.DataFrame, rated: pd.DataFrame) -> pd.DataFrame:
    """Add our rating for each (club, date): the post-match rating of the
    club's last match before that date. Drops clubs we have not rated."""
    long = pd.concat([
        rated[["match_date", "home_club", "home_elo_post", "home_tier"]].set_axis(["match_date", "club", "elo", "tier"], axis=1),
        rated[["match_date", "away_club", "away_elo_post", "away_tier"]].set_axis(["match_date", "club", "elo", "tier"], axis=1),
    ])
    long["valid_from"] = long["match_date"] + pd.Timedelta(days=1)
    long = long.sort_values("valid_from")
    t = targets.sort_values("date")
    out = pd.merge_asof(t, long[["valid_from", "club", "elo", "tier"]], left_on="date", right_on="valid_from",
                        by="club", direction="backward")
    return out.dropna(subset=["elo"]).rename(columns={"elo": "our_elo"})


def score(cmp: pd.DataFrame) -> dict:
    err = cmp["our_elo"] - cmp["clubelo_elo"]
    # error after removing each snapshot's mean offset: Club Elo's English
    # level moves with European results, which a closed league pool cannot see
    shape = err - err.groupby(cmp["date"]).transform("mean")
    by_date_rank = cmp.groupby("date")[["our_elo", "clubelo_elo"]].corr(method="spearman").xs("our_elo", level=1)
    return {
        "n": int(len(cmp)),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "bias": float(err.mean()),
        "rmse_debiased": float(err.std()),
        "rmse_shape": float(np.sqrt(np.mean(shape ** 2))),
        "mean_spearman": float(by_date_rank["clubelo_elo"].mean()),
    }


def score_by(cmp: pd.DataFrame, by: str) -> pd.DataFrame:
    return pd.DataFrame({k: score(g) for k, g in cmp.groupby(by) if len(g) > 2}).T


def evaluate(matches: pd.DataFrame, targets: pd.DataFrame, params: engine.EloParams):
    """`matches` should already be engine.prepare()d."""
    rated, _ = engine.run(matches, params)
    cmp = attach_ours(targets, rated)
    return score(cmp), cmp, rated


# Parameters the optimiser may move, with how they map onto EloParams.
def _country(params: engine.EloParams) -> str:
    return next(iter(params.countries))


def _apply(params: engine.EloParams, names: list[str], x: np.ndarray) -> engine.EloParams:
    """Names: any scalar EloParams field (k, hfa, margin_exponent); `tier_gap`
    (start ratings of the first country become start_1 - gap * (tier - 1),
    and non-league start_4 - gap); `start_N`; `foreign` (default foreign
    start); `k_<type>` (K multiplier for a competition type)."""
    p = replace(params, countries=copy.deepcopy(params.countries),
                foreign_start=dict(params.foreign_start), k_multiplier=dict(params.k_multiplier))
    spec = p.countries[_country(p)]
    for name, v in zip(names, x):
        v = float(v)
        if name.startswith("level_"):     # level_ESP: tier-1 start of a country, gaps kept
            c = p.countries[name[6:]]
            shift = v - c["start_ratings"][1]
            c["start_ratings"] = {t: r + shift for t, r in c["start_ratings"].items()}
            c["nonleague"] += shift
        elif name.startswith("gap_"):     # gap_ESP: tier gap of a country, tier 1 kept
            c = p.countries[name[4:]]
            top = c["start_ratings"][1]
            c["start_ratings"] = {t: top - v * (t - 1) for t in c["start_ratings"]}
            c["nonleague"] = top - v * len(c["start_ratings"])
        elif name == "tier_gap":
            top = spec["start_ratings"][1]
            for t in spec["start_ratings"]:
                spec["start_ratings"][t] = top - v * (t - 1)
            spec["nonleague"] = top - v * len(spec["start_ratings"])
        elif name.startswith("start_"):
            spec["start_ratings"][int(name.split("_")[1])] = v
        elif name == "foreign":
            p.foreign_start["default"] = v
        elif name.startswith("k_") and name[2:] in p.k_multiplier:
            p.k_multiplier[name[2:]] = v
        else:
            setattr(p, name, v)
    return p


def _value(params: engine.EloParams, name: str) -> float:
    spec = params.countries[_country(params)]
    if name.startswith("level_"):
        return params.countries[name[6:]]["start_ratings"][1]
    if name.startswith("gap_"):
        sr = params.countries[name[4:]]["start_ratings"]
        return sr[1] - sr[2]
    if name == "tier_gap":
        return spec["start_ratings"][1] - spec["start_ratings"][2]
    if name.startswith("start_"):
        return spec["start_ratings"][int(name.split("_")[1])]
    if name == "foreign":
        return params.foreign_start["default"]
    if name.startswith("k_") and name[2:] in params.k_multiplier:
        return params.k_multiplier[name[2:]]
    return getattr(params, name)


def align_level(params: engine.EloParams, bias: float) -> engine.EloParams:
    """Shift every start rating by -bias. Elo updates depend only on rating
    differences, so this moves every rating by exactly -bias."""
    countries = {c: {"start_ratings": {t: r - bias for t, r in v["start_ratings"].items()},
                     "nonleague": v["nonleague"] - bias} for c, v in params.countries.items()}
    return replace(params, countries=countries,
                   foreign_start={c: r - bias for c, r in params.foreign_start.items()})


def fit(matches: pd.DataFrame, targets: pd.DataFrame, params: engine.EloParams,
        names: list[str], objective: str = "rmse_shape") -> tuple[engine.EloParams, dict]:
    """Nelder-Mead over the named parameters, minimising the given score, then
    shift the overall level so mean error against Club Elo is zero."""
    def f(x):
        s, _, _ = evaluate(matches, targets, _apply(params, names, x))
        return s[objective]

    x0 = np.array([_value(params, n) for n in names], dtype=float)
    res = minimize(f, x0, method="Nelder-Mead", options={"maxiter": 400, "xatol": 0.5, "fatol": 0.05})
    best = _apply(params, names, res.x)
    s, _, _ = evaluate(matches, targets, best)
    best = align_level(best, s["bias"])
    s, _, _ = evaluate(matches, targets, best)
    log.info("fit %s -> %s", dict(zip(names, np.round(res.x, 2))), s)
    return best, s
