"""Link engsoccerdata league names for newly added countries to canonical
names clubs already have (from European data), as `engsoccerdata` alias rows.

1. Transfermarkt top-flight fixtures (2012-) are lined up with engsoccerdata
   league fixtures, giving Transfermarkt id -> league name. Where that id
   already maps to a canonical club, the league name becomes an alias of it.
2. League names with no Transfermarkt overlap fall back to a normalised-name
   match against canonical clubs of the same country.

When the linked canonical name was invented from Wikipedia/Transfermarkt
(it is not an engsoccerdata name), the club is renamed to its league name
everywhere in the aliases file instead, e.g. "Frankfurter SG Eintracht" ->
"Eintracht Frankfurt". engsoccerdata European Cup names are kept.

    python tools/link_league_names.py ESP GER ITA FRA
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_aliases import compatible, match_keys, norm  # noqa: E402
from football_elo import sources  # noqa: E402
from football_elo.config import load_config  # noqa: E402
from football_elo.silver import SourceReader  # noqa: E402


def main(countries: list[str]):
    cfg = load_config()
    reader = SourceReader(cfg)
    aliases = pd.read_csv(cfg["aliases"], dtype=str)
    clubs = pd.read_parquet(cfg["paths"]["silver"] / "clubs.parquet").set_index("club")["country"]
    tm_ids = aliases[aliases["source"] == "transfermarkt"].set_index("source_name")["club"]
    match_only = cfg["sources"]["transfermarkt"]["match_only"]
    tm = sources.transfermarkt(cfg["paths"]["bronze"] / "transfermarkt", match_only)

    rows, report = [], []
    for country in countries:
        comp = f"{country}-L"
        es = reader.read("engsoccerdata", comp)
        names = sorted(set(es["home_club"]) | set(es["away_club"]))
        tm_c = tm[tm["competition"] == comp]
        linked = match_keys(tm_c, es[es["match_date"] >= "2012-07-01"])  # key = TM id, club = es name
        linked["canonical"] = linked["key"].map(tm_ids)
        by_name = linked.dropna(subset=["canonical"]).groupby("club")["canonical"].agg(
            lambda s: s.value_counts().index[0])
        country_clubs = [c for c, k in clubs.items() if compatible(k, country)]
        norm_index: dict = {}
        for c in country_clubs:
            norm_index.setdefault(norm(c), []).append(c)
        for name in names:
            how, target = None, None
            if name in by_name.index:
                how, target = "transfermarkt", by_name[name]
            else:
                hits = [c for c in norm_index.get(norm(name), []) if c != name]
                if len(hits) == 1 and name not in clubs.index:
                    how, target = "name", hits[0]
            if target and target != name:
                rows.append({"source": "engsoccerdata", "source_name": name, "club": target})
            report.append({"country": country, "league_name": name, "canonical": target or name, "how": how})

    # rename invented canonical names to the (most used) league name
    champs = reader.read("engsoccerdata", "UCL")
    es_names = set(champs["home_club"]) | set(champs["away_club"])
    for comp in ("ENG-L", "ENG-FAC", "ENG-LC", "ENG-PO"):
        e = reader.read("engsoccerdata", comp)
        es_names |= set(e["home_club"]) | set(e["away_club"])
    links = pd.DataFrame(rows, columns=["source", "source_name", "club"])
    rename = {}
    if len(links):
        usage = {}
        for country in countries:
            e = reader.read("engsoccerdata", f"{country}-L")
            usage.update(pd.concat([e["home_club"], e["away_club"]]).value_counts().to_dict())
        for target, grp in links.groupby("club"):
            if target in es_names:
                continue
            best = max(grp["source_name"], key=lambda n: usage.get(n, 0))
            # if `best` is already a canonical club this merges a duplicate
            # (e.g. the 1960 European Cup's "Eintracht Frankfurt" and a
            # Wikipedia-named "Frankfurter SG Eintracht"); only same country
            if best not in clubs.index or compatible(clubs.get(best), clubs.get(target)):
                rename[target] = best
        if rename:
            print(f"renaming {len(rename)} canonical clubs to league names:", rename)
            aliases["club"] = aliases["club"].replace(rename)
            links["club"] = links["club"].replace(rename)
            links = links[links["source_name"] != links["club"]]
            rows = links.to_dict("records")
            for r in report:
                r["canonical"] = rename.get(r["canonical"], r["canonical"])
    rep = pd.DataFrame(report)
    out_path = cfg["paths"]["silver"] / "league_name_links.csv"
    rep.to_csv(out_path, index=False)
    print(rep.groupby(["country", "how"], dropna=False).size().unstack(fill_value=0))
    new = pd.DataFrame(rows)
    have = set(zip(aliases["source"], aliases["source_name"]))
    new = new[[(s, n) not in have for s, n in zip(new["source"], new["source_name"])]] if len(new) else new
    print(f"adding {len(new)} engsoccerdata aliases; full report in {out_path}")
    if len(new):
        print(new.to_string(index=False))
    if len(new) or rename:
        out = pd.concat([aliases, new])
        out = out[~((out["source"] == "engsoccerdata") & (out["source_name"] == out["club"]))]  # self-maps
        out.to_csv(cfg["aliases"], index=False)


if __name__ == "__main__":
    main(sys.argv[1:] or ["ESP", "GER", "ITA", "FRA"])
