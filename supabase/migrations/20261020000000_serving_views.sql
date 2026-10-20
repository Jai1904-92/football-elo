-- Serving layer for the dashboard: summaries precomputed once per pipeline run
-- (refreshed by gold.refresh_serving()), so page queries are indexed lookups
-- instead of re-aggregating every rating period on each open.

-- One row per club per season in a modelled league.
create materialized view gold.mv_club_seasons as
with s as (
  select club, max(country) as country, season, min(tier) as tier,
         (array_agg(elo order by valid_from desc))[1] as elo_end, max(elo) as elo_peak
  from gold.club_ratings where tier is not null group by club, season
), field as (
  select season, avg(elo_end) as field_avg from s where tier = 1 group by season
)
select s.club, s.country, s.season,
       s.season::text || '/' || lpad(((s.season + 1) % 100)::text, 2, '0') as season_label,
       s.tier::int as tier,
       round(s.elo_end)::int as elo_end, round(s.elo_peak)::int as elo_peak,
       s.elo_end - f.field_avg as above_field_raw,
       round(s.elo_end - f.field_avg)::int as above_field,
       round(s.elo_peak - f.field_avg)::int as peak_above_field,
       (rank() over (partition by s.season order by s.elo_end desc))::int as world_rank,
       (rank() over (partition by s.season, s.country, s.tier order by s.elo_end desc))::int as league_rank
from s join field f using (season);
create unique index mv_club_seasons_pk on gold.mv_club_seasons (club, season);
create index mv_club_seasons_rank_idx on gold.mv_club_seasons (season, world_rank);

-- Each club's rating at the end of every month it played.
create materialized view gold.mv_club_months as
select club, date_trunc('month', valid_from)::date as month,
       round((array_agg(elo order by valid_from desc))[1])::int as elo
from gold.club_ratings
group by club, date_trunc('month', valid_from);
create unique index mv_club_months_pk on gold.mv_club_months (club, month);

-- Career summary since 1965.
create materialized view gold.mv_club_summary as
with d as (
  select club, (floor(season / 10) * 10)::int as decade, avg(above_field_raw) as a
  from gold.mv_club_seasons where season >= 1965 group by 1, 2 having count(*) >= 3
), bd as (select distinct on (club) club, decade from d order by club, a desc),
pk as (
  select distinct on (club) club, season as peak_season, season_label as peak_season_label
  from gold.mv_club_seasons where season >= 1965 order by club, elo_peak desc
)
select r.club, max(r.country) as country,
       (count(*) filter (where r.tier = 1))::int as top_flight_seasons,
       min(r.season)::int as first_season, max(r.season)::int as last_season,
       max(r.elo_peak) filter (where r.season >= 1965) as peak_elo,
       max(pk.peak_season) as peak_season, max(pk.peak_season_label) as peak_season_label,
       (count(*) filter (where r.world_rank = 1 and r.season >= 1965))::int as seasons_at_1,
       (count(*) filter (where r.world_rank <= 10 and r.season >= 1965))::int as seasons_top10,
       min(r.world_rank) filter (where r.season >= 1965) as best_rank,
       max(bd.decade) as best_decade,
       max(bd.decade)::text || 's' as best_decade_label
from gold.mv_club_seasons r left join bd using (club) left join pk using (club)
group by r.club;
create unique index mv_club_summary_pk on gold.mv_club_summary (club);

-- Top-rated club at the end of each season.
create materialized view gold.mv_number_ones as
with r2 as (
  select r.*, lead(elo_end) over (partition by season order by above_field_raw desc) as next_elo,
         lead(club) over (partition by season order by above_field_raw desc) as runner_up
  from gold.mv_club_seasons r
)
select season, club, country, elo_end, (elo_end - next_elo)::int as margin, runner_up
from r2 where world_rank = 1;
create unique index mv_number_ones_pk on gold.mv_number_ones (season);

-- Best ten clubs per decade since 1965 (top-flight seasons, at least three).
create materialized view gold.mv_decade_kings as
with d as (
  select (floor(season / 10) * 10)::int as decade, club, max(country) as country, count(*)::int as seasons,
         round(avg(above_field_raw))::int as avg_above_field, min(world_rank)::int as best_rank,
         (count(*) filter (where world_rank = 1))::int as seasons_at_1
  from gold.mv_club_seasons where tier = 1 and season >= 1965 group by 1, 2 having count(*) >= 3
), k as (select d.*, (row_number() over (partition by decade order by avg_above_field desc))::int as pos from d)
select decade, pos, club, country, seasons, avg_above_field, best_rank, seasons_at_1 from k where pos <= 10;
create unique index mv_decade_kings_pk on gold.mv_decade_kings (decade, pos);

-- Average and best top-flight rating per country per season.
create materialized view gold.mv_league_strength as
select season, country, round(avg(elo_end))::int as avg_top_flight, max(elo_end) as best
from gold.mv_club_seasons where tier = 1 group by season, country;
create unique index mv_league_strength_pk on gold.mv_league_strength (season, country);

-- 100 best top-flight seasons since 1965 above the average top-flight club.
create materialized view gold.mv_greatest_seasons as
select club, country, season, season_label, elo_end, elo_peak, above_field, world_rank
from gold.mv_club_seasons where season >= 1965 and tier = 1
order by above_field_raw desc limit 100;
create unique index mv_greatest_seasons_pk on gold.mv_greatest_seasons (club, season);

-- Longest unbroken runs in the top N (N = 1, 3, 5, 10) since 1965.
create materialized view gold.mv_dynasties as
with n as (select unnest(array[1, 3, 5, 10]) as top_n),
t as (
  select n.top_n, r.club, r.country, r.season, r.world_rank,
         r.season - row_number() over (partition by n.top_n, r.club order by r.season) as grp
  from n join gold.mv_club_seasons r on r.world_rank <= n.top_n and r.season >= 1965
), g as (
  select top_n, club, max(country) as country, min(season)::int as from_season, max(season)::int as to_season,
         count(*)::int as seasons, round(avg(world_rank), 1)::float as avg_rank,
         (count(*) filter (where world_rank = 1))::int as seasons_at_1
  from t group by top_n, club, grp having count(*) >= 3
), k as (select g.*, row_number() over (partition by top_n order by seasons desc, avg_rank) as pos from g)
select top_n, club, country, from_season, to_season,
       from_season::text || '/' || lpad(((from_season + 1) % 100)::text, 2, '0') || ' – ' ||
         to_season::text || '/' || lpad(((to_season + 1) % 100)::text, 2, '0') as span,
       seasons, avg_rank, seasons_at_1, pos::int as pos
from k where pos <= 40;
create unique index mv_dynasties_pk on gold.mv_dynasties (top_n, club, from_season);

-- All-time ranking ingredients, each scaled 0..1 across clubs; the page's
-- weights are applied at query time.
create materialized view gold.mv_alltime_parts as
with roll as (
  select club, season,
         avg(above_field_raw) over (partition by club order by season rows between 4 preceding and current row) as avg5,
         count(*) over (partition by club order by season rows between 4 preceding and current row) as n5
  from gold.mv_club_seasons where season >= 1965
), m as (
  select club, max(country) as country,
         max(above_field_raw) filter (where season >= 1965 and tier = 1) as peak_above,
         count(*) filter (where season >= 1965 and tier = 1) as tf,
         count(*) filter (where world_rank = 1 and season >= 1965) as at1,
         count(*) filter (where world_rank <= 10 and season >= 1965) as top10
  from gold.mv_club_seasons group by club
), rb as (select club, max(avg5) as best5 from roll where n5 = 5 group by club),
f as (select m.*, rb.best5 from m join rb using (club) where m.tf >= 5 and m.peak_above is not null)
select club, country, round(peak_above)::int as peak_above, round(best5)::int as best5_above,
       at1::int as seasons_at_1, top10::int as seasons_top10, tf::int as top_flight_seasons,
       (peak_above - min(peak_above) over ()) / nullif(max(peak_above) over () - min(peak_above) over (), 0) as s_peak,
       (best5 - min(best5) over ()) / nullif(max(best5) over () - min(best5) over (), 0) as s_sus,
       at1::float / nullif(max(at1) over (), 0) as s_at1,
       top10::float / nullif(max(top10) over (), 0) as s_top10
from f;
create unique index mv_alltime_parts_pk on gold.mv_alltime_parts (club);

-- 200 biggest upsets since 1965.
create materialized view gold.mv_upsets as
select m.match_id, m.match_date::text as match_date, m.competition, m.comp_type,
       m.home_club, m.away_club, m.home_goals, m.away_goals, m.home_goals || '–' || m.away_goals as score,
       case when m.home_goals > m.away_goals then m.home_club else m.away_club end as winner,
       case when m.home_goals > m.away_goals then m.away_club else m.home_club end as loser,
       round(r.home_elo_pre)::int as home_elo, round(r.away_elo_pre)::int as away_elo,
       round((case when m.home_goals > m.away_goals then r.home_win_exp else 1 - r.home_win_exp end)::numeric, 3)::float as winner_chance
from silver.matches m join gold.match_ratings r using (match_id)
where m.home_goals <> m.away_goals and m.match_date >= '1965-07-01'
order by winner_chance asc limit 200;
create unique index mv_upsets_pk on gold.mv_upsets (match_id);

-- Trophy winners worked out from the finals (current season excluded).
create materialized view gold.mv_trophies as
with last as (
  select distinct on (competition, season) competition, season, match_date as last_date,
         least(home_club, away_club) as c1, greatest(home_club, away_club) as c2
  from silver.matches
  where competition in ('UCL', 'UEL', 'UCWC', 'FAIRS', 'UECL', 'ENG-FAC', 'ENG-LC')
    and season < (select max(season) from silver.matches)
  order by competition, season, match_date desc, match_id desc
), fin as (
  select l.competition as comp, l.season as yr, l.c1, l.c2, m.home_club, m.home_goals, m.away_goals,
         m.home_pens, m.away_pens, m.match_date
  from last l join silver.matches m on m.competition = l.competition and m.season = l.season
   and least(m.home_club, m.away_club) = l.c1 and greatest(m.home_club, m.away_club) = l.c2
   and m.match_date >= l.last_date - 30
), agg as (
  select comp, yr, c1, c2,
         sum(case when home_club = c1 then home_goals else away_goals end) as g1,
         sum(case when home_club = c2 then home_goals else away_goals end) as g2,
         (array_agg(case when home_club = c1 then home_pens else away_pens end order by match_date desc))[1] as p1,
         (array_agg(case when home_club = c2 then home_pens else away_pens end order by match_date desc))[1] as p2,
         count(*)::int as legs
  from fin group by comp, yr, c1, c2
), w as (
  select comp, yr, legs,
         case when g1 > g2 or (g1 = g2 and p1 > p2) then c1 when g2 > g1 or (g1 = g2 and p2 > p1) then c2 end as winner,
         case when g1 > g2 or (g1 = g2 and p1 > p2) then c2 when g2 > g1 or (g1 = g2 and p2 > p1) then c1 end as runner_up
  from agg
)
select comp as competition, yr as season, yr::text || '/' || lpad(((yr + 1) % 100)::text, 2, '0') as season_label,
       winner, runner_up, legs
from w where winner is not null and yr >= 1955;
create unique index mv_trophies_pk on gold.mv_trophies (competition, season);

-- Faster "ratings on a date": a range index instead of scanning every period
-- that started before the date.
create index club_ratings_period_gist on gold.club_ratings
  using gist (daterange(valid_from, valid_to, '[]'));

create or replace function gold.ratings_on(on_date date, league_only boolean default true)
returns table (rank bigint, club text, country text, elo double precision, tier smallint,
               valid_from date, valid_to date)
language sql stable
set search_path = ''
as $$
  select rank() over (order by r.elo desc), r.club, r.country, r.elo, r.tier, r.valid_from, r.valid_to
  from gold.club_ratings r
  where daterange(r.valid_from, r.valid_to, '[]') @> on_date
    and (not league_only or r.tier is not null)
  order by r.elo desc;
$$;

-- Refresh everything above, in dependency order. Called at the end of each
-- pipeline run.
create or replace function gold.refresh_serving()
returns void
language plpgsql
set search_path = ''
as $$
begin
  refresh materialized view gold.mv_club_seasons;
  refresh materialized view gold.mv_club_months;
  refresh materialized view gold.mv_club_summary;
  refresh materialized view gold.mv_number_ones;
  refresh materialized view gold.mv_decade_kings;
  refresh materialized view gold.mv_league_strength;
  refresh materialized view gold.mv_greatest_seasons;
  refresh materialized view gold.mv_dynasties;
  refresh materialized view gold.mv_alltime_parts;
  refresh materialized view gold.mv_upsets;
  refresh materialized view gold.mv_trophies;
end;
$$;

revoke all on all tables in schema gold from anon, authenticated;
revoke execute on function gold.refresh_serving() from public, anon, authenticated;
