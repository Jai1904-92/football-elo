"""Plain-text parsers for league results as RSSSF and Wikipedia print them.

Three layouts are recognised, independent of country:
  - results grids: one row per club, one cell per opponent, the diagonal marked
    (X, xxx, ***, -); columns follow row order
  - round lists: "Round N" headings (optionally dated) with one match per line
  - stage pairs (Italian pages): "Stages a-b" headings, each line holding the
    first-leg score and the return-leg score (home and away swapped)

Parsers return plain dicts; sources.py turns them into match frames.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

DIAG = r"X|x{2,3}|\*{3}|-{1,3}|=+"
SCORE = r"\d{1,2}-\d{1,2}"
_TRAIL_SCORE = re.compile(rf"\s*({SCORE})[a-z*+]?\s*$")
_TRAIL_DIAG = re.compile(rf"(?:\s+({DIAG})|(\*{{3}}))\s*$")   # "***" may touch the name

# typing slips seen in the pages: letter O for zero, "0.0" / "0,1", two cells
# run together ("3-0-2-0"), a row number "1l"
_FIXES = [(re.compile(r"(?<=\s)O(?=-\d)|(?<=\d-)O(?=\s|$)"), "0"),
          (re.compile(r"(?<=\s)(\d)[.,](\d)(?=\s|$)"), r"\1-\2"),
          (re.compile(rf"(?<=\s)({SCORE})-({SCORE})(?=\s|$)"), r"\1 \2"),
          (re.compile(r"^(\s*\d)l(?=\s)"), r"\g<1>1")]


def _fix(line: str) -> str:
    for pat, rep in _FIXES:
        line = pat.sub(rep, line)
    return line


def page_text(path: Path) -> str:
    """Page as plain text: tags stripped, entities decoded. RSSSF pages are
    Latin-1; a UTF-8 file is detected and decoded as such."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\r", "")


def _grid_row(line: str) -> tuple[str, list[tuple[int, str]]] | None:
    """Split a line into (club name, [(column, cell)]) when it ends in a run
    of at least three score/diagonal cells. Scores may touch the name
    ("C.d.Sangro1-3"). Columns are character offsets of each cell's end."""
    line = _fix(line)
    cells, rest = [], line.rstrip()
    while True:
        m = _TRAIL_SCORE.search(rest) or _TRAIL_DIAG.search(rest)
        if not m:
            break
        g = 1 if m.group(1) else 2
        cells.append((m.end(g), m.group(g)))
        rest = rest[:m.start(g)]
    if len(cells) < 3:
        return None
    name = re.sub(r"^\s*\d{1,2}\s*[.)]?\s*", "", rest).strip()
    if not name or re.fullmatch(r"[\d\s.-]*", name):
        return None
    return name, cells[::-1]


def _square(rows: list[tuple[str, list[tuple[int, str]]]]) -> list[list[str | None]] | None:
    """Cells of an n-row run as an n x n matrix, or None. Rows with fewer
    than n cells (blanks for matches not played) are placed by column, using
    the column ends of the complete rows."""
    n = len(rows)
    full = [c for _, c in rows if len(c) == n]
    if len(full) < max(2, n // 2) or any(len(c) > n for _, c in rows):
        return None
    ends = [sorted(c[k][0] for c in full)[len(full) // 2] for k in range(n)]   # median end per column
    out = []
    for _, c in rows:
        if len(c) == n:
            out.append([cell for _, cell in c])
            continue
        row: list[str | None] = [None] * n
        for end, cell in c:
            k = min(range(n), key=lambda k: abs(ends[k] - end))
            if abs(ends[k] - end) > 2 or row[k] is not None:
                return None
            row[k] = cell
        out.append(row)
    return out


def grids(text: str, min_teams: int = 6) -> list[dict]:
    """Every results grid in `text`, in page order, as
    {"teams": [...], "scores": {(i, j): (hg, ag)}, "start": char offset}.
    A grid is a run of consecutive rows where row i has one cell per club and
    its diagonal at position i. Unplayed cells (blank, or anything but a
    score) are skipped. Runs that don't form a square grid come back as
    {"reject": True, ...}."""
    out, run = [], []
    pos = 0

    def close():
        nonlocal run
        if len(run) >= min_teams:
            rows = [r for _, r in run]
            m = _square(rows)
            if m and all(c is not None and re.fullmatch(DIAG, c) for c in (m[i][i] for i in range(len(m)))):
                scores = {}
                for i, cells in enumerate(m):
                    for j, cell in enumerate(cells):
                        if i != j and cell and re.fullmatch(SCORE, cell):
                            hg, ag = cell.split("-")
                            scores[(i, j)] = (int(hg), int(ag))
                out.append({"teams": [name for name, _ in rows], "scores": scores, "start": run[0][0]})
            else:
                out.append({"reject": True, "start": run[0][0], "rows": len(rows),
                            "cells": sorted({len(c) for _, c in rows})})
        run = []

    for line in text.split("\n"):
        row = _grid_row(line)
        if row:
            run.append((pos, row))
        else:
            close()
        pos += len(line) + 1
    close()
    return out


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                                       "oct", "nov", "dec"], start=1)}
_MONTHS.update({"gen": 1, "mag": 5, "giu": 6, "lug": 7, "ago": 8, "set": 9, "ott": 10, "dic": 12})   # Italian
_ROUND = re.compile(r"^\s*(?:(?:Extra\s+)?(?:Round|Matchday|Giornata|Stage)\s*(\d+)?|(\d+)\s*a\s+giornata)\b(.*)$",
                    re.I)      # "Round 3 (August 27)", "Extra Round [Oct 27]", "1a GIORNATA 27 ago 1961"
_DATE = re.compile(r"\b(\d{1,2})?\s*([A-Z][a-z]{2})[a-z]*\.?\s*(\d{1,2})?\b")
# "Home  2-1 Away" (Dutch pages) and "Home - Away   2-1" (Italian pages)
_SCORE_MID = re.compile(rf"^\s*(\S.*?\S)\s+({SCORE})\s+(\S.*?)\s*$")
_SCORE_END = re.compile(rf"^\s*(\S.*?\S)\s+-\s+(\S.*?\S)\s+({SCORE})\s*(.*)$")


def _month_day(s: str) -> tuple[int, int] | None:
    """'August 27', '27 Aug', 'Aug 13' -> (month, day)."""
    for m in _DATE.finditer(s):
        mon = _MONTHS.get(m.group(2).lower()[:3])
        day = m.group(3) or m.group(1)
        if mon and day:
            return mon, int(day)
    return None


def round_lists(text: str) -> list[dict]:
    """Matches under "Round N" headings, with the round and, where printed,
    (month, day): from the heading ("Round 1 (August 27)") or from a
    bracketed date line ("[Aug 13]") before the match. Lines after a blank
    line that are not matches end nothing; scorer lines ("[...]") are
    skipped. Returns [{"round", "md", "home", "away", "hg", "ag", "note"}]."""
    out, rnd, md = [], None, None
    for line in text.split("\n"):
        m = _ROUND.match(line)
        if m and (m.group(1) or m.group(2) or rnd is not None):
            num = m.group(1) or m.group(2)
            rnd = int(num) if num else rnd    # "Extra Round": keep the round number
            md = _month_day(m.group(3))
            continue
        if rnd is None:
            continue
        s = re.sub(r"^\{", "[", line.strip())
        if len(s) <= 40 and _month_day(s) and re.fullmatch(r"\[?[A-Za-z]{3,9}\.?\s+\d{1,2}(,?\s+\d{4})?\]?"
                                                           r"|\[?\d{1,2}\s+[A-Za-z]{3,9}\.?(\s+\d{4})?\]?", s):
            md = _month_day(s)       # "[Aug 13]", "May 5", "27 August 1995"
            continue
        d = re.match(r"\[(\d{1,2})/(\d{1,2})/\d{4}\]\s*(.*)$", s)
        if d:                        # "[11/09/2004] Home  3-1 Away" (Serie B 2004/05)
            md, line = (int(d.group(2)), int(d.group(1))), d.group(3)
            s = line.strip()
        if not s or s.startswith("[") or re.search(r"\babd\b|abandoned", s, re.I):
            continue                 # scorers, notes, abandoned matches (replayed later)
        line = re.sub(r"\s*\[.*$", "", line)        # trailing note: "2-1 Ajax  [awarded ...]"
        m = _SCORE_END.match(line)
        if m:
            hg, ag = m.group(3).split("-")
            out.append({"round": rnd, "md": md, "home": m.group(1), "away": m.group(2),
                        "hg": int(hg), "ag": int(ag), "note": m.group(4).strip()})
            continue
        m = _SCORE_MID.match(line)
        if m and re.search(r"[A-Za-z]{2}", m.group(1)) and not re.match(r"\d+\.|.*\s\d+\s+\d+\s", m.group(1)):
            hg, ag = m.group(2).split("-")
            away = re.sub(r"\s{2,}.*$", "", m.group(3))
            if not re.search(r"[A-Za-z]{2}", away):
                continue             # a league-table row ("1.Heracles 36 23 6 7  67-34  75")
            out.append({"round": rnd, "md": md, "home": m.group(1), "away": away,
                        "hg": int(hg), "ag": int(ag), "note": m.group(3)[len(away):].strip()})
    return out


_STAGES = re.compile(r"^\s*Stages?\s+(\d+)\s*-\s*(\d+)\s*(?:(\d{1,2})\.(\d{1,2})\.?\s+(\d{1,2})\.(\d{1,2})\.?)?\s*$",
                     re.I)
_PAIR = re.compile(r"^\s*(\S.*?\S)\s+-\s+(\S.*?\S)\s*=\s*(\d+)\s*-\s*(\d+)\s*\*\s*(\d+)\s*-\s*(\d+)\s*$")


def stage_pairs(text: str) -> list[dict]:
    """Italian-style pairs: under "Stages a-b", "Home - Away = 1 - 0 * 2 - 3"
    is round a (Home at home, won 1-0) and round b (Away at home, won 3-2):
    both scores are printed from Home's side. Some headings carry both
    rounds' dates ("Stages 1-20   13.09.  07.02.")."""
    out, first, second, md1, md2 = [], None, None, None, None
    for line in text.split("\n"):
        m = _STAGES.match(line)
        if m:
            first, second = int(m.group(1)), int(m.group(2))
            md1 = (int(m.group(4)), int(m.group(3))) if m.group(3) else None
            md2 = (int(m.group(6)), int(m.group(5))) if m.group(5) else None
            continue
        m = _PAIR.match(line) if first else None
        if m:
            a, b = m.group(1), m.group(2)
            out.append({"round": first, "md": md1, "home": a, "away": b,
                        "hg": int(m.group(3)), "ag": int(m.group(4)), "note": ""})
            out.append({"round": second, "md": md2, "home": b, "away": a,      # printed from a's side
                        "hg": int(m.group(6)), "ag": int(m.group(5)), "note": ""})
    return out


def sections(text: str, start: str, end: str) -> list[tuple[str, str]]:
    """(heading, body) for each line fully matching `start` (case-insensitive),
    the body running to the next `start` or `end` line. A heading's group
    letter, if any, stays in the heading ("Eerste divisie A")."""
    s_re, e_re = re.compile(start, re.I), re.compile(end, re.I)
    lines = text.split("\n")
    out, head, body = [], None, []
    for line in lines:
        st = line.strip()
        if s_re.fullmatch(st):
            if head is not None:
                out.append((head, "\n".join(body)))
            head, body = st, []
        elif head is not None and e_re.fullmatch(st):
            out.append((head, "\n".join(body)))
            head, body = None, []
        elif head is not None:
            body.append(line)
    if head is not None:
        out.append((head, "\n".join(body)))
    return out


def clean_name(name: str) -> str:
    """Club name without footnote marks ("Bari*", "Ajax (*)", "Roda [1]")."""
    name = re.sub(r"\s*(\(\*+\)|\[\w*\]|\*+)\s*$", "", name.strip())
    return re.sub(r"\s{2,}", " ", name)


def section_matches(body: str) -> tuple[list[dict], list[dict]]:
    """(ordered, grid) matches in one league section. `ordered` comes from
    round lists or stage pairs (whichever finds more) and carries round and
    any printed dates; `grid` from complete results grids, each match with a
    "group" index and the grid size "n"."""
    rl = round_lists(body)
    sp = stage_pairs(body)
    ordered = sp if len(sp) >= len(rl) else rl
    for m in ordered:
        m["home"], m["away"] = clean_name(m["home"]), clean_name(m["away"])
    grid = []
    for g, block in enumerate(x for x in grids(body) if "teams" in x):
        teams = [clean_name(t) for t in block["teams"]]
        for (i, j), (hg, ag) in block["scores"].items():
            grid.append({"round": None, "md": None, "group": g, "n": len(teams), "i": i, "j": j,
                         "home": teams[i], "away": teams[j], "hg": hg, "ag": ag, "note": ""})
    return ordered, grid


def order_grid(ordered: list[dict], grid: list[dict]) -> tuple[list[dict], int]:
    """Give grid matches the round (and date) of the same fixture in
    `ordered`, whose club names may be spelt differently. Each ordered name
    is mapped to the same grid name, else to the grid name it most often
    lines up with on score against an opponent already mapped; grid matches
    left without a round keep round None. Returns (grid matches, number of
    fixtures whose score still differs between the two; the grid's is kept)."""
    grid_names = {g["home"] for g in grid} | {g["away"] for g in grid}
    name = {n: n for n in {o["home"] for o in ordered} | {o["away"] for o in ordered} if n in grid_names}
    by_side: dict = {}
    for g in grid:
        by_side.setdefault(("away", g["away"], g["hg"], g["ag"]), []).append(g["home"])
        by_side.setdefault(("home", g["home"], g["hg"], g["ag"]), []).append(g["away"])
    for _ in range(3):
        votes: dict = {}
        for o in ordered:
            for me, other, side in ((o["home"], o["away"], "away"), (o["away"], o["home"], "home")):
                if me in name or other not in name:
                    continue
                for cand in by_side.get((side, name[other], o["hg"], o["ag"]), []):
                    votes.setdefault(me, {}).setdefault(cand, 0)
                    votes[me][cand] += 1
        taken = set(name.values())
        new = {a: max(v, key=v.get) for a, v in votes.items() if max(v, key=v.get) not in taken}
        if not new:
            break
        name.update(new)
    slot = {(name.get(o["home"]), name.get(o["away"])): o for o in ordered}
    # a club whose grid results disagree with the round list again and again
    # has a misplaced grid row (1966/67 swaps Messina's and Modena's): for its
    # matches the round list's results win
    wrong: dict = {}
    for g in grid:
        o = slot.get((g["home"], g["away"]))
        if o and (o["hg"], o["ag"]) != (g["hg"], g["ag"]):
            for c in (g["home"], g["away"]):
                wrong[c] = wrong.get(c, 0) + 1
    misplaced = {c for c, n in wrong.items() if n >= 10}
    out, clashes = [], 0
    for g in grid:
        o = slot.get((g["home"], g["away"]))
        if o:
            if (o["hg"], o["ag"]) != (g["hg"], g["ag"]):
                if {g["home"], g["away"]} & misplaced:
                    g = dict(g, hg=o["hg"], ag=o["ag"])
                else:
                    clashes += 1
            g = dict(g, round=o["round"], md=o["md"])
        out.append(g)
    return out, clashes
