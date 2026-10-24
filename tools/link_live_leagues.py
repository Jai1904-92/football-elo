"""Link the club keys of the current-season league sources (ESPN ids,
football-data extra-league names) to canonical clubs.

The Wikipedia grids these leagues come from before have synthetic dates, so
fixtures are lined up on season and score instead of date (derive_aliases
does it on date):
1. Seeds: aliases the key already has (ESPN ids from UEFA games), else a
   unique normalised-name match among the canonical clubs of the same league
   season.
2. Votes: a source fixture and a Wikipedia fixture of the same season with
   the same score, where one side is already linked to the same club, vote
   for the other side. A key takes its top club with >= 3 votes and 3x the
   runner-up; repeated until nothing changes. A vote that contradicts a seed
   is reported.
3. Keys with no overlap (clubs promoted for the current season): a unique
   normalised-name match (else a unique prefix match) among every club of
   the country (successor states included), else none, so the build
   registers them as new clubs.

Report: data/silver/live_league_links.csv.

    python tools/link_live_leagues.py [--dry-run]
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_aliases import compatible, norm  # noqa: E402
from football_elo import sources  # noqa: E402
from football_elo.config import load_config  # noqa: E402
from football_elo.silver import SourceReader, apply_aliases  # noqa: E402


def live_sources(cfg: dict) -> dict[str, pd.DataFrame]:
    """Source -> its league rows, every season it has (for the overlap)."""
    bronze = cfg["paths"]["bronze"]
    extra = cfg["sources"]["football_data_extra"]
    return {"espn": sources.espn(bronze / "espn", {}, leagues=cfg["sources"]["espn"]["leagues"]),
            "football_data_extra": sources.football_data_extra(bronze / "football_data_extra", extra["files"], 0)}


def votes(src: pd.DataFrame, canon: pd.DataFrame, mapped: dict) -> pd.DataFrame:
    """(key, club, n): same season and score, the other side agreeing."""
    j = src.merge(canon, on=["season", "home_goals", "away_goals"], suffixes=("_s", "_c"))
    hm, am = j["home_club_s"].map(mapped), j["away_club_s"].map(mapped)
    p = pd.concat([j.loc[am.eq(j["away_club_c"]), ["home_club_s", "home_club_c"]].set_axis(["key", "club"], axis=1),
                   j.loc[hm.eq(j["home_club_c"]), ["away_club_s", "away_club_c"]].set_axis(["key", "club"], axis=1)])
    return p.value_counts().rename("n").reset_index()


def link(src: pd.DataFrame, canon: pd.DataFrame, seeds: dict, country_clubs: list[str]) -> pd.DataFrame:
    names = pd.concat([src[["home_club", "home_name", "season"]].set_axis(["key", "name", "season"], axis=1),
                       src[["away_club", "away_name", "season"]].set_axis(["key", "name", "season"], axis=1)])
    info = names.groupby("key").agg(name=("name", "last"), first=("season", "min"), last=("season", "max"))
    canon_seasons = pd.concat([canon[["home_club", "season"]].set_axis(["club", "season"], axis=1),
                               canon[["away_club", "season"]].set_axis(["club", "season"], axis=1)]).drop_duplicates()
    by_season = canon_seasons.groupby("season")["club"].agg(set).to_dict()
    mapped, how = {}, {}
    for key, row in info.iterrows():
        if key in seeds:
            mapped[key], how[key] = seeds[key], "alias"
            continue
        played = names.loc[names["key"] == key, "season"].unique()
        hits = {c for s in played for c in by_season.get(s, ()) if norm(c) == norm(row["name"])}
        if len(hits) == 1:
            mapped[key], how[key] = hits.pop(), "name"
    conflicts = {}
    for _ in range(10):
        v = votes(src, canon, mapped).sort_values("n", ascending=False)
        top = v.drop_duplicates("key").set_index("key")
        runner = v[~v.index.isin(v.drop_duplicates("key").index)].drop_duplicates("key").set_index("key")["n"]
        changed = False
        for key, r in top.iterrows():
            if r["n"] < 3 or r["n"] < 3 * runner.get(key, 0):
                continue
            if key in mapped and mapped[key] != r["club"]:
                conflicts[key] = r["club"]
                continue
            if key not in mapped:
                mapped[key], how[key], changed = r["club"], "fixtures", True
        if not changed:
            break
    support = votes(src, canon, mapped).set_index(["key", "club"])["n"]
    norm_index: dict = {}
    for c in country_clubs:
        norm_index.setdefault(norm(c), []).append(c)
    for key, row in info.iterrows():
        if key not in mapped:
            n = norm(row["name"])
            hits = norm_index.get(n, [])
            if not hits and len(n) >= 5:     # "Corvinul" -> Corvinul Hunedoara
                hits = [c for k, cs in norm_index.items() if k.startswith(n) for c in cs]
            if len(hits) == 1:
                mapped[key], how[key] = hits[0], "country name"
    out = info.reset_index()
    out["club"] = out["key"].map(mapped)
    out["how"] = out["key"].map(how)
    out["votes"] = [support.get((k, c), 0) for k, c in zip(out["key"], out["club"])]
    out["conflict"] = out["key"].map(conflicts)
    return out


def main(dry_run: bool) -> None:
    cfg = load_config()
    reader = SourceReader(cfg)
    aliases = pd.read_csv(cfg["aliases"], dtype=str)
    clubs = pd.read_parquet(cfg["paths"]["silver"] / "clubs.parquet").set_index("club")["country"]
    live = live_sources(cfg)
    report, rows = [], []
    for comp, spec in cfg["competitions"].items():
        for source in {w["source"] for w in spec["windows"]} & set(live):
            src = live[source]
            src = src[src["competition"] == comp].astype({"home_club": str, "away_club": str})
            if src.empty:
                continue
            canon = apply_aliases(reader.read("wikipedia", comp), aliases, "wikipedia")
            seeds = aliases[aliases["source"] == source].set_index("source_name")["club"].to_dict()
            country_clubs = [c for c, k in clubs.items() if compatible(k, spec["country"])]
            out = link(src, canon, seeds, country_clubs).assign(competition=comp, source=source)
            report.append(out)
            new = out[out["club"].notna() & ~out["key"].isin(seeds)]
            rows += [{"source": source, "source_name": k, "club": c} for k, c in zip(new["key"], new["club"])]
    rep = pd.concat(report, ignore_index=True)
    path = cfg["paths"]["silver"] / "live_league_links.csv"
    rep.to_csv(path, index=False)
    print(rep.groupby(["competition", "how"], dropna=False).size().unstack(fill_value=0))
    odd = rep[rep["conflict"].notna() | rep["club"].isna() | (rep["how"].isin(["name", "country name"]) & (rep["votes"] < 3))]
    if len(odd):
        print("review (conflicts, unlinked, name-only links with little fixture support):")
        print(odd[["competition", "source", "key", "name", "first", "last", "club", "how", "votes", "conflict"]]
              .to_string(index=False))
    dup = rep.dropna(subset=["club"])
    dup = dup[dup.duplicated(["source", "club"], keep=False)]
    if len(dup):
        print("several keys -> one club:")
        print(dup[["competition", "source", "key", "name", "club", "how", "votes"]].to_string(index=False))
    print(f"{len(rows)} new aliases; report in {path}")
    if rows and not dry_run:
        out = pd.concat([aliases, pd.DataFrame(rows)]).drop_duplicates(["source", "source_name"])
        out.to_csv(cfg["aliases"], index=False)


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
