-- Read-only verification for Formula RACE Demo. Expected result: no exception.
-- This script does not alter persisted data.
begin transaction read only;

do $$
declare
  actual integer;
  invalid integer;
begin
  if not exists (
    select 1 from public.runtime_events
    where event_id = 'FORMULA-RACE-DEMO-001'
      and join_code = 'RACEDEMO'
      and event_name = 'Formula RACE Demo'
      and active and credit_wallet_enabled
  ) then raise exception 'Formula RACE demo event is missing or misconfigured'; end if;

  select count(*) into actual from public.runtime_teams where event_id = 'FORMULA-RACE-DEMO-001';
  if actual <> 10 then raise exception 'Expected 10 teams, found %', actual; end if;

  select count(*) into invalid
  from (values
    (0,'F1-01','Sandstorm'),(1,'F1-02','Bolt'),(2,'F1-03','Zenith'),
    (3,'F1-04','Scuderia Best'),(4,'F1-05','Apex Velocity'),
    (5,'F1-06','Velocity'),(6,'F1-07','Fast & Curious'),(7,'F1-08','Lakas'),
    (8,'F1-09','Drift Club'),(9,'F1-10','Papaya Crew')
  ) expected(position, team_id, team_name)
  left join public.runtime_teams actual_team
    on actual_team.event_id = 'FORMULA-RACE-DEMO-001'
   and actual_team.position = expected.position
   and actual_team.team_id = expected.team_id
   and actual_team.team_name = expected.team_name
  where actual_team.team_id is null;
  if invalid <> 0 then raise exception '% fixed team rows are missing or incorrect', invalid; end if;

  select count(*) into actual from public.formula_race_team_access where event_id = 'FORMULA-RACE-DEMO-001';
  if actual <> 10 then raise exception 'Expected 10 team PIN configurations, found %', actual; end if;
  select count(*) into invalid from public.formula_race_team_access
   where event_id = 'FORMULA-RACE-DEMO-001'
     and (pin_hash is null or active_device_id is not null or active_session_token is not null);
  if invalid <> 0 then raise exception 'Captain access must start disconnected with hashed PINs'; end if;

  select count(*) into actual from public.runtime_missions where event_id = 'FORMULA-RACE-DEMO-001';
  if actual <> 9 then raise exception 'Expected 9 programme stages, found %', actual; end if;
  select count(*) into invalid from public.runtime_missions
   where event_id = 'FORMULA-RACE-DEMO-001'
     and (jsonb_typeof(mission_payload->'CheckpointList') <> 'array'
          or jsonb_array_length(mission_payload->'CheckpointList') = 0);
  if invalid <> 0 then raise exception '% stages have no checkpoint list', invalid; end if;

  select count(*) into actual from public.event_experience_assignments where event_id = 'FORMULA-RACE-DEMO-001';
  if actual <> 9 then raise exception 'Expected 9 experience assignments, found %', actual; end if;

  select count(*) into actual from public.runtime_marketplace_items where event_id = 'FORMULA-RACE-DEMO-001' and active;
  if actual <> 12 then raise exception 'Expected 12 active marketplace items, found %', actual; end if;
  select count(*) into invalid from public.runtime_marketplace_items
   where event_id = 'FORMULA-RACE-DEMO-001' and (credit_cost < 0 or stock_quantity is null or stock_quantity < 0);
  if invalid <> 0 then raise exception '% marketplace inventory rows are invalid', invalid; end if;

  select count(*) into actual from public.runtime_team_wallets
   where event_id = 'FORMULA-RACE-DEMO-001'
     and earned_credits = 0 and spent_credits = 0 and adjusted_credits = 100;
  if actual <> 10 then raise exception 'Expected 10 runtime wallets with 100 credits, found %', actual; end if;
  select count(*) into actual from public.team_balance_projection
   where event_id = 'FORMULA-RACE-DEMO-001' and available_balance = 100;
  if actual <> 10 then raise exception 'Expected 10 canonical wallets with 100 credits, found %', actual; end if;

  select count(*) into actual from public.formula_race_build_status where event_id = 'FORMULA-RACE-DEMO-001';
  if actual <> 10 then raise exception 'Expected 10 initial build statuses, found %', actual; end if;
  select count(*) into invalid from public.formula_race_build_status
   where event_id = 'FORMULA-RACE-DEMO-001' and status <> 'Not Started';
  if invalid <> 0 then raise exception 'All build statuses must start at Not Started'; end if;

  select count(*) into actual from public.judging_configurations
   where event_id = 'FORMULA-RACE-DEMO-001'
     and judging_configuration_id = 'FR-DEMO-JUDGE-CONFIG-V1'
     and jsonb_array_length(criteria) = 6 and required_judge_count = 2;
  if actual <> 1 then raise exception 'Judge configuration is missing or invalid'; end if;

  if not exists (
    select 1 from public.formula_race_event_config
    where event_id = 'FORMULA-RACE-DEMO-001'
      and not results_locked
      and scoring_config #>> '{Race,Format}' = 'TIME_TRIAL'
      and scoring_config #>> '{Race,ResultSelection}' = 'FASTEST_VERIFIED_HEAT'
  ) then raise exception 'Race configuration is missing or invalid'; end if;

  if exists (select 1 from public.formula_race_judging where event_id = 'FORMULA-RACE-DEMO-001')
     or exists (select 1 from public.formula_race_results where event_id = 'FORMULA-RACE-DEMO-001')
     or exists (select 1 from public.runtime_marketplace_purchases where event_id = 'FORMULA-RACE-DEMO-001')
  then raise exception 'Demo transactional state must start clean'; end if;
end $$;

select
  event.event_id,
  event.join_code,
  count(distinct team.team_id) as teams,
  count(distinct mission.mission_id) as stages,
  count(distinct item.item_id) as marketplace_items,
  count(distinct wallet.team_name) as wallets
from public.runtime_events event
left join public.runtime_teams team on team.event_id = event.event_id
left join public.runtime_missions mission on mission.event_id = event.event_id
left join public.runtime_marketplace_items item on item.event_id = event.event_id
left join public.runtime_team_wallets wallet on wallet.event_id = event.event_id
where event.event_id = 'FORMULA-RACE-DEMO-001'
group by event.event_id, event.join_code;

rollback;
