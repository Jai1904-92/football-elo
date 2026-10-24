"""CLI: python -m football_elo <command>

  build       fetch sources, rebuild silver + gold locally (parquet), score calibration
  load        build, then replace everything in Supabase (full run)
  update      weekly incremental update against Supabase
  validate    compare engsoccerdata vs football-data league results where both exist
  calibrate   score current config against Club Elo; --fit PARAM... to re-fit parameters
  export      write the static JSON snapshot for the site (web/public/data)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from . import calibrate, engine, export, pipeline, silver
from .config import load_config


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="football_elo", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "load", "update", "validate", "calibrate", "export"])
    ap.add_argument("--config", help="path to config yaml (default config/elo.yaml)")
    ap.add_argument("--no-fetch", action="store_true", help="use cached bronze files")
    ap.add_argument("--fit", nargs="*", metavar="PARAM",
                    help="calibrate: parameters to fit, e.g. k hfa tier_gap foreign k_cup k_europe "
                         "(default: k_cup k_europe foreign)")
    ap.add_argument("--out", help="export: output folder (default web/public/data)")
    ap.add_argument("--objective", default="rmse", help="calibrate --fit objective (rmse, rmse_shape, ...)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    pd.set_option("display.width", 200)

    if args.command == "build":
        pipeline.build_local(cfg, fetch=not args.no_fetch)
    elif args.command == "load":
        pipeline.full_load(cfg, fetch=not args.no_fetch)
    elif args.command == "export":
        export.export(Path(args.out)) if args.out else export.export()
    elif args.command == "update":
        pipeline.incremental_update(cfg)
    elif args.command == "validate":
        issues = silver.validate_overlap(cfg)
        out = cfg["paths"]["silver"] / "overlap_issues.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        issues.to_csv(out, index=False)
        print(issues.groupby(["competition", "issue"]).size().unstack(1).fillna(0).astype(int).to_string())
        print(f"\n{len(issues)} issues written to {out}")
    elif args.command == "calibrate":
        built = pipeline.build_local(cfg, fetch=not args.no_fetch)
        print(built["scores"].round(3).to_string())
        if args.fit is not None:
            names = args.fit or ["k_cup", "k_europe", "foreign"]
            targets = calibrate.load_targets(cfg, cfg["elo"]["burn_in_until"])
            params = engine.EloParams.from_config(cfg)
            prepared = engine.prepare(built["matches"], params, built["club_seasons"])
            best, s = calibrate.fit(prepared, targets, params, names, objective=args.objective)
            print("\nfitted:", best)
            print({k: round(v, 3) for k, v in s.items()})
            print("Copy the values you want into config/elo.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
