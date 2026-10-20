-- Dynamic home advantage: its value per key (home country, or "europe") over
-- time, and the home advantage used in each match.

alter table gold.match_ratings add column hfa double precision not null default 0;

create table gold.hfa_levels (
  hfa_key     text not null,              -- home country code, or 'europe'
  valid_from  date not null,              -- day after the match that moved it
  hfa         double precision not null,
  run_id      bigint not null references gold.runs (run_id),
  primary key (hfa_key, valid_from)
);
create index hfa_levels_run_idx on gold.hfa_levels (run_id);
alter table gold.hfa_levels enable row level security;
revoke all on gold.hfa_levels from anon, authenticated;
