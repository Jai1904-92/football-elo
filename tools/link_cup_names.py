"""Link club keys from the Wikipedia cup pages (sources.wikipedia_cup) to
canonical clubs, as alias rows for source "wikipedia".

Keys are the articles the pages link to ("Calcio Como"), "<country>:<name>"
for unlinked names, or "<article> [<label>]" for a reserve side linked to its
first team. Old pages link old titles, so every title is first resolved
through Wikipedia's redirects (cached in data/bronze/wikipedia/redirects.json):
"Calcio Como" and "Como 1907" are one club. In order:

  1. title     the resolved title is already an alias: a league page's
               (source wikipedia) or a European one (DataRozhlas keys are
               article slugs); only if that club is of the cup's country
  2. name      the display name or the title (raw or resolved) (loosely)
               normalises to exactly one club of the cup's country, by any
               name the club is known by: canonical, name-type aliases, and
               Transfermarkt / ESPN display names ("Stade Brestois 29")
  3. fixtures  seasons that overlap the cup's other sources (Transfermarkt,
               ESPN, 2012/13 on) link the rest on (season, opponent, venue, score)
  4. variant   a near-identical name among the country's clubs (accents,
               spelling: "Elazığspor"/"Elazigspor"); not for reserve or
               amateur sides ("X II", "X (A)") of league clubs
  5. new       a new club, named as the page shows it (with the title or the
               country added when that name is taken). Keys the cup shows
               under one name ("BEL:Aalter", "K.V.V. Eendracht Aalter") are one
               new club.

Two keys that meet in a match must not share a club: those links are
dropped and the keys become new clubs. Existing alias rows win.

Only matches with a league club on at least one side are rated (silver.league_ties),
so new clubs are made, and alias rows written, only for keys in those matches;
the rest show as "dropped" in the review.

    python tools/link_cup_names.py                    # all cups in config
    python tools/link_cup_names.py SCO-SC GRE-GC      # some
    python tools/link_cup_names.py --dry-run ...      # review only

Uses the clubs and matches of the last build (data/silver). Writes new rows
to config/club_aliases.csv and a review list to data/silver/cup_alias_review.csv.
"""
import difflib
import json
import re
import urllib.parse
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_aliases import norm  # noqa: E402
from football_elo.config import load_config  # noqa: E402
from football_elo.silver import SourceReader  # noqa: E402
from football_elo.wikicups import RESERVE  # noqa: E402
from link_grid_names import link, loose  # noqa: E402

API = "https://en.wikipedia.org/w/api.php"

# Hand links, checked against club histories: (competition, key) -> club.
MANUAL: dict[tuple[str, str], str] = {
    # Wikipedia now redirects the Racing article to Paris FC; they are separate clubs here
    ("FRA-CDF", "Racing Club de France Football"): "Racing Club de France",
    ("FRA-CDF", "Gazélec Ajaccio"): "GFC Ajaccio",
}


def resolve_titles(titles: set[str], cache_path: Path) -> dict[str, str]:
    """title -> the title it redirects to (itself when it isn't a redirect or
    doesn't exist). Cached; only unseen titles are asked for, 50 a request."""
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    todo = sorted(t for t in titles if t not in cache)
    session = requests.Session()
    session.headers["User-Agent"] = "football-elo/0.1 (research project)"
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        for attempt in range(6):
            resp = session.get(API, params={"action": "query", "titles": "|".join(batch), "redirects": 1,
                                            "format": "json", "formatversion": 2}, timeout=60)
            if resp.ok and resp.text.startswith("{"):
                break
            time.sleep(int(resp.headers.get("Retry-After", 0) or 0) or 10 * (attempt + 1))
        else:
            resp.raise_for_status()
        q = resp.json().get("query", {})
        norm_map = {x["from"]: x["to"] for x in q.get("normalized", [])}
        redir = {x["from"]: x["to"] for x in q.get("redirects", [])}
        for t in batch:
            n = norm_map.get(t, t)
            cache[t] = redir.get(n, n)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        time.sleep(1)
    return {t: cache.get(t, t) for t in titles}


def is_title(key: str) -> bool:
    """An article title, not an unlinked name or a reserve-side key."""
    return not re.match(r"^[A-Z]{3}:", key) and "[" not in key


def light(name: str) -> str:
    """Accents, case and punctuation only: "Rot-Weiß Lüdenscheid" -> "rotweilludenscheid"
    keeps "RC Paris" apart from "Paris FC" (loose() would not)."""
    s = unicodedata.normalize("NFKD", str(name).replace("ß", "ss").replace("ı", "i"))
    return re.sub(r"[^a-z0-9]", "", s.encode("ascii", "ignore").decode().lower())


TYPE_WORDS = {"ac", "acd", "acf", "ad", "as", "asd", "ca", "cd", "cf", "cs", "ec", "es", "fc", "fk", "gd", "kfc",
              "ksk", "ksv", "kv", "rc", "rcd", "rfc", "rsc", "sc", "sd", "sk", "sport", "ss", "ssc", "sv", "ud",
              "us", "usd", "vfb", "vfl", "vv"}


def type_words(name: str) -> set[str]:
    """Club-type initials in a name: "AC Amiens" -> {"ac"}, "Amiens SC" -> {"sc"}."""
    return {w for w in re.split(r"[\W\d_]+", re.sub(r"(?<=\w)\.", "", str(name)).lower()) if w in TYPE_WORDS}


def tokens(name: str) -> set[str]:
    return {light(w) for w in re.split(r"[\s\-/'.]+", bare_title(str(name))) if len(light(w)) >= 4}


def bare_title(title: str) -> str:
    """"Iraklis F.C. (Thessaloniki)" -> "Iraklis"; "Club Brugge KV" stays."""
    s = re.sub(r"\s*\([^)]*\)$", "", title)
    return re.sub(r"\s+(?:F\.?C\.?|A\.?F\.?C\.?|S\.?C\.?)$", "", s).strip()


def known_names(reader: SourceReader, aliases: pd.DataFrame) -> pd.DataFrame:
    """(name, club) for every name a canonical club is known by."""
    named = aliases[~aliases["source"].isin(["transfermarkt", "espn"])][["source_name", "club"]]
    out = [named.set_axis(["name", "club"], axis=1)]
    for source, frame in (("transfermarkt", reader._transfermarkt()), ("espn", reader._espn())):
        ids = aliases[aliases["source"] == source].set_index("source_name")["club"]
        for side in ("home", "away"):
            part = frame[[f"{side}_club", f"{side}_name"]].drop_duplicates()
            out.append(pd.DataFrame({"name": part[f"{side}_name"],
                                     "club": part[f"{side}_club"].astype(str).map(ids)}))
    names = pd.concat(out).dropna()
    names["name"] = names["name"].astype(str).str.replace("_", " ")
    return names.drop_duplicates()


def main(competitions: list[str], dry_run: bool) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config()
    reader = SourceReader(cfg)
    alias_path = cfg["aliases"]
    aliases = pd.read_csv(alias_path, dtype=str)
    clubs = pd.read_parquet(cfg["paths"]["silver"] / "clubs.parquet")
    silver = pd.read_parquet(cfg["paths"]["silver"] / "matches.parquet")
    club_country = clubs.set_index("club")["country"].to_dict()
    league_clubs = set(clubs.loc[clubs["league_club"], "club"])
    cups = cfg["sources"]["wikipedia"]["cups"]
    competitions = competitions or list(cups)

    srcs = {c: reader.read("wikipedia", c) for c in competitions}
    keys_all = set().union(*({*d["home_club"], *d["away_club"]} for d in srcs.values()))
    wiki_alias = aliases[aliases["source"] == "wikipedia"].set_index("source_name")["club"].to_dict()
    dr_alias = aliases[aliases["source"] == "datarozhlas"]
    # DataRozhlas keys are article slugs, URL-encoded ("CS_Gaz_Metan_Media%C8%99")
    dr_titles = {urllib.parse.unquote(k).replace("_", " "): v for k, v in zip(dr_alias["source_name"], dr_alias["club"])}
    titles = {k for k in keys_all if is_title(k)} | {k for k in wiki_alias if is_title(k)} | set(dr_titles)
    print(f"resolving {len(titles)} titles (cached after the first run)")
    resolved = resolve_titles(titles, cfg["paths"]["bronze"] / "wikipedia" / "redirects.json")

    by_title = defaultdict(set)       # resolved title -> clubs it's an alias of
    for k, v in list(wiki_alias.items()) + list(dr_titles.items()):
        by_title[resolved.get(k, k)].add(v)

    names = known_names(reader, aliases)
    known = dict(wiki_alias)
    taken_names = set(aliases["club"]) | set(clubs["club"])
    rows, report = [], []
    for comp in competitions:
        country = cfg["competitions"][comp]["country"]
        src = srcs[comp]
        long = pd.concat([src[["home_club", "home_name", "season"]].set_axis(["key", "name", "season"], axis=1),
                          src[["away_club", "away_name", "season"]].set_axis(["key", "name", "season"], axis=1)])
        display = long.groupby("key")["name"].agg(lambda s: s.value_counts().index[0])
        games = long["key"].value_counts()
        first = long.groupby("key")["season"].min()
        last = long.groupby("key")["season"].max()
        keys = set(display.index)
        country_clubs = [c for c, k in club_country.items() if k == country]
        index = {f: defaultdict(set) for f in (norm, loose)}
        variants = [(c, c) for c in country_clubs] + [
            (n, c) for n, c in zip(names["name"], names["club"]) if club_country.get(c) == country]
        for n, c in variants:
            for f, idx in index.items():
                if f(bare_title(n)):
                    idx[f(bare_title(n))].add(c)

        links, how = {}, {}
        for key in sorted(keys):
            if (comp, key) in MANUAL:
                links[key], how[key] = MANUAL[(comp, key)], "manual"
            elif key in known:
                links[key], how[key] = known[key], "alias"
        club_names = defaultdict(set)
        for n, c in variants:
            club_names[c].add(n)
        # 1. resolved title already an alias of a club of this country. Through
        # a redirect, the page's name must share a word with one of the club's
        # names (merged-club articles: "USV Holland" redirects to DOS's), and a
        # reserve side's article never maps to its first team.
        for key in sorted(keys - set(links)):
            if not is_title(key):
                continue
            hits = {c for c in by_title.get(resolved.get(key, key), ()) if club_country.get(c) in (country, None)}
            if len(hits) != 1:
                continue
            club = next(iter(hits))
            if resolved.get(key, key) != key:
                if RESERVE.search(key) or RESERVE.search(display[key]) or re.search(r"\(A\)", display[key]):
                    continue
                if not (tokens(key) | tokens(display[key])) & set().union(*map(tokens, club_names[club] | {club})):
                    continue
            links[key], how[key] = club, "title"
        # 2. a unique (loose) name among the country's clubs, by display or bare title
        for key in sorted(keys - set(links)):
            if "[" in key:                            # a reserve side: its own label only
                cands = [display[key]]
            else:
                cands = [display[key], bare_title(key.split(":", 1)[-1]), bare_title(resolved.get(key, key))]
            for f, idx in index.items():
                hits = {c for n in cands for c in idx.get(f(n), ())}
                if len(hits) > 1 and len(hits & league_clubs) == 1:   # a stray European-only duplicate
                    hits &= league_clubs
                if len(hits) == 1:
                    hit = next(iter(hits))
                    mine, theirs = type_words(display[key]), type_words(hit)
                    if mine and theirs and not mine & theirs:          # "AC Amiens" is not "Amiens SC"
                        hits = set()
                    elif re.search(r"\(A\)|\sA$", display[key]) and hit in league_clubs:
                        hits = set()                                    # amateur side of a league club
                if len(hits) == 1:
                    links[key], how[key] = hits.pop(), "name"
                    break
        # 3. fixtures against the cup's other sources
        canon = silver[(silver["competition"] == comp) & (silver["source"] != "wikipedia")]
        if len(canon):
            linked, _ = link(src, canon, dict(links))
            for key, club in linked.items():
                if key not in links:
                    links[key], how[key] = club, "fixtures"
        # 4. clearly closest name (not for reserve sides)
        targets = {light(c): c for c in country_clubs}
        for key in sorted(keys - set(links)):
            if "[" in key or RESERVE.search(display[key]):
                continue
            amateur = re.search(r"\s\(?A\)?$", display[key])
            hits = difflib.get_close_matches(light(display[key]), sorted(targets), n=2, cutoff=0.92)
            initials = [re.match(r"^((?:[A-Z]\.?){2,4})\s", n) for n in (display[key], targets[hits[0]])] if hits else []
            if initials and all(initials) and light(initials[0].group(1)) != light(initials[1].group(1)):
                continue                      # "AD Oliveirense" is not "UD Oliveirense"
            if len(hits) == 1 and not (amateur and targets[hits[0]] in league_clubs):
                links[key], how[key] = targets[hits[0]], f"variant of {targets[hits[0]]}"
        # keys that meet but share a club: keep the stronger link only
        rank = {"alias": 0, "manual": 0, "title": 1, "name": 2, "fixtures": 2}
        for h, a in set(zip(src["home_club"], src["away_club"])):
            if h in links and a in links and links[h] == links[a]:
                weak = max((h, a), key=lambda k: (rank.get(how[k], 3), -games[k]))
                if how[weak] in ("alias", "manual"):
                    print(f"  WARNING {comp}: {h!r} and {a!r} meet but both are aliases of {links[h]!r}")
                    continue
                print(f"  {comp}: {h!r} v {a!r} both -> {links[h]!r}; {weak!r} becomes its own club")
                del links[weak]
                how[weak] = "new (met its link)"
        # keys in matches that will be rated: a league club on one side
        lg = src["home_club"].map(links).isin(league_clubs) | src["away_club"].map(links).isin(league_clubs)
        needed = set(src.loc[lg, "home_club"]) | set(src.loc[lg, "away_club"])
        for key in keys - needed:
            links.pop(key, None)
            how[key] = "dropped"
        # 5. the rest: new clubs, one per name the cup shows
        groups = defaultdict(list)
        for key in needed - set(links):
            groups[light(display[key])].append(key)
        for group in groups.values():
            group.sort(key=lambda k: (-games[k], k))
            key = group[0]
            name = display[key]
            title = bare_title(resolved.get(key, key)) if is_title(key) else name
            for cand in (name, title, f"{name} ({country})", f"{title} ({country}, {first[key]})"):
                if cand not in taken_names:
                    break
            taken_names.add(cand)
            for k in group:
                links[k] = cand
                how[k] = how.get(k, "new")
        for key in sorted(keys):
            report.append({"competition": comp, "key": key, "resolved": resolved.get(key, ""),
                           "name": display[key], "club": links.get(key), "how": how[key],
                           "club_country": club_country.get(links.get(key), country if how[key].startswith("new")
                                                            else None),
                           "games": int(games[key]), "first_season": int(first[key]),
                           "last_season": int(last[key])})
            if key not in known and key in links:
                rows.append({"source": "wikipedia", "source_name": key, "club": links[key]})
                known[key] = links[key]

    rep = pd.DataFrame(report)
    out = cfg["paths"]["silver"] / "cup_alias_review.csv"
    rep.sort_values(["competition", "how", "games"], ascending=[True, True, False]).to_csv(out, index=False)
    summary = rep.assign(how=rep["how"].str.replace(r"variant of .*", "variant", regex=True)
                         .str.replace(r"new.*", "new", regex=True))
    print(summary.pivot_table(index="competition", columns="how", values="games", aggfunc="size",
                              fill_value=0).to_string())
    if rows and not dry_run:
        pd.concat([aliases, pd.DataFrame(rows)]).to_csv(alias_path, index=False)
    print(f"{'would add' if dry_run else 'added'} {len(rows)} wikipedia aliases; review list in {out}")


if __name__ == "__main__":
    args = sys.argv[1:]
    main([a for a in args if not a.startswith("--")], "--dry-run" in args)
