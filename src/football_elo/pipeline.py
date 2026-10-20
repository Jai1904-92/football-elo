"""Pipeline entry points: full rebuild and weekly incremental update."""
from __future__ import annotations

import logging
from dataclasses import asdict

import pandas as pd

from . import bronze, calibrate, db, engine, silver

log = logging.getLogger(__name__)


def run_params(cfg: dict) -> dict:
    """Everything that changes ratings; a change triggers a full rebuild."""
    p = asdict(engine.EloParams.from_config(cfg))
    p["countries"] = {c: {"start_ratings": {str(t): r for t, r in v["start_ratings"].items()},
                          "nonleague": v["nonleague"]} for c, v in p["countries"].items()}
    p["start_date"] = cfg["elo"]["start_date"]
    p["burn_in_until"] = cfg["elo"]["burn_in_until"]
    p["competitions"] = sorted(cfg["competitions"])
    return p


def persist_new_aliases(cfg: dict, new: pd.DataFrame) -> None:
    """Append auto-registered aliases to the aliases file."""
    if new.empty:
        return
    path = cfg["aliases"]
    current = pd.read_csv(path, dtype=str)
    pd.concat([current, new]).drop_duplicates(["source", "source_name"]).to_csv(path, index=False)
    log.warning("added %d auto-registered aliases to %s", len(new), path)


def rate(cfg: dict, built: dict) -> dict:
    params = engine.EloParams.from_config(cfg)
    country = built["clubs"].set_index("club")["country"]
    rated, _ = engine.run(built["matches"], params, club_country=country)
    per = engine.periods(rated, burn_in_until=cfg["elo"]["burn_in_until"])
    return {"rated": rated, "periods": per, "offsets": engine.league_offsets(rated),
            "hfa": engine.hfa_levels(rated)}


def calibration_scores(cfg: dict, rated: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    targets = calibrate.load_targets(cfg, cfg["elo"]["burn_in_until"])
    cmp = calibrate.attach_ours(targets, rated)
    scores = calibrate.score_by(cmp, "source")
    scores.loc["all"] = calibrate.score(cmp)
    return scores, cmp


def build_local(cfg: dict, fetch: bool = True) -> dict:
    """Fetch sources, build silver and gold, write parquet/CSV locally."""
    if fetch:
        bronze.fetch_all(cfg)
    built = silver.build(cfg)
    persist_new_aliases(cfg, built["new_aliases"])
    built.update(rate(cfg, built))
    built["scores"], cmp = calibration_scores(cfg, built["rated"])

    paths = cfg["paths"]
    paths["silver"].mkdir(parents=True, exist_ok=True)
    paths["gold"].mkdir(parents=True, exist_ok=True)
    built["matches"].to_parquet(paths["silver"] / "matches.parquet", index=False)
    built["clubs"].to_parquet(paths["silver"] / "clubs.parquet", index=False)
    built["rated"].to_parquet(paths["gold"] / "match_ratings.parquet", index=False)
    built["periods"].to_parquet(paths["gold"] / "club_ratings.parquet", index=False)
    built["scores"].to_csv(paths["gold"] / "calibration_scores.csv")
    cmp.to_csv(paths["gold"] / "calibration_comparison.csv", index=False)
    log.info("built %d matches, %d rating periods, %d clubs; calibration: %s",
             len(built["rated"]), len(built["periods"]), len(built["clubs"]),
             built["scores"].loc["all"].round(3).to_dict())
    return built


def _hashes(cfg: dict, source_rows: pd.DataFrame) -> dict:
    root = cfg["paths"]["bronze"]
    files = source_rows[["source", "file_name"]].drop_duplicates()
    return {(s, f): db.file_hash(root / f) for s, f in files.itertuples(index=False)}


def full_load(cfg: dict, fetch: bool = True) -> int:
    """Rebuild everything locally and replace the Supabase contents."""
    built = build_local(cfg, fetch=fetch)
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("truncate gold.hfa_levels, gold.league_offsets, gold.calibration_scores, gold.club_ratings, gold.match_ratings, gold.runs, "
                    "silver.matches, silver.club_aliases, silver.clubs, silver.competitions, "
                    "bronze.source_matches, bronze.source_files")
        written = db.replace_bronze_files(cur, built["source_rows"], _hashes(cfg, built["source_rows"]),
                                          only_changed=False)
        log.info("bronze: %d files, %d rows", len(written), len(built["source_rows"]))
        db.replace_reference(cur, silver.competitions_table(cfg), built["clubs"], built["aliases"])
        db.copy_frame(cur, "silver.matches", built["matches"][db.MATCH_COLUMNS])
        run_id = db.start_run(cur, "full", run_params(cfg), built["matches"]["match_date"].min().date())
        db.write_match_ratings(cur, built["rated"], run_id, cfg["elo"]["burn_in_until"])
        db.write_club_ratings(cur, built["periods"], run_id)
        db.write_league_offsets(cur, built["offsets"], run_id)
        db.write_hfa_levels(cur, built["hfa"], run_id)
        db.write_calibration(cur, run_id, built["scores"])
        db.finish_run(cur, run_id, len(built["rated"]), built["rated"]["match_date"].max().date())
        db.refresh_serving(cur)
        conn.commit()
    log.info("full load complete (run %d)", run_id)
    return run_id


def incremental_update(cfg: dict) -> int | None:
    """Weekly job: refresh live sources, rate new or corrected matches.

    Matches are re-rated from the earliest new/changed match date onwards,
    starting from the stored ratings just before that date. If the rating
    parameters differ from the last run, does a full load instead."""
    params = run_params(cfg)
    with db.connect() as conn, conn.cursor() as cur:
        last = db.last_run_params(cur)
    if last != params:
        log.info("parameters changed since last run (or no run yet): doing a full load")
        return full_load(cfg)

    bronze.fetch_all(cfg)  # past files are cached; live files re-download
    with db.connect() as conn, conn.cursor() as cur:
        aliases = pd.concat([silver.load_aliases(cfg["aliases"]), db.fetch_aliases(cur)]) \
            .drop_duplicates(["source", "source_name"])
        built = silver.build(cfg, aliases=aliases)
        persist_new_aliases(cfg, built["new_aliases"])

        written = db.replace_bronze_files(cur, built["source_rows"], _hashes(cfg, built["source_rows"]))
        log.info("bronze: %d changed files", len(written))
        db.upsert_clubs(cur, built["clubs"])
        db.add_aliases(cur, built["new_aliases"])

        live_from = pd.Timestamp(bronze.current_season() - 1, 7, 1)  # last and current season
        live = built["matches"][built["matches"]["match_date"] >= live_from]
        changed = db.upsert_matches(cur, live)
        if changed.empty:
            conn.commit()
            log.info("no new or changed matches")
            return None

        replay_from = pd.Timestamp(changed["match_date"].min())
        base = db.base_before(cur, replay_from.date())
        offsets = db.offsets_before(cur, replay_from.date())
        hfa_state = db.hfa_before(cur, replay_from.date())
        played = db.played_before(cur, replay_from.date())
        to_rate = db.fetch_matches(cur, since=replay_from.date())
        membership = db.fetch_membership(cur)
        run_id = db.start_run(cur, "incremental", params, replay_from.date())
        cur.execute("delete from gold.match_ratings where match_date >= %s", (replay_from.date(),))
        cur.execute("delete from gold.club_ratings where valid_from > %s", (replay_from.date(),))
        cur.execute("delete from gold.league_offsets where valid_from > %s", (replay_from.date(),))
        cur.execute("delete from gold.hfa_levels where valid_from > %s", (replay_from.date(),))

        rated, _ = engine.run(to_rate, engine.EloParams.from_config(cfg), initial_base=base, offsets=offsets,
                              hfa_state=hfa_state, played=played,
                              club_country=db.fetch_club_country(cur), membership=membership)
        per = engine.periods(rated, burn_in_until=cfg["elo"]["burn_in_until"])
        db.write_match_ratings(cur, rated, run_id, cfg["elo"]["burn_in_until"])
        db.write_club_ratings(cur, per, run_id)
        db.write_league_offsets(cur, engine.league_offsets(rated), run_id)
        db.write_hfa_levels(cur, engine.hfa_levels(rated), run_id)
        db.refresh_valid_to(cur)
        db.finish_run(cur, run_id, len(rated), rated["match_date"].max().date())
        db.refresh_serving(cur)
        conn.commit()
    log.info("incremental run %d: %d new/changed matches, re-rated %d from %s",
             run_id, len(changed), len(rated), replay_from.date())
    return run_id
