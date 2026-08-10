-- Formula RACE Demo seed
-- GENERATE ONLY: review before running. This file is not a migration.
-- Prerequisites: runtime_schema.sql and migrations 003, 006, 011-017.
-- Demo join code: RACEDEMO
-- Demo team PINs: F1-01 => 4101, F1-02 => 4102, ... F1-10 => 4110.

begin;

select pg_advisory_xact_lock(hashtext('FORMULA-RACE-DEMO-SEED'));

do $$
declare
  required_table text;
begin
  foreach required_table in array array[
    'runtime_events', 'runtime_teams', 'runtime_missions', 'runtime_team_wallets',
    'runtime_credit_transactions', 'runtime_marketplace_items',
    'formula_race_team_access', 'formula_race_build_status',
    'formula_race_event_config', 'experience_definitions',
    'event_experience_assignments', 'judging_configurations', 'award_transactions'
  ] loop
    if to_regclass('public.' || required_table) is null then
      raise exception 'Missing prerequisite table public.%', required_table;
    end if;
  end loop;
end $$;

-- Event. This seed never touches another EventID.
insert into public.runtime_events (
  event_id, join_code, event_name, active, next_team_index,
  current_stage_no, stage_state, stage_name, current_mission_id,
  display_mode, stage_payload, state_version, credit_wallet_enabled,
  credit_earning_frozen, credit_leaderboard_frozen_at, published_at, updated_at
) values (
  'FORMULA-RACE-DEMO-001', 'RACEDEMO', 'Formula RACE Demo', true, 0,
  0, 'READY', 'Event Briefing', 'FR-STAGE-00',
  'Hybrid',
  jsonb_build_object(
    'StageNo', 0,
    'StageType', 'READY',
    'StageName', 'Event Briefing',
    'MissionID', 'FR-STAGE-00',
    'DisplayMode', 'Hybrid',
    'ProgrammeID', 'FORMULA-RACE-DEMO',
    'ExperienceAssignmentID', 'FR-DEMO-ASG-00'
  ),
  1, true, false, null, now(), now()
)
on conflict (event_id) do update set
  join_code = excluded.join_code,
  event_name = excluded.event_name,
  active = excluded.active,
  next_team_index = 0,
  current_stage_no = excluded.current_stage_no,
  stage_state = excluded.stage_state,
  stage_name = excluded.stage_name,
  current_mission_id = excluded.current_mission_id,
  display_mode = excluded.display_mode,
  stage_payload = excluded.stage_payload,
  state_version = public.runtime_events.state_version + 1,
  credit_wallet_enabled = true,
  credit_earning_frozen = false,
  credit_leaderboard_frozen_at = null,
  updated_at = now();

-- Fixed roster. Positions are zero-based because runtime ordering is zero-based.
delete from public.runtime_teams where event_id = 'FORMULA-RACE-DEMO-001';
insert into public.runtime_teams (event_id, position, team_id, team_name) values
  ('FORMULA-RACE-DEMO-001', 0, 'F1-01', 'Sandstorm'),
  ('FORMULA-RACE-DEMO-001', 1, 'F1-02', 'Bolt'),
  ('FORMULA-RACE-DEMO-001', 2, 'F1-03', 'Zenith'),
  ('FORMULA-RACE-DEMO-001', 3, 'F1-04', 'Scuderia Best'),
  ('FORMULA-RACE-DEMO-001', 4, 'F1-05', 'Apex Velocity'),
  ('FORMULA-RACE-DEMO-001', 5, 'F1-06', 'Velocity'),
  ('FORMULA-RACE-DEMO-001', 6, 'F1-07', 'Fast & Curious'),
  ('FORMULA-RACE-DEMO-001', 7, 'F1-08', 'Lakas'),
  ('FORMULA-RACE-DEMO-001', 8, 'F1-09', 'Drift Club'),
  ('FORMULA-RACE-DEMO-001', 9, 'F1-10', 'Papaya Crew');

-- Captain access. Re-seeding intentionally clears demo device/session bindings.
insert into public.formula_race_team_access (
  event_id, team_id, pin_hash, active_device_id, active_session_token,
  connected_at, last_seen_at, updated_at, updated_by
)
select
  'FORMULA-RACE-DEMO-001',
  'F1-' || lpad(team_no::text, 2, '0'),
  crypt((4100 + team_no)::text, gen_salt('bf')),
  null, null, null, null, now(), 'formula-race-demo-seed'
from generate_series(1, 10) as team_no
on conflict (event_id, team_id) do update set
  pin_hash = excluded.pin_hash,
  active_device_id = null,
  active_session_token = null,
  connected_at = null,
  last_seen_at = null,
  updated_at = now(),
  updated_by = excluded.updated_by;

-- Canonical experience definitions for the programme stages/checkpoints.
insert into public.experience_definitions (
  experience_definition_id, version, name, internal_description,
  participant_title, participant_narrative, participant_task,
  experience_type, difficulty, default_intelligence_credits,
  default_evidence_type, default_evidence_instructions,
  tags, learning_themes, venue_tags, status, updated_at
) values
  ('FR-DEMO-EXP-00', 1, 'Event Briefing', 'Captain orientation and safety briefing.', 'Grid Briefing', 'Welcome to Formula RACE.', 'Review the rules, roles and safety requirements.', 'Briefing', 'Easy', 0, 'NONE', '', '["formula-race","briefing"]', '["teamwork","safety"]', '["indoor"]', 'PUBLISHED', now()),
  ('FR-DEMO-EXP-01', 1, 'Design Blueprint', 'Create the team car blueprint.', 'Design Blueprint', 'Translate your race strategy into a build plan.', 'Submit a labelled car design and materials plan.', 'Checkpoint', 'Medium', 20, 'IMAGE', 'Upload one clear image of the approved blueprint.', '["formula-race","design"]', '["planning","engineering"]', '["pit"]', 'PUBLISHED', now()),
  ('FR-DEMO-EXP-02', 1, 'Parts Procurement', 'Select and purchase build components.', 'Pit Marketplace', 'Spend credits carefully to assemble your parts inventory.', 'Purchase the parts required for your approved design.', 'Marketplace', 'Medium', 0, 'NONE', '', '["formula-race","marketplace"]', '["budgeting","decision-making"]', '["marketplace"]', 'PUBLISHED', now()),
  ('FR-DEMO-EXP-03', 1, 'Chassis Check', 'Validate the rolling chassis.', 'Chassis Checkpoint', 'A fast car begins with a straight and stable chassis.', 'Present a rolling chassis that passes the checkpoint list.', 'Checkpoint', 'Medium', 25, 'IMAGE', 'Upload a side view of the completed chassis.', '["formula-race","build"]', '["engineering","quality"]', '["pit"]', 'PUBLISHED', now()),
  ('FR-DEMO-EXP-04', 1, 'Body and Aero Check', 'Validate bodywork and aerodynamic choices.', 'Body & Aero Checkpoint', 'Shape the car for stability, identity and speed.', 'Complete the body, aero and team livery checks.', 'Checkpoint', 'Hard', 25, 'IMAGE', 'Upload front and side views of the car.', '["formula-race","aero"]', '["creativity","engineering"]', '["pit"]', 'PUBLISHED', now()),
  ('FR-DEMO-EXP-05', 1, 'Scrutineering', 'Final safety and compliance inspection.', 'Scrutineering', 'Your build must be safe and race-ready.', 'Pass every mandatory pre-race inspection item.', 'Checkpoint', 'Hard', 30, 'IMAGE', 'Upload the completed race-ready car.', '["formula-race","inspection"]', '["quality","safety"]', '["scrutineering"]', 'PUBLISHED', now()),
  ('FR-DEMO-EXP-06', 1, 'Team Presentation', 'Team pitch and design defence.', 'Design Defence', 'Explain the decisions behind your race machine.', 'Deliver a two-minute design and strategy presentation.', 'Judging', 'Hard', 30, 'NONE', '', '["formula-race","judging"]', '["communication","reflection"]', '["judging"]', 'PUBLISHED', now()),
  ('FR-DEMO-EXP-07', 1, 'Race Heat', 'Timed Formula RACE heat.', 'Race Heat', 'Take your place on the starting grid.', 'Complete the timed race heat and await verification.', 'Race', 'Hard', 50, 'NONE', '', '["formula-race","race"]', '["performance","teamwork"]', '["track"]', 'PUBLISHED', now()),
  ('FR-DEMO-EXP-08', 1, 'Podium and Debrief', 'Results, awards and learning debrief.', 'Podium & Debrief', 'Celebrate the result and capture what the team learned.', 'Complete the team reflection after results are locked.', 'Debrief', 'Easy', 20, 'TEXT', 'Submit a short team reflection.', '["formula-race","debrief"]', '["reflection","teamwork"]', '["podium"]', 'PUBLISHED', now())
on conflict (experience_definition_id, version) do update set
  name = excluded.name,
  internal_description = excluded.internal_description,
  participant_title = excluded.participant_title,
  participant_narrative = excluded.participant_narrative,
  participant_task = excluded.participant_task,
  experience_type = excluded.experience_type,
  difficulty = excluded.difficulty,
  default_intelligence_credits = excluded.default_intelligence_credits,
  default_evidence_type = excluded.default_evidence_type,
  default_evidence_instructions = excluded.default_evidence_instructions,
  tags = excluded.tags,
  learning_themes = excluded.learning_themes,
  venue_tags = excluded.venue_tags,
  status = excluded.status,
  updated_at = now();

insert into public.event_experience_assignments (
  experience_assignment_id, event_id, programme_id, module_id, activity_id,
  experience_definition_id, definition_version, assignment_order, active,
  availability_rule, start_rule, end_rule, unlock_rule, runtime_eligible,
  assignment_version, submission_rule, allows_multiple_submissions, updated_at
)
select
  'FR-DEMO-ASG-' || lpad(stage_no::text, 2, '0'),
  'FORMULA-RACE-DEMO-001', 'FORMULA-RACE-DEMO',
  case
    when stage_no <= 1 then '01-BRIEF-DESIGN'
    when stage_no <= 5 then '02-BUILD'
    when stage_no = 6 then '03-JUDGE'
    when stage_no = 7 then '04-RACE'
    else '05-DEBRIEF'
  end,
  'FR-ACT-' || lpad(stage_no::text, 2, '0'),
  'FR-DEMO-EXP-' || lpad(stage_no::text, 2, '0'),
  1, stage_no + 1, true, 'SEQUENTIAL', 'FACILITATOR', 'FACILITATOR',
  case when stage_no = 0 then 'NONE' else 'PREVIOUS_COMPLETE' end,
  true, 1, 'LEADER_ONLY', false, now()
from generate_series(0, 8) as stage_no
on conflict (experience_assignment_id) do update set
  event_id = excluded.event_id,
  programme_id = excluded.programme_id,
  module_id = excluded.module_id,
  activity_id = excluded.activity_id,
  experience_definition_id = excluded.experience_definition_id,
  definition_version = excluded.definition_version,
  assignment_order = excluded.assignment_order,
  active = true,
  availability_rule = excluded.availability_rule,
  start_rule = excluded.start_rule,
  end_rule = excluded.end_rule,
  unlock_rule = excluded.unlock_rule,
  runtime_eligible = true,
  assignment_version = excluded.assignment_version,
  submission_rule = excluded.submission_rule,
  allows_multiple_submissions = excluded.allows_multiple_submissions,
  updated_at = now();

-- Runtime programme. CheckpointList is consumed directly from mission_payload.
delete from public.runtime_missions where event_id = 'FORMULA-RACE-DEMO-001';
insert into public.runtime_missions (event_id, mission_id, mission_payload, updated_at) values
  ('FORMULA-RACE-DEMO-001', 'FR-STAGE-00', '{"StageNo":0,"StageType":"READY","StageName":"Event Briefing","ExperienceAssignmentID":"FR-DEMO-ASG-00","Objective":"Review roles, rules and safety.","CheckpointList":["Captain PIN confirmed","Team identity confirmed","Safety briefing complete","Build area assigned"]}', now()),
  ('FORMULA-RACE-DEMO-001', 'FR-STAGE-01', '{"StageNo":1,"StageType":"MISSION","StageName":"Design Blueprint","ExperienceAssignmentID":"FR-DEMO-ASG-01","Credits":20,"Objective":"Create and approve the car blueprint.","CheckpointList":["Wheelbase marked","Axle positions marked","Materials list complete","Facilitator approval received"]}', now()),
  ('FORMULA-RACE-DEMO-001', 'FR-STAGE-02', '{"StageNo":2,"StageType":"MARKETPLACE","StageName":"Parts Procurement","ExperienceAssignmentID":"FR-DEMO-ASG-02","Credits":0,"Objective":"Purchase the required components.","CheckpointList":["Wallet checked","Required parts selected","Purchase confirmed","Inventory reconciled"]}', now()),
  ('FORMULA-RACE-DEMO-001', 'FR-STAGE-03', '{"StageNo":3,"StageType":"MISSION","StageName":"Chassis Check","ExperienceAssignmentID":"FR-DEMO-ASG-03","Credits":25,"Objective":"Build a straight, free-rolling chassis.","CheckpointList":["Axles parallel","All wheels rotate freely","Chassis is rigid","Ground clearance confirmed"]}', now()),
  ('FORMULA-RACE-DEMO-001', 'FR-STAGE-04', '{"StageNo":4,"StageType":"MISSION","StageName":"Body & Aero Check","ExperienceAssignmentID":"FR-DEMO-ASG-04","Credits":25,"Objective":"Finish the body, aero and team livery.","CheckpointList":["Body securely attached","No wheel obstruction","Team name visible","Logo and race number visible"]}', now()),
  ('FORMULA-RACE-DEMO-001', 'FR-STAGE-05', '{"StageNo":5,"StageType":"CHECKPOINT","StageName":"Scrutineering","ExperienceAssignmentID":"FR-DEMO-ASG-05","Credits":30,"Objective":"Pass final race inspection.","CheckpointList":["Overall dimensions compliant","Loose parts secured","Wheels and axles safe","Car rolls straight","Team inventory reconciled","Approved for grid"]}', now()),
  ('FORMULA-RACE-DEMO-001', 'FR-STAGE-06', '{"StageNo":6,"StageType":"JUDGING","StageName":"Team Presentation","ExperienceAssignmentID":"FR-DEMO-ASG-06","Credits":30,"Objective":"Present and defend the design.","CheckpointList":["Two-minute presentation ready","Design choices explained","Team roles represented","Judge questions answered"]}', now()),
  ('FORMULA-RACE-DEMO-001', 'FR-STAGE-07', '{"StageNo":7,"StageType":"RACE","StageName":"Race Heat","ExperienceAssignmentID":"FR-DEMO-ASG-07","Credits":50,"Objective":"Complete a verified timed race.","CheckpointList":["Grid position confirmed","Start marshal ready","Finish time captured","Penalties recorded","Result verified"]}', now()),
  ('FORMULA-RACE-DEMO-001', 'FR-STAGE-08', '{"StageNo":8,"StageType":"RESULTS","StageName":"Podium & Debrief","ExperienceAssignmentID":"FR-DEMO-ASG-08","Credits":20,"Objective":"Lock results and complete the debrief.","CheckpointList":["Judging complete","Race results verified","Final score calculated","Results locked","Team reflection submitted"]}', now());

-- Marketplace catalogue and stock inventory.
delete from public.runtime_marketplace_items where event_id = 'FORMULA-RACE-DEMO-001';
insert into public.runtime_marketplace_items (
  event_id, item_id, item_name, description, credit_cost,
  stock_quantity, active, position, updated_at
) values
  ('FORMULA-RACE-DEMO-001', 'CHASSIS-BOARD', 'Chassis Board', 'Rigid base board for one car.', 20, 20, true, 1, now()),
  ('FORMULA-RACE-DEMO-001', 'AXLE-PAIR', 'Axle Pair', 'Two straight axles.', 12, 30, true, 2, now()),
  ('FORMULA-RACE-DEMO-001', 'WHEEL-SET', 'Wheel Set', 'Four matched wheels.', 18, 20, true, 3, now()),
  ('FORMULA-RACE-DEMO-001', 'BEARING-SET', 'Low-Friction Bearing Set', 'Four axle bearing guides.', 16, 15, true, 4, now()),
  ('FORMULA-RACE-DEMO-001', 'BODY-PANEL', 'Body Panel Pack', 'Lightweight panels for bodywork.', 14, 25, true, 5, now()),
  ('FORMULA-RACE-DEMO-001', 'AERO-KIT', 'Aero Kit', 'Front splitter and rear wing materials.', 15, 15, true, 6, now()),
  ('FORMULA-RACE-DEMO-001', 'FASTENER-KIT', 'Fastener Kit', 'Tape, ties and reusable fasteners.', 8, 40, true, 7, now()),
  ('FORMULA-RACE-DEMO-001', 'ADHESIVE', 'Adhesive Pack', 'Build-safe adhesive supply.', 7, 30, true, 8, now()),
  ('FORMULA-RACE-DEMO-001', 'LIVERY-PACK', 'Livery Pack', 'Colour, number and identity materials.', 10, 20, true, 9, now()),
  ('FORMULA-RACE-DEMO-001', 'WEIGHT-PACK', 'Balance Weight Pack', 'Adjustable ballast for tuning.', 9, 20, true, 10, now()),
  ('FORMULA-RACE-DEMO-001', 'PIT-REPAIR', 'Pit Repair Token', 'One facilitated repair intervention.', 25, 10, true, 11, now()),
  ('FORMULA-RACE-DEMO-001', 'TEST-RUN', 'Track Test Token', 'One supervised pre-race test run.', 20, 20, true, 12, now());

-- Runtime wallets: 100 opening credits, no demo purchases.
delete from public.runtime_marketplace_purchases where event_id = 'FORMULA-RACE-DEMO-001';
delete from public.runtime_credit_transactions where event_id = 'FORMULA-RACE-DEMO-001';
delete from public.runtime_team_wallets where event_id = 'FORMULA-RACE-DEMO-001';
insert into public.runtime_team_wallets (
  event_id, team_name, earned_credits, spent_credits, adjusted_credits, updated_at
)
select 'FORMULA-RACE-DEMO-001', team_name, 0, 0, 100, now()
from public.runtime_teams where event_id = 'FORMULA-RACE-DEMO-001';

insert into public.runtime_credit_transactions (
  transaction_id, event_id, team_name, transaction_type, amount,
  source_type, source_id, description, metadata, created_at
)
select
  ('d0000000-0000-4000-8000-' || lpad((position + 1)::text, 12, '0'))::uuid,
  event_id, team_name, 'ADJUSTMENT', 100, 'DEMO_SEED',
  team_id || '-OPENING', 'Formula RACE demo opening balance',
  jsonb_build_object('EventID', event_id, 'TeamID', team_id, 'Seed', 'FORMULA-RACE-DEMO'),
  now()
from public.runtime_teams where event_id = 'FORMULA-RACE-DEMO-001';

-- Canonical wallet projection mirrors the runtime wallet opening balance.
delete from public.award_transactions
where event_id = 'FORMULA-RACE-DEMO-001' and source = 'DEMO_SEED';
insert into public.award_transactions (
  award_transaction_id, event_id, team_id, award_type, amount, source,
  reason, idempotency_key, created_by, audit_metadata
)
select
  'FR-DEMO-AWARD-' || team_id,
  event_id, team_id, 'MANUAL_ADJUSTMENT', 100, 'DEMO_SEED',
  'Formula RACE demo opening balance', 'FR-DEMO-OPENING-' || team_id,
  'formula-race-demo-seed', jsonb_build_object('Seed', 'FORMULA-RACE-DEMO')
from public.runtime_teams where event_id = 'FORMULA-RACE-DEMO-001'
on conflict (award_transaction_id) do update set
  amount = excluded.amount,
  reason = excluded.reason,
  audit_metadata = excluded.audit_metadata;

-- Judge configuration. Six criteria match the enforced Formula RACE scoring API.
insert into public.judging_configurations (
  judging_configuration_id, event_id, activity_id, version, criteria,
  required_judge_count, aggregation_method, exclude_highest_lowest,
  tie_break_method, finalisation_rule
) values (
  'FR-DEMO-JUDGE-CONFIG-V1', 'FORMULA-RACE-DEMO-001', 'FR-ACT-06', 1,
  '[
    {"CriterionID":"ENGINEERING_DESIGN","Name":"Engineering Design","Min":0,"Max":10,"Weight":1},
    {"CriterionID":"STRUCTURAL_INTEGRITY","Name":"Structural Integrity","Min":0,"Max":10,"Weight":1},
    {"CriterionID":"INNOVATION","Name":"Innovation","Min":0,"Max":10,"Weight":1},
    {"CriterionID":"CREATIVITY","Name":"Creativity","Min":0,"Max":10,"Weight":1},
    {"CriterionID":"RACE_PERFORMANCE","Name":"Race Performance","Min":0,"Max":10,"Weight":1},
    {"CriterionID":"TEAM_PRESENTATION","Name":"Team Presentation","Min":0,"Max":10,"Weight":1}
  ]'::jsonb,
  2, 'AVERAGE', false, 'STABLE_TEAM_ID', 'MANUAL'
)
on conflict (judging_configuration_id) do update set
  criteria = excluded.criteria,
  required_judge_count = excluded.required_judge_count,
  aggregation_method = excluded.aggregation_method,
  exclude_highest_lowest = excluded.exclude_highest_lowest,
  tie_break_method = excluded.tie_break_method,
  finalisation_rule = excluded.finalisation_rule;

-- Event scoring/race configuration and clean operational state.
insert into public.formula_race_event_config (
  event_id, scoring_config, results_locked, updated_by, updated_at
) values (
  'FORMULA-RACE-DEMO-001',
  '{
    "Version":1,
    "MaximumJudgingScore":60,
    "JudgingActivityID":"FR-ACT-06",
    "JudgeCount":2,
    "JudgeAggregation":"AVERAGE",
    "Race":{
      "Format":"TIME_TRIAL",
      "HeatsPerTeam":2,
      "ResultSelection":"FASTEST_VERIFIED_HEAT",
      "LaneCount":2,
      "CountdownSeconds":3,
      "MaximumRunSeconds":120,
      "FalseStartPenaltyMs":5000,
      "TrackDeparturePenaltyMs":3000,
      "UnverifiedResultsExcluded":true
    },
    "FinalRanking":{
      "Primary":"TOTAL_SCORE_DESC",
      "TieBreakers":["RACE_TIME_ASC","TEAM_ID_ASC"]
    }
  }'::jsonb,
  false, 'formula-race-demo-seed', now()
)
on conflict (event_id) do update set
  scoring_config = excluded.scoring_config,
  results_locked = false,
  updated_by = excluded.updated_by,
  updated_at = now();

delete from public.formula_race_judging where event_id = 'FORMULA-RACE-DEMO-001';
delete from public.formula_race_results where event_id = 'FORMULA-RACE-DEMO-001';
delete from public.formula_race_build_status where event_id = 'FORMULA-RACE-DEMO-001';
insert into public.formula_race_build_status (
  event_id, team_id, status, checklist, reason, created_by
)
select
  event_id, team_id, 'Not Started',
  '{"BlueprintApproved":false,"ChassisPassed":false,"BodyAndAeroPassed":false,"ScrutineeringPassed":false,"GridReady":false}'::jsonb,
  'Initial Formula RACE demo state', 'formula-race-demo-seed'
from public.runtime_teams where event_id = 'FORMULA-RACE-DEMO-001';

commit;
