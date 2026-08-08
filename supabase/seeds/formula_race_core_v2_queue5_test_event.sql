-- EXOS Core v2 Formula R.A.C.E. test event (non-production, isolated).
-- Intended for local/test/staging recovery and UI validation only.
-- Creates one dedicated event and the required team skeleton.

begin;
select pg_advisory_xact_lock(hashtext('FORMULA-RACE-CORE-V2-QUEUE5-TEST'));

insert into public.runtime_events (
  event_id, join_code, event_name, active, next_team_index, current_stage_no,
  stage_state, stage_name, current_mission_id, credit_wallet_enabled, updated_at
) values (
  'RACE-CORE-V2-Q5-01', 'RACEQ5', 'Formula R.A.C.E. Core v2 Queue 5', true, 0, 0,
  'READY', 'Briefing', 'RACEQ5-STAGE-00', true, now()
) on conflict (event_id) do update set
  event_name = excluded.event_name,
  join_code = excluded.join_code,
  active = true,
  updated_at = now();

delete from public.runtime_teams where event_id = 'RACE-CORE-V2-Q5-01';
insert into public.runtime_teams (event_id, position, team_id, team_name) values
  ('RACE-CORE-V2-Q5-01', 0, 'Q5-TEAM-01', 'Thunder'),
  ('RACE-CORE-V2-Q5-01', 1, 'Q5-TEAM-02', 'Comet');

insert into public.formula_race_team_access (event_id, team_id, pin_hash, active_device_id)
  values
  ('RACE-CORE-V2-Q5-01', 'Q5-TEAM-01', crypt('4010', gen_salt('bf')), null),
  ('RACE-CORE-V2-Q5-01', 'Q5-TEAM-02', crypt('4011', gen_salt('bf')), null)
on conflict (event_id, team_id) do update set
  pin_hash = excluded.pin_hash,
  active_device_id = null,
  updated_at = now();

commit;
