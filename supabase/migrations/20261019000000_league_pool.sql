-- League pooling: each country's rating level offset over time, and the
-- offset in force at each club rating period (so incremental runs can split
-- a stored rating into the club's own part and its country's level).

alter table gold.club_ratings add column country_offset double precision not null default 0;

create table gold.league_offsets (
  country     text not null,
  valid_from  date not null,             -- day after the European match that moved it
  level_offset double precision not null,
  run_id      bigint not null references gold.runs (run_id),
  primary key (country, valid_from)
);
create index league_offsets_run_idx on gold.league_offsets (run_id);
alter table gold.league_offsets enable row level security;
revoke all on gold.league_offsets from anon, authenticated;
