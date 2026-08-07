-- Correct EVT-0006 from four sequential challenges to one parallel RACE Checkpoints module.
begin;
select pg_advisory_xact_lock(hashtext('FORMULA-RACE-EVT-0006-CHECKPOINTS'));
do $$ begin
 if (select count(*) from runtime_teams where event_id='EVT-0006')<>10 then raise exception 'EVT-0006 team roster must remain intact';end if;
 if (select count(*) from formula_race_team_access where event_id='EVT-0006' and pin_hash is not null)<>10 then raise exception 'EVT-0006 PIN hashes must remain intact';end if;
end $$;

delete from formula_race_checkpoints where event_id='EVT-0006';
insert into formula_race_checkpoints(event_id,module_id,activity_id,name,instructions,credits,proof_type,facilitator_notes,position,active,updated_by) values
 ('EVT-0006','EVT-0006-RACE-CHECKPOINTS','RACE-CP-01','R.A.C.E. Credit Challenge 1','Facilitator-configurable checkpoint instructions.',0,'Photo + Text','Enter approved content and Credits in Programme Builder.',1,true,'migration-019'),
 ('EVT-0006','EVT-0006-RACE-CHECKPOINTS','RACE-CP-02','R.A.C.E. Credit Challenge 2','Facilitator-configurable checkpoint instructions.',0,'Photo + Text','Enter approved content and Credits in Programme Builder.',2,true,'migration-019'),
 ('EVT-0006','EVT-0006-RACE-CHECKPOINTS','RACE-CP-03','R.A.C.E. Credit Challenge 3','Facilitator-configurable checkpoint instructions.',0,'Photo + Text','Enter approved content and Credits in Programme Builder.',3,true,'migration-019'),
 ('EVT-0006','EVT-0006-RACE-CHECKPOINTS','RACE-CP-04','R.A.C.E. Credit Challenge 4','Facilitator-configurable checkpoint instructions.',0,'Photo + Text','Enter approved content and Credits in Programme Builder.',4,true,'migration-019');
insert into formula_race_checkpoint_runtime(event_id,module_id,status,updated_by)
 values('EVT-0006','EVT-0006-RACE-CHECKPOINTS','READY','migration-019')
on conflict(event_id,module_id) do update set status='READY',updated_by=excluded.updated_by,updated_at=now();

delete from runtime_missions where event_id='EVT-0006' and mission_id in
 ('RACE-D1-01','RACE-D1-02','RACE-D1-03','RACE-D1-04','RACE-D1-05','RACE-D1-06');
insert into runtime_missions(event_id,mission_id,mission_payload) values
 ('EVT-0006','RACE-CHECKPOINTS','{"StageNo":1,"StageType":"RACE_CHECKPOINTS","StageName":"RACE Checkpoints","ModuleID":"EVT-0006-RACE-CHECKPOINTS","Parallel":true,"CheckpointCount":4,"ConfigurationSource":"Programme Builder"}')
on conflict(event_id,mission_id) do update set mission_payload=excluded.mission_payload,updated_at=now();
update runtime_events set stage_state='READY',stage_name='Launch EXOS',current_mission_id='RACE-D1-00',
 stage_payload='{"EventID":"EVT-0006","StageNo":0,"StageType":"READY","StageName":"Launch EXOS"}'::jsonb,
 state_version=state_version+1,state_updated_at=now(),updated_at=now() where event_id='EVT-0006';
commit;
