-- Football Elo: bronze / silver / gold schemas.
-- Internal asset: RLS is on with no policies, so only the postgres/service
-- roles (pipeline, SQL editor) can read or write. The schemas are not
-- exposed through the Data API.

create schema if not exists bronze;
create schema if not exists silver;
create schema if not exists gold;

-- ---------------------------------------------------------------- bronze
-- Raw rows exactly as downloaded, one jsonb per source row.
create table bronze.raw_files (
  file_name   text primary key,             -- e.g. engsoccerdata/england.csv, football_data/2627_E0.csv
  source      text not null check (source in ('engsoccerdata', 'football_data')),
  sha256      text not null,
  row_count   integer not null,
  fetched_at  timestamptz not null default now()
);

create table bronze.raw_rows (
  file_name   text not null references bronze.raw_files (file_name) on delete cascade,
  row_num     integer not null,
  data        jsonb not null,
  primary key (file_name, row_num)
);

-- ---------------------------------------------------------------- silver
create table silver.club_aliases (
  source       text not null,
  source_name  text not null,
  club         text not null,
  primary key (source, source_name)
);

create table silver.matches (
  match_id    text primary key,               -- yyyymmdd_Home_Away
  match_date  date not null,
  season      smallint not null,              -- start year, 2025 = 2025/26
  tier        smallint not null check (tier between 1 and 4),
  home_club   text not null,
  away_club   text not null,
  home_goals  smallint not null check (home_goals >= 0),
  away_goals  smallint not null check (away_goals >= 0),
  source      text not null,
  loaded_at   timestamptz not null default now(),
  check (home_club <> away_club)
);
create index matches_date_idx on silver.matches (match_date);
create index matches_home_idx on silver.matches (home_club, match_date);
create index matches_away_idx on silver.matches (away_club, match_date);

-- ---------------------------------------------------------------- gold
create table gold.runs (
  run_id           bigint generated always as identity primary key,
  kind             text not null check (kind in ('full', 'incremental')),
  started_at       timestamptz not null default now(),
  finished_at      timestamptz,
  params           jsonb not null,
  replay_from      date,                     -- first match date (re)rated in this run
  matches_rated    integer,
  last_match_date  date
);

-- Per-match pre/post ratings.
create table gold.match_ratings (
  match_id       text primary key references silver.matches (match_id) on delete cascade,
  match_date     date not null,
  home_elo_pre   double precision not null,
  away_elo_pre   double precision not null,
  home_elo_post  double precision not null,
  away_elo_post  double precision not null,
  home_win_exp   double precision not null,
  elo_delta      double precision not null,
  burn_in        boolean not null,
  run_id         bigint not null references gold.runs (run_id)
);
create index match_ratings_date_idx on gold.match_ratings (match_date);
create index match_ratings_run_idx on gold.match_ratings (run_id);

-- Club Elo grain: one row per club per rating period. valid_from is the day
-- after a match, valid_to the day of the club's next match. The last period
-- is open (null) for clubs in the latest season; for clubs that dropped out
-- of the league it closes on the last match day of their final season.
create table gold.club_ratings (
  club           text not null,
  valid_from     date not null,
  valid_to       date,
  elo            double precision not null,
  tier           smallint not null,
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
  target         text not null,              -- 'all', 'elhabr', 'wayback_2008-02-02', ...
  n              integer not null,
  rmse           double precision not null,
  bias           double precision not null,
  rmse_shape     double precision not null,
  mean_spearman  double precision,
  primary key (run_id, target)
);

-- Latest rating per club, ranked like the Club Elo front page.
create view gold.current_ratings
with (security_invoker = true) as
select rank() over (order by elo desc) as rank,
       club, elo, tier, season, valid_from, last_match_id
from gold.club_ratings
where valid_to is null;

-- Ratings table on any date, like api.clubelo.com/YYYY-MM-DD.
create function gold.ratings_on(on_date date)
returns table (rank bigint, club text, elo double precision, tier smallint,
               valid_from date, valid_to date)
language sql stable
set search_path = ''
as $$
  select rank() over (order by r.elo desc), r.club, r.elo, r.tier, r.valid_from, r.valid_to
  from gold.club_ratings r
  where r.valid_from <= on_date
    and (r.valid_to is null or r.valid_to >= on_date)
  order by r.elo desc;
$$;

alter table bronze.raw_files enable row level security;
alter table bronze.raw_rows enable row level security;
alter table silver.club_aliases enable row level security;
alter table silver.matches enable row level security;
alter table gold.runs enable row level security;
alter table gold.match_ratings enable row level security;
alter table gold.club_ratings enable row level security;
alter table gold.calibration_scores enable row level security;

revoke all on schema bronze, silver, gold from anon, authenticated;
