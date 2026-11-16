-- The Taça da Liga (POR-TL) gets its own trophies. Transfermarkt's Portuguese
-- cup (POCP) is the Taça da Liga, not the Taça de Portugal: its winners
-- 2012/13-2019/20 and 2022/23 were listed as Taça de Portugal winners. The
-- Taça de Portugal now comes from Wikipedia to 2020/21 and ESPN after that.
-- Also hand-enters 40 domestic finals the computed trophies couldn't settle
-- (League Cup shoot-outs missing from the source, away-goals Coppa Italia
-- finals, finals missing or mis-dated on Wikipedia pages, Coppa Italia final
-- groups with a winner only). Still open: Coupe de France 1991/92 (not
-- played), Greek Cup 1961/62, 1963/64 and 1965/66.
-- Otherwise as 20261024010000_european_finals.sql.
drop materialized view gold.mv_trophies;
create materialized view gold.mv_trophies as
with last as (
  select distinct on (competition, season) competition, season, match_date as last_date, source, round,
         least(home_club, away_club) as c1, greatest(home_club, away_club) as c2
  from silver.matches
  where competition in ('UCL', 'UEL', 'UCWC', 'FAIRS', 'UECL', 'ENG-FAC', 'ENG-LC',
                        'ESP-CDR', 'GER-DFB', 'ITA-CI', 'FRA-CDF', 'NED-KNVB', 'POR-TP', 'POR-TL', 'GER-CH',
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
  ('UEL', 2006, 'Sevilla', 'Espanyol Barcelona', 1),
  -- domestic finals: shoot-outs the source lacks, away goals, finals missing or mis-dated
  ('ENG-LC', 1972, 'Tottenham Hotspur', 'Norwich City', 1),
  ('ENG-LC', 2000, 'Liverpool', 'Birmingham City', 1),
  ('ENG-LC', 2008, 'Manchester United', 'Tottenham Hotspur', 1),
  ('ENG-LC', 2011, 'Liverpool', 'Cardiff City', 1),
  ('ENG-LC', 2015, 'Manchester City', 'Liverpool', 1),
  ('ENG-LC', 2018, 'Manchester City', 'Chelsea', 1),
  ('ENG-FAC', 1971, 'Leeds United', 'Arsenal', 1),
  ('ESP-CDR', 1956, 'Barcelona', 'Espanyol Barcelona', 1),
  ('ESP-CDR', 1957, 'Athletic Bilbao', 'Real Madrid', 1),
  ('ESP-CDR', 1968, 'Athletic Bilbao', 'Elche CF', 1),
  ('ITA-CI', 1960, 'ACF Fiorentina', 'Lazio', 1),
  ('ITA-CI', 1967, 'Torino', NULL, NULL),          -- final group
  ('ITA-CI', 1968, 'AS Roma', NULL, NULL),         -- final group
  ('ITA-CI', 1969, 'Bologna FC', NULL, NULL),      -- final group
  ('ITA-CI', 1970, 'Torino', 'AC Milan', 1),
  ('ITA-CI', 1992, 'Torino', 'AS Roma', 2),
  ('ITA-CI', 1998, 'Parma', 'ACF Fiorentina', 2),
  ('ITA-CI', 1999, 'Lazio', 'Internazionale', 2),
  ('ITA-CI', 2001, 'Parma', 'Juventus', 2),
  ('ITA-CI', 2003, 'Lazio', 'Juventus', 2),
  ('FRA-CDF', 1973, 'AS Saint-Etienne', 'AS Monaco', 1),
  ('FRA-CDF', 1974, 'AS Saint-Etienne', 'RC Lens', 1),
  ('FRA-CDF', 1976, 'AS Saint-Etienne', 'Stade Reims', 1),
  ('FRA-CDF', 1977, 'AS Nancy', 'OGC Nice', 1),
  ('FRA-CDF', 1979, 'AS Monaco', 'Orleans', 1),
  ('FRA-CDF', 1981, 'Paris Saint-Germain', 'AS Saint-Etienne', 1),
  ('FRA-CDF', 1984, 'AS Monaco', 'Paris Saint-Germain', 1),
  ('NED-KNVB', 1972, 'NAC Breda', 'NEC Nijmegen', 1),
  ('NED-KNVB', 1973, 'PSV Eindhoven', 'NAC Breda', 1),
  ('BEL-BC', 1992, 'Standard Liege', 'Charleroi', 1),
  ('BEL-BC', 1993, 'Anderlecht', 'Club Brugge', 1),
  ('POR-TP', 1964, 'Vitória de Setúbal', 'SL Benfica', 1),
  ('POR-TP', 1968, 'SL Benfica', 'Academica', 1),
  ('POR-TP', 1982, 'SL Benfica', 'FC Porto', 1),
  ('GRE-GC', 1959, 'Olympiacos', 'Panathinaikos', 1),
  ('GRE-GC', 1968, 'Panathinaikos', 'Olympiacos', 1),   -- 1-1, settled by a coin toss
  ('SCO-SC', 2011, 'Hearts', 'Hibernian', 1),
  ('TUR-TC', 1965, 'Galatasaray', 'Fenerbahce', 1),
  ('TUR-TC', 1998, 'Galatasaray', 'Besiktas', 2),
  ('TUR-TC', 2017, 'Akhisar Belediyespor', 'Fenerbahce', 1),
  ('TUR-TC', 2018, 'Galatasaray', 'Akhisar Belediyespor', 1)
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
