-- European finals the computed trophies can't settle, entered by hand (all
-- documented results): away goals (UEFA Cup 1976/77, 1979/80, 1991/92),
-- shoot-outs the source lacks (Cup Winners' Cup 1979/80; UEFA Cup 1983/84,
-- 1987/88, 1996/97, 2006/07), a Fairs Cup final whose legs were 35 days apart
-- (1967/68), the Fairs Cup 1970/71 final whose first match was abandoned and
-- replayed (Leeds on away goals), and the Fairs Cup 1966/67 final missing from
-- the source. The list only fills in or overrides those seasons.
drop materialized view gold.mv_trophies;
create materialized view gold.mv_trophies as
with last as (
  select distinct on (competition, season) competition, season, match_date as last_date, source, round,
         least(home_club, away_club) as c1, greatest(home_club, away_club) as c2
  from silver.matches
  where competition in ('UCL', 'UEL', 'UCWC', 'FAIRS', 'UECL', 'ENG-FAC', 'ENG-LC',
                        'ESP-CDR', 'GER-DFB', 'ITA-CI', 'FRA-CDF', 'NED-KNVB', 'POR-TP', 'GER-CH',
                        'SCO-SC', 'BEL-BC', 'TUR-TC', 'GRE-GC')
    and season < (select max(season) from silver.matches)
  order by competition, season, match_date desc, match_id desc
), real_final as (
  select * from last
  where source <> 'wikipedia' or round ~* '^\s*finals?\s*$'
), fin as (
  select l.competition as comp, l.season as yr, l.c1, l.c2, m.home_club, m.home_goals, m.away_goals,
         m.home_pens, m.away_pens, m.match_date
  from real_final l join silver.matches m on m.competition = l.competition and m.season = l.season
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
), w0 as (
  select comp, yr, legs,
         case when g1 > g2 or (g1 = g2 and p1 > p2) then c1 when g2 > g1 or (g1 = g2 and p2 > p1) then c2 end as winner,
         case when g1 > g2 or (g1 = g2 and p1 > p2) then c2 when g2 > g1 or (g1 = g2 and p2 > p1) then c1 end as runner_up
  from agg
), fixed (comp, yr, winner, runner_up, legs) as (values
  ('FAIRS', 1966, 'Dinamo Zagreb', 'Leeds United', 2),
  ('FAIRS', 1967, 'Leeds United', 'Ferencvaros', 2),
  ('FAIRS', 1970, 'Leeds United', 'Juventus', 2),
  ('UCWC', 1979, 'Valencia CF', 'Arsenal', 1),
  ('UEL', 1976, 'Juventus', 'Athletic Bilbao', 2),
  ('UEL', 1979, 'Eintracht Frankfurt', 'Borussia Monchengladbach', 2),
  ('UEL', 1983, 'Tottenham Hotspur', 'Anderlecht', 2),
  ('UEL', 1987, 'Bayer Leverkusen', 'Espanyol Barcelona', 2),
  ('UEL', 1991, 'AFC Ajax', 'Torino', 2),
  ('UEL', 1996, 'Schalke 04', 'Internazionale', 2),
  ('UEL', 2006, 'Sevilla', 'Espanyol Barcelona', 1)
), w as (
  select coalesce(f.comp, w0.comp) as comp, coalesce(f.yr, w0.yr) as yr,
         coalesce(f.winner, w0.winner) as winner, coalesce(f.runner_up, w0.runner_up) as runner_up,
         coalesce(f.legs, w0.legs) as legs
  from w0 full join fixed f on f.comp = w0.comp and f.yr = w0.yr
)
select comp as competition, yr as season, yr::text || '/' || lpad(((yr + 1) % 100)::text, 2, '0') as season_label,
       winner, runner_up, legs
from w where winner is not null and yr >= 1955;
create unique index mv_trophies_pk on gold.mv_trophies (competition, season);

revoke all on gold.mv_trophies from anon, authenticated;
