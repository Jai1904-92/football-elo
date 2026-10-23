"""Coverage of the Wikipedia domestic-cup pages, per cup and season.

For each page: matches kept per layout, clubs, rounds, the share with a
printed date, and whether the late rounds are complete (ties found against
the number a knockout needs: final 1, semi-finals 2, quarter-finals 4,
"round of N" N/2). Seasons the current build already holds from another
source (Transfermarkt / ESPN, 2012/13 on) show that count for comparison.

    python tools/cup_coverage.py            # all cups in config
    python tools/cup_coverage.py ESP-CDR    # one cup

Writes data/silver/cup_coverage.csv and prints a summary by cup and decade.
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_elo import wikicups  # noqa: E402
from football_elo.config import load_config  # noqa: E402

EXPECTED = [(re.compile(r"^finals?$", re.I), 1), (re.compile(r"^semi[- ]?finals?$", re.I), 2),
            (re.compile(r"^quarter[- ]?finals?$", re.I), 4)]


def expected_ties(rnd: str) -> int | None:
    for pat, n in EXPECTED:
        if pat.match(rnd.strip()):
            return n
    m = re.match(r"^(?:round|last) of (\d+)$", rnd.strip(), re.I)
    return int(m.group(1)) // 2 if m else None


def page_row(text: str, season: int) -> dict:
    rows = wikicups.parse_page(text, season)
    df = pd.DataFrame(rows)
    out = {"matches": len(rows)}
    for fmt in wikicups.PRIORITY:
        out[fmt] = int((df["fmt"] == fmt).sum()) if len(df) else 0
    if not len(df):
        return dict(out, clubs=0, rounds=0, dated=0.0, final=False, semis=0, quarters=0, late_complete=False,
                    first_round="")
    main = df[df["slot"] == df["round"]]               # replays and second-leg slots aside
    ties = main.assign(pair=main.apply(lambda r: frozenset((r["home"], r["away"])), axis=1)) \
               .groupby("round", sort=False)["pair"].nunique()
    found = {}
    for rnd, n in ties.items():
        e = expected_ties(rnd)
        if e in (1, 2, 4):
            found[e] = max(found.get(e, 0), n)
    return dict(out, clubs=len(set(df["home"]) | set(df["away"])), rounds=len(ties),
                dated=round(df["date"].notna().mean(), 2), final=found.get(1, 0) >= 1, semis=found.get(2, 0),
                quarters=found.get(4, 0),
                late_complete=found.get(1, 0) >= 1 and found.get(2, 0) >= 2 and found.get(4, 0) >= 4,
                first_round=ties.index[0])


def main(only: list[str]) -> None:
    cfg = load_config()
    bronze = cfg["paths"]["bronze"]
    try:
        built = pd.read_parquet(cfg["paths"]["silver"] / "matches.parquet", columns=["competition", "season"])
        existing = built.groupby(["competition", "season"]).size()
    except (FileNotFoundError, KeyError):
        existing = pd.Series(dtype=int)
    rows = []
    for comp, specs in cfg["sources"]["wikipedia"]["cups"].items():
        if only and comp not in only:
            continue
        folders = {s["folder"] for s in specs}
        seasons = sorted({y for s in specs for y in range(s["seasons"][0], s["seasons"][1] + 1)})
        for season in range(1955, max(seasons) + 1):
            path = next((bronze / "wikipedia" / f / f"{season}.txt" for f in folders
                         if (bronze / "wikipedia" / f / f"{season}.txt").exists()), None)
            row = {"competition": comp, "season": season, "page": path is not None}
            if path is not None:
                text = path.read_text(encoding="utf-8")
                row["final_transcluded"] = bool(wikicups.transcluded(text))
                row.update(page_row(wikicups.expand(text, path.parent / "transcluded"), season))
            row["existing"] = int(existing.get((comp, season), 0))
            rows.append(row)
    df = pd.DataFrame(rows)
    out = cfg["paths"]["silver"] / "cup_coverage.csv"
    df.to_csv(out, index=False)
    df["decade"] = df["season"] // 10 * 10
    p = df[df["page"]]
    summary = p.groupby(["competition", "decade"]).agg(
        pages=("season", "size"), matches=("matches", "sum"), per_season=("matches", "median"),
        final=("final", "sum"), late_complete=("late_complete", "sum"), dated=("dated", "mean"),
        box=("box", "sum"), oneleg=("oneleg", "sum"), twoleg=("twoleg", "sum"), table=("table", "sum"),
        bracket=("bracket", "sum"))
    summary["dated"] = summary["dated"].round(2)
    missing = df[~df["page"]].groupby("competition")["season"].apply(
        lambda s: ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in _runs(list(s))))
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 500)
    print(summary.to_string())
    print("\nSeasons without a page (from 1955/56):")
    print(missing.to_string())
    print(f"\n{int(p['matches'].sum())} matches on {len(p)} pages; wrote {out}")


def _runs(xs: list[int]) -> list[tuple[int, int]]:
    out = []
    for x in xs:
        if out and out[-1][1] == x - 1:
            out[-1] = (out[-1][0], x)
        else:
            out.append((x, x))
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
