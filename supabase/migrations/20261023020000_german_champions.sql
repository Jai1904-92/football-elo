-- German champions 1955/56-1962/63, from the championship final (GER-CH), as trophies.
drop materialized view gold.mv_trophies;
create materialized view gold.mv_trophies as
with last as (
  select distinct on (competition, season) competition, season, match_date as last_date,
         least(home_club, away_club) as c1, greatest(home_club, away_club) as c2
  from silver.matches
  where competition in ('UCL', 'UEL', 'UCWC', 'FAIRS', 'UECL', 'ENG-FAC', 'ENG-LC',
                        'ESP-CDR', 'GER-DFB', 'ITA-CI', 'FRA-CDF', 'NED-KNVB', 'POR-TP', 'GER-CH')
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

revoke all on gold.mv_trophies from anon, authenticated;
