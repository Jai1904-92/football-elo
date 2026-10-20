"""Elo engine.

For each match, in date order:
    dr  = elo_home - elo_away + hfa          (hfa = 0 at neutral venues)
    We  = 1 / (10 ** (-dr / scale) + 1)      home win expectancy
    R   = 1 / 0.5 / 0 for home win / draw / loss (after extra time;
          a penalty shoot-out counts as a draw)
    d   = k * k_mult(competition type) * margin(|goal diff|) * (R - We)
    elo_home += d ; elo_away -= d

A club's first rating depends on where it is when first seen: its league
tier's start rating if it plays in a modelled league that season, its
country's non-league rating if the country is modelled but the club is not
in the league, otherwise a foreign start rating. Ratings carry across tiers
and competitions (no reset).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class EloParams:
    k: float = 20.0
    hfa: float = 70.0
    scale: float = 400.0
    margin_method: str = "power"
    margin_exponent: float = 0.5
    margin_table: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.5, 1.75, 1.875])
    # country -> {"start_ratings": {tier: rating}, "nonleague": rating}
    countries: dict = field(default_factory=lambda: {
        "ENG": {"start_ratings": {1: 1650.0, 2: 1450.0, 3: 1300.0, 4: 1200.0}, "nonleague": 1050.0}})
    foreign_start: dict = field(default_factory=lambda: {"default": 1500.0})
    k_multiplier: dict = field(default_factory=lambda: {"league": 1.0, "playoff": 1.0, "cup": 1.0, "europe": 1.0})
    # a club joining a country's lowest modelled tier after that country's
    # first season came up from below: start it one tier lower
    newcomer_from_below: bool = False
    # League pooling: a share of every European rating change also moves the
    # club's whole country (all its clubs), so a league that over- or
    # under-performs in Europe is re-levelled quickly instead of over decades.
    # 0 switches it off (plain Club Elo).
    league_pool: float = 0.0
    # Provisional ratings: a club's first `provisional_matches` rated matches
    # use K x `provisional_k`, so a new club (a foreign side entering Europe,
    # a newly promoted club) reaches its level quickly. 0 matches = off.
    provisional_matches: int = 0
    provisional_k: float = 1.0
    # Dynamic home advantage: each home country's HFA (starting at `hfa`)
    # moves by `hfa_eta` x (result - expected) after every match with home
    # advantage, so it tracks how strong home advantage really is in that
    # era. European home games share one HFA of their own when
    # `hfa_europe_separate`. `hfa_start` is where every HFA begins in the
    # first season (defaults to `hfa`). 0 eta = fixed HFA.
    hfa_eta: float = 0.0
    hfa_europe_separate: bool = True
    hfa_start: float | None = None

    @classmethod
    def from_config(cls, cfg: dict) -> "EloParams":
        e = cfg["elo"]
        countries = {c: {"start_ratings": {int(t): float(r) for t, r in v["start_ratings"].items()},
                         "nonleague": float(v["nonleague"])}
                     for c, v in e["countries"].items()}
        return cls(k=e["k"], hfa=e["hfa"], scale=e["scale"],
                   margin_method=e["margin"]["method"],
                   margin_exponent=e["margin"].get("exponent", 0.5),
                   margin_table=list(e["margin"].get("table", [1.0])),
                   countries=countries,
                   foreign_start={str(c): float(r) for c, r in e["foreign_start"].items()},
                   k_multiplier={t: float(v) for t, v in e["k_multiplier"].items()},
                   newcomer_from_below=bool(e.get("newcomer_from_below", False)),
                   league_pool=float(e.get("league_pool", 0.0)),
                   provisional_matches=int(e.get("provisional", {}).get("matches", 0)),
                   provisional_k=float(e.get("provisional", {}).get("k_multiplier", 1.0)),
                   hfa_eta=float(e.get("hfa_dynamic", {}).get("eta", 0.0)),
                   hfa_europe_separate=bool(e.get("hfa_dynamic", {}).get("europe_separate", True)),
                   hfa_start=e.get("hfa_dynamic", {}).get("start"))

    def start_rating(self, country, tier) -> float:
        spec = self.countries.get(country)
        if spec is None:
            return self.foreign_start.get(country, self.foreign_start["default"])
        if tier is not None and not pd.isna(tier) and int(tier) in spec["start_ratings"]:  # -1 = no tier
            return spec["start_ratings"][int(tier)]
        return spec["nonleague"]

    def margin_lookup(self, max_gd: int = 20) -> np.ndarray:
        """Multiplier indexed by absolute goal difference (0..max_gd)."""
        gd = np.arange(max_gd + 1, dtype=float)
        if self.margin_method == "none":
            return np.ones_like(gd)
        if self.margin_method in ("sqrt", "power"):
            exp = 0.5 if self.margin_method == "sqrt" else self.margin_exponent
            return np.maximum(gd, 1.0) ** exp
        if self.margin_method == "table":
            t = list(self.margin_table)
            return np.array([t[min(int(g), len(t) - 1)] for g in gd])
        raise ValueError(f"unknown margin method {self.margin_method!r}")


def league_membership(matches: pd.DataFrame) -> pd.Series:
    """(club, season) -> league tier, from league matches."""
    lg = matches[matches["comp_type"] == "league"] if "comp_type" in matches else matches
    long = pd.concat([lg[["home_club", "season", "tier"]].set_axis(["club", "season", "tier"], axis=1),
                      lg[["away_club", "season", "tier"]].set_axis(["club", "season", "tier"], axis=1)])
    return long.groupby(["club", "season"])["tier"].agg(lambda s: s.value_counts().index[0])


def prepare(matches: pd.DataFrame, params: EloParams, club_country: pd.Series | None = None,
            membership: pd.Series | None = None) -> pd.DataFrame:
    """Add the per-match inputs the rating loop needs: home/away tier and
    country, start ratings, HFA on/off and K multiplier.

    `club_country` maps club -> country (default: every club belongs to the
    first modelled country); `membership` maps (club, season) -> tier
    (default: derived from the league matches given)."""
    m = matches.copy()
    if "comp_type" not in m:
        m["comp_type"] = "league"
    if "neutral" not in m:
        m["neutral"] = False
    membership = league_membership(m) if membership is None else membership
    default_country = next(iter(params.countries))
    newcomer = _newcomer_seasons(membership, club_country, default_country)
    for side in ("home", "away"):
        key = pd.MultiIndex.from_arrays([m[f"{side}_club"], m["season"]])
        m[f"{side}_tier"] = membership.reindex(key).to_numpy()
        m[f"{side}_country"] = (m[f"{side}_club"].map(club_country).to_numpy()
                                if club_country is not None else default_country)
        m[f"{side}_newcomer"] = newcomer.reindex(key).fillna(False).to_numpy(dtype=bool)
    m["hfa_on"] = ~m["neutral"].astype(bool)
    return assign_params(m, params)


def _newcomer_seasons(membership: pd.Series, club_country: pd.Series | None,
                      default_country: str) -> pd.Series:
    """(club, season) -> True when that season is the club's first league
    season, it is not its country's first modelled season, and the club is
    in the lowest tier modelled for its country that season."""
    df = membership.rename("tier").reset_index()
    df["country"] = df["club"].map(club_country) if club_country is not None else default_country
    first_club = df.groupby("club")["season"].transform("min")
    first_country = df.groupby("country")["season"].transform("min")
    lowest = df.groupby(["country", "season"])["tier"].transform("max")
    flag = (df["season"] == first_club) & (df["season"] > first_country) & (df["tier"] == lowest)
    return pd.Series(flag.to_numpy(), index=pd.MultiIndex.from_frame(df[["club", "season"]]))


def assign_params(m: pd.DataFrame, params: EloParams) -> pd.DataFrame:
    """(Re)compute the parameter-dependent inputs: start ratings and K
    multipliers. Cheap, so calibration can vary parameters on one prepared frame."""
    m = m.copy()
    for side in ("home", "away"):
        tier = m[f"{side}_tier"]
        if params.newcomer_from_below and f"{side}_newcomer" in m:
            tier = tier.where(~m[f"{side}_newcomer"], tier + 1)   # start one tier down
        pairs = pd.DataFrame({"c": m[f"{side}_country"], "t": tier}).fillna({"t": -1})
        uniq = pairs.drop_duplicates()
        lookup = {(c, t): params.start_rating(c, t) for c, t in zip(uniq["c"], uniq["t"])}
        m[f"{side}_start"] = [lookup[(c, t)] for c, t in zip(pairs["c"], pairs["t"])]
    m["k_mult"] = m["comp_type"].map(params.k_multiplier).fillna(1.0)
    return m


def run(matches: pd.DataFrame, params: EloParams, initial: dict[str, float] | None = None,
        club_country: pd.Series | None = None,
        membership: pd.Series | None = None,
        offsets: dict[str, float] | None = None,
        initial_base: dict[str, float] | None = None,
        played: dict[str, int] | None = None,
        hfa_state: dict[str, float] | None = None) -> tuple[pd.DataFrame, dict[str, float]]:
    """Rate matches in order. `initial` holds ratings carried in from an earlier
    run (incremental updates); clubs not in it get their start rating.

    With league pooling a club's rating is its own part plus its country's
    level offset. `offsets` carries country offsets in from an earlier run,
    and `initial_base` each club's own part (rating minus its country's
    offset when it last played); without `initial_base`, `initial` full
    ratings are split using the current offsets.

    `hfa_state` carries dynamic home advantage per key (home country, or
    "europe") from an earlier run.
    `played` carries each club's count of rated matches before this run
    (for provisional K); clubs carried in without a count are treated as
    established.

    Returns (per-match frame with pre/post ratings and each side's country
    offset after the match, final full ratings). Final offsets are left in
    `run.last_offsets`."""
    if "home_tier" not in matches:
        matches = prepare(matches, params, club_country, membership)
    else:
        matches = assign_params(matches, params)
    sort = ["match_date", "match_id"] if "match_id" in matches else ["match_date", "home_club"]
    m = matches.sort_values(sort).reset_index(drop=True)
    off = dict(offsets or {})
    hc_arr = m["home_country"].to_numpy() if "home_country" in m else np.full(len(m), None)
    ac_arr = m["away_country"].to_numpy() if "away_country" in m else np.full(len(m), None)
    # base (club) part of each carried-in rating
    country_of = {}
    for c, k_ in zip(m["home_club"], hc_arr):
        country_of.setdefault(c, k_)
    for c, k_ in zip(m["away_club"], ac_arr):
        country_of.setdefault(c, k_)
    if initial_base is not None:
        base = dict(initial_base)
    else:
        base = {c: r - off.get(country_of.get(c), 0.0) for c, r in (initial or {}).items()}
    mult = params.margin_lookup(max(20, int((m["home_goals"] - m["away_goals"]).abs().max() or 0)))
    k, hfa, scale, lam = params.k, params.hfa, params.scale, params.league_pool
    prov_n, prov_k = params.provisional_matches, params.provisional_k
    eta, hfa_sep = params.hfa_eta, params.hfa_europe_separate
    hstate = dict(hfa_state or {})
    n_played = dict(played or {})
    for c in (initial_base or initial or {}):
        n_played.setdefault(c, prov_n)

    n = len(m)
    hfa_used = np.zeros(n)
    hfa_keys = np.full(n, None, dtype=object)
    hfa_after = np.full(n, np.nan)
    pre_h = np.empty(n); pre_a = np.empty(n); exp_h = np.empty(n); delta = np.empty(n)
    post_h = np.empty(n); post_a = np.empty(n); off_h = np.zeros(n); off_a = np.zeros(n)
    homes = m["home_club"].to_numpy(); aways = m["away_club"].to_numpy()
    hg = m["home_goals"].to_numpy(); ag = m["away_goals"].to_numpy()
    hs = m["home_start"].to_numpy(dtype=float); as_ = m["away_start"].to_numpy(dtype=float)
    hfa_on = m["hfa_on"].to_numpy(dtype=bool); km = m["k_mult"].to_numpy(dtype=float)
    europe = (m["comp_type"] == "europe").to_numpy() if "comp_type" in m else np.zeros(n, bool)

    for i in range(n):
        h, a = homes[i], aways[i]
        ch = hc_arr[i] if isinstance(hc_arr[i], str) else None
        ca = ac_arr[i] if isinstance(ac_arr[i], str) else None
        oh, oa = off.get(ch, 0.0), off.get(ca, 0.0)
        # a club seen for the first time starts at its start rating on top of
        # its country's current level, so it inherits what pooling has learned
        bh = base.get(h)
        if bh is None:
            bh = hs[i]
        ba = base.get(a)
        if ba is None:
            ba = as_[i]
        rh, ra = bh + oh, ba + oa
        hkey = None
        h_adv = 0.0
        if hfa_on[i]:
            if eta:
                hkey = "europe" if hfa_sep and europe[i] else (ch or "?")
                h_adv = hstate.get(hkey, hfa if params.hfa_start is None else params.hfa_start)
            else:
                h_adv = hfa
        we = 1.0 / (10.0 ** (-(rh - ra + h_adv) / scale) + 1.0)
        gd = int(hg[i] - ag[i])
        res = 1.0 if gd > 0 else (0.5 if gd == 0 else 0.0)
        hfa_used[i] = h_adv
        if hkey is not None:
            hstate[hkey] = h_adv + eta * (res - we)
            hfa_keys[i], hfa_after[i] = hkey, hstate[hkey]
        d = k * km[i] * mult[abs(gd)] * (res - we)
        dh = da = d
        if prov_n:
            nh, na = n_played.get(h, 0), n_played.get(a, 0)
            if nh < prov_n:
                dh = d * prov_k
            if na < prov_n:
                da = d * prov_k
            n_played[h], n_played[a] = nh + 1, na + 1
        base[h] = bh + dh
        base[a] = ba - da
        if lam and europe[i] and ch != ca:
            if ch is not None:
                off[ch] = oh + lam * dh
            if ca is not None:
                off[ca] = oa - lam * da
        pre_h[i], pre_a[i], exp_h[i], delta[i] = rh, ra, we, d
        off_h[i], off_a[i] = off.get(ch, 0.0), off.get(ca, 0.0)
        post_h[i] = base[h] + off_h[i]
        post_a[i] = base[a] + off_a[i]

    out = m.assign(home_elo_pre=pre_h, away_elo_pre=pre_a,
                   home_elo_post=post_h, away_elo_post=post_a,
                   home_win_exp=exp_h, elo_delta=delta,
                   home_offset=off_h, away_offset=off_a, hfa_used=hfa_used,
                   hfa_key=hfa_keys, hfa_after=hfa_after)
    final = {c: b + off.get(country_of.get(c), 0.0) for c, b in base.items()}
    run.last_offsets = off
    run.last_played = n_played
    run.last_hfa = hstate
    return out, final


def periods(rated: pd.DataFrame, season_ends: pd.Series | None = None,
            burn_in_until: str | None = None) -> pd.DataFrame:
    """Club Elo grain: one row per club per rating period. `rated` comes from
    `run`, so it carries tier and country columns; `tier` is the club's
    league tier that season, null outside a modelled league.

    A period starts the day after a match (valid_from) and ends on the day of
    the club's next match (valid_to). A club's last period stays open (null)
    if it played in the latest season; otherwise it closes on the last match
    day of the club's final season (`season_ends`: season -> date; defaults
    to the last match date per season in `rated`)."""
    if season_ends is None:
        season_ends = rated.groupby("season")["match_date"].max()
    cols = ["match_id", "match_date", "season"]
    side_cols = ["club", "elo", "tier", "country", "country_offset"]
    h_off = "home_offset" if "home_offset" in rated else None
    rated = rated if h_off else rated.assign(home_offset=0.0, away_offset=0.0)
    long = pd.concat([
        rated[cols + ["home_club", "home_elo_post", "home_tier", "home_country", "home_offset"]].set_axis(cols + side_cols, axis=1),
        rated[cols + ["away_club", "away_elo_post", "away_tier", "away_country", "away_offset"]].set_axis(cols + side_cols, axis=1),
    ]).sort_values(["club", "match_date", "match_id"])
    long["valid_from"] = long["match_date"] + pd.Timedelta(days=1)
    long["valid_to"] = long.groupby("club")["match_date"].shift(-1)
    last = long["valid_to"].isna()
    latest = season_ends.index.max()
    dropped = last & (long["season"] < latest)
    long.loc[dropped, "valid_to"] = np.maximum(long.loc[dropped, "season"].map(season_ends),
                                               long.loc[dropped, "valid_from"])
    long["burn_in"] = (long["match_date"] < pd.Timestamp(burn_in_until)) if burn_in_until else False
    # two matches on one day (source date errors): keep the later rating only
    long = long.drop_duplicates(["club", "valid_from"], keep="last")
    return long.rename(columns={"match_id": "last_match_id"})[
        ["club", "country", "valid_from", "valid_to", "elo", "tier", "season", "last_match_id", "burn_in",
         "country_offset"]
    ].reset_index(drop=True)


def hfa_levels(rated: pd.DataFrame) -> pd.DataFrame:
    """Dynamic home advantage over time: one row per key (home country, or
    "europe") per day it changed, valid from the day after the match."""
    if "hfa_key" not in rated:
        return pd.DataFrame(columns=["hfa_key", "valid_from", "hfa"])
    h = rated.dropna(subset=["hfa_key"]).sort_values(["match_date", "match_id"])
    h = h.assign(valid_from=h["match_date"] + pd.Timedelta(days=1))
    h = h.drop_duplicates(["hfa_key", "valid_from"], keep="last")
    return h[["hfa_key", "valid_from", "hfa_after"]].rename(columns={"hfa_after": "hfa"}).reset_index(drop=True)


def league_offsets(rated: pd.DataFrame) -> pd.DataFrame:
    """Each country's pooling offset over time: one row per country per day
    it changed (valid from the day after the match), from a run's output."""
    e = rated[rated.get("comp_type", pd.Series("", index=rated.index)) == "europe"]
    long = pd.concat([
        e[["match_date", "match_id", "home_country", "home_offset"]].set_axis(["match_date", "match_id", "country", "offset"], axis=1),
        e[["match_date", "match_id", "away_country", "away_offset"]].set_axis(["match_date", "match_id", "country", "offset"], axis=1),
    ]).dropna(subset=["country"]).sort_values(["country", "match_date", "match_id"])
    long["valid_from"] = long["match_date"] + pd.Timedelta(days=1)
    long = long.drop_duplicates(["country", "valid_from"], keep="last")
    long = long[long.groupby("country")["offset"].diff().fillna(long["offset"]) != 0]
    return long[["country", "valid_from", "offset"]].reset_index(drop=True)


def ratings_on(per: pd.DataFrame, when) -> pd.DataFrame:
    """Each club's rating on a given date (the period covering it)."""
    when = pd.Timestamp(when)
    p = per[(per["valid_from"] <= when) & (per["valid_to"].isna() | (per["valid_to"] >= when))]
    return p.sort_values("elo", ascending=False).reset_index(drop=True)


def _result(rated: pd.DataFrame) -> np.ndarray:
    return np.where(rated["home_goals"] > rated["away_goals"], 1.0,
                    np.where(rated["home_goals"] == rated["away_goals"], 0.5, 0.0))


def log_loss(rated: pd.DataFrame) -> float:
    """Mean log loss of home win expectancy vs result (draw = 0.5)."""
    r = _result(rated)
    p = rated["home_win_exp"].clip(1e-9, 1 - 1e-9)
    return float(-np.mean(r * np.log(p) + (1 - r) * np.log(1 - p)))


def brier(rated: pd.DataFrame) -> float:
    return float(np.mean((rated["home_win_exp"] - _result(rated)) ** 2))
