"""Supabase (Postgres) access. Connection string comes from SUPABASE_DB_URL,
read from the environment or a .env file in the project root."""
from __future__ import annotations

import hashlib
import io
import json
import os

import pandas as pd
import psycopg

from .config import ROOT


def db_url() -> str:
    url = os.environ.get("SUPABASE_DB_URL")
    env = ROOT / ".env"
    if not url and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "SUPABASE_DB_URL":
                url = value.strip().strip('"').strip("'")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL is not set (environment or .env)")
    return url


def connect() -> psycopg.Connection:
    return psycopg.connect(db_url(), autocommit=False)


def copy_frame(cur: psycopg.Cursor, table: str, df: pd.DataFrame) -> None:
    """Bulk insert a frame with COPY (columns named as in the table)."""
    buf = io.StringIO()
    out = df.copy()
    for c in out.columns:  # nullable integers would otherwise print as 1.0
        if out[c].dtype.kind == "f" and c not in FLOAT_COLUMNS:
            out[c] = out[c].astype("Int64")
    out.to_csv(buf, index=False, header=False, na_rep="\\N", date_format="%Y-%m-%d")
    buf.seek(0)
    cols = ", ".join(df.columns)
    with cur.copy(f"copy {table} ({cols}) from stdin with (format csv, null '\\N')") as cp:
        while chunk := buf.read(1 << 20):
            cp.write(chunk)


FLOAT_COLUMNS = {"elo", "elo_perf", "elo_avg", "correction", "home_elo_pre", "away_elo_pre", "home_elo_post", "away_elo_post",
                 "home_win_exp", "elo_delta", "k_mult", "rmse", "bias", "rmse_shape", "mean_spearman",
                 "country_offset", "level_offset", "hfa"}


# ------------------------------------------------------------------ bronze
BRONZE_COLUMNS = ["source", "file_name", "competition", "match_date", "season", "tier", "round", "leg",
                  "home_key", "away_key", "home_name", "away_name", "home_goals", "away_goals",
                  "neutral", "extra_time", "home_pens", "away_pens", "home_country", "away_country"]


def file_hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_bronze_files(cur: psycopg.Cursor, rows: pd.DataFrame, hashes: dict[tuple[str, str], str],
                         only_changed: bool = True) -> list[tuple[str, str]]:
    """Store source rows per (source, file). With only_changed, files whose
    hash matches what is stored are skipped. Returns the files written."""
    cur.execute("select source, file_name, sha256 from bronze.source_files")
    stored = {(s, f): h for s, f, h in cur.fetchall()}
    written = []
    rows = rows.rename(columns={"home_club": "home_key", "away_club": "away_key"})
    for (source, file_name), part in rows.groupby(["source", "file_name"]):
        sha = hashes.get((source, file_name), "")
        if only_changed and stored.get((source, file_name)) == sha:
            continue
        cur.execute("delete from bronze.source_files where source = %s and file_name = %s", (source, file_name))
        cur.execute("insert into bronze.source_files (source, file_name, sha256) values (%s, %s, %s)",
                    (source, file_name, sha))
        copy_frame(cur, "bronze.source_matches", part[BRONZE_COLUMNS])
        written.append((source, file_name))
    return written


# ------------------------------------------------------------------ silver
def replace_reference(cur: psycopg.Cursor, competitions: pd.DataFrame, clubs: pd.DataFrame,
                      aliases: pd.DataFrame) -> None:
    cur.execute("delete from silver.club_aliases")
    cur.execute("delete from silver.competitions")
    copy_frame(cur, "silver.competitions", competitions)
    upsert_clubs(cur, clubs)
    copy_frame(cur, "silver.club_aliases", aliases[["source", "source_name", "club"]].drop_duplicates(
        ["source", "source_name"]))


def upsert_clubs(cur: psycopg.Cursor, clubs: pd.DataFrame) -> None:
    cur.execute("create temp table _c (like silver.clubs) on commit drop")
    copy_frame(cur, "_c", clubs[["club", "country", "league_club"]])
    cur.execute("""insert into silver.clubs select * from _c
                   on conflict (club) do update set country = excluded.country,
                                                    league_club = excluded.league_club""")
    cur.execute("drop table _c")


def add_aliases(cur: psycopg.Cursor, aliases: pd.DataFrame) -> None:
    if aliases.empty:
        return
    cur.execute("create temp table _a (like silver.club_aliases) on commit drop")
    copy_frame(cur, "_a", aliases[["source", "source_name", "club"]])
    cur.execute("insert into silver.club_aliases select * from _a on conflict do nothing")
    cur.execute("drop table _a")


def fetch_aliases(cur: psycopg.Cursor) -> pd.DataFrame:
    cur.execute("select source, source_name, club from silver.club_aliases")
    return pd.DataFrame(cur.fetchall(), columns=["source", "source_name", "club"])


MATCH_COLUMNS = ["match_id", "match_date", "season", "competition", "comp_type", "tier", "round", "leg",
                 "home_club", "away_club", "home_goals", "away_goals", "neutral", "extra_time",
                 "home_pens", "away_pens", "source"]


def upsert_matches(cur: psycopg.Cursor, matches: pd.DataFrame) -> pd.DataFrame:
    """Insert new matches and update changed results. Returns the rows that
    were new or changed (match_id, match_date)."""
    cols = MATCH_COLUMNS
    cur.execute("create temp table _m (like silver.matches including defaults) on commit drop")
    copy_frame(cur, "_m", matches[cols])
    sets = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "match_id")
    cur.execute(f"""
        with changed as (
          select n.match_id from _m n
          left join silver.matches o using (match_id)
          where o.match_id is null
             or (o.home_goals, o.away_goals, o.match_date, o.neutral, o.competition, o.tier)
                is distinct from (n.home_goals, n.away_goals, n.match_date, n.neutral, n.competition, n.tier)
        ), up as (
          insert into silver.matches ({", ".join(cols)})
          select {", ".join(cols)} from _m where match_id in (select match_id from changed)
          on conflict (match_id) do update set {sets}, loaded_at = now()
          returning match_id, match_date
        )
        select match_id, match_date from up""")
    out = pd.DataFrame(cur.fetchall(), columns=["match_id", "match_date"])
    cur.execute("drop table _m")
    return out


def fetch_matches(cur: psycopg.Cursor, since=None) -> pd.DataFrame:
    sql = f"select {', '.join(MATCH_COLUMNS)} from silver.matches"
    args: tuple = ()
    if since is not None:
        sql += " where match_date >= %s"
        args = (since,)
    cur.execute(sql, args)
    df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    df["match_date"] = pd.to_datetime(df["match_date"])
    return df


def fetch_club_country(cur: psycopg.Cursor) -> pd.Series:
    cur.execute("select club, country from silver.clubs")
    return pd.DataFrame(cur.fetchall(), columns=["club", "country"]).set_index("club")["country"]


def fetch_europe_games(cur: psycopg.Cursor) -> pd.Series:
    """(country, season) -> European games, from the rated history (each
    club's country that season), for evidence-scaled pooling."""
    cur.execute("""
        with cs as (select distinct club, season, country from gold.club_ratings where country is not null),
        e as (select season, home_club as club from silver.matches where comp_type = 'europe'
              union all select season, away_club from silver.matches where comp_type = 'europe')
        select cs.country, e.season, count(*) from e join cs using (club, season) group by cs.country, e.season""")
    df = pd.DataFrame(cur.fetchall(), columns=["country", "season", "n"])
    return df.set_index(["country", "season"])["n"]


def last_season_before(cur: psycopg.Cursor, day) -> dict[str, int]:
    """club -> season of its last rated match before `day` (season regression)."""
    cur.execute("select club, max(season) from gold.club_ratings where valid_from <= %s group by club", (day,))
    return {c: int(s) for c, s in cur.fetchall()}


def fetch_membership(cur: psycopg.Cursor) -> pd.Series:
    """(club, season) -> league tier, all seasons (needed to spot newcomers)."""
    cur.execute("""
        select club, season, mode() within group (order by tier) as tier from (
          select home_club as club, season, tier from silver.matches where comp_type = 'league'
          union all
          select away_club, season, tier from silver.matches where comp_type = 'league'
        ) x group by club, season""")
    df = pd.DataFrame(cur.fetchall(), columns=["club", "season", "tier"])
    return df.set_index(["club", "season"])["tier"]


# ------------------------------------------------------------------ gold
def start_run(cur: psycopg.Cursor, kind: str, params: dict, replay_from=None) -> int:
    cur.execute("insert into gold.runs (kind, params, replay_from) values (%s, %s, %s) returning run_id",
                (kind, json.dumps(params), replay_from))
    return cur.fetchone()[0]


def finish_run(cur: psycopg.Cursor, run_id: int, matches_rated: int, last_match_date) -> None:
    cur.execute("update gold.runs set finished_at = now(), matches_rated = %s, last_match_date = %s "
                "where run_id = %s", (matches_rated, last_match_date, run_id))


def last_run_params(cur: psycopg.Cursor) -> dict | None:
    cur.execute("select params from gold.runs where finished_at is not null order by run_id desc limit 1")
    row = cur.fetchone()
    return row[0] if row else None


def base_before(cur: psycopg.Cursor, when) -> dict[str, float]:
    """Each club's own rating part (rating minus its country's pooling
    offset at the time) after its last match strictly before `when`."""
    cur.execute("""
        select distinct on (club) club, elo - country_offset from gold.club_ratings
        where valid_from <= %s order by club, valid_from desc""", (when,))
    return dict(cur.fetchall())


def offsets_before(cur: psycopg.Cursor, when) -> dict[str, float]:
    """Each country's pooling offset in force on `when`."""
    cur.execute("""
        select distinct on (country) country, level_offset from gold.league_offsets
        where valid_from <= %s order by country, valid_from desc""", (when,))
    return dict(cur.fetchall())


def hfa_before(cur: psycopg.Cursor, when) -> dict[str, float]:
    """Each dynamic home-advantage key's value in force on `when`."""
    cur.execute("""
        select distinct on (hfa_key) hfa_key, hfa from gold.hfa_levels
        where valid_from <= %s order by hfa_key, valid_from desc""", (when,))
    return dict(cur.fetchall())


def played_before(cur: psycopg.Cursor, when) -> dict[str, int]:
    """Rated matches per club before `when` (for provisional ratings)."""
    cur.execute("""
        select club, count(*) from (
          select home_club as club from silver.matches where match_date < %s
          union all select away_club from silver.matches where match_date < %s) x
        group by club""", (when, when))
    return {c: int(n) for c, n in cur.fetchall()}


def write_hfa_levels(cur: psycopg.Cursor, levels: pd.DataFrame, run_id: int) -> None:
    if levels.empty:
        return
    out = levels[["hfa_key", "valid_from", "hfa"]].copy()
    out["run_id"] = run_id
    copy_frame(cur, "gold.hfa_levels", out)


def write_league_offsets(cur: psycopg.Cursor, offsets: pd.DataFrame, run_id: int) -> None:
    if offsets.empty:
        return
    out = offsets[["country", "valid_from", "offset"]].rename(columns={"offset": "level_offset"})
    out["run_id"] = run_id
    copy_frame(cur, "gold.league_offsets", out)


def write_match_ratings(cur: psycopg.Cursor, rated: pd.DataFrame, run_id: int, burn_in_until: str) -> None:
    out = rated[["match_id", "match_date", "home_elo_pre", "away_elo_pre", "home_elo_post",
                 "away_elo_post", "home_win_exp", "elo_delta", "hfa_on", "k_mult", "hfa_used"]].rename(
        columns={"hfa_on": "hfa_applied", "hfa_used": "hfa"}).copy()
    out["burn_in"] = rated["match_date"] < pd.Timestamp(burn_in_until)
    out["run_id"] = run_id
    copy_frame(cur, "gold.match_ratings", out)


def write_club_ratings(cur: psycopg.Cursor, per: pd.DataFrame, run_id: int) -> None:
    out = per.copy()
    out["run_id"] = run_id
    copy_frame(cur, "gold.club_ratings", out)


def refresh_valid_to(cur: psycopg.Cursor) -> None:
    """Recompute period ends after an incremental write: next period's start
    minus one day; open for clubs that played in the latest season; otherwise
    the last match day of the club's final season."""
    cur.execute("""
        with season_end as (
          select season, max(match_date) as end_date from silver.matches group by season
        ), latest as (select max(season) as season from silver.matches),
        x as (
          select c.club, c.valid_from,
                 case
                   when lead(c.valid_from) over w is not null then lead(c.valid_from) over w - 1
                   when c.season = (select season from latest) then null
                   else greatest(se.end_date, c.valid_from)
                 end as new_to
          from gold.club_ratings c join season_end se using (season)
          window w as (partition by c.club order by c.valid_from)
        )
        update gold.club_ratings c set valid_to = x.new_to
        from x
        where c.club = x.club and c.valid_from = x.valid_from
          and c.valid_to is distinct from x.new_to""")


def write_season_perf(cur: psycopg.Cursor, perf: pd.DataFrame, run_id: int, from_season: int | None = None) -> None:
    """Replace whole-season performance ratings (all, or from a season on)."""
    if from_season is None:
        cur.execute("delete from gold.club_season_perf")
    else:
        cur.execute("delete from gold.club_season_perf where season >= %s", (from_season,))
    if perf.empty:
        return
    copy_frame(cur, "gold.club_season_perf", perf[["club", "season", "elo_perf", "elo_avg", "matches"]].assign(run_id=run_id))


def fetch_season_inputs(cur: psycopg.Cursor, from_season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rated matches and rating periods from a season on, for seasons.season_performance."""
    cur.execute("""select m.season, m.home_club, m.away_club, m.home_goals, m.away_goals,
                          r.home_elo_pre, r.away_elo_pre, r.home_win_exp, r.k_mult
                   from silver.matches m join gold.match_ratings r using (match_id) where m.season >= %s""",
                (from_season,))
    rated = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    cur.execute("select club, season, tier, valid_from, valid_to, elo from gold.club_ratings where season >= %s",
                (from_season,))
    periods = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    for c in ("home_elo_pre", "away_elo_pre", "home_win_exp", "k_mult"):
        rated[c] = rated[c].astype(float)
    return rated, periods


def refresh_serving(cur: psycopg.Cursor) -> None:
    """Rebuild the dashboard's precomputed tables (gold.mv_*) from the new ratings."""
    cur.execute("select gold.refresh_serving()")


def write_calibration(cur: psycopg.Cursor, run_id: int, scores: pd.DataFrame) -> None:
    out = scores.reset_index().rename(columns={"index": "target"})
    out["run_id"] = run_id
    out["n"] = out["n"].astype(int)
    copy_frame(cur, "gold.calibration_scores",
               out[["run_id", "target", "n", "rmse", "bias", "rmse_shape", "mean_spearman"]])
