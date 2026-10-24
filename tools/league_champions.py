"""League champions for the honours, from each country's "List of ...
football champions" Wikipedia article, cross-checked against a table worked
out from the rated results.

The list pages are authoritative where a results table isn't (play-offs,
points deductions, revoked titles, halved points before a championship
round), but their layouts differ. Every table row whose cell is a season
gives a candidate: the next cell's linked article or plain name. A season's
champion is the candidate that played in that season's top flight, matched
on article (through Wikipedia's redirects) or on name among that season's
clubs only; lower-division tables on the same page drop out that way.
A season's candidates are tried in order: the spring half season's year
when the season has one (Hungary's 1957, Ukraine's 1992; it then stands for
the season), an autumn-spring row for an autumn-spring season, a single year
for a calendar-year season; among matched ones, one agreeing with the table
wins. Seasons with no usable candidate take the results table's leader
(points, then goal difference). Union-era seasons come from the successor's page
(Soviet seasons from the Soviet and Russian list, Czechoslovak ones from the
Czech list, Yugoslav ones from the Serbian list); Slovakia and Croatia have
no list page and use the table only. MANUAL overrides both, for seasons checked by hand.

    python tools/league_champions.py

Uses the matches of the last build (data/silver). Caches the list pages in
data/bronze/wikipedia/champions, writes config/league_champions.csv
(competition, season, club, how) and data/silver/league_champions_review.csv
(every season with the table's leader and margin, for the seasons the two
disagree on).
"""
import difflib
import re
import sys
import urllib.parse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_aliases import norm  # noqa: E402
from football_elo.bronze import _wiki_raw  # noqa: E402
from football_elo.config import load_config  # noqa: E402
from link_cup_names import resolve_titles  # noqa: E402

# list page per country; seasons up to `split` belong to the union league
PAGES = {
    "ENG-L": "List of English football champions", "ESP-L": "List of Spanish football champions",
    "GER-L": "List of German football champions", "ITA-L": "List of Italian football champions",
    "FRA-L": "List of French football champions", "NED-L": "List of Dutch football champions",
    "POR-L": "List of Portuguese football champions", "SCO-L": "List of Scottish football champions",
    "BEL-L": "List of Belgian football champions", "TUR-L": "List of Turkish football champions",
    "GRE-L": "List of Greek football champions", "AUT-L": "List of Austrian football champions",
    "SUI-L": "List of Swiss football champions", "SWE-L": "List of Swedish football champions",
    "DEN-L": "List of Danish football champions", "ROU-L": "List of Romanian football champions",
    "HUN-L": "List of Hungarian football champions", "GDR-L": "List of East German football champions",
    "UKR-L": "List of Ukrainian football champions",
    "URS-L": "List of Soviet and Russian football champions", "RUS-L": "List of Soviet and Russian football champions",
    "TCH-L": "List of Czech football champions", "CZE-L": "List of Czech football champions",
    "YUG-L": "List of Serbian football champions", "SRB-L": "List of Serbian football champions",
}

# Seasons checked by hand: (competition, season) -> club, or None when no title
# was awarded.
MANUAL: dict[tuple[str, int], str | None] = {
    ("FRA-L", 1992): None,      # stripped from Marseille (match fixing), not reassigned
    ("ITA-L", 2004): None,      # revoked from Juventus (Calciopoli), left unassigned
    ("NED-L", 2019): None,      # abandoned (COVID-19), no champion
    ("UKR-L", 2021): None,      # abandoned (Russian invasion), no champion
    ("GDR-L", 1955): None,      # autumn transition round, no title
    ("HUN-L", 1963): "Gyori ETO",                  # autumn 1963 championship
    ("CRO-L", 2003): "Hajduk Split",               # no list page; table level on points
    ("CRO-L", 2024): "HNK Rijeka",
    ("SVK-L", 2022): "SK Slovan Bratislava",       # no list page; the table misses the championship round
}

# A second title under one season label: a season split into two championships
# (the USSR's 1976 spring and autumn), or a calendar season followed by a spring
# half season stored under the same label (Denmark 1990 / spring 1991, Hungary
# 1969 / spring 1970).
EXTRA = [("URS-L", 1976, "Torpedo Moskva"), ("DEN-L", 1990, "Brondby IF"), ("HUN-L", 1969, "Ujpesti Dozsa SC")]

LINK = re.compile(r"\[\[([^|\]#]+)(?:\|([^\]]+))?\]\]")
SEASON = re.compile(r"^\s*'*(?:\[\[[^|\]]*\|)?'*\s*(?:<s>)?(19[5-9]\d|20[0-2]\d)(?:\s*[–\-/]\s*(\d{2,4}))?\s*"
                    r"(?:</s>)?'*(?:\]\])?\s*'*\s*$")


def clean_cell(c: str) -> str:
    c = re.sub(r"^\s*(?:(?:style|align|bgcolor|rowspan|colspan|scope|class)=\"?[^|\"]*\"?\s*)+\|", "", c)
    c = c.replace("&ndash;", "–").replace("&nbsp;", " ")
    c = re.sub(r"\{\{(?:nowrap|small|center|centre)\|([^{}]*)\}\}", r"\1", c, flags=re.I)
    c = re.sub(r"\{\{(?:flagicon|flag|fb|fbaicon|sort|sortname)\|[^{}]*\}\}", "", c, flags=re.I)
    return c.strip()


def candidates(text: str):
    """(season start year, autumn-spring?, linked article or None, plain name) per table row."""
    text = re.sub(r"<ref[^>]*/>|<ref.*?</ref>|\{\{#tag:ref.*?\}\}", "", text, flags=re.S)
    for row in re.split(r"\n\|-[^\n]*", text):
        cells = [clean_cell(c) for c in re.split(r"\|\||!!|\n[|!]", row)]
        for i, cell in enumerate(cells):
            m = SEASON.match(re.sub(r"\s*\(.*?\)\s*$", "", cell))
            if not m:
                continue
            rest = [c for c in cells[i + 1:] if c and not re.fullmatch(r"[\s'\-–—]*", c)]
            if rest:
                lk = LINK.search(rest[0])
                name = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", rest[0])
                name = re.sub(r"\{\{[^{}]*\}\}|'{2,}|<[^>]+>|\(\d+\)|\*", "", name).strip(" ,")
                yield int(m.group(1)), m.group(2) is not None, (lk.group(1).strip() if lk else None), name
            break


def leaders(lg: pd.DataFrame) -> pd.DataFrame:
    """Table leader per competition and season: 2 points a win (3 from 1994/95,
    England 1981/82), then goal difference."""
    out = []
    for (comp, season), g in lg.groupby(["competition", "season"]):
        win = 3 if season >= (1981 if comp == "ENG-L" else 1994) else 2
        hp = np.select([g.home_goals > g.away_goals, g.home_goals == g.away_goals], [win, 1], 0)
        ap = np.select([g.away_goals > g.home_goals, g.home_goals == g.away_goals], [win, 1], 0)
        t = pd.concat([pd.DataFrame({"club": g.home_club, "p": hp, "gd": g.home_goals - g.away_goals}),
                       pd.DataFrame({"club": g.away_club, "p": ap, "gd": g.away_goals - g.home_goals})])
        t = t.groupby("club").sum().sort_values(["p", "gd"], ascending=False)
        out.append({"competition": comp, "season": season, "table": t.index[0], "runner_up": t.index[1],
                    "margin": int(t.p.iloc[0] - t.p.iloc[1])})
    return pd.DataFrame(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config()
    folder = cfg["paths"]["bronze"] / "wikipedia" / "champions"
    pages = {}
    for comp, title in PAGES.items():
        path = folder / f"{comp[:3]}.txt"
        if title in pages:
            continue
        if not path.exists():
            _wiki_raw(cfg["sources"]["wikipedia"]["url"], title, path)
        pages[title] = path.read_text(encoding="utf-8") if path.exists() else ""

    m = pd.read_parquet(cfg["paths"]["silver"] / "matches.parquet")
    last = m["season"].max()
    lg = m[(m.comp_type == "league") & (m.tier == 1) & (m.season < last)]      # finished seasons
    table = leaders(lg)
    members = pd.concat([lg[["competition", "season", "home_club"]].set_axis(["c", "s", "club"], axis=1),
                         lg[["competition", "season", "away_club"]].set_axis(["c", "s", "club"], axis=1)])
    members = members.drop_duplicates().groupby(["c", "s"])["club"].agg(set).to_dict()

    aliases = pd.read_csv(cfg["aliases"], dtype=str)
    names = aliases[~aliases.source.isin(["transfermarkt", "espn"])][["source_name", "club"]]
    names = pd.concat([names, pd.DataFrame({"source_name": names.club.unique(), "club": names.club.unique()})])
    names["source_name"] = names.source_name.str.replace("_", " ").map(urllib.parse.unquote)
    club_names = names.groupby("club")["source_name"].agg(set).to_dict()
    titled = aliases[aliases.source.isin(["wikipedia", "datarozhlas"])]
    title_club = {urllib.parse.unquote(k).replace("_", " "): v for k, v in zip(titled.source_name, titled.club)}
    cands = {title: list(candidates(text)) for title, text in pages.items()}
    all_titles = {t for cs in cands.values() for _, _, t, _ in cs if t} | set(title_club)
    resolved = resolve_titles(all_titles, cfg["paths"]["bronze"] / "wikipedia" / "redirects.json")
    by_title = {}
    for k, v in title_club.items():
        by_title.setdefault(resolved.get(k, k), set()).add(v)

    def match(title, name, clubs):
        """The club of `clubs` this candidate names, or None."""
        if title:
            hit = by_title.get(resolved.get(title, title), set()) & clubs
            if len(hit) == 1:
                return next(iter(hit))
        best, score = None, 0.0
        for c in clubs:
            for n in club_names.get(c, {c}):
                r = difflib.SequenceMatcher(None, norm(name), norm(n)).ratio() if norm(name) else 0
                if r > score:
                    best, score = c, r
        return best if score >= 0.75 else None

    kinds = {}           # (competition, season) -> season kinds of its Wikipedia pages
    for comp, specs in cfg["sources"]["wikipedia"]["leagues"].items():
        for spec in specs:
            if spec["tier"] == 1:
                for season in range(spec["seasons"][0], spec["seasons"][1] + 1):
                    kinds.setdefault((comp, season), set()).add(spec.get("kind", "split"))

    rows = []
    for t in table.itertuples(index=False):
        clubs = members[(t.competition, t.season)]
        kind = kinds.get((t.competition, t.season), {"split"})
        tries = ([(t.season + 1, False)] if "spring" in kind else []) +                 ([(t.season, True)] if "split" in kind else []) + ([(t.season, False)] if "calendar" in kind else [])
        tries += [w for w in [(t.season, True), (t.season, False)] if w not in tries]
        listed = None
        for want in tries:
            hits = [match(title, name, clubs) for year, split, title, name in cands.get(PAGES.get(t.competition), [])
                    if (year, split) == want]
            hits = [h for h in hits if h]
            if hits:
                listed = t.table if t.table in hits else hits[0]
                break
        if (t.competition, t.season) in MANUAL:
            club, how = MANUAL[(t.competition, t.season)], "manual"
            if club is None:
                continue
        elif listed:
            club, how = listed, "list" if listed == t.table else "list (table differs)"
        else:
            club, how = t.table, "table" if t.margin > 0 else "table (level on points)"
        rows.append({**t._asdict(), "club": club, "how": how})
    rows += [{"competition": c, "season": s_, "club": club, "how": "manual (second title)"} for c, s_, club in EXTRA]
    rev = pd.DataFrame(rows)
    rev.to_csv(cfg["paths"]["silver"] / "league_champions_review.csv", index=False)
    rev[["competition", "season", "club", "how"]].to_csv(Path(cfg["aliases"]).parent / "league_champions.csv",
                                                         index=False)
    print(rev.pivot_table(index="competition", columns="how", values="season", aggfunc="size", fill_value=0)
          .to_string())


if __name__ == "__main__":
    main()
