"""Bronze layer: raw source files, downloaded as-is."""
from __future__ import annotations

import datetime as dt
import logging
import re
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)


def season_code(start_year: int) -> str:
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def current_season(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return today.year if today.month >= 7 else today.year - 1


def _download(url: str, dest: Path, params: dict | None = None, attempts: int = 4,
              headers: dict | None = None) -> bool:
    """Download to `dest`. Returns False for a 404, or when the server keeps
    failing (5xx, timeouts) after retries; a cached copy, if any, is kept."""
    for i in range(attempts):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=120)
        except requests.RequestException as e:
            err = str(e)
        else:
            if resp.status_code == 404:
                return False
            if resp.status_code < 500:
                resp.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(resp.content)
                log.info("downloaded %s -> %s (%d bytes)", resp.url, dest, len(resp.content))
                return True
            err = f"HTTP {resp.status_code}"
        time.sleep(2 ** i)
    log.warning("giving up on %s after %d attempts (%s)%s", url, attempts, err,
                "; keeping the cached copy" if dest.exists() else "")
    return False


def fetch_engsoccerdata(cfg: dict, force: bool = False) -> list[Path]:
    src = cfg["sources"]["engsoccerdata"]
    out = []
    for name in src["files"]:
        dest = cfg["paths"]["bronze"] / "engsoccerdata" / f"{name}.csv"
        if force or not dest.exists():
            _download(src["url_template"].format(name=name), dest)
        out.append(dest)
    return out


def fetch_football_data(cfg: dict, seasons: list[int] | None = None, force: bool = False) -> list[Path]:
    """Download football-data.co.uk files. Past seasons are cached; the
    current season is always re-downloaded since it changes weekly."""
    src = cfg["sources"]["football_data"]
    now = current_season()
    seasons = seasons or list(range(src["first_season"], now + 1))
    out = []
    for season in seasons:
        for div in src["divisions"]:
            dest = cfg["paths"]["bronze"] / "football_data" / f"{season_code(season)}_{div}.csv"
            if force or season >= now or not dest.exists():
                url = src["url_template"].format(season_code=season_code(season), division=div)
                if not _download(url, dest):
                    continue
            out.append(dest)
    return out


def fetch_transfermarkt(cfg: dict, force: bool = False) -> list[Path]:
    """transfermarkt-datasets stopped updating in July 2026, so cache it."""
    src = cfg["sources"]["transfermarkt"]
    out = []
    for name in src["files"]:
        dest = cfg["paths"]["bronze"] / "transfermarkt" / f"{name}.csv.gz"
        if force or not dest.exists():
            _download(src["url_template"].format(name=name), dest)
        out.append(dest)
    return out


def fetch_datarozhlas(cfg: dict, force: bool = False) -> Path:
    dest = cfg["paths"]["bronze"] / "datarozhlas" / "matches.csv"
    if force or not dest.exists():
        _download(cfg["sources"]["datarozhlas"]["url"], dest)
    return dest


def _season_fields(season: int) -> dict:
    end = season + 1
    return {"season": season, "end2": f"{end % 100:02d}", "end": f"{end % 100:02d}" if end < 2010 else str(end),
            "endw": str(end) if end % 100 == 0 else f"{end % 100:02d}"}


def fetch_rsssf_finals(cfg: dict, force: bool = False) -> list[Path]:
    """RSSSF championship-history pages (one page per competition, cached once)."""
    out = []
    for spec in cfg["sources"].get("rsssf_finals", {}).values():
        dest = cfg["paths"]["bronze"] / "rsssf" / spec["folder"] / spec["file"]
        if force or not dest.exists():
            if not _download(spec["url"], dest, headers={"User-Agent": "Mozilla/5.0 (football-elo research)"}):
                continue
        out.append(dest)
    return out


def fetch_rsssf(cfg: dict, force: bool = False) -> list[Path]:
    """RSSSF season pages (static history: cached once)."""
    out = []
    for spec in cfg["sources"]["rsssf"]["leagues"].values():
        first, last = spec["seasons"]
        urls = {s: spec["url_template"].format(**_season_fields(s)) for s in range(first, last + 1)}
        urls.update(spec.get("extra_pages", {}))
        for season, url in urls.items():
            dest = cfg["paths"]["bronze"] / "rsssf" / spec["folder"] / f"{season}.html"
            if force or not dest.exists():
                if not _download(url, dest, headers={"User-Agent": "Mozilla/5.0 (football-elo research)"}):
                    continue
                time.sleep(1)
            out.append(dest)
    return out


def fetch_wikipedia(cfg: dict, force: bool = False) -> list[Path]:
    """Raw wikitext of Wikipedia season articles (cached once)."""
    src = cfg["sources"]["wikipedia"]
    out = []
    for spec in (s for specs in src["leagues"].values() for s in specs):
        first, last = spec["seasons"]
        for season in range(first, last + 1):
            dest = cfg["paths"]["bronze"] / "wikipedia" / spec["folder"] / f"{season}.txt"
            if force or not dest.exists():
                title = spec["title_template"].format(**_season_fields(season))
                for _ in range(3):   # action=raw returns a redirect's own text: follow it
                    if not _download(src["url"], dest, params={"title": title, "action": "raw"},
                                     headers={"User-Agent": "football-elo/0.1 (research project)"}):
                        break
                    time.sleep(0.5)
                    m = re.match(r"\s*#REDIRECT\s*\[\[([^\]|#]+)", dest.read_text(encoding="utf-8"), re.I)
                    if not m:
                        break
                    title = m.group(1).strip()
                if not dest.exists():
                    continue
            out.append(dest)
    return out


def fetch_espn(cfg: dict, years: list[int] | None = None, force: bool = False) -> list[Path]:
    """One scoreboard file per league slug per calendar year. Past years are
    cached; the current year (and last year, for late corrections in
    January) is always re-downloaded."""
    src = cfg["sources"]["espn"]
    this_year = dt.date.today().year
    years = years or list(range(src["first_year"], this_year + 1))
    out = []
    for slug in src["slugs"]:
        for year in years:
            dest = cfg["paths"]["bronze"] / "espn" / slug / f"{year}.json"
            if force or year >= this_year - 1 or not dest.exists():
                if not _download(src["url_template"].format(slug=slug), dest,
                                 params={"dates": str(year), "limit": 1000}):
                    continue
                time.sleep(0.3)
            out.append(dest)
    return out


def fetch_all(cfg: dict) -> None:
    fetch_engsoccerdata(cfg)
    fetch_football_data(cfg)
    fetch_transfermarkt(cfg)
    fetch_datarozhlas(cfg)
    fetch_rsssf(cfg)
    fetch_rsssf_finals(cfg)
    fetch_wikipedia(cfg)
    fetch_espn(cfg)
