"""Fit league pooling and country start levels together. Objective: European
log loss over all seasons (cross-country evidence back to 1955) plus a smaller
weight on the modern Club Elo fit. Prints the best parameters."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from football_elo import calibrate as c, engine  # noqa: E402
from football_elo.config import load_config  # noqa: E402
from pool_experiment import summarize  # noqa: E402

NAMES = ["league_pool", "level_ESP", "level_GER", "level_ITA", "level_FRA", "foreign"]
W_RMSE = float(sys.argv[1]) if len(sys.argv) > 1 else 0.15

cfg = load_config()
pm = pd.read_parquet(cfg["paths"]["silver"] / "matches_prepared.parquet")
t = c.load_targets(cfg, cfg["elo"]["burn_in_until"])
base = engine.EloParams.from_config(cfg)
# model structure under test: dynamic home advantage and provisional ratings
from dataclasses import replace  # noqa: E402
base = replace(base, provisional_matches=40, provisional_k=2.0, hfa_eta=1.0, hfa_europe_separate=True, hfa_start=120.0)


def objective(x):
    p = c._apply(base, NAMES, x)
    s, cmp, r = c.evaluate(pm, t, p)
    e = r[r.comp_type == "europe"]
    ll_eu = engine.log_loss(e)
    debiased = s["rmse_debiased"]  # one overall offset is free (align_level)
    return ll_eu / 0.58 + W_RMSE * debiased / 25.0


# start from equal levels for every country (England's tier 1) and let the
# European evidence move them
eng_top = base.countries["ENG"]["start_ratings"][1]
x0 = np.array([0.25, eng_top, eng_top, eng_top, eng_top, eng_top - 250], dtype=float)
print("start", dict(zip(NAMES, x0)), flush=True)
res = minimize(objective, x0, method="Nelder-Mead",
               options={"maxiter": 300, "xatol": 1.0, "fatol": 1e-4, "initial_simplex": None})
best = c._apply(base, NAMES, res.x)
best = c.align_level(best, c.evaluate(pm, t, best)[0]["bias"])
s, b, r = summarize(cfg, pm, t, best)
print("x", dict(zip(NAMES, np.round(res.x, 3))))
print(json.dumps({"league_pool": best.league_pool,
                  "countries": {k: {"sr": {kk: round(vv) for kk, vv in v["start_ratings"].items()}, "nl": round(v["nonleague"])}
                                for k, v in best.countries.items()},
                  "foreign": round(best.foreign_start["default"])}))
print({k: round(float(v), 4) for k, v in s.items()})
print((b.pivot(index="decade", columns="c", values="mean") * 100).round(1).to_string())
