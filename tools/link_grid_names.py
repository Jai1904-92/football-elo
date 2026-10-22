"""Link club names from date-less league sources (RSSSF pages, Wikipedia
grids) to canonical clubs, as alias rows for that source.

Synthetic dates rule out matching on date, so fixtures are matched within a
season instead: a source club and a canonical club agree on a fixture when
they hosted (or visited) the same opponent with the same score. Seeds are
names that normalise to a canonical club of the same country seen that
season; links then spread through opponents already linked, with votes
pooled over all seasons. The source's tier-1 sections overlap engsoccerdata,
which links every club that ever played in the top flight; football-data
seasons link later second-tier clubs.

Keys left over are matched on (loosely) normalised name against the
country's canonical clubs; abbreviations ("Salernit.") and typos ("HHaarlem")
of a known club or a regular key are folded into it; the rest become new
clubs named as the source shows them. Keys seen only in tier-1 sections are
left unlinked (those sections are read for linking only, never rated).

    python tools/link_grid_names.py rsssf ITA-L NED-L
    python tools/link_grid_names.py wikipedia ESP-L

Uses the canonical matches of the last build (data/silver). Writes new rows
to config/club_aliases.csv (existing rows win) and a review list to
data/silver/grid_alias_review_<source>.csv.
"""
import difflib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_aliases import norm  # noqa: E402
from football_elo.config import load_config  # noqa: E402
from football_elo.silver import SourceReader  # noqa: E402

# Hand links, checked against club histories, for spellings the rules above
# can't link: second-tier-only names with no canonical overlap, renamed clubs,
# and same-named different clubs. (source, key) -> canonical club.
MANUAL = {
    # Netherlands (RSSSF)
    ("rsssf", "Spcl. Cambuur"): "SC Cambuur", ("rsssf", "Cambuur Leeuwarden"): "SC Cambuur",
    ("rsssf", "Cambuur-Leeuwarden"): "SC Cambuur",
    ("rsssf", "T.O.P."): "TOP Oss", ("rsssf", "T.O.P. Oss"): "TOP Oss", ("rsssf", "TOP"): "TOP Oss",
    ("rsssf", "Oss"): "TOP Oss", ("rsssf", "FC Oss"): "TOP Oss",              # renamed FC Oss 2009, TOP Oss 2018
    ("rsssf", "A.G.O.V.V."): "AGOVV Apeldoorn", ("rsssf", "AGOVV"): "AGOVV Apeldoorn",
    ("rsssf", "RBC"): "RBC Roosendaal", ("rsssf", "RBC RBC"): "RBC Roosendaal",
    ("rsssf", "Zwolle"): "PEC Zwolle",
    ("rsssf", "Omniworld"): "Almere City", ("rsssf", "FC Omniworld"): "Almere City",   # renamed 2010
    ("rsssf", "V.V.V"): "VVV-Venlo", ("rsssf", "FC V.V.V"): "VVV-Venlo",
    ("rsssf", "Stormvogels/Telstar"): "Telstar", ("rsssf", "Stormv/Telst."): "Telstar",
    ("rsssf", "Stormv./Telst."): "Telstar",                                    # Stormvogels Telstar 2001-08
    ("rsssf", "MVV Maastricht"): "MVV", ("rsssf", "HHaarlem"): "HFC Haarlem",
    ("rsssf", "FCVlaardingen"): "FC Vlaardingen", ("rsssf", "Roda Sport"): "Roda Sport",
    # Italy (RSSSF)
    ("rsssf", "Fidelis Andria"): "F. Andria",
    # Spain (Wikipedia)
    ("wikipedia", "Real Avilés CF"): "Avilés", ("wikipedia", "Ontinyent CF"): "Onteniente CF",
    ("wikipedia", "CE Hospitalet"): "CD Hospitalet", ("wikipedia", "CD Orense"): "Ourense",
    ("wikipedia", "Atlético Madrid B"): "At. Madrileño", ("wikipedia", "Atlético de Madrid B"): "At. Madrileño",
    ("wikipedia", "Athletic Bilbao B"): "Bilbao Ath.", ("wikipedia", "Real Sociedad B"): "San Sebastián",
    ("rsssf", "FC Haarlem"): "HFC Haarlem",
}

CLUB_WORDS = {"us", "ac", "acf", "as", "ss", "ssc", "fc", "sc", "cf", "cd", "ud", "sd", "rc", "sv", "vv", "bv",
              "afc", "calcio", "club", "sport", "sporting"}


def loose(name: str) -> str:
    """norm() that also drops club-type words, dotted initials and digits
    ("US Lecce", "ACF Fiorentina", "Salernitana Calcio 1919", sponsor initials
    as in "Z. Modena" or "0. Mantova" -> the town). A bare letter stays: the
    "B" of a reserve team ("Athletic Bilbao B") tells it from the first team."""
    s = re.sub(r"(?<![^\W\d_])[^\W_]\.", " ", str(name))          # "Z.", "C.d.", "0."
    words = [w for w in re.split(r"[\W\d_]+", s) if w and w.lower() not in CLUB_WORDS]
    return norm(" ".join(words)) or norm(name)


def close_match(key: str, targets: list[str]) -> list[str]:
    """The one target clearly closest to `key` (ratio >= 0.85, and 0.05 ahead
    of the next), or []. Short town names need the high cutoff: Savona and
    Savoia, Trani and Trapani are different clubs."""
    hits = difflib.get_close_matches(key, targets, n=2, cutoff=0.85)
    if len(hits) == 2:
        r = [difflib.SequenceMatcher(None, key, h).ratio() for h in hits]
        return hits[:1] if r[0] > r[1] + 0.05 else []
    return hits


def fixtures(df: pd.DataFrame) -> dict:
    """season -> {(club, opponent, venue, goals for, goals against)}"""
    out = defaultdict(set)
    for s, h, a, hg, ag in zip(df["season"], df["home_club"], df["away_club"], df["home_goals"], df["away_goals"]):
        out[s].add((h, a, "H", hg, ag))
        out[s].add((a, h, "A", ag, hg))
    return out


def link(src: pd.DataFrame, canon: pd.DataFrame, seeds: dict, rounds: int = 6) -> tuple[dict, dict]:
    """Source key -> canonical club by fixture agreement, spreading out from
    `seeds`. Returns (links, votes) with votes[key] = (best, runner-up)."""
    s_fx, c_fx = fixtures(src), fixtures(canon)
    c_idx = defaultdict(list)           # (season, opponent, venue, gf, ga) -> canonical clubs
    for season, rows in c_fx.items():
        for club, opp, venue, gf, ga in rows:
            c_idx[(season, opp, venue, gf, ga)].append(club)
    links, votes = dict(seeds), {}
    for _ in range(rounds):
        tally = defaultdict(Counter)
        for season, rows in s_fx.items():
            for key, opp, venue, gf, ga in rows:
                o = links.get(opp)
                if o is not None:
                    for club in c_idx.get((season, o, venue, gf, ga), []):
                        tally[key][club] += 1
        new = {}
        for key, cnt in tally.items():
            top = cnt.most_common(2) + [(None, 0)]
            votes[key] = (top[0][1], top[1][1])
            if key not in seeds and top[0][1] >= 3 and top[0][1] >= 3 * top[1][1]:
                new[key] = top[0][0]
        if all(links.get(k) == v for k, v in new.items()):
            break
        links = {**links, **new}
    return links, votes


def main(source: str, competitions: list[str]):
    cfg = load_config()
    reader = SourceReader(cfg)
    alias_path = cfg["aliases"]
    aliases = pd.read_csv(alias_path, dtype=str)
    silver = pd.read_parquet(cfg["paths"]["silver"] / "matches.parquet")
    clubs = pd.read_parquet(cfg["paths"]["silver"] / "clubs.parquet")
    known = aliases[aliases["source"] == source].set_index("source_name")["club"].to_dict()
    taken_names = set(aliases["club"]) | set(clubs["club"])
    rows, report = [], []
    for comp in competitions:
        country = cfg["competitions"][comp]["country"]
        src = reader.read(source, comp)
        canon = silver[(silver["competition"] == comp) & (silver["source"] != source)]
        country_clubs = clubs.loc[clubs["country"] == country, "club"].tolist()
        index = {f: defaultdict(list) for f in (norm, loose)}
        for c in country_clubs:
            for f, idx in index.items():
                idx[f(c)].append(c)

        # seeds: existing aliases and hand links, then names that (loosely)
        # normalise to exactly one canonical club seen in that season and tier
        keys = set(src["home_club"]) | set(src["away_club"])
        seeds = {k: v for k, v in known.items() if k in keys}
        seeds.update({k: v for (s_, k), v in MANUAL.items() if s_ == source and k in keys and k not in seeds})
        canon_season = defaultdict(set)
        for s, t, h, a in zip(canon["season"], canon["tier"], canon["home_club"], canon["away_club"]):
            canon_season[(s, t)] |= {h, a}
        name_votes = defaultdict(Counter)
        for s, t, h, a in zip(src["season"], src["tier"], src["home_club"], src["away_club"]):
            for key in (h, a):
                for f, idx in index.items():
                    hits = [c for c in idx.get(f(key), []) if c in canon_season[(s, t)]]
                    if len(hits) == 1:
                        name_votes[key][hits[0]] += 1
                        break
        for key, cnt in name_votes.items():
            if key not in seeds and len(cnt) == 1:
                seeds[key] = next(iter(cnt))
        links, votes = link(src, canon, seeds)

        display = pd.concat([src[["home_club", "home_name"]].set_axis(["key", "name"], axis=1),
                             src[["away_club", "away_name"]].set_axis(["key", "name"], axis=1)])
        display = display.groupby("key")["name"].agg(lambda s: s.value_counts().index[0])
        games = Counter(list(src["home_club"]) + list(src["away_club"]))
        seasons = pd.concat([src[["home_club", "season", "tier"]].set_axis(["key", "season", "tier"], axis=1),
                             src[["away_club", "season", "tier"]].set_axis(["key", "season", "tier"], axis=1)])
        key_seasons = seasons.groupby("key")[["season", "tier"]].apply(lambda d: set(zip(d["season"], d["tier"])))

        how = {k: "alias" if k in known else "manual" if (source, k) in MANUAL else
               "name+season" if k in seeds else "fixtures" for k in links}
        # leftovers 1: a unique (loosely) normalised name in the country
        for key in sorted(keys - set(links)):
            for f, idx in index.items():
                hits = idx.get(f(key), []) or idx.get(f(display[key]), [])
                if len(hits) == 1:
                    links[key], how[key] = hits[0], "name"
                    break
        # leftovers 2: abbreviations ("Salernit.") of a canonical club or of a
        # regular key (one seen in 3+ seasons), and typos for keys seen in at most
        # two seasons
        regular = {k for k in keys if len({s for s, _ in key_seasons[k]}) >= 3}
        targets = {loose(c): c for c in country_clubs}
        targets.update({loose(k): k for k in regular if loose(k) not in targets})
        for key in sorted(keys - set(links)):
            lk = loose(key)
            if key.rstrip().endswith("."):
                hits = [t for t in targets if t.startswith(lk) and t != lk]
            elif key in regular or re.search(r"[BC]$|Jong|Atl[eé]tico \w+ B", key):
                continue          # a reserve team is never a typo of its first team
            else:
                hits = close_match(lk, sorted(t for t in targets if t != lk))
            if len(hits) == 1:
                target = targets[hits[0]]
                links[key] = links.get(target, target)
                how[key] = f"variant of {target}"
        # the rest: new clubs, named as the source shows them
        new_names = {}
        for key in sorted(keys - set(links)):
            if {t for _, t in key_seasons[key]} == {1}:
                how[key] = "unlinked (tier 1 only)"
                continue
            name = display[key]
            # keys shown under one name are one club (Wikipedia links "SD Indauchu"
            # and "SD Indautxu", both shown as Indauchu)
            same = [k for k, n in new_names.items() if loose(display[k]) == loose(name)]
            if same:
                new_names[key] = new_names[same[0]]
            else:
                new_names[key] = name if name not in taken_names else f"{name} ({country})"
                taken_names.add(new_names[key])
            links[key], how[key] = new_names[key], "new"
        for key, h in how.items():           # variants of a key that became a new club
            if h.startswith("variant of ") and links[key] in new_names:
                links[key] = new_names[links[key]]

        for key in sorted(keys):
            n, second = votes.get(key, (0, 0))
            report.append({"source": source, "competition": comp, "key": key, "name": display[key],
                           "club": links.get(key), "how": how[key], "games": games[key], "votes": n,
                           "runner_up": second, "first_season": min(s for s, _ in key_seasons[key]),
                           "tiers": ",".join(str(t) for t in sorted({t for _, t in key_seasons[key]}))})
            if key not in known and key in links:
                rows.append({"source": source, "source_name": key, "club": links[key]})
                known[key] = links[key]

        # two keys that meet in a season must not share a club
        mapped = src.assign(h=src["home_club"].map(links), a=src["away_club"].map(links)).dropna(subset=["h", "a"])
        bad = mapped[mapped["h"] == mapped["a"]]
        for (h, a), _ in bad.groupby(["home_club", "away_club"]):
            print(f"  WARNING {comp}: {h!r} and {a!r} meet but both link to {links[h]!r}")

    rep = pd.DataFrame(report)
    out = cfg["paths"]["silver"] / f"grid_alias_review_{source}.csv"
    rep.sort_values(["competition", "how", "games"]).to_csv(out, index=False)
    for comp, grp in rep.groupby("competition"):
        print(comp, grp["how"].str.replace(r"variant of .*", "variant", regex=True).value_counts().to_dict())
    if rows:
        pd.concat([aliases, pd.DataFrame(rows)]).to_csv(alias_path, index=False)
    print(f"added {len(rows)} {source} aliases; review list in {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
