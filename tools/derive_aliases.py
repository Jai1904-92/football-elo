"""Propose club aliases for Transfermarkt and ESPN (keyed by their club ids),
plus football-data names, by matching fixtures against already-canonical
results on (date +/- 1 day, score).

Source keys that never overlap canonical data become new canonical clubs
named after the source's display name. Existing rows in the aliases file
win; only missing keys are added. Review the printed low-confidence rows.

    python tools/derive_aliases.py            # add missing aliases
"""
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_elo import sources  # noqa: E402
from football_elo.config import load_config  # noqa: E402
from football_elo.silver import SourceReader, apply_aliases  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 400)


def sides(df, key_col="club"):
    """Long format: one row per (date, club, goals for, goals against, home?)."""
    h = df[["match_date", "home_club", "home_name", "home_goals", "away_goals", "home_country"]].set_axis(
        ["d", key_col, "name", "gf", "ga", "country"], axis=1).assign(home=True)
    a = df[["match_date", "away_club", "away_name", "away_goals", "home_goals", "away_country"]].set_axis(
        ["d", key_col, "name", "gf", "ga", "country"], axis=1).assign(home=False)
    return pd.concat([h, a], ignore_index=True)


def _join(src: pd.DataFrame, canon: pd.DataFrame) -> pd.DataFrame:
    """Source x canonical fixtures within a day of each other with the same score."""
    frames = [src.merge(canon.assign(d=canon["match_date"] + pd.Timedelta(days=shift)),
                        on=["d", "home_goals", "away_goals"], suffixes=("_s", "_c"))
              for shift in (-1, 0, 1)]
    return pd.concat(frames, ignore_index=True)


def _best(pairs: pd.DataFrame) -> pd.DataFrame:
    cnt = pairs.value_counts(["key", "club"]).reset_index(name="n").sort_values("n", ascending=False)
    first = cnt.drop_duplicates("key")
    second = cnt[~cnt.index.isin(first.index)].drop_duplicates("key").set_index("key")["n"]
    first = first.assign(runner_up=first["key"].map(second).fillna(0))
    return first


def match_keys(src: pd.DataFrame, canon: pd.DataFrame) -> pd.DataFrame:
    """Map source keys to canonical clubs in two passes.

    Pass 1 lines fixtures up on date (+/- 1 day) and score only, and keeps a
    key's top candidate when it clearly dominates (>= 3x the runner-up).
    Pass 2 repeats using only line-ups where the opponent is already mapped
    and matches, which resolves clubs with few fixtures. It iterates until
    nothing changes."""
    s = src.assign(d=src["match_date"])
    j = _join(s, canon)
    pairs = pd.concat([j[["home_club_s", "home_club_c"]].set_axis(["key", "club"], axis=1),
                       j[["away_club_s", "away_club_c"]].set_axis(["key", "club"], axis=1)])
    b = _best(pairs)
    mapped = b[(b["n"] >= 5) & (b["n"] >= 3 * b["runner_up"])].set_index("key")["club"]
    for _ in range(5):
        hm, am = j["home_club_s"].map(mapped), j["away_club_s"].map(mapped)
        # a line-up counts for the home key if the away side agrees, and vice versa
        p_home = j.loc[am.eq(j["away_club_c"]), ["home_club_s", "home_club_c"]].set_axis(["key", "club"], axis=1)
        p_away = j.loc[hm.eq(j["home_club_c"]), ["away_club_s", "away_club_c"]].set_axis(["key", "club"], axis=1)
        b2 = _best(pd.concat([p_home, p_away]))
        new = b2[(b2["n"] >= 1) & (b2["n"] > b2["runner_up"])].set_index("key")["club"]
        merged = new.combine_first(mapped)
        if merged.equals(mapped):
            break
        mapped = merged
    # one canonical club per source key and (mostly) one key per club
    counts = pairs.value_counts(["key", "club"])
    out = mapped.rename("club").reset_index().rename(columns={"index": "key"})
    out["n"] = [counts.get((k, c), 0) for k, c in zip(out["key"], out["club"])]
    return out


def propose(source: str, src: pd.DataFrame, canon: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    best = match_keys(src, canon)
    names = sides(src, "key").groupby("key").agg(name=("name", "last"), country=("country", "first"),
                                                  games=("d", "size"))
    out = names.join(best.set_index("key"), how="left").reset_index()
    out["new"] = out["club"].isna()
    out.loc[out["new"], "club"] = out.loc[out["new"], "name"]
    out["share"] = out["n"] / out["games"]
    have = set(existing.loc[existing["source"] == source, "source_name"])
    return out[~out["key"].isin(have)]


STOP = r"\b(fc|cf|ac|afc|sc|fk|sk|cd|sv|bk|kv|rc|as|ss|ssc|club|calcio|the|football|futbol|clube|kf|nk|pfc)\b"


def norm(name: str) -> str:
    """Accent-free, lower case, without club-type words. Digits are kept so
    e.g. CSKA Sofia and CSKA 1948 Sofia stay apart."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"^1\.\s*", "", s)
    s = re.sub(STOP, " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


# Countries treated as one when matching names: successor states, and the
# British Isles (Welsh clubs play in the English league).
COUNTRY_GROUP = {}
for group in (["YUG", "SCG", "SRB", "CRO", "BIH", "SVN", "MKD", "MNE", "KOS"],
              ["TCH", "CZE", "SVK"],
              ["URS", "CIS", "RUS", "UKR", "BLR", "GEO", "ARM", "AZE", "KAZ", "LVA", "LTU", "EST", "MDA"],
              ["GER", "GDR", "SAA"],
              ["ENG", "WAL", "SCO", "NIR", "IRL"]):
    for code in group:
        COUNTRY_GROUP[code] = group[0]


def compatible(c1, c2) -> bool:
    if not isinstance(c1, str) or not isinstance(c2, str):
        return True
    return COUNTRY_GROUP.get(c1, c1) == COUNTRY_GROUP.get(c2, c2)


# Different clubs whose normalised names collide.
KEEP_APART = {"Riga FC", "Rīga", "Ranger's", "Rangers"}


def consolidate(new: pd.DataFrame, preexisting: set, countries: dict) -> pd.DataFrame:
    """Merge clubs created in this run into an equivalent club (same
    normalised name, compatible country). Pre-existing canonical clubs are
    never merged with each other."""
    created = set(new.loc[new["new"], "club"])
    groups: dict = {}
    for club in sorted(created | preexisting):
        key = norm(re.sub(r" \((\w+|\?)\)$", "", club))
        if len(key) >= 2 and club not in KEEP_APART:
            groups.setdefault(key, []).append(club)
    remap = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        # target: a pre-existing club if any, else the one with most aliases
        pre = [m for m in members if m in preexisting]
        target = pre[0] if len(pre) == 1 else None
        if target is None and not pre:
            target = max(members, key=lambda m: (new["club"] == m).sum())
        if target is None:
            continue
        for m in members:
            short = len(norm(target)) < 4  # short names need both countries known and equal
            ok = (countries.get(m) is not None and countries.get(m) == countries.get(target)) if short                 else compatible(countries.get(m), countries.get(target))
            if m != target and m in created and ok:
                remap[m] = target
    if remap:
        print(f"consolidated {len(remap)} clubs: {dict(list(remap.items())[:15])}")
    new = new.copy()
    new["club"] = new["club"].replace(remap)
    return new


NAME_PREFERENCE = ["espn", "datarozhlas", "transfermarkt", "football_data"]  # short names first


def main():
    cfg = load_config()
    reader = SourceReader(cfg)
    alias_path = cfg["aliases"]
    aliases = pd.read_csv(alias_path, dtype=str)

    leagues = [c for c, spec in cfg["competitions"].items() if spec["type"] == "league"]
    canon = pd.concat([reader.read("engsoccerdata", c)
                       for c in leagues + ["ENG-FAC", "ENG-LC", "ENG-PO", "UCL"]], ignore_index=True)
    canon = apply_aliases(canon, aliases, "engsoccerdata")
    canonical_names = set(canon["home_club"]) | set(canon["away_club"]) | set(aliases["club"])
    preexisting = set(canonical_names)

    def idx_countries(frame):
        long = pd.concat([frame[["home_club", "home_country"]].set_axis(["club", "country"], axis=1),
                          frame[["away_club", "away_country"]].set_axis(["club", "country"], axis=1)])
        return long.dropna().groupby("club")["country"].first().to_dict()

    def name_index(frame):
        long = pd.concat([frame[["home_club", "home_country"]].set_axis(["club", "country"], axis=1),
                          frame[["away_club", "away_country"]].set_axis(["club", "country"], axis=1)])
        country = long.dropna().groupby("club")["country"].first()
        idx = {}
        for club in long["club"].dropna().unique():
            key = norm(club)
            if len(key) >= 4:
                idx.setdefault(key, []).append((club, country.get(club)))
        return idx
    bronze = cfg["paths"]["bronze"]

    # sources in matching order; each is matched against everything mapped so far
    # top flights are read for matching only
    tm_comps = dict(cfg["sources"]["transfermarkt"]["competitions"], **cfg["sources"]["transfermarkt"]["match_only"])
    srcs = [
        ("football_data", sources.football_data(bronze / "football_data",
                                                cfg["sources"]["football_data"]["divisions"])),
        ("datarozhlas", sources.datarozhlas(bronze / "datarozhlas" / "matches.csv",
                                            cfg["sources"]["datarozhlas"]["competitions"])),
        ("transfermarkt", sources.transfermarkt(bronze / "transfermarkt", tm_comps)),
        # league slugs read in full (not just play-offs) for more overlap
        ("espn", sources.espn(bronze / "espn", cfg["sources"]["espn"]["slugs"], playoffs_only=False)),
    ]
    added = []
    for name, src in srcs:
        prop = propose(name, src, canon, aliases)
        # a "new" club whose normalised name and country match an existing
        # canonical club is that club (too few fixtures to line up)
        idx = name_index(canon)
        merged = 0
        for i in prop.index[prop["new"]]:
            hits = [c for c, ctry in idx.get(norm(prop.at[i, "name"]), [])
                    if compatible(ctry, prop.at[i, "country"])]
            if len(hits) == 1:
                prop.at[i, "club"], prop.at[i, "new"] = hits[0], False
                merged += 1
        clash = prop["new"] & prop["club"].isin(canonical_names)
        prop.loc[clash, "club"] = [f"{c} ({k if isinstance(k, str) else '?'})"
                                   for c, k in zip(prop.loc[clash, "club"], prop.loc[clash, "country"])]
        print(f"{name}: {merged} merged on normalised name")
        canonical_names |= set(prop["club"])
        prop["source"] = name
        added.append(prop)
        known = pd.concat([aliases[aliases["source"] == name].set_index("source_name")["club"],
                           prop.set_index("key")["club"]])
        mapped = src.assign(home_club=src["home_club"].map(known), away_club=src["away_club"].map(known))
        canon = pd.concat([canon, mapped.dropna(subset=["home_club", "away_club"])], ignore_index=True)
        log_line = f"{name}: {len(prop)} keys, {int(prop['new'].sum())} new clubs"
        print(log_line)

    new = pd.concat(added, ignore_index=True)

    # New clubs are named after the shortest-style source name available
    created = set(new.loc[new["new"], "club"])
    rename = {}
    for club, grp in new[new["club"].isin(created)].groupby("club"):
        for src_name in NAME_PREFERENCE:
            cand = grp.loc[grp["source"] == src_name, "name"]
            if len(cand):
                nice = cand.iloc[0]
                if nice != club and nice not in canonical_names and nice not in rename.values():
                    rename[club] = nice
                break
    new["club"] = new["club"].replace(rename)
    countries = new.dropna(subset=["country"]).groupby("club")["country"].first().to_dict()
    countries.update(idx_countries(canon))
    new = consolidate(new, preexisting, countries)

    review = new[(new["share"] < 0.5) | new["new"]]
    review[["source", "key", "name", "country", "games", "club", "n", "share", "new"]].sort_values(
        ["source", "new", "share"]).to_csv(cfg["paths"]["silver"] / "alias_review.csv", index=False)
    print(f"adding {len(new)} aliases ({int(new['new'].sum())} new clubs, {len(rename)} renamed); "
          f"review list in data/silver/alias_review.csv")
    out = pd.concat([aliases, new.rename(columns={"key": "source_name"})[["source", "source_name", "club"]]])
    out.to_csv(alias_path, index=False)


if __name__ == "__main__":
    main()
