-- Two ways to judge a season, side by side in every season-based view:
--   measure 'end'  - the rating at the end of the season (where the club finished)
--   measure 'perf' - the whole-season performance rating (how good it was over
--                    the season; see src/football_elo/seasons.py)
-- `rating` holds the measure's value; above-average, ranks and the lists built
-- on them are computed per measure. elo_end / elo_peak stay as they were.

create table gold.club_season_perf (
  club     text     not null,
  season   smallint not null,
  elo_perf double precision not null,
  elo_avg  double precision not null,
  matches  int      not null,
  run_id   bigint   not null references gold.runs (run_id),
  primary key (club, season)
);
revoke all on gold.club_season_perf from anon, authenticated;

drop materialized view gold.mv_alltime_parts;
drop materialized view gold.mv_dynasties;
drop materialized view gold.mv_greatest_seasons;
drop materialized view gold.mv_league_strength;
drop materialized view gold.mv_decade_kings;
drop materialized view gold.mv_number_ones;
drop materialized view gold.mv_club_summary;
drop materialized view gold.mv_club_seasons;

-- One row per club per season in a modelled league, per measure.
create materialized view gold.mv_club_seasons as
with s as (
  select club, max(country) as country, season, min(tier) as tier,
         (array_agg(elo order by valid_from desc))[1] as elo_end, max(elo) as elo_peak
  from gold.club_ratings where tier is not null group by club, season
), m as (
  select s.*, 'end'::text as measure, s.elo_end as rating from s
  union all
  select s.*, 'perf'::text, p.elo_perf from s join gold.club_season_perf p using (club, season)
), field as (
  select measure, season, avg(rating) as field_avg from m where tier = 1 group by measure, season
)
select m.club, m.country, m.season, m.measure,
       m.season::text || '/' || lpad(((m.season + 1) % 100)::text, 2, '0') as season_label,
       m.tier::int as tier,
       round(m.rating)::int as rating,
       round(m.elo_end)::int as elo_end, round(m.elo_peak)::int as elo_peak,
       m.rating - f.field_avg as above_field_raw,
       round(m.rating - f.field_avg)::int as above_field,
       round(m.elo_peak - f.field_avg)::int as peak_above_field,
       (rank() over (partition by m.measure, m.season order by m.rating desc))::int as world_rank,
       (rank() over (partition by m.measure, m.season, m.country, m.tier order by m.rating desc))::int as league_rank
from m join field f using (measure, season);
create unique index mv_club_seasons_pk on gold.mv_club_seasons (measure, club, season);
create index mv_club_seasons_rank_idx on gold.mv_club_seasons (measure, season, world_rank);

-- Career summary since 1965, per measure.
create materialized view gold.mv_club_summary as
with d as (
  select measure, club, (floor(season / 10) * 10)::int as decade, avg(above_field_raw) as a
  from gold.mv_club_seasons where season >= 1965 group by 1, 2, 3 having count(*) >= 3
), bd as (select distinct on (measure, club) measure, club, decade from d order by measure, club, a desc),
pk as (
  select distinct on (measure, club) measure, club, season as peak_season, season_label as peak_season_label
  from gold.mv_club_seasons where season >= 1965 order by measure, club, elo_peak desc
)
select r.measure, r.club, max(r.country) as country,
       (count(*) filter (where r.tier = 1))::int as top_flight_seasons,
       min(r.season)::int as first_season, max(r.season)::int as last_season,
       max(r.elo_peak) filter (where r.season >= 1965) as peak_elo,
       max(pk.peak_season) as peak_season, max(pk.peak_season_label) as peak_season_label,
       (count(*) filter (where r.world_rank = 1 and r.season >= 1965))::int as seasons_at_1,
       (count(*) filter (where r.world_rank <= 10 and r.season >= 1965))::int as seasons_top10,
       min(r.world_rank) filter (where r.season >= 1965) as best_rank,
       max(bd.decade) as best_decade,
       max(bd.decade)::text || 's' as best_decade_label
from gold.mv_club_seasons r left join bd using (measure, club) left join pk using (measure, club)
group by r.measure, r.club;
create unique index mv_club_summary_pk on gold.mv_club_summary (measure, club);

-- Top-rated club of each season.
create materialized view gold.mv_number_ones as
with r2 as (
  select r.*, lead(rating) over (partition by measure, season order by above_field_raw desc) as next_rating,
         lead(club) over (partition by measure, season order by above_field_raw desc) as runner_up
  from gold.mv_club_seasons r
)
select measure, season, club, country, rating, elo_end, (rating - next_rating)::int as margin, runner_up
from r2 where world_rank = 1;
create unique index mv_number_ones_pk on gold.mv_number_ones (measure, season);

-- Best ten clubs per decade since 1965 (top-flight seasons, at least three).
create materialized view gold.mv_decade_kings as
with d as (
  select measure, (floor(season / 10) * 10)::int as decade, club, max(country) as country, count(*)::int as seasons,
         round(avg(above_field_raw))::int as avg_above_field, min(world_rank)::int as best_rank,
         (count(*) filter (where world_rank = 1))::int as seasons_at_1
  from gold.mv_club_seasons where tier = 1 and season >= 1965 group by 1, 2, 3 having count(*) >= 3
), k as (select d.*, (row_number() over (partition by measure, decade order by avg_above_field desc))::int as pos from d)
select measure, decade, pos, club, country, seasons, avg_above_field, best_rank, seasons_at_1 from k where pos <= 10;
create unique index mv_decade_kings_pk on gold.mv_decade_kings (measure, decade, pos);

-- Average and best top-flight rating per country per season.
create materialized view gold.mv_league_strength as
select measure, season, country, round(avg(rating))::int as avg_top_flight, max(rating) as best
from gold.mv_club_seasons where tier = 1 group by measure, season, country;
create unique index mv_league_strength_pk on gold.mv_league_strength (measure, season, country);

-- 100 best top-flight seasons since 1965 above the average top-flight club.
create materialized view gold.mv_greatest_seasons as
select measure, club, country, season, season_label, rating, elo_end, elo_peak, above_field, world_rank
from (
  select r.*, row_number() over (partition by measure order by above_field_raw desc) as pos
  from gold.mv_club_seasons r where season >= 1965 and tier = 1
) x where pos <= 100;
create unique index mv_greatest_seasons_pk on gold.mv_greatest_seasons (measure, club, season);

-- Longest unbroken runs in the top N (N = 1, 3, 5, 10) since 1965.
create materialized view gold.mv_dynasties as
with n as (select unnest(array[1, 3, 5, 10]) as top_n),
t as (
  select r.measure, n.top_n, r.club, r.country, r.season, r.world_rank,
         r.season - row_number() over (partition by r.measure, n.top_n, r.club order by r.season) as grp
  from n join gold.mv_club_seasons r on r.world_rank <= n.top_n and r.season >= 1965
), g as (
  select measure, top_n, club, max(country) as country, min(season)::int as from_season, max(season)::int as to_season,
         count(*)::int as seasons, round(avg(world_rank), 1)::float as avg_rank,
         (count(*) filter (where world_rank = 1))::int as seasons_at_1
  from t group by measure, top_n, club, grp having count(*) >= 3
), k as (select g.*, row_number() over (partition by measure, top_n order by seasons desc, avg_rank) as pos from g)
select measure, top_n, club, country, from_season, to_season,
       from_season::text || '/' || lpad(((from_season + 1) % 100)::text, 2, '0') || ' – ' ||
         to_season::text || '/' || lpad(((to_season + 1) % 100)::text, 2, '0') as span,
       seasons, avg_rank, seasons_at_1, pos::int as pos
from k where pos <= 40;
create unique index mv_dynasties_pk on gold.mv_dynasties (measure, top_n, club, from_season);

-- All-time ranking ingredients, each scaled 0..1 across clubs, per measure.
create materialized view gold.mv_alltime_parts as
with roll as (
  select measure, club, season,
         avg(above_field_raw) over (partition by measure, club order by season rows between 4 preceding and current row) as avg5,
         count(*) over (partition by measure, club order by season rows between 4 preceding and current row) as n5
  from gold.mv_club_seasons where season >= 1965
), m as (
  select measure, club, max(country) as country,
         max(above_field_raw) filter (where season >= 1965 and tier = 1) as peak_above,
         count(*) filter (where season >= 1965 and tier = 1) as tf,
         count(*) filter (where world_rank = 1 and season >= 1965) as at1,
         count(*) filter (where world_rank <= 10 and season >= 1965) as top10
  from gold.mv_club_seasons group by measure, club
), rb as (select measure, club, max(avg5) as best5 from roll where n5 = 5 group by measure, club),
f as (select m.*, rb.best5 from m join rb using (measure, club) where m.tf >= 5 and m.peak_above is not null)
select measure, club, country, round(peak_above)::int as peak_above, round(best5)::int as best5_above,
       at1::int as seasons_at_1, top10::int as seasons_top10, tf::int as top_flight_seasons,
       (peak_above - min(peak_above) over w) / nullif(max(peak_above) over w - min(peak_above) over w, 0) as s_peak,
       (best5 - min(best5) over w) / nullif(max(best5) over w - min(best5) over w, 0) as s_sus,
       at1::float / nullif(max(at1) over w, 0) as s_at1,
       top10::float / nullif(max(top10) over w, 0) as s_top10
from f window w as (partition by measure);
create unique index mv_alltime_parts_pk on gold.mv_alltime_parts (measure, club);

revoke all on all tables in schema gold from anon, authenticated;
