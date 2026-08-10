-- Narrow rollback for formula_race_demo_seed.sql.
-- GENERATE ONLY: review before running. Deletes only FORMULA-RACE-DEMO-001
-- and the FR-DEMO-* global experience definitions created by that seed.

begin;

select pg_advisory_xact_lock(hashtext('FORMULA-RACE-DEMO-SEED'));

do $$
begin
  if exists (
    select 1 from public.event_experience_assignments
    where experience_assignment_id like 'FR-DEMO-ASG-%'
      and event_id <> 'FORMULA-RACE-DEMO-001'
  ) then
    raise exception 'Rollback refused: FR-DEMO assignments exist outside the demo EventID';
  end if;
end $$;

-- Tables without an EventID foreign key to runtime_events are removed explicitly.
delete from public.scoring_locks where event_id = 'FORMULA-RACE-DEMO-001';
delete from public.judge_scores where event_id = 'FORMULA-RACE-DEMO-001';
delete from public.judging_configurations where event_id = 'FORMULA-RACE-DEMO-001';
delete from public.award_transactions where event_id = 'FORMULA-RACE-DEMO-001';
delete from public.review_decisions where event_id = 'FORMULA-RACE-DEMO-001';
delete from public.canonical_submissions where event_id = 'FORMULA-RACE-DEMO-001';

-- Assignment uses ON DELETE RESTRICT and therefore precedes event deletion.
delete from public.event_experience_assignments where event_id = 'FORMULA-RACE-DEMO-001';

-- Event-owned runtime and Formula RACE rows cascade from this one deletion.
delete from public.runtime_events where event_id = 'FORMULA-RACE-DEMO-001';

-- Definitions are global, so remove only the seed's reserved identifiers and only
-- after their assignments have been removed.
delete from public.experience_definitions
where experience_definition_id like 'FR-DEMO-EXP-%';

commit;
