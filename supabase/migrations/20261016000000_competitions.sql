-- Phase 2: cups, play-offs and European competitions; multi-country ready.
-- Tables were empty when this ran, so changed tables are recreated.

drop view if exists gold.current_ratings;
drop function if exists gold.ratings_on(date);
drop table if exists gold.calibration_scores, gold.club_ratings, gold.match_ratings, gold.runs;
drop table if exists silver.matches, silver.club_aliases;
drop table if exists bronze.raw_rows, bronze.raw_files;

-- ---------------------------------------------------------------- bronze
-- Every row each source supplied, minimally parsed, with the source's own
-- club keys and names (before alias mapping). Overlapping sources are all
-- kept here; silver picks one per competition window.
create table bronze.source_files (
  source      text not null,
  file_name   text not null,                 -- e.g. football_data/2627_E0.csv, espn/eng.fa/2026.json
  sha256      text not null,
  fetched_at  timestamptz not null default now(),
  primary key (source, file_name)
);

create table bronze.source_matches (
  source        text not null,
  file_name     text not null,
  competition   text not null,
  match_date    date not null,
  season        smallint not null,
  tier          smallint,
  round         text,
  leg           text,
  home_key      text not null,
  away_key      text not null,
  home_name     text,
  away_name     text,
  home_goals    smallint not null,
  away_goals    smallint not null,
  neutral       boolean not null,
  extra_time    boolean not null,
  home_pens     smallint,
  away_pens     smallint,
  home_country  text,
  away_country  text,
  foreign key (source, file_name) references bronze.source_files (source, file_name) on delete cascade
);
create index source_matches_file_idx on bronze.source_matches (source, file_name);
create index source_matches_comp_idx on bronze.source_matches (competition, match_date);

-- ---------------------------------------------------------------- silver
create table silver.competitions (
  competition  text primary key,             -- ENG-L, ENG-FAC, UCL, ...
  name         text not null,
  comp_type    text not null check (comp_type in ('league', 'playoff', 'cup', 'europe')),
  country      text                          -- null for UEFA competitions
);

create table silver.clubs (
  club         text primary key,             -- canonical name
  country      text,
  league_club  boolean not null              -- has played in a modelled league
);

create table silver.club_aliases (
  source       text not null,
  source_name  text not null,                -- name, or club id for transfermarkt / espn
  club         text not null,
  primary key (source, source_name)
);
create index club_aliases_club_idx on silver.club_aliases (club);

create table silver.matches (
  match_id     text primary key,             -- yyyymmdd_Home_Away
  match_date   date not null,
  season       smallint not null,            -- start year, 2025 = 2025/26
  competition  text not null references silver.competitions (competition),
  comp_type    text not null,
  tier         smallint check (tier between 1 and 10),   -- league matches only
  round        text,
  leg          text,
  home_club    text not null references silver.clubs (club),
  away_club    text not null references silver.clubs (club),
  home_goals   smallint not null check (home_goals >= 0),   -- after extra time
  away_goals   smallint not null check (away_goals >= 0),
  neutral      boolean not null,
  extra_time   boolean not null,
  home_pens    smallint,
  away_pens    smallint,
  source       text not null,
  loaded_at    timestamptz not null default now(),
  check (home_club <> away_club)
);
create index matches_date_idx on silver.matches (match_date);
create index matches_comp_idx on silver.matches (competition, season);
create index matches_home_idx on silver.matches (home_club, match_date);
create index matches_away_idx on silver.matches (away_club, match_date);

-- ---------------------------------------------------------------- gold
create table gold.runs (
  run_id           bigint generated always as identity primary key,
  kind             text not null check (kind in ('full', 'incremental')),
  started_at       timestamptz not null default now(),
  finished_at      timestamptz,
  params           jsonb not null,
  replay_from      date,
  matches_rated    integer,
  last_match_date  date
);

create table gold.match_ratings (
  match_id       text primary key references silver.matches (match_id) on delete cascade,
  match_date     date not null,
  home_elo_pre   double precision not null,
  away_elo_pre   double precision not null,
  home_elo_post  double precision not null,
  away_elo_post  double precision not null,
  home_win_exp   double precision not null,
  elo_delta      double precision not null,
  hfa_applied    boolean not null,
  k_mult         double precision not null,
  burn_in        boolean not null,
  run_id         bigint not null references gold.runs (run_id)
);
create index match_ratings_date_idx on gold.match_ratings (match_date);
create index match_ratings_run_idx on gold.match_ratings (run_id);

-- Club Elo grain. valid_from = day after a match, valid_to = day of the
-- club's next match; open (null) for clubs that played in the latest
-- season, otherwise closed at the end of their last season. tier is the
-- club's league tier that season (null: non-league or foreign club).
create table gold.club_ratings (
  club           text not null references silver.clubs (club),
  country        text,
  valid_from     date not null,
  valid_to       date,
  elo            double precision not null,
  tier           smallint,
  season         smallint not null,
  last_match_id  text not null references silver.matches (match_id) on delete cascade,
  burn_in        boolean not null,
  run_id         bigint not null references gold.runs (run_id),
  primary key (club, valid_from)
);
create index club_ratings_period_idx on gold.club_ratings (valid_from, valid_to);
create index club_ratings_current_idx on gold.club_ratings (club) where valid_to is null;
create index club_ratings_match_idx on gold.club_ratings (last_match_id);
create index club_ratings_run_idx on gold.club_ratings (run_id);

create table gold.calibration_scores (
  run_id         bigint not null references gold.runs (run_id) on delete cascade,
  target         text not null,
  n              integer not null,
  rmse           double precision not null,
  bias           double precision not null,
  rmse_shape     double precision not null,
  mean_spearman  double precision,
  primary key (run_id, target)
);

-- Latest rating per club. By default lists clubs in a modelled league this
-- season, like the Club Elo front page; query gold.club_ratings for others.
create view gold.current_ratings
with (security_invoker = true) as
select rank() over (order by elo desc) as rank,
       club, country, elo, tier, season, valid_from, last_match_id
from gold.club_ratings
where valid_to is null and tier is not null;

-- Ratings table on any date, like api.clubelo.com/YYYY-MM-DD.
-- league_only = false also lists non-league and foreign clubs.
create function gold.ratings_on(on_date date, league_only boolean default true)
returns table (rank bigint, club text, country text, elo double precision, tier smallint,
               valid_from date, valid_to date)
language sql stable
set search_path = ''
as $$
  select rank() over (order by r.elo desc), r.club, r.country, r.elo, r.tier, r.valid_from, r.valid_to
  from gold.club_ratings r
  where r.valid_from <= on_date
    and (r.valid_to is null or r.valid_to >= on_date)
    and (not league_only or r.tier is not null)
  order by r.elo desc;
$$;

alter table bronze.source_files enable row level security;
alter table bronze.source_matches enable row level security;
alter table silver.competitions enable row level security;
alter table silver.clubs enable row level security;
alter table silver.club_aliases enable row level security;
alter table silver.matches enable row level security;
alter table gold.runs enable row level security;
alter table gold.match_ratings enable row level security;
alter table gold.club_ratings enable row level security;
alter table gold.calibration_scores enable row level security;

revoke all on all tables in schema bronze, silver, gold from anon, authenticated;
