"""Compare league-pooling strengths: European bias by country and decade,
log loss, and fit to Club Elo. Run from the project root."""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_elo import calibrate as c, engine  # noqa: E402
from football_elo.config import load_config  # noqa: E402

MODS = ["ENG", "ESP", "GER", "ITA", "FRA", "POR", "NED", "SCO", "BEL", "TUR", "GRE"]


def europe_bias(r: pd.DataFrame) -> pd.DataFrame:
    e = r[r.comp_type == "europe"].copy()
    e["res"] = np.where(e.home_goals > e.away_goals, 1, np.where(e.home_goals == e.away_goals, .5, 0)) - e.home_win_exp
    e["decade"] = (e.season // 10) * 10
    long = pd.concat([e[["decade", "home_country", "res"]].set_axis(["decade", "c", "res"], axis=1),
                      e[["decade", "away_country", "res"]].assign(res=-e.res).set_axis(["decade", "c", "res"], axis=1)])
    long["c"] = long.c.where(long.c.isin(MODS), "other")
    return long.groupby(["c", "decade"]).res.agg(["mean", "count"]).reset_index()


def summarize(cfg, pm, t, p):
    s, cmp, r = c.evaluate(pm, t, p)
    b = europe_bias(r)
    b = b[b.decade >= 1960]
    bias_rms = np.sqrt(np.average(b["mean"] ** 2, weights=b["count"])) * 100
    x = r[r.match_date >= "1965-07-01"]
    return {"rmse": s["rmse"], "spear": s["mean_spearman"], "eu_bias_rms_pp": bias_rms,
            "ll_league": engine.log_loss(x[x.comp_type == "league"]),
            "ll_europe": engine.log_loss(x[x.comp_type == "europe"])}, b, r


if __name__ == "__main__":
    cfg = load_config()
    pm = pd.read_parquet(cfg["paths"]["silver"] / "matches_prepared.parquet")
    t = c.load_targets(cfg, cfg["elo"]["burn_in_until"])
    base = engine.EloParams.from_config(cfg)
    rows = []
    for lam in [float(v) for v in (sys.argv[1:] or [0, 0.05, 0.1, 0.2, 0.3, 0.5])]:
        p = replace(base, league_pool=lam)
        s, b, r = summarize(cfg, pm, t, p)
        p = c.align_level(p, c.evaluate(pm, t, p)[0]["bias"])
        s, b, r = summarize(cfg, pm, t, p)
        rows.append({"pool": lam, **{k: round(v, 4) for k, v in s.items()}})
        print((b.pivot(index="decade", columns="c", values="mean") * 100).round(1).to_string(), flush=True)
        print(rows[-1], flush=True)
    print(pd.DataFrame(rows).to_string())
