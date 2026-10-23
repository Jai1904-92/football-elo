"""Silver layer: one cleaned match table across competitions, with canonical
club names and a club registry.

Canonical names are engsoccerdata's. Other sources map through
config/club_aliases.csv (source, source_name, club); for Transfermarkt and
ESPN source_name is the source's club id.
"""
from __future__ import annotations

import logging
from functools import cache

import pandas as pd

from . import sources

log = logging.getLogger(__name__)

MATCH_COLUMNS = ["match_id", "match_date", "season", "competition", "comp_type", "tier", "round", "leg",
                 "home_club", "away_club", "home_goals", "away_goals", "neutral", "extra_time",
                 "home_pens", "away_pens", "source"]


class SourceReader:
    """Reads (and caches) each source once per build."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.bronze = cfg["paths"]["bronze"]

    def read(self, source: str, competition: str) -> pd.DataFrame:
        df = self._read(source, competition)
        for c in self.cfg.get("corrections", []):
            if c["source"] == source and c["competition"] == competition:
                hit = df["season"] == c["season"]
                for col in ("home_club", "away_club"):
                    df.loc[hit & (df[col] == c["club"]), col] = c["to"]
        return df

    def _read(self, source: str, competition: str) -> pd.DataFrame:
        if source == "transfermarkt":
            df = self._transfermarkt()
        elif source == "espn":
            df = self._espn()
        elif source == "football_data":
            df = self._football_data()
        elif source == "datarozhlas":
            df = self._datarozhlas()
        elif source == "rsssf":
            df = self._rsssf(competition)
        elif source == "rsssf_finals":
            df = self._rsssf_finals(competition)
        elif source == "wikipedia":
            df = self._wikipedia(competition)
        elif source == "engsoccerdata":
            df = self._engsoccerdata(competition)
        else:
            raise ValueError(f"unknown source {source!r}")
        return df[df["competition"] == competition].copy()

    @cache
    def _transfermarkt(self) -> pd.DataFrame:
        return sources.transfermarkt(self.bronze / "transfermarkt",
                                     self.cfg["sources"]["transfermarkt"]["competitions"])

    @cache
    def _espn(self) -> pd.DataFrame:
        return sources.espn(self.bronze / "espn", self.cfg["sources"]["espn"]["slugs"])

    @cache
    def _datarozhlas(self) -> pd.DataFrame:
        return sources.datarozhlas(self.bronze / "datarozhlas" / "matches.csv",
                                   self.cfg["sources"]["datarozhlas"]["competitions"])

    @cache
    def _rsssf_finals(self, competition: str) -> pd.DataFrame:
        spec = self.cfg["sources"]["rsssf_finals"][competition]
        return sources.rsssf_final_rounds(self.bronze / "rsssf" / spec["folder"] / spec["file"], competition,
                                          self.cfg["competitions"][competition]["country"], tuple(spec["seasons"]))

    @cache
    def _rsssf(self, competition: str) -> pd.DataFrame:
        spec = self.cfg["sources"]["rsssf"]["leagues"][competition]
        return sources.rsssf_league(self.bronze / "rsssf" / spec["folder"], competition,
                                    self.cfg["competitions"][competition]["country"], spec["tiers"])

    @cache
    def _wikipedia(self, competition: str) -> pd.DataFrame:
        country = self.cfg["competitions"][competition]["country"]
        parts = []
        for spec in self.cfg["sources"]["wikipedia"]["leagues"][competition]:
            df = sources.wikipedia_league(self.bronze / "wikipedia" / spec["folder"], competition, country, spec["tier"])
            first, last = spec["seasons"]   # specs can share a folder (a league renamed over the years)
            parts.append(df[df["season"].between(first, last)])
        return pd.concat(parts, ignore_index=True)

    @cache
    def _football_data(self) -> pd.DataFrame:
        return sources.football_data(self.bronze / "football_data",
                                     self.cfg["sources"]["football_data"]["divisions"])

    @cache
    def _engsoccerdata(self, competition: str) -> pd.DataFrame:
        es = self.bronze / "engsoccerdata"
        spec = self.cfg["competitions"][competition]
        if spec["type"] == "league":
            league = spec["engsoccerdata"]
            return sources.es_league(es / f"{league['file']}.csv", spec["country"], competition,
                                     league["max_tier"])
        readers = {
            "ENG-FAC": lambda: sources.es_facup(es / "facup.csv"),
            "ENG-LC": lambda: sources.es_leaguecup(es / "leaguecup.csv"),
            "ENG-PO": lambda: sources.es_playoffs(es / "englandplayoffs.csv", 4),
            "UCL": lambda: sources.es_champs(es / "champs.csv"),
        }
        return readers[competition]()



def load_aliases(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str)


def apply_aliases(df: pd.DataFrame, aliases: pd.DataFrame, source: str,
                  auto_new: list | None = None) -> pd.DataFrame:
    """Map source club keys to canonical names.

    engsoccerdata names are canonical except where its cup files spell a
    club differently from its league file (aliases with source
    engsoccerdata). For other sources unmapped keys raise, unless `auto_new`
    (a list) is given: then each unmapped key becomes a new canonical club
    named after its display name, and the new alias rows are appended to
    `auto_new` for the caller to persist."""
    if source == "engsoccerdata":
        fix = aliases[aliases["source"] == "engsoccerdata"].set_index("source_name")["club"]
        return df.assign(home_club=df["home_club"].replace(fix), away_club=df["away_club"].replace(fix))
    mapping = aliases[aliases["source"] == source].set_index("source_name")["club"]
    if auto_new is not None:
        keys = pd.concat([df[["home_club", "home_name", "home_country"]].set_axis(["key", "name", "country"], axis=1),
                          df[["away_club", "away_name", "away_country"]].set_axis(["key", "name", "country"], axis=1)])
        missing = keys[~keys["key"].isin(mapping.index)].drop_duplicates("key")
        taken = set(aliases["club"])
        for key, name, country in missing.itertuples(index=False):
            club = name if name not in taken else f"{name} ({country if isinstance(country, str) else source})"
            taken.add(club)
            auto_new.append({"source": source, "source_name": key, "club": club})
            log.warning("new %s club %r (%s) registered as %r - review config/club_aliases.csv",
                        source, name, key, club)
        if len(missing):
            mapping = pd.concat([mapping, pd.Series({r["source_name"]: r["club"] for r in auto_new
                                                     if r["source"] == source})])
    out = df.copy()
    for side in ("home", "away"):
        col = f"{side}_club"
        mapped = out[col].map(mapping)
        missing = out.loc[mapped.isna(), [col, f"{side}_name"]].drop_duplicates()
        if len(missing):
            sample = missing.head(20).values.tolist()
            raise ValueError(f"{len(missing)} unmapped {source} clubs, e.g. {sample} - "
                             f"run tools/derive_aliases.py and review config/club_aliases.csv")
        out[col] = mapped
    return out


def combine_windows(cfg: dict, competition: str, reader: SourceReader) -> pd.DataFrame:
    """Apply a competition's source windows: each source fills only the
    (season, tier) blocks not already covered by an earlier source."""
    spec = cfg["competitions"][competition]
    taken: set = set()
    frames = []
    for w in spec["windows"]:
        df = reader.read(w["source"], competition)
        if "from" in w:
            df = df[df["match_date"] >= pd.Timestamp(w["from"])]
        if "until" in w:
            df = df[df["match_date"] <= pd.Timestamp(w["until"])]
        if "tiers" in w:
            df = df[df["tier"].isin(w["tiers"])]
        if df.empty:
            continue
        block = pd.Series(list(zip(df["season"], df["tier"].fillna(0))), index=df.index)
        if "replace_partial" in w and frames:
            # take over blocks where the earlier sources hold under this share of our matches
            have = pd.concat(frames)
            have_n = pd.Series(list(zip(have["season"], have["tier"].fillna(0)))).value_counts()
            ours = block.value_counts()
            partial = {b for b, n in ours.items() if b in taken and have_n.get(b, 0) < w["replace_partial"] * n}
            for b in sorted(partial):
                log.info("%s: %s replaces a partial season %d tier %d (%d matches, now %d)", competition,
                         w["source"], b[0], b[1], have_n.get(b, 0), ours[b])
            frames = [f[~pd.Series(list(zip(f["season"], f["tier"].fillna(0))), index=f.index).isin(partial)]
                      for f in frames]
            taken -= partial
        keep = ~block.isin(taken)
        df = df[keep]
        if df.empty:
            continue
        new_blocks = set(zip(df["season"], df["tier"].fillna(0)))
        log.info("%s: %d matches from %s, seasons %d-%d", competition, len(df), w["source"],
                 df["season"].min(), df["season"].max())
        taken |= new_blocks
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=sources.COLUMNS)


def build(cfg: dict, aliases: pd.DataFrame | None = None, auto_new_sources=("espn",)) -> dict:
    """Build silver. Returns a dict with:
      matches   - the combined match table (MATCH_COLUMNS)
      clubs     - club registry (club, country, league_club)
      aliases   - aliases used, including any auto-registered ones
      new_aliases - aliases auto-registered in this build (new clubs)
      source_rows - every source row read (bronze), before alias mapping
    """
    reader = SourceReader(cfg)
    aliases = load_aliases(cfg["aliases"]) if aliases is None else aliases
    start = pd.Timestamp(cfg["elo"]["start_date"])
    new_aliases: list = []
    frames, raw = [], []
    for comp, spec in cfg["competitions"].items():
        for src in {w["source"] for w in spec["windows"]}:
            raw.append(reader.read(src, comp))
        df = combine_windows(cfg, comp, reader)
        df = df[df["match_date"] >= start]
        if spec["type"] == "cup" and spec.get("country"):
            # a domestic cup's clubs are that country's (amateur sides have no country in the sources)
            df = df.fillna({"home_country": spec["country"], "away_country": spec["country"]})
        for src, part in df.groupby("source"):
            auto = new_aliases if src in auto_new_sources else None
            frames.append(apply_aliases(part, aliases, src, auto_new=auto))
    df = pd.concat(frames, ignore_index=True)
    df["comp_type"] = df["competition"].map({c: s["type"] for c, s in cfg["competitions"].items()})
    df = df.drop_duplicates(subset=["match_date", "home_club", "away_club"], keep="first")
    df = df.sort_values(["match_date", "competition", "home_club"]).reset_index(drop=True)
    df["match_id"] = (df["match_date"].dt.strftime("%Y%m%d") + "_"
                      + df["home_club"].str.replace(r"\W+", "", regex=True) + "_"
                      + df["away_club"].str.replace(r"\W+", "", regex=True))
    new_aliases_df = pd.DataFrame(new_aliases, columns=["source", "source_name", "club"])
    all_aliases = pd.concat([aliases, new_aliases_df], ignore_index=True)
    clubs = club_registry(df, all_aliases)
    # clubs whose league games were abroad (Cypriot champions in the Greek league, 1967-74)
    fixed = cfg.get("club_countries", {})
    clubs["country"] = clubs["club"].map(fixed).fillna(clubs["country"])
    warn_thin_seasons(df)
    quality = check_matches(df)
    quality_path = cfg["paths"]["silver"] / "data_quality.csv"
    quality_path.parent.mkdir(parents=True, exist_ok=True)
    quality.to_csv(quality_path, index=False)
    source_rows = pd.concat(raw, ignore_index=True)
    source_rows = source_rows[source_rows["match_date"] >= start]
    return {"matches": df[MATCH_COLUMNS], "clubs": clubs, "aliases": all_aliases,
            "new_aliases": new_aliases_df, "source_rows": source_rows}


def warn_thin_seasons(df: pd.DataFrame, share: float = 0.5) -> pd.DataFrame:
    """Log competition seasons (per tier) with under `share` of that
    competition's median match count: usually a source holding only part of a
    season, which then blocks a complete source for that season. The latest
    season is skipped (still in progress)."""
    counts = df.groupby(["competition", df["tier"].fillna(0), "season"]).size().rename("n").reset_index()
    counts = counts[counts["season"] < counts["season"].max()]
    counts["usual"] = counts.groupby(["competition", "tier"])["n"].transform("median")
    thin = counts[counts["n"] < share * counts["usual"]]
    for r in thin.itertuples(index=False):
        log.warning("thin season: %s tier %s %s has %d matches (usual %d)",
                    r.competition, int(r.tier) or "-", r.season, r.n, int(r.usual))
    return thin


def competitions_table(cfg: dict) -> pd.DataFrame:
    return pd.DataFrame([{"competition": c, "name": s["name"], "comp_type": s["type"],
                          "country": s.get("country")} for c, s in cfg["competitions"].items()])


def club_registry(df: pd.DataFrame, aliases: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per club: country (most common observed) and whether it has
    ever played in a modelled league. Includes alias targets without matches
    so every alias points at a registered club."""
    long = pd.concat([
        df[["home_club", "home_country"]].set_axis(["club", "country"], axis=1),
        df[["away_club", "away_country"]].set_axis(["club", "country"], axis=1)])
    country = long.dropna().groupby("club")["country"].agg(lambda s: s.value_counts().index[0])
    names = set(long["club"]) | (set(aliases["club"]) if aliases is not None else set())
    clubs = pd.DataFrame({"club": sorted(names)})
    clubs["country"] = clubs["club"].map(country)
    league = df[df["comp_type"] == "league"]
    in_league = set(league["home_club"]) | set(league["away_club"])
    clubs["league_club"] = clubs["club"].isin(in_league)
    return clubs


def check_matches(df: pd.DataFrame) -> pd.DataFrame:
    """Sanity checks. Hard errors raise; date clashes (a club with two
    matches on one day, from wrong dates in a source) are returned as a
    data-quality report instead, since they only affect match order."""
    problems = []
    if (df["home_club"] == df["away_club"]).any():
        problems.append(f"club playing itself: {df.loc[df.home_club == df.away_club, 'match_id'].tolist()[:5]}")
    if (df[["home_goals", "away_goals"]] < 0).any().any():
        problems.append("negative goals")
    if df["match_id"].duplicated().any():
        problems.append(f"duplicate match ids: {df.loc[df.match_id.duplicated(), 'match_id'].tolist()[:5]}")
    if problems:
        raise ValueError("silver checks failed: " + "; ".join(problems))
    cols = ["match_date", "match_id", "competition", "source"]
    long = pd.concat([df[cols + ["home_club"]].rename(columns={"home_club": "club"}),
                      df[cols + ["away_club"]].rename(columns={"away_club": "club"})])
    clash = long[long.duplicated(["match_date", "club"], keep=False)].sort_values(["club", "match_date"])
    if len(clash):
        log.warning("%d club-days with two matches (source date errors); see data quality report",
                    len(clash) // 2)
    return clash.assign(issue="two_matches_same_day")


def validate_overlap(cfg: dict) -> pd.DataFrame:
    """Compare engsoccerdata and football-data league results where both
    exist (1993-2025), for every modelled league. One row per mismatch."""
    reader = SourceReader(cfg)
    aliases = load_aliases(cfg["aliases"])
    out = []
    for comp, spec in cfg["competitions"].items():
        if spec["type"] != "league":
            continue
        es = apply_aliases(reader.read("engsoccerdata", comp), aliases, "engsoccerdata")
        fd = apply_aliases(reader.read("football_data", comp), aliases, "football_data")
        if fd.empty or es.empty:
            continue
        lo, hi = fd["match_date"].min(), es["match_date"].max()
        es = es[es["match_date"].between(lo, hi)]
        fd = fd[fd["match_date"].between(lo, hi) & fd["tier"].isin(es["tier"].unique())]
        key = ["season", "home_club", "away_club"]
        cols = key + ["match_date", "tier", "home_goals", "away_goals"]
        m = es[cols].merge(fd[cols], on=key, how="outer", suffixes=("_es", "_fd"), indicator=True)
        m["issue"] = None
        m.loc[m["_merge"] == "left_only", "issue"] = "missing_in_football_data"
        m.loc[m["_merge"] == "right_only", "issue"] = "missing_in_engsoccerdata"
        both = m["_merge"] == "both"
        m.loc[both & ((m["home_goals_es"] != m["home_goals_fd"]) |
                      (m["away_goals_es"] != m["away_goals_fd"])), "issue"] = "score_mismatch"
        m.loc[both & m["issue"].isna() &
              ((m["match_date_es"] - m["match_date_fd"]).abs() > pd.Timedelta(days=1)), "issue"] = "date_mismatch"
        log.info("%s overlap: %d es, %d fd, %d matched", comp, len(es), len(fd), int(both.sum()))
        out.append(m[m["issue"].notna()].drop(columns="_merge").assign(competition=comp))
    return pd.concat(out, ignore_index=True)
