-- Approved high-level L'Oreal Formula R.A.C.E. structure for EVT-0006.
-- No unapproved timings, challenge scores, material prices or stock are invented.
begin;
select pg_advisory_xact_lock(hashtext('FORMULA-RACE-EVT-0006-CONFIG'));

do $$ begin
 if not exists(select 1 from public.runtime_events where event_id='EVT-0006' and event_name='RACE') then
  raise exception 'EVT-0006 is not the expected RACE event';
 end if;
 if (select count(*) from public.runtime_teams where event_id='EVT-0006')<>10 then
  raise exception 'EVT-0006 must contain exactly ten teams';
 end if;
end $$;

update public.runtime_events set active=true,next_team_index=0,current_stage_no=0,stage_state='READY',
 stage_name='Briefing',current_mission_id='RACE-D1-00',display_mode='Hybrid',credit_wallet_enabled=true,
 credit_earning_frozen=false,credit_leaderboard_frozen_at=null,
 stage_payload='{"StageNo":0,"StageType":"READY","StageName":"Briefing","MissionID":"RACE-D1-00","Day":1}'::jsonb,
 updated_at=now() where event_id='EVT-0006';

delete from public.runtime_missions where event_id='EVT-0006';
insert into public.runtime_missions(event_id,mission_id,mission_payload) values
 ('EVT-0006','RACE-D1-00','{"StageNo":0,"Day":1,"StageType":"BRIEFING","StageName":"Briefing","MissionID":"RACE-D1-00","ConfigurationSource":"Approved R.A.C.E. structure"}'),
 ('EVT-0006','RACE-D1-01','{"StageNo":1,"Day":1,"StageType":"CREDIT_CHALLENGE","StageName":"R.A.C.E. Credit Challenge 1","MissionID":"RACE-D1-01","CreditValue":null,"TimingMinutes":null,"RequiresFacilitatorReview":true}'),
 ('EVT-0006','RACE-D1-02','{"StageNo":2,"Day":1,"StageType":"CREDIT_CHALLENGE","StageName":"R.A.C.E. Credit Challenge 2","MissionID":"RACE-D1-02","CreditValue":null,"TimingMinutes":null,"RequiresFacilitatorReview":true}'),
 ('EVT-0006','RACE-D1-03','{"StageNo":3,"Day":1,"StageType":"CREDIT_CHALLENGE","StageName":"R.A.C.E. Credit Challenge 3","MissionID":"RACE-D1-03","CreditValue":null,"TimingMinutes":null,"RequiresFacilitatorReview":true}'),
 ('EVT-0006','RACE-D1-04','{"StageNo":4,"Day":1,"StageType":"CREDIT_CHALLENGE","StageName":"R.A.C.E. Credit Challenge 4","MissionID":"RACE-D1-04","CreditValue":null,"TimingMinutes":null,"RequiresFacilitatorReview":true}'),
 ('EVT-0006','RACE-D1-05','{"StageNo":5,"Day":1,"StageType":"REVIEW","StageName":"Facilitator Review","MissionID":"RACE-D1-05"}'),
 ('EVT-0006','RACE-D1-06','{"StageNo":6,"Day":1,"StageType":"CREDIT_AWARD","StageName":"Credit Awards","MissionID":"RACE-D1-06"}'),
 ('EVT-0006','RACE-D2-07','{"StageNo":7,"Day":2,"StageType":"MARKETPLACE","StageName":"Spend Credits","MissionID":"RACE-D2-07"}'),
 ('EVT-0006','RACE-D2-08','{"StageNo":8,"Day":2,"StageType":"MATERIAL_COLLECTION","StageName":"Marketplace / Material Collection","MissionID":"RACE-D2-08"}'),
 ('EVT-0006','RACE-D2-09','{"StageNo":9,"Day":2,"StageType":"BUILD","StageName":"Formula Car Build","MissionID":"RACE-D2-09"}'),
 ('EVT-0006','RACE-D2-10','{"StageNo":10,"Day":2,"StageType":"DESIGN","StageName":"Painting / Design","MissionID":"RACE-D2-10"}'),
 ('EVT-0006','RACE-D2-11','{"StageNo":11,"Day":2,"StageType":"PHOTO","StageName":"Team Photo","MissionID":"RACE-D2-11","EvidenceType":"IMAGE","RequiresFacilitatorReview":true}'),
 ('EVT-0006','RACE-D2-12','{"StageNo":12,"Day":2,"StageType":"RACE","StageName":"Drag Push Race","MissionID":"RACE-D2-12"}'),
 ('EVT-0006','RACE-D2-13','{"StageNo":13,"Day":2,"StageType":"JUDGING","StageName":"Judging","MissionID":"RACE-D2-13"}'),
 ('EVT-0006','RACE-D2-14','{"StageNo":14,"Day":2,"StageType":"FINAL","StageName":"Final Championship","MissionID":"RACE-D2-14"}');

-- Editable catalogue. Items remain inactive until approved prices and stock are entered.
delete from public.runtime_marketplace_items where event_id='EVT-0006';
insert into public.runtime_marketplace_items(event_id,item_id,item_name,description,credit_cost,stock_quantity,
 initial_stock_quantity,active,position) values
 ('EVT-0006','WOODEN-CHASSIS-BOARD','Wooden Chassis Board','Approved material; facilitator must enter price and stock.',0,0,0,false,1),
 ('EVT-0006','METAL-AXLE-RODS','Metal Axle Rods','Approved material; facilitator must enter price and stock.',0,0,0,false,2),
 ('EVT-0006','WHEELBARROW-TYRES','Wheelbarrow Tyres','Approved material; facilitator must enter price and stock.',0,0,0,false,3),
 ('EVT-0006','CARDBOARD','Cardboard Sheets or Boxes','Approved material; facilitator must enter price and stock.',0,0,0,false,4),
 ('EVT-0006','BOLTS-NUTS-WASHERS','Bolts, Nuts and Washers','Approved material; facilitator must enter price and stock.',0,0,0,false,5),
 ('EVT-0006','TAPE-FASTENERS','Tape and Fasteners','Approved material; facilitator must enter price and stock.',0,0,0,false,6),
 ('EVT-0006','SPRAY-PAINT','Spray Paint','Approved material; facilitator must enter price and stock.',0,0,0,false,7);

insert into public.runtime_team_wallets(event_id,team_name,team_id)
 select event_id,team_name,team_id from public.runtime_teams where event_id='EVT-0006'
on conflict(event_id,team_name) do update set team_id=excluded.team_id;

insert into public.judging_configurations(judging_configuration_id,event_id,activity_id,version,criteria,
 required_judge_count,aggregation_method,exclude_highest_lowest,tie_break_method,finalisation_rule)
values('EVT-0006-RACE-JUDGING-V1','EVT-0006','RACE-D2-13',1,
 '[{"CriterionID":"ENGINEERING_DESIGN","Name":"Engineering Design","Min":0,"Max":10,"Weight":1},{"CriterionID":"STRUCTURAL_INTEGRITY","Name":"Structural Integrity","Min":0,"Max":10,"Weight":1},{"CriterionID":"INNOVATION","Name":"Innovation","Min":0,"Max":10,"Weight":1},{"CriterionID":"CREATIVITY","Name":"Creativity","Min":0,"Max":10,"Weight":1},{"CriterionID":"RACE_PERFORMANCE","Name":"Race Performance","Min":0,"Max":10,"Weight":1},{"CriterionID":"TEAM_PRESENTATION","Name":"Team Presentation","Min":0,"Max":10,"Weight":1}]',
 1,'AVERAGE',false,'STABLE_TEAM_ID','MANUAL')
on conflict(judging_configuration_id) do update set criteria=excluded.criteria,finalisation_rule=excluded.finalisation_rule;

insert into public.formula_race_event_config(event_id,scoring_config,results_locked,updated_by)
values('EVT-0006','{"Version":1,"JudgingActivityID":"RACE-D2-13","MaximumJudgingScore":60,"Race":{"Format":"DRAG_PUSH","ResultSelection":"VERIFIED_RESULT"},"FinalRanking":{"TieBreakers":["RACE_TIME_ASC","TEAM_ID_ASC"]},"UnapprovedValues":{"ChallengeCredits":null,"Timings":null,"MarketplacePrices":null,"MarketplaceStock":null}}',false,'production-activation-2026-08-07')
on conflict(event_id) do update set scoring_config=excluded.scoring_config,results_locked=false,updated_by=excluded.updated_by,updated_at=now();

delete from public.formula_race_build_status where event_id='EVT-0006';
insert into public.formula_race_build_status(event_id,team_id,status,checklist,reason,created_by)
 select event_id,team_id,'Not Started','{}','Initial live event state','production-activation-2026-08-07'
 from public.runtime_teams where event_id='EVT-0006';

commit;
