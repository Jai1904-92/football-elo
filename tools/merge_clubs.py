"""Merge duplicate canonical clubs: every alias row pointing at a duplicate is
pointed at the club it duplicates, and a source that names the duplicate
directly (no alias row: its own key is the club name) gets one.

    python tools/merge_clubs.py "Sparta Prague=Sparta Praha" "Rijeka=HNK Rijeka"
    python tools/merge_clubs.py --file pairs.csv      # columns: merge, into

Uses the matches of the last build (data/silver) to see which sources name
each duplicate. Rewrites config/club_aliases.csv.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_elo.config import load_config  # noqa: E402


def merge(pairs: dict[str, str], aliases: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """pairs: duplicate -> club. Returns the new alias table."""
    into = {d: c for d, c in pairs.items() if d != c}
    for d in into:                      # chains: a -> b -> c
        while into[d] in into:
            into[d] = into[into[d]]
    out = aliases.assign(club=aliases["club"].replace(into))
    named = set(zip(out["source"], out["source_name"]))
    extra = []
    for side in ("home", "away"):
        part = matches[matches[f"{side}_club"].isin(into)][["source", f"{side}_club"]].drop_duplicates()
        for source, dup in part.itertuples(index=False):
            if (source, dup) not in named:
                extra.append({"source": source, "source_name": dup, "club": into[dup]})
                named.add((source, dup))
    return pd.concat([out, pd.DataFrame(extra, columns=out.columns)], ignore_index=True)


if __name__ == "__main__":
    cfg = load_config()
    args = sys.argv[1:]
    if args[:1] == ["--file"]:
        df = pd.read_csv(args[1], dtype=str)
        pairs = dict(zip(df["merge"], df["into"]))
    else:
        pairs = dict(a.split("=", 1) for a in args)
    aliases = pd.read_csv(cfg["aliases"], dtype=str)
    matches = pd.read_parquet(cfg["paths"]["silver"] / "matches.parquet")
    new = merge(pairs, aliases, matches)
    new.to_csv(cfg["aliases"], index=False)
    print(f"merged {len(pairs)} clubs; {len(new) - len(aliases)} alias rows added")
