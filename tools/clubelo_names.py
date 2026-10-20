"""Map Club Elo names (Elhabr CSV + Wayback captures) to canonical names, for
calibration. Club Elo's rating periods start the day after each match, so a
Club Elo club lines up with the canonical club (same country) whose match
dates best match its rating-change dates. Existing `clubelo` alias rows win.

    python tools/clubelo_names.py ENG ESP GER ITA FRA
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_aliases import compatible, norm  # noqa: E402
from football_elo.config import load_config  # noqa: E402


def main(countries: list[str]):
    cfg = load_config()
    matches = pd.read_parquet(cfg["paths"]["silver"] / "matches.parquet")
    clubs = pd.read_parquet(cfg["paths"]["silver"] / "clubs.parquet").set_index("club")["country"]
    m = matches[matches["match_date"] >= "2007-07-01"]
    ours = pd.concat([m[["match_date", "home_club"]].set_axis(["d", "club"], axis=1),
                      m[["match_date", "away_club"]].set_axis(["d", "club"], axis=1)]).drop_duplicates()
    ours["country"] = ours["club"].map(clubs)

    cal = cfg["paths"]["calibration"]
    eh = pd.read_csv(cal / "clubelo-club-rankings.csv", usecols=["Club", "Country", "From"])
    wb = pd.concat([pd.read_csv(p, usecols=["Club", "Country", "From"]) for p in (cal / "wayback").glob("table_*.csv")])
    ce = pd.concat([eh, wb])
    ce = ce[ce["Country"].isin(countries)].drop_duplicates()
    ce["d"] = pd.to_datetime(ce["From"]) - pd.Timedelta(days=1)

    j = ce.merge(ours, on="d")
    j = j[[compatible(a, b) for a, b in zip(j["Country"], j["country"])]]
    # Jaccard similarity of the two date sets: clubs in one league share
    # weekend dates, so raw overlap counts don't separate them; the full
    # fixture rhythm (midweek games, gaps) does
    cnt = j.groupby(["Club", "club"]).size().reset_index(name="n")
    size_ce = ce.groupby("Club")["d"].nunique()
    recent = ce[ce["d"] >= "2023-01-01"]  # Elhabr's continuous snapshots
    j = j[j["d"] >= "2023-01-01"]
    cnt = j.groupby(["Club", "club"]).size().reset_index(name="n")
    size_ce = recent.groupby("Club")["d"].nunique()
    window = ours[ours["d"].between(recent["d"].min(), recent["d"].max())]
    size_ours = window.groupby("club")["d"].nunique()
    cnt["jac"] = cnt["n"] / (cnt["Club"].map(size_ce) + cnt["club"].map(size_ours) - cnt["n"])
    cnt = cnt.sort_values("jac", ascending=False)
    # assign clear winners, remove them from the pool, repeat: clubs that only
    # play at weekends look alike until their rivals are taken
    mapped = pd.Series(dtype=object)
    pool = cnt
    while True:
        first = pool.drop_duplicates("Club")
        second = pool[~pool.index.isin(first.index)].drop_duplicates("Club").set_index("Club")["jac"]
        first = first.assign(runner_up=first["Club"].map(second).fillna(0))
        ok = (first["n"] >= 5) & (first["jac"] >= 0.3) & (first["jac"] >= 1.2 * first["runner_up"])
        won = first[ok].drop_duplicates("club").set_index("Club")["club"]
        if won.empty:
            break
        mapped = pd.concat([mapped, won])
        pool = pool[~pool["Club"].isin(won.index) & ~pool["club"].isin(won.values)]

    names = ce.drop_duplicates("Club")[["Club", "Country"]].reset_index(drop=True)
    names["club"] = names["Club"].map(mapped).astype(object)
    names["how"] = names["club"].notna().map({True: "dates", False: None}).astype(object)
    for i in names.index[names["club"].isna()]:  # too few dates: same-country name match
        hits = [c for c, k in clubs.items() if norm(c) == norm(names.at[i, "Club"]) and compatible(k, names.at[i, "Country"])]
        if len(hits) == 1:
            names.at[i, "club"], names.at[i, "how"] = hits[0], "name"

    aliases = pd.read_csv(cfg["aliases"], dtype=str)
    have = set(aliases.loc[aliases["source"] == "clubelo", "source_name"])
    new = names[names["club"].notna() & ~names["Club"].isin(have)]
    print(names.groupby(["Country", "how"], dropna=False).size().unstack(fill_value=0))
    unmatched = names[names["club"].isna()]
    print(f"unmatched ({len(unmatched)}):", unmatched[["Club", "Country"]].values.tolist())
    print(f"adding {len(new)} clubelo aliases")
    out = pd.concat([aliases, pd.DataFrame({"source": "clubelo", "source_name": new["Club"], "club": new["club"]})])
    out.to_csv(cfg["aliases"], index=False)
    names.to_csv(cfg["paths"]["silver"] / "clubelo_name_links.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1:] or ["ENG", "ESP", "GER", "ITA", "FRA"])
