"""Knockout-cup results as English Wikipedia season articles print them.

Five layouts, often mixed on one page:
  - {{Football box}} / {{Football box collapsible}}: one match, team1 at home,
    usually dated
  - {{OneLegResult|team1||score|team2}}: one match, team1 at home
  - {{TwoLegResult|team1||agg|team2||leg1|leg2}}: a two-legged tie; both leg
    scores are from team1's side, and team1 is at home in the first leg
  - bracket templates ({{16TeamBracket}} etc.): RDn-teamNN paired 1-2, 3-4...,
    with RDn-scoreNN or RDn-scoreNN-L per leg. Venues aren't given: a two-leg
    tie has the upper team at home first, a one-leg tie counts as neutral
  - wikitables: one row per match (home, score, away) or per two-legged tie
    (team1, agg, team2, leg 1, leg 2)

A match printed in more than one layout is kept once, from the most detailed
(box, then result row or table, then bracket). parse_page returns plain dicts;
sources.wikipedia_cup dates them and builds the match frame.
"""
from __future__ import annotations

import html
import re

import pandas as pd

LINK = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]*))?\]\]")
SCORE = re.compile(r"(\d{1,2})\s*[–—−:-]\s*(\d{1,2})")
PENS = re.compile(r"(\d{1,2})\s*[–—−-]\s*(\d{1,2})\s*(?:p\b|pen|pso|\]\]\s*p)"
                  r"|\(\s*(?:p|pen\.?|pens\.?|penalties)\s*:?\s*(\d{1,2})\s*[–—−-]\s*(\d{1,2})\s*\)", re.I)
AET = re.compile(r"a\.?\s*e\.?\s*t\.?|extra time|\b(?:aet|asdet|n\.?V\.?)\b", re.I)
# results that weren't played out: awarded, walkovers, abandoned, annulled
VOID = re.compile(r"w/o|walk-?over|awarded|\bawd\b|forfeit|annul|abandon|\bvoid\b|cancel|not played|"
                  r"withdr|expelled|disqualif|\bw\.o\.|\bn/p\b", re.I)
BYE = re.compile(r"^\s*(?:bye|\(?bye\)?|walkover|w/o|—|-|–)?\s*$", re.I)

PRIORITY = {"box": 0, "oneleg": 1, "twoleg": 1, "table": 1, "bracket": 2}
# headings that hold rounds rather than name one
GENERIC = re.compile(r"^(?:matches|results|fixtures|schedule|competition|tournament|main (?:draw|tournament|"
                     r"competition)|competition proper|rounds|knockout(?: stage| phase| rounds)?|final (?:stage|phase|"
                     r"rounds|tournament)|draw|proper rounds?|bracket|overview|format|.* stages?|.* phases?|.* rounds)$", re.I)
SUBSLOT = re.compile(r"replay|second leg|2nd leg|return leg|play-?off", re.I)


# ------------------------------------------------------------ wikitext helpers
def clean(text: str) -> str:
    """Strip what never carries a result: comments, refs, <br>-free tags."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref[^>/]*/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    return text


def template_at(text: str, start: int) -> str:
    """The {{...}} starting at `start`, nested templates included."""
    depth, i = 0, start
    while i < len(text):
        if text.startswith("{{", i):
            depth, i = depth + 1, i + 2
        elif text.startswith("}}", i):
            depth, i = depth - 1, i + 2
            if depth == 0:
                break
        else:
            i += 1
    return text[start:i]


def split_top(s: str, sep: str = "|") -> list[str]:
    """Split on `sep` outside [[...]] and {{...}}."""
    out, depth, cur, i = [], 0, [], 0
    while i < len(s):
        two = s[i:i + 2]
        if two in ("[[", "{{"):
            depth, cur, i = depth + 1, cur + [two], i + 2
            continue
        if two in ("]]", "}}"):
            depth, cur, i = max(depth - 1, 0), cur + [two], i + 2
            continue
        if depth == 0 and s.startswith(sep, i):
            out.append("".join(cur))
            cur, i = [], i + len(sep)
            continue
        cur.append(s[i])
        i += 1
    out.append("".join(cur))
    return out


def params(body: str) -> tuple[list[str], dict[str, str]]:
    """A template's positional and named parameters (body includes the braces)."""
    parts = split_top(body[2:-2])[1:]
    pos, named = [], {}
    for p in parts:
        k, eq, v = p.partition("=")
        if eq and re.fullmatch(r"\s*[\w -]+\s*", k) and "[[" not in k:
            named[k.strip()] = v.strip()
        else:
            pos.append(p)
    return pos, named


def plain(s: str) -> str:
    """Display text: links to their labels, templates and markup removed."""
    # wrappers that keep their (last) argument: {{nobold|[[Club]]}}, {{sort|key|text}}
    s = re.sub(r"\{\{\s*(?:nobold|bold|nowrap|nobr|small|big|sup|sub|center|sort)\s*\|(?:[^{}|\[]*\|)?"
               r"((?:[^{}\[]|\[\[[^\]]*\]\])*)\}\}", r"\1", s, flags=re.I)
    s = re.sub(r"\{\{\s*(?:aet|a\.e\.t\.)\s*\}\}", " (a.e.t.) ", s, flags=re.I)
    s = re.sub(r"\{\{\s*(?:pso|pen|pens)\s*\|\s*(\d+)\s*\|\s*(\d+)[^{}]*\}\}", r" (\1–\2 p) ", s, flags=re.I)
    for _ in range(3):
        s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = LINK.sub(lambda m: m.group(2) if m.group(2) is not None else m.group(1), s)
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<sup>\s*(?:\d+|[a-z*†‡])\s*</sup>", " ", s)       # footnote marks: "0–4<sup>1</sup>"
    s = re.sub(r"<[^>]*>", " ", s)
    s = re.sub(r"'{2,}", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


RESERVE = re.compile(r"(?:^|\s)(?:B|C|II|III|2|Jong|Young|Reserves?|Amateure|Atl[eè]tic|U-?\d{2})(?:\s|$)")


def club(cell: str) -> tuple[str, str] | None:
    """(key, display name) for a team cell: the article its first link points
    to (stable across seasons), else "~" + the plain name (sources prefixes the
    country, so an unlinked "Olympic" in one cup isn't another country's);
    None for byes/blanks. A reserve side linked to its first team's article
    ("[[PSV Eindhoven|Jong PSV]]") is keyed "PSV Eindhoven [Jong PSV]"."""
    s = re.sub(r"\{\{\s*(?:flagicon|flag|fb|fbaicon|flagdeco)[^{}]*\}\}", "", cell, flags=re.I)
    s = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", s, flags=re.I)
    name = re.sub(r"\s*\([^)]*\)\s*$", "", plain(s)).strip()          # "(D1)", "(3)", "(HL)"
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if BYE.match(name) or not re.search(r"[A-Za-zÀ-ɏͰ-Ͽ]", name):
        return None
    for m in LINK.finditer(s):
        target = m.group(1).strip()
        if re.match(r"(?:File|Image|Category|Bye|Away goals|Extra time|Penalty)", target, re.I):
            continue
        label = plain(m.group(2) if m.group(2) is not None else target)
        target = target.split("#")[0].replace("_", " ").strip()
        if target:
            target = target[0].upper() + target[1:]
            label = label or name
            if RESERVE.search(label) and not RESERVE.search(target):
                return f"{target} [{label}]", label
            return target, label
    return "~" + name, name


def score(cell: str) -> dict | None:
    """{"hg", "ag", "aet", "pens": (h, a) | None} from a score cell, None when
    there's no played score."""
    s = plain(cell)
    if not s or VOID.search(s) or VOID.search(cell):
        return None
    pens = PENS.search(s)
    body = s[:pens.start()] + s[pens.end():] if pens else s
    body = re.sub(r"\(\s*\d{1,2}\s*[–—−-]\s*\d{1,2}\s*\)", "", body) if pens else body
    m = SCORE.search(body)
    if not m:
        return None
    if pens is None:     # "(5–4)" alone after a score is a shoot-out
        p2 = re.search(r"\(\s*(\d{1,2})\s*[–—−-]\s*(\d{1,2})\s*\)", s[m.end():])
        pens_t = (int(p2.group(1)), int(p2.group(2))) if p2 else None
    else:
        pens_t = tuple(int(g) for g in pens.groups() if g is not None)
    return {"hg": int(m.group(1)), "ag": int(m.group(2)),
            "aet": bool(AET.search(s) or AET.search(cell)) or pens_t is not None, "pens": pens_t}


def parse_date(s: str, season: int) -> pd.Timestamp | None:
    """A printed date within the season (1 July to 31 July a year later)."""
    m = re.search(r"\{\{\s*(?:start date|dts)\s*\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})", s, re.I)
    s = plain(s)
    if m:
        cand = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        m = (re.search(r"\d{1,2}\s+[A-Z][a-z]+\.?\s+\d{4}", s) or re.search(r"[A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4}", s)
             or re.search(r"\d{4}-\d{2}-\d{2}", s))
        if not m:
            return None
        cand = m.group(0)
    d = pd.to_datetime(cand, errors="coerce")
    if pd.isna(d) or not (pd.Timestamp(season, 7, 1) <= d <= pd.Timestamp(season + 1, 7, 31)):
        return None
    return d.normalize()


# ------------------------------------------------------------ transcluded pages
# {{:Title}}, or a labelled section: {{#lst:Title|label}} ({{#section:}}), {{#lsth:Title|heading}}
TRANSCLUDE = re.compile(r"\{\{\s*(?::|#(lsth|lst|section)\s*:)\s*([^{}|]+?)\s*(?:\|\s*([^{}|]*?)\s*)?\}\}", re.I)


def transcluded(text: str) -> list[str]:
    """Titles of pages transcluded into the page (finals, mostly)."""
    return sorted({m.group(2).strip() for m in TRANSCLUDE.finditer(clean(text))})


def cache_name(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", title) + ".txt"


def expand(text: str, folder) -> str:
    """Replace {{:Title}} with the cached page (folder/cache_name), as
    MediaWiki would: its <onlyinclude> parts if any, else all but <noinclude>."""
    def sub(m: re.Match) -> str:
        path = folder / cache_name(m.group(2).strip())
        if not path.exists():
            return m.group(0)
        page = path.read_text(encoding="utf-8")
        kind, label = (m.group(1) or "").lower(), (m.group(3) or "").strip()
        if kind in ("lst", "section"):
            q = r"""\s*=\s*["']?""" + re.escape(label) + r"""["']?\s*/?>"""
            parts = re.findall(r"<section\s+begin" + q + r"(.*?)<section\s+end" + q, page, re.S | re.I)
            return "\n".join(parts)
        if kind == "lsth":
            hm = re.search(r"^(=+)\s*" + re.escape(label) + r"\s*\1\s*$", page, re.M)
            if not hm:
                return ""
            nxt = re.search(r"^={1,%d}[^=]" % len(hm.group(1)), page[hm.end():], re.M)
            return page[hm.end(): hm.end() + nxt.start() if nxt else len(page)]
        only = re.findall(r"<onlyinclude>(.*?)</onlyinclude>", page, re.S)
        page = "\n".join(only) if only else re.sub(r"<noinclude>.*?</noinclude>", "", page, flags=re.S)
        return re.sub(r"</?includeonly>", "", page)
    return TRANSCLUDE.sub(sub, text)


# ------------------------------------------------------------ page structure
def _headings(text: str) -> list[tuple[int, int, str]]:
    """(position, level, title) of every heading."""
    return [(m.start(), len(m.group(1)), plain(m.group(2)))
            for m in re.finditer(r"^(={2,5})\s*(.*?)\s*\1\s*$", text, re.M)]


def _path(heads: list, pos: int) -> list[str]:
    """The headings above `pos`, outermost first."""
    path: dict[int, str] = {}
    for p, lvl, title in heads:
        if p > pos:
            break
        path = {k: v for k, v in path.items() if k < lvl}
        path[lvl] = title
    return [path[k] for k in sorted(path)]


def _round_of(path: list[str]) -> tuple[str, str]:
    """(round, slot) from a heading path: the outermost heading that names a
    round (not "Matches", "Knockout stage"...; a group heading stays inside
    its round), and the round plus a replay / second-leg marker for dating."""
    rnd = ""
    for title in path:
        if rnd and (SUBSLOT.search(title) or re.search(r"\b(?:group|pool|zone|section|region)\b", title, re.I)):
            break
        rnd = title
        if not GENERIC.match(title):
            break
    sub = next((t for t in path if SUBSLOT.search(t) and t != rnd), "")
    return rnd, rnd + (f" / {sub}" if sub else "")


def _boxes(text: str) -> list[dict]:
    out = []
    for m in re.finditer(r"\{\{\s*football ?box(?:[ _]collapsible)?\s*\|", text, re.I):
        body = template_at(text, m.start())
        _, p = params(body)
        h, a = club(p.get("team1", "")), club(p.get("team2", ""))
        sc = score(p.get("score", ""))
        if not (h and a and sc):
            continue
        if p.get("result", "").strip().upper() in ("W/O", "AWD", "AW"):
            continue
        pens = p.get("penaltyscore") or p.get("penalties") or ""
        pm = SCORE.search(plain(pens))
        if pm:
            sc["pens"], sc["aet"] = (int(pm.group(1)), int(pm.group(2))), True
        if re.search(r"yes|y|true|1", p.get("aet", ""), re.I) and p.get("aet", "").strip():
            sc["aet"] = True
        out.append(dict(sc, fmt="box", pos=m.start(), home=h, away=a, leg=None,
                        date=p.get("date", ""), venue=p.get("stadium", "")))
    return out


def _onelegs(text: str) -> list[dict]:
    out = []
    for m in re.finditer(r"\{\{\s*OneLegResult\s*\|", text, re.I):
        pos, _ = params(template_at(text, m.start()))
        cells = [c for c in pos if c.strip()]           # team1, score, team2 (blank cells between)
        if len(cells) < 3:
            continue
        h, a, sc = club(cells[0]), club(cells[2]), score(cells[1])
        if h and a and sc:
            out.append(dict(sc, fmt="oneleg", pos=m.start(), home=h, away=a, leg=None, date="", venue=""))
    return out


def _twolegs(text: str) -> list[dict]:
    out = []
    for m in re.finditer(r"\{\{\s*TwoLegResult\s*\|", text, re.I):
        pos, _ = params(template_at(text, m.start()))
        cells = [c for c in pos if c.strip()]           # team1, agg, team2, leg1, leg2 (blank cells between)
        if len(cells) < 5:
            continue
        t1, t2 = club(cells[0]), club(cells[2])
        if not (t1 and t2):
            continue
        agg = score(cells[1])
        for leg, cell, home, away in ((1, cells[3], t1, t2), (2, cells[4], t2, t1)):
            sc = score(cell)
            if sc is None:
                continue
            if leg == 2:     # printed from team1's side
                sc["hg"], sc["ag"] = sc["ag"], sc["hg"]
                if sc["pens"]:
                    sc["pens"] = sc["pens"][::-1]
                if agg and agg["pens"] and not sc["pens"]:
                    sc["pens"], sc["aet"] = agg["pens"][::-1], True
            out.append(dict(sc, fmt="twoleg", pos=m.start(), home=home, away=away, leg=leg, date="", venue=""))
    return out


def _brackets(text: str) -> list[dict]:
    out = []
    for m in re.finditer(r"\{\{\s*\d*(?:Team|Round)Bracket[^|}]*\|", text, re.I):
        body = template_at(text, m.start())
        _, p = params(body)
        teams: dict[tuple[int, int], str] = {}
        for k, v in p.items():
            mm = re.fullmatch(r"RD(\d+)-team(\d+)", k)
            if mm:
                teams[(int(mm.group(1)), int(mm.group(2)))] = v
        for (rd, n), cell in sorted(teams.items()):
            if n % 2 == 0:
                continue
            t1, t2 = club(cell), club(teams.get((rd, n + 1), ""))
            if not (t1 and t2):
                continue
            label = plain(p.get(f"RD{rd}", f"Round {rd}"))

            def sc_of(team: int, leg: int | None) -> str:
                for w in (2, 1):
                    key = f"RD{rd}-score{team:0{w}d}" + (f"-{leg}" if leg else "")
                    if key in p:
                        return p[key]
                return ""

            legs = [lg for lg in (1, 2, 3) if sc_of(n, lg).strip() and sc_of(n + 1, lg).strip()]
            for leg in legs or [None]:
                a, b = sc_of(n, leg), sc_of(n + 1, leg)
                ma, mb = re.match(r"\s*'*\s*(\d{1,2})", plain(a)), re.match(r"\s*'*\s*(\d{1,2})", plain(b))
                if not (ma and mb) or VOID.search(a + b):
                    continue
                pa = re.search(r"\(\s*(\d{1,2})\s*\)", plain(a)[ma.end():])
                pb = re.search(r"\(\s*(\d{1,2})\s*\)", plain(b)[mb.end():])
                pens = (int(pa.group(1)), int(pb.group(1))) if pa and pb else None
                aet = bool(AET.search(a + b)) or pens is not None
                if leg == 2:
                    home, away, hg, ag = t2, t1, int(mb.group(1)), int(ma.group(1))
                    pens = pens[::-1] if pens else None
                else:
                    home, away, hg, ag = t1, t2, int(ma.group(1)), int(mb.group(1))
                out.append({"fmt": "bracket", "pos": m.start(), "rd": rd, "home": home, "away": away, "hg": hg, "ag": ag,
                            "aet": aet, "pens": pens, "leg": leg if legs and len(legs) > 1 else None,
                            "date": "", "venue": "", "round": label, "neutral": not (legs and len(legs) > 1)})
    return out


def _table_rows(table: str) -> tuple[list[str], list[list[str]]]:
    """(header cells, data rows as cell lists) of one {| ... |} table."""
    header, rows, cur = [], [], []
    for line in table.split("\n")[1:]:
        s = line.strip()
        if s.startswith("|}"):
            break
        if s.startswith("|-") or s.startswith("|+"):
            if cur:
                rows.append(cur)
            cur = []
            continue
        if s.startswith("!"):
            for c in split_top(s[1:], "!!"):
                c = split_top(c, "||")
                header.extend(plain(x.split("|")[-1] if "[[" not in x else x) for x in c)
            continue
        if s.startswith("|"):
            for c in split_top(s[1:], "||"):
                bits = split_top(c, "|")
                # "attr | content": an attribute part has "=" and no link
                content = bits[-1] if len(bits) > 1 and "=" in bits[0] and "[[" not in bits[0] else c
                cur.append(content)
        elif cur:
            cur[-1] += " " + s
    if cur:
        rows.append(cur)
    return header, rows


def _tables(text: str) -> list[dict]:
    out = []
    for m in re.finditer(r"^\{\|", text, re.M):
        end = text.find("\n|}", m.start())
        table = text[m.start(): end + 3 if end > 0 else len(text)]
        if re.search(r"#invoke|Football box|TwoLegResult|OneLegResult", table, re.I):
            continue
        header, rows = _table_rows(table)
        hl = [h.lower() for h in header]
        if any(re.search(r"\b(?:pld|pts|points|w\b|gd)", h) for h in hl) or "team" in hl and "pts" in hl:
            continue                  # a standings table
        date_col = next((i for i, h in enumerate(hl) if "date" in h), None)
        for k, row in enumerate(rows):
            pos = m.start() + k                       # keeps row order within the table
            cells = [c.strip() for c in row]
            scores = [i for i, c in enumerate(cells) if _is_score_cell(c)]
            if not scores:
                continue
            i = scores[0]
            if i == 0 or i + 1 >= len(cells):
                continue
            t1, t2 = club(cells[i - 1]), club(cells[i + 1])
            if not (t1 and t2):
                continue
            rest = " ".join(cells[i + 2:])
            date = cells[date_col] if date_col is not None and date_col < len(cells) else ""
            if not date:
                date = next((c for c in cells if re.search(r"\d{1,2}\s+[A-Z][a-z]+\s+\d{4}", plain(c))), "")
            two_leg = (i + 3 < len(cells) and _is_score_cell(cells[i + 2]) and _is_score_cell(cells[i + 3]))
            if two_leg:
                agg = score(cells[i])
                for leg, cell, home, away in ((1, cells[i + 2], t1, t2), (2, cells[i + 3], t2, t1)):
                    sc = score(cell)
                    if sc is None:
                        continue
                    if leg == 2:
                        sc["hg"], sc["ag"] = sc["ag"], sc["hg"]
                        sc["pens"] = sc["pens"][::-1] if sc["pens"] else (
                            agg["pens"][::-1] if agg and agg["pens"] else None)
                        sc["aet"] = sc["aet"] or sc["pens"] is not None
                    out.append(dict(sc, fmt="table", pos=pos, home=home, away=away, leg=leg,
                                    date="", venue=""))
                continue
            sc = score(cells[i])
            if sc is None:
                continue
            if AET.search(rest):
                sc["aet"] = True
            pm = PENS.search(plain(rest))
            if pm and not sc["pens"]:
                sc["pens"], sc["aet"] = (int(pm.group(1)), int(pm.group(2))), True
            out.append(dict(sc, fmt="table", pos=pos, home=t1, away=t2, leg=None, date=date, venue=""))
    return out


def _is_score_cell(cell: str) -> bool:
    s = plain(cell)
    if VOID.search(s):
        return bool(SCORE.search(s))     # kept as a score position, dropped by score()
    return bool(re.fullmatch(r"\(?\s*(?:\(a\)\s*)?\d{1,2}\s*[–—−:-]\s*\d{1,2}\b.{0,40}", s)) and not re.search(
        r"\d{4}", s)


# ------------------------------------------------------------ the page
def _key(team: tuple[str, str]) -> str:
    return re.sub(r"[^a-z0-9]", "", team[1].lower())


def _ids(team: tuple[str, str]) -> set[str]:
    return {team[0], _key(team), re.sub(r"[^a-z0-9]", "", team[0].lower())}


def _same(r: dict, k: dict) -> bool:
    """r repeats kept match k (see parse_page)."""
    if r["fmt"] != "bracket" and k["fmt"] != "bracket" and r.get("round") != k.get("round"):
        return False
    rh, ra, kh, ka = _ids(r["home"]), _ids(r["away"]), _ids(k["home"]), _ids(k["away"])
    if (rh & kh or ra & ka) and (r["hg"], r["ag"]) == (k["hg"], k["ag"]):
        return True
    return r["fmt"] == "bracket" and bool(rh & ka or ra & kh) and (r["hg"], r["ag"]) == (k["ag"], k["hg"])


def parse_page(text: str, season: int) -> list[dict]:
    """Every played match on a cup season page, once each, in page order.
    Dicts: home, away, home_name, away_name, hg, ag, aet, pens, leg, fmt,
    round (level-2 heading, or the bracket's round label), slot (the round
    plus a replay/second-leg sub-heading, for dating), date (Timestamp or
    None), neutral (None unless the layout says), pos."""
    text = clean(text)
    heads = _headings(text)
    found = _boxes(text) + _onelegs(text) + _twolegs(text) + _tables(text) + _brackets(text)
    for r in found:
        rnd, slot = _round_of(_path(heads, r["pos"]))
        if r.get("round"):                     # a bracket's own label
            slot = r["round"]
        else:
            r["round"] = rnd
        r["slot"] = slot
        if r["leg"] is None and re.search(r"second leg|2nd leg|return leg", slot, re.I):
            r["leg"] = 2
        r["date"] = parse_date(r["date"], season) if r["date"] else None
        r.setdefault("neutral", None)
    # Keep each match once: the most detailed layout wins. Formats link the
    # same club under different articles or labels ("1. FC Köln" / "Köln"),
    # so a later listing is a duplicate when it shares one club (by article
    # or display name) and the score with a kept match: in the same round
    # for tables and result rows, anywhere in the season for brackets
    # (whose round labels and venues differ from the sections').
    found.sort(key=lambda r: (PRIORITY[r["fmt"]], r["pos"]))
    kept: list[dict] = []
    out = []
    for r in found:
        if r["fmt"] != "box" and any(_same(r, k) for k in kept):
            continue
        kept.append(r)
        out.append(r)
    # brackets left after that may repeat within themselves (a tie shown in
    # two brackets): de-duplicate on (pair, leg, score)
    final, bseen = [], set()
    for r in sorted(out, key=lambda r: r["pos"]):
        if r["fmt"] == "bracket":
            k = (frozenset((r["home"][0], r["away"][0])), r["leg"], r["hg"], r["ag"])
            if k in bseen:
                continue
            bseen.add(k)
        final.append(r)
    # A pairing met again in the same slot without leg labels is a replay (or
    # a second leg) printed under the round's own heading: give it a slot of
    # its own so it is dated after the first meeting.
    met: dict = {}
    for r in final:
        k = (r["slot"], frozenset((r["home"][0], r["away"][0])))
        met[k] = met.get(k, 0) + 1
        if r["leg"] is None and met[k] > 1 and not re.search(r"group|pool", r["slot"], re.I):
            r["slot"] += f" / meeting {met[k]}"
    for r in final:
        (r["home"], r["home_name"]), (r["away"], r["away_name"]) = r["home"], r["away"]
    return final


def page_span(text: str, season: int) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """First and last date the page's lead or infobox gives for the competition."""
    lead = clean(text)[:6000]
    dates = []
    for m in re.finditer(r"\d{1,2}\s+[A-Z][a-z]+\s+\d{4}|[A-Z][a-z]+\s+\d{1,2},\s+\d{4}", lead):
        d = parse_date(m.group(0), season)
        if d is not None:
            dates.append(d)
    return (min(dates), max(dates)) if dates else (None, None)
