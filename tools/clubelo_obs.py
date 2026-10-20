"""Build per-match Club Elo observations (pre/post ratings for both clubs)
from the Elhabr CSV, for reverse-engineering and calibration."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_elo.config import load_config
from football_elo.silver import build_matches


def clubelo_periods(cfg):
    cal = cfg["paths"]["calibration"]
    eh = pd.read_csv(cal / "clubelo-club-rankings.csv", usecols=["Club", "Country", "Elo", "From", "To"])
    eh = eh[eh.Country == "ENG"].drop(columns="Country").drop_duplicates(["Club", "From"])
    a = pd.read_csv(cfg["aliases"])
    a = a[a.source == "clubelo"].set_index("source_name").club
    eh["club"] = eh.Club.map(a)
    eh["From"] = pd.to_datetime(eh.From); eh["To"] = pd.to_datetime(eh.To)
    return eh.sort_values(["club", "From"])


def observations(cfg):
    p = clubelo_periods(cfg)
    m = build_matches(cfg)
    m = m[(m.match_date > p.From.min()) & (m.match_date < p.To.max())]
    def rating_at(side, col, when):
        x = m[["match_id", side]].assign(t=when).sort_values("t")
        r = pd.merge_asof(x, p[["club", "From", "Elo"]].sort_values("From"), left_on="t", right_on="From",
                          left_by=side, right_by="club", direction="backward")
        return r.set_index("match_id").Elo.rename(col)
    for side, s in (("home_club", "h"), ("away_club", "a")):
        m = m.join(rating_at(side, f"pre_{s}", m.match_date - pd.Timedelta(days=0)), on="match_id")
        m = m.join(rating_at(side, f"post_{s}", m.match_date + pd.Timedelta(days=1)), on="match_id")
    # pre: the period covering the match day must end on the match day
    return m.dropna()


if __name__ == "__main__":
    cfg = load_config()
    o = observations(cfg)
    o.to_csv(cfg["paths"]["calibration"] / "clubelo_match_obs.csv", index=False)
    print(len(o)); print(o.head().to_string())
