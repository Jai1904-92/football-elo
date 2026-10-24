"""Static JSON snapshot of the serving layer, for the standalone site (web/).

Reads Supabase (the gold.mv_* views plus ratings and matches) and writes
compact JSON under `out`:

  meta.json            run, dates, competitions
  clubs.json           every club: id, slug, name, country, league flag,
                       career summary and branding (logo, colours)
  field.json           average top-flight rating at each month end
  <view>.json          number_ones, decade_kings, league_strength,
                       greatest_seasons, upsets, trophies, alltime_parts,
                       dynasties (trophies adds the league champions of
                       config/league_champions.csv, competition = the league)
  club/<slug>.json     one league club: monthly ratings, seasons, matches
  tables/<year>.json   month-end rankings of league clubs in that year

Monthly ratings, month-end tables and field.json carry the hindsight country
levels before 2000 (gold.country_hindsight, as the season views do): each
rating period gets its country's correction for its season. Match ratings
stay forward-only (they are the predictions).

Rows are arrays with the column names given once per file ("cols"), and
clubs are referred to by their id in clubs.json.

    python -m football_elo export [--out web/public/data]
"""
from __future__ import annotations

import io
import json
import logging
import re
import shutil
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from . import db
from .config import ROOT

log = logging.getLogger(__name__)

DEFAULT_OUT = ROOT / "web" / "public" / "data"
BRANDING = ROOT / "config" / "club_branding.csv"
CHAMPIONS = ROOT / "config" / "league_champions.csv"     # tools/league_champions.py


def _query(cur, sql: str) -> pd.DataFrame:
    buf = io.BytesIO()
    with cur.copy(f"copy ({sql}) to stdout with (format csv, header)") as cp:
        for chunk in cp:
            buf.write(chunk)
    buf.seek(0)
    df = pd.read_csv(buf, keep_default_na=True)
    for c in df.columns:  # Postgres writes booleans to CSV as t/f
        if (not pd.api.types.is_numeric_dtype(df[c]) and df[c].notna().any()
                and set(df[c].dropna().unique()) <= {"t", "f"}):
            df[c] = df[c].eq("t")
    return df


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "club"


def _rows(df: pd.DataFrame) -> dict:
    """{"cols": [...], "rows": [[...], ...]} with NaN as null."""
    clean = df.astype(object).where(df.notna(), None)
    return {"cols": list(df.columns), "rows": clean.values.tolist()}


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def with_hindsight(ratings: pd.DataFrame, hindsight: pd.DataFrame) -> pd.DataFrame:
    """Add each rating period's hindsight correction (its country, its season) to elo."""
    corr = hindsight.set_index(["country", "season"])["correction"]
    key = pd.MultiIndex.from_arrays([ratings["country"], ratings["season"].astype(int)])
    return ratings.assign(elo=ratings["elo"] + corr.reindex(key).fillna(0).to_numpy())


def club_months(ratings: pd.DataFrame) -> pd.DataFrame:
    """Each club's rating at the end of every month it played (as gold.mv_club_months)."""
    r = ratings.assign(month=pd.to_datetime(ratings["valid_from"]).dt.to_period("M")).sort_values("valid_from")
    out = r.groupby(["club", "month"], as_index=False)["elo"].last()
    return out.assign(month=out["month"].astype(str), elo=out["elo"].round().astype(int))


def month_tables(ratings: pd.DataFrame) -> pd.DataFrame:
    """Rank of every league club at each month end: the rating period that
    covers the date, among periods with a league tier (as gold.ratings_on)."""
    r = ratings[ratings["tier"].notna()].copy()
    r["valid_from"] = pd.to_datetime(r["valid_from"])
    r["valid_to"] = pd.to_datetime(r["valid_to"])
    last = r["valid_to"].max()
    ends = pd.date_range(r["valid_from"].min(), last, freq="ME")
    if ends[-1] < last:              # the month in progress, as of the last match
        ends = ends.append(pd.DatetimeIndex([last]))
    r = r.sort_values("valid_from")
    grid = (pd.MultiIndex.from_product([r["club"].unique(), ends], names=["club", "d"])
            .to_frame(index=False).sort_values("d"))
    hit = pd.merge_asof(grid, r[["club", "valid_from", "valid_to", "elo", "tier"]],
                        left_on="d", right_on="valid_from", by="club", direction="backward")
    hit = hit[hit["valid_from"].notna() & (hit["d"] <= hit["valid_to"])]
    hit["rank"] = hit.groupby("d")["elo"].rank(ascending=False, method="min").astype(int)
    return hit[["d", "club", "elo", "tier", "rank"]].sort_values(["d", "rank"])


def export(out: Path = DEFAULT_OUT) -> Path:
    with db.connect() as conn, conn.cursor() as cur:
        q = lambda sql: _query(cur, sql)  # noqa: E731
        run = q("select run_id, finished_at, last_match_date from gold.runs order by run_id desc limit 1")
        comps = q("select competition, name, comp_type, country from silver.competitions")
        clubs = q("select club, country, league_club from silver.clubs")
        summary = q("select * from gold.mv_club_summary")
        # season-end ("end") figures under their own names, whole-season ("perf") ones with a _perf suffix
        perf_cols = ["seasons_at_1", "seasons_top10", "best_rank", "best_decade"]
        summary = (summary[summary["measure"] == "end"].drop(columns="measure")
                   .merge(summary.loc[summary["measure"] == "perf", ["club"] + perf_cols], on="club", how="left",
                          suffixes=("", "_perf")))
        views = {v: q(f"select * from gold.mv_{v}") for v in
                 ["number_ones", "decade_kings", "league_strength", "greatest_seasons", "upsets",
                  "trophies", "alltime_parts", "dynasties"]}
        seasons = q("select e.club, e.season, e.tier, e.elo_end, e.elo_peak, e.above_field, e.world_rank, "
                    "e.league_rank, p.rating as perf, p.above_field as above_perf, p.world_rank as world_rank_perf, "
                    "p.league_rank as league_rank_perf from gold.mv_club_seasons e left join gold.mv_club_seasons p "
                    "on p.club = e.club and p.season = e.season and p.measure = 'perf' where e.measure = 'end'")
        hindsight = q("select country, season, correction from gold.country_hindsight")
        ratings = with_hindsight(q("select club, country, season, valid_from, valid_to, elo, tier "
                                   "from gold.club_ratings"), hindsight)
        months = club_months(ratings)
        matches = q("select m.match_id, m.match_date, m.competition, m.home_club, m.away_club, m.home_goals, "
                    "m.away_goals, m.neutral, m.home_pens, m.away_pens, r.home_elo_pre, r.away_elo_pre, "
                    "r.home_win_exp, r.elo_delta from silver.matches m join gold.match_ratings r using (match_id)")
    log.info("read %d clubs, %d matches, %d rating periods", len(clubs), len(matches), len(ratings))

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # clubs: ids by name order, unique slugs
    clubs = clubs.sort_values("club").reset_index(drop=True)
    clubs["id"] = clubs.index
    slugs, seen = [], {}
    for name in clubs["club"]:
        s = slugify(name)
        seen[s] = seen.get(s, 0) + 1
        slugs.append(s if seen[s] == 1 else f"{s}-{seen[s]}")
    clubs["slug"] = slugs
    cid = dict(zip(clubs["club"], clubs["id"]))
    clubs = clubs.merge(summary.drop(columns=["country"]), on="club", how="left")
    if BRANDING.exists():
        brand = pd.read_csv(BRANDING, dtype=str)[["club", "logo", "primary", "secondary"]]
        clubs = clubs.merge(brand, on="club", how="left")
    else:
        clubs[["logo", "primary", "secondary"]] = None
    has_file = set(seasons["club"])
    clubs["has_page"] = clubs["club"].isin(has_file)
    _write(out / "clubs.json", _rows(clubs[[
        "id", "slug", "club", "country", "league_club", "has_page", "top_flight_seasons", "first_season",
        "last_season", "peak_elo", "peak_season", "seasons_at_1", "seasons_top10", "best_rank", "best_decade",
        "seasons_at_1_perf", "seasons_top10_perf", "best_rank_perf", "best_decade_perf",
        "logo", "primary", "secondary"]].rename(columns={"club": "name"})))

    meta = {"run_id": int(run["run_id"].iloc[0]), "finished_at": str(run["finished_at"].iloc[0]),
            "last_match_date": str(run["last_match_date"].iloc[0]),
            "competitions": {r.competition: {"name": r.name, "type": r.comp_type,
                                             "country": None if pd.isna(r.country) else r.country}
                             for r in comps.itertuples()}}
    _write(out / "meta.json", meta)

    if CHAMPIONS.exists():
        champs = pd.read_csv(CHAMPIONS).rename(columns={"club": "winner"})
        champs = champs[champs["winner"].isin(cid)]
        champs = champs.assign(season_label=champs["season"].map(lambda s: f"{s}/{(s + 1) % 100:02d}"),
                               runner_up=None, legs=None)
        views["trophies"] = pd.concat([views["trophies"], champs[views["trophies"].columns]], ignore_index=True)
    for name, df in views.items():
        for col in [c for c in df.columns if c in ("club", "runner_up", "winner", "loser", "home_club", "away_club")]:
            df[col] = df[col].map(cid)
        _write(out / f"{name}.json", _rows(df))

    # month-end tables and the top-flight field average
    tables = month_tables(ratings)
    field = tables[tables["tier"] == 1].groupby("d")["elo"].mean().round(1)
    _write(out / "field.json", {d.strftime("%Y-%m"): v for d, v in field.items()})
    tables["club"] = tables["club"].map(cid)
    tables["elo"] = tables["elo"].round().astype(int)
    tables["tier"] = tables["tier"].astype(int)
    for year, t in tables.groupby(tables["d"].dt.year):
        _write(out / "tables" / f"{year}.json",
               {"cols": ["club", "elo", "tier", "rank"],
                "months": {d.strftime("%Y-%m"): g[["club", "elo", "tier", "rank"]].values.tolist()
                           for d, g in t.groupby("d")}})

    # one file per league club
    comp_code = {c: i for i, c in enumerate(sorted(comps["competition"]))}
    _write(out / "competitions.json", sorted(comps["competition"]))
    m = matches.copy()
    for col in ("home_elo_pre", "away_elo_pre"):
        m[col] = m[col].round().astype(int)
    m["home_win_exp"] = m["home_win_exp"].round(3)
    m["elo_delta"] = m["elo_delta"].round(1)
    m["comp"] = m["competition"].map(comp_code)
    home = pd.DataFrame({"club": m["home_club"], "date": m["match_date"], "comp": m["comp"],
                         "opp": m["away_club"].map(cid), "venue": np.where(m["neutral"], "n", "h"),
                         "gf": m["home_goals"], "ga": m["away_goals"], "pf": m["home_pens"], "pa": m["away_pens"],
                         "elo": m["home_elo_pre"], "opp_elo": m["away_elo_pre"], "exp": m["home_win_exp"],
                         "delta": m["elo_delta"]})
    away = pd.DataFrame({"club": m["away_club"], "date": m["match_date"], "comp": m["comp"],
                         "opp": m["home_club"].map(cid), "venue": np.where(m["neutral"], "n", "a"),
                         "gf": m["away_goals"], "ga": m["home_goals"], "pf": m["away_pens"], "pa": m["home_pens"],
                         "elo": m["away_elo_pre"], "opp_elo": m["home_elo_pre"], "exp": (1 - m["home_win_exp"]).round(3),
                         "delta": -m["elo_delta"]})
    long = pd.concat([home, away], ignore_index=True)
    long = long[long["club"].isin(has_file)].sort_values(["club", "date"])
    by_club = {k: g.drop(columns="club") for k, g in long.groupby("club")}
    s_by = {k: g.drop(columns="club") for k, g in seasons.groupby("club")}
    m_by = {k: g.drop(columns="club") for k, g in months.groupby("club")}
    slug_of = dict(zip(clubs["club"], clubs["slug"]))
    for club in has_file:
        _write(out / "club" / f"{slug_of[club]}.json",
               {"id": cid[club], "months": _rows(m_by[club])["rows"],
                "seasons": _rows(s_by[club]),
                "matches": _rows(by_club.get(club, long.iloc[0:0].drop(columns="club")))})
    size = sum(p.stat().st_size for p in out.rglob("*.json"))
    log.info("exported %d club files, %d table years to %s (%.1f MB)", len(has_file),
             tables["d"].dt.year.nunique(), out, size / 1e6)
    return out
