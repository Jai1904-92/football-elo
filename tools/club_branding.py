"""Crest URLs and colours for the site, written to config/club_branding.csv.

For each club with an ESPN id (club_aliases.csv), ESPN's team record gives a
crest (the dark-background variant when listed) and primary/alternate
colours. Clubs without one use the Transfermarkt crest. Where ESPN has no
usable colours, the two most common colours of the crest are used instead.
Crests are only linked, never stored; downloaded team records and crests
are cached under data/bronze/branding/.

    python tools/club_branding.py            # league clubs and their opponents
"""
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_elo.config import load_config  # noqa: E402

ESPN_TEAM = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/teams/{id}"
TM_CREST = "https://tmssl.akamaized.net/images/wappen/head/{id}.png"
UA = {"User-Agent": "football-elo/0.1 (research project)"}


def get_cached(url: str, path: Path, binary=False):
    if not path.exists():
        r = requests.get(url, headers=UA, timeout=30)
        time.sleep(0.15)
        if r.status_code != 200:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"")
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    data = path.read_bytes()
    if not data:
        return None
    return data if binary else json.loads(data)


def hexok(h) -> str | None:
    if not isinstance(h, str) or len(h.strip("#")) != 6:
        return None
    return "#" + h.strip("#").lower()


def crest_colours(png: bytes) -> tuple[str | None, str | None]:
    """The two most common colours of a crest, ignoring transparent pixels
    and merging near-identical shades."""
    try:
        im = Image.open(io.BytesIO(png)).convert("RGBA").resize((96, 96))
    except Exception:
        return None, None
    a = np.asarray(im).reshape(-1, 4)
    a = a[a[:, 3] > 200][:, :3]
    if len(a) < 50:
        return None, None
    q = (a // 32) * 32 + 16                     # 8 levels per channel
    keys, counts = np.unique(q, axis=0, return_counts=True)
    order = np.argsort(-counts)
    picked = []
    for i in order:
        c = keys[i]
        if any(np.abs(c.astype(int) - p.astype(int)).sum() < 96 for p in picked):
            continue
        picked.append(c)
        if len(picked) == 3:
            break
    # prefer a chromatic or dark colour as primary over plain white
    picked.sort(key=lambda c: (c.min() > 200, 0))
    hexes = ["#%02x%02x%02x" % tuple(int(v) for v in c) for c in picked]
    return (hexes + [None, None])[0], (hexes + [None, None])[1]


PLAIN = {"#000000", "#ffffff", "#111111", "#1a1a1a", "#fefefe"}


def crest_accent(png: bytes) -> str | None:
    """The crest's most common saturated colour (gold, blue, ...), if any."""
    try:
        im = Image.open(io.BytesIO(png)).convert("RGBA").resize((96, 96))
    except Exception:
        return None
    a = np.asarray(im).reshape(-1, 4)
    a = a[a[:, 3] > 200][:, :3].astype(int)
    mx, mn = a.max(axis=1), a.min(axis=1)
    sat = a[(mx > 70) & ((mx - mn) / np.maximum(mx, 1) > 0.35)]
    if len(sat) < 0.04 * max(len(a), 1):
        return None
    q = (sat // 32) * 32 + 16
    keys, counts = np.unique(q, axis=0, return_counts=True)
    return "#%02x%02x%02x" % tuple(int(v) for v in keys[counts.argmax()])


def main():
    cfg = load_config()
    cache = cfg["paths"]["bronze"] / "branding"
    al = pd.read_csv(cfg["aliases"], dtype=str)
    clubs = pd.read_parquet(cfg["paths"]["silver"] / "clubs.parquet")
    m = pd.read_parquet(cfg["paths"]["silver"] / "matches.parquet")
    league = set(clubs.loc[clubs["league_club"], "club"])
    opp = set(m.loc[m["home_club"].isin(league), "away_club"]) | set(m.loc[m["away_club"].isin(league), "home_club"])
    wanted = sorted(league | opp)

    espn_ids = al[al["source"] == "espn"].groupby("club")["source_name"].apply(list).to_dict()
    tm_ids = al[al["source"] == "transfermarkt"].groupby("club")["source_name"].apply(list).to_dict()

    rows = []
    for n, club in enumerate(wanted):
        logo = primary = secondary = None
        source = None
        for eid in espn_ids.get(club, []):
            team = get_cached(ESPN_TEAM.format(id=eid), cache / "espn" / f"{eid}.json")
            t = (team or {}).get("team")
            if not t:
                continue
            logos = {tuple(l.get("rel", [])): l["href"] for l in t.get("logos", [])}
            dark = next((h for rel, h in logos.items() if "dark" in rel), None)
            logo = dark or next(iter(logos.values()), None)
            primary, secondary = hexok(t.get("color")), hexok(t.get("alternateColor"))
            source = "espn"
            if logo:
                break
        if not logo:
            for tid in tm_ids.get(club, []):
                url = TM_CREST.format(id=tid)
                if get_cached(url, cache / "tm" / f"{tid}.png", binary=True):
                    logo, source = url, "transfermarkt"
                    break
        # colours from the crest when ESPN gave none (or only black/white placeholders)
        if logo and club in league and (primary is None or {primary, secondary} <= {"#000000", "#ffffff", None}):
            key = logo.rsplit("/", 2)[-2] + "_" + logo.rsplit("/", 1)[-1]
            png = get_cached(logo, cache / "crests" / key, binary=True)
            if png:
                p2, s2 = crest_colours(png)
                primary, secondary = p2 or primary, s2 or secondary
                source = (source or "") + "+crest"
        # ESPN's alternate colour is often an away kit: for black/white clubs take the
        # crest's own colour instead, or the other of black/white when it has none
        if logo and club in league and primary in PLAIN:
            key = logo.rsplit("/", 2)[-2] + "_" + logo.rsplit("/", 1)[-1]
            png = get_cached(logo, cache / "crests" / key, binary=True)
            accent = crest_accent(png) if png else None
            secondary = accent or ("#ffffff" if primary != "#ffffff" else "#000000")
            source = (source or "") + "+crest2"
        rows.append({"club": club, "logo": logo, "primary": primary, "secondary": secondary, "source": source})
        if n % 200 == 0:
            print(f"{n}/{len(wanted)}", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(cfg["paths"]["silver"].parents[1] / "config" / "club_branding.csv", index=False, lineterminator="\n")
    lg = out[out["club"].isin(league)]
    print(f"{len(out)} clubs; league clubs with a crest {lg['logo'].notna().sum()}/{len(lg)}, "
          f"with colours {lg['primary'].notna().sum()}/{len(lg)}")
    print(out["source"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
