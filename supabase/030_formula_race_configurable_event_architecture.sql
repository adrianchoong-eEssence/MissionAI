-- Formula R.A.C.E. configurable event architecture.
-- Forward migration; depends on 020, 022, 023, 024, 027, 028 and 029.
-- R.A.C.E.-only: it uses Core-v2 JSON configuration and canonical tables. It
-- does not alter Standard event flows, Standard review semantics, or tables.
-- Installation status: UNKNOWN. Query migration history before applying.
BEGIN;

create or replace function public.exos_v2_formula_race_save_event_configuration(
 p_event_id text, p_configuration jsonb, p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_event public.events_v2%rowtype; v_payload jsonb; v_submissions integer; v_purchases integer; v_judging integer; v_station jsonb; v_item jsonb; v_module_id text; v_programme_id text;
begin
 if nullif(trim(p_event_id),'') is null or nullif(trim(p_actor),'') is null then raise exception 'EventID and configuration actor are required'; end if;
 if jsonb_typeof(coalesce(p_configuration,'null'::jsonb)) <> 'object' then raise exception 'R.A.C.E. configuration must be a JSON object'; end if;
 select * into v_event from public.events_v2 where event_id=trim(p_event_id) for update;
 if not found then raise exception 'R.A.C.E. event not found'; end if;
 select count(*) into v_submissions from public.submissions_v2 where event_id=v_event.event_id;
 select count(*) into v_purchases from public.marketplace_transactions_v2 where event_id=v_event.event_id;
 select count(*) into v_judging from public.judging_scores_v2 where event_id=v_event.event_id;
 if v_submissions > 0 and p_configuration ? 'Stations' then raise exception 'Station configuration is locked after submissions exist'; end if;
 if v_purchases > 0 and p_configuration ? 'Marketplace' then raise exception 'Marketplace price and catalogue configuration is locked after purchases exist'; end if;
 if v_judging > 0 and p_configuration ? 'JudgingCriteria' then raise exception 'Judging criteria are locked after scores exist'; end if;
 if p_configuration ? 'Stations' then
  select m.module_id,p.programme_id into v_module_id,v_programme_id from public.modules_v2 m join public.programmes_v2 p on p.programme_id=m.programme_id where p.event_id=v_event.event_id order by m.activity_sequence,m.module_id limit 1;
  if v_module_id is null then raise exception 'R.A.C.E. event requires a programme module before stations can be configured'; end if;
  for v_station in select value from jsonb_array_elements(coalesce(p_configuration->'Stations','[]'::jsonb)) loop
   if nullif(v_station->>'ActivityID','') is null then raise exception 'Every station requires an ActivityID'; end if;
   update public.activities_v2 set activity_payload=activity_payload||jsonb_build_object('race_station',v_station),activity_order=coalesce(nullif(v_station->>'DisplayOrder','')::integer,activity_order),updated_at=now()
    where activity_id=v_station->>'ActivityID' and programme_id in (select programme_id from public.programmes_v2 where event_id=v_event.event_id);
   if not found then
    insert into public.activities_v2(activity_id,module_id,programme_id,activity_type,scoring_mode,activity_name,activity_order,activity_payload,is_active)
    values(v_station->>'ActivityID',v_module_id,v_programme_id,'CHECKPOINT','TEAM_COMPETITIVE',v_station->>'DisplayName',coalesce(nullif(v_station->>'DisplayOrder','')::integer,0),jsonb_build_object('race_station',v_station),coalesce((v_station->>'Enabled')::boolean,true));
   end if;
  end loop;
 end if;
 if p_configuration ? 'Marketplace' then
  for v_item in select value from jsonb_array_elements(coalesce(p_configuration->'Marketplace','[]'::jsonb)) loop
   if nullif(v_item->>'ItemID','') is null or nullif(v_item->>'ItemName','') is null then raise exception 'Every marketplace item requires an ItemID and ItemName'; end if;
   if coalesce((v_item->>'CreditCost')::integer,0)<0 or (nullif(v_item->>'StockLimit','') is not null and (v_item->>'StockLimit')::integer<0) then raise exception 'Marketplace cost and stock cannot be negative'; end if;
   insert into public.marketplace_items_v2(item_id,event_id,item_name,item_type,unit_cost_credits,stock_limit,is_active,item_payload)
    values(v_item->>'ItemID',v_event.event_id,v_item->>'ItemName',coalesce(nullif(v_item->>'Category',''),'CUSTOM'),coalesce((v_item->>'CreditCost')::integer,0),nullif(v_item->>'StockLimit','')::integer,coalesce((v_item->>'Enabled')::boolean,true),v_item)
    on conflict(item_id) do update set item_name=excluded.item_name,item_type=excluded.item_type,unit_cost_credits=excluded.unit_cost_credits,stock_limit=excluded.stock_limit,is_active=excluded.is_active,item_payload=excluded.item_payload;
  end loop;
 end if;
 v_payload:=coalesce(v_event.event_payload,'{}'::jsonb) || jsonb_build_object('RaceConfiguration',coalesce(v_event.event_payload->'RaceConfiguration','{}'::jsonb)||p_configuration||jsonb_build_object('UpdatedBy',trim(p_actor),'UpdatedAt',now()));
 update public.events_v2 set event_payload=v_payload,updated_at=now() where event_id=v_event.event_id;
 return jsonb_build_object('EventID',v_event.event_id,'Saved',true,'ConfigurationLocked',jsonb_build_object('Stations',v_submissions>0,'Marketplace',v_purchases>0,'Judging',v_judging>0));
end $$;

create or replace function public.exos_v2_formula_race_reconcile_station_ranking(p_event_id text,p_activity_id text,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_station jsonb:='{}'::jsonb; v_method text; v_team_count integer; v_verified_count integer; v_awarded integer:=0; v_row record; v_credits integer;
begin
 if nullif(trim(p_actor),'') is null then raise exception 'Facilitator identity is required'; end if;
 select coalesce(activity_payload->'race_station','{}'::jsonb) into v_station from public.activities_v2 where activity_id=trim(p_activity_id);
 if not found then raise exception 'Station not found'; end if;
 v_method:=upper(coalesce(v_station->>'ScoringMethod','NON_SCORING'));
 if v_method not in ('LOWEST_TIME','HIGHEST_COUNT','SUCCESS_COUNT') then return jsonb_build_object('Ranked',false,'Reason','This scoring method does not rank verified results'); end if;
 select count(*) into v_team_count from public.teams_v2 where event_id=trim(p_event_id) and is_active=true;
 select count(distinct team_id) into v_verified_count from public.submissions_v2 where event_id=trim(p_event_id) and activity_id=trim(p_activity_id) and submission_status='APPROVED';
 if v_team_count=0 or v_verified_count<>v_team_count then return jsonb_build_object('Ranked',false,'RankPending',true,'VerifiedTeams',v_verified_count,'ActiveTeams',v_team_count); end if;
 for v_row in
  select s.submission_id,s.team_id,s.participant_id,rank() over(order by case when v_method='LOWEST_TIME' then coalesce((s.submission_payload->>'official_result')::numeric,s.score) end asc nulls last,case when v_method in ('HIGHEST_COUNT','SUCCESS_COUNT') then coalesce((s.submission_payload->>'official_result')::numeric,s.score) end desc nulls last,s.team_id asc) as placement,coalesce((s.submission_payload->>'official_result')::numeric,s.score,0) as official_result from public.submissions_v2 s where s.event_id=trim(p_event_id) and s.activity_id=trim(p_activity_id) and s.submission_status='APPROVED'
 loop
  v_credits:=coalesce(nullif(v_station->'PerformanceCredits'->'RankCredits'->>v_row.placement::text,'')::integer,case when v_method='SUCCESS_COUNT' then coalesce(nullif(v_station->'PerformanceCredits'->>'PerSuccess','')::integer,0)*v_row.official_result::integer else 0 end);
  update public.submissions_v2 set submission_payload=submission_payload||jsonb_build_object('official_result',v_row.official_result,'official_rank',v_row.placement,'rank_status','CREDITS_AWARDED'),updated_at=now() where submission_id=v_row.submission_id;
  if v_credits<>0 then insert into public.credit_transactions_v2(event_id,team_id,participant_id,transaction_type,amount,idempotency_key,reason,created_by) values(trim(p_event_id),v_row.team_id,v_row.participant_id,'RACE_STATION_PERFORMANCE',v_credits,'race-station-performance|'||trim(p_activity_id)||'|'||v_row.team_id,'R.A.C.E. verified station performance Credits',trim(p_actor)) on conflict(event_id,idempotency_key) do update set amount=excluded.amount,reason=excluded.reason; end if;
  v_awarded:=v_awarded+1;
 end loop;
 return jsonb_build_object('Ranked',true,'RankPending',false,'Teams',v_awarded,'TiePolicy','RANK() with TeamID deterministic display order');
end $$;

create or replace function public.exos_v2_formula_race_submit_station(
 p_session_token uuid,p_device_id text,p_activity_id text,p_text_response text default '',p_storage_reference text default '',p_idempotency_key text default '',p_result_value numeric default null,p_result_unit text default '')
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_session public.team_access_sessions_v2%rowtype; v_activity public.activities_v2%rowtype; v_submission public.submissions_v2%rowtype;
 v_config jsonb; v_station jsonb:='{}'::jsonb; v_route jsonb:='[]'::jsonb; v_current text; v_next text; v_revision integer; v_actor uuid; v_requirement text; v_method text; v_min numeric; v_max numeric;
begin
 select * into v_session from public.team_access_sessions_v2 where session_token=p_session_token and device_id=trim(p_device_id) and is_active=true limit 1 for update;
 if not found then raise exception 'Invalid captain session'; end if;
 select a.* into v_activity from public.activities_v2 a join public.modules_v2 m on m.module_id=a.module_id join public.programmes_v2 p on p.programme_id=m.programme_id where a.activity_id=trim(p_activity_id) and p.event_id=v_session.event_id and a.activity_type='CHECKPOINT' limit 1;
 if not found then raise exception 'Station does not belong to this R.A.C.E. event'; end if;
 select coalesce(event_payload->'RaceConfiguration','{}'::jsonb) into v_config from public.events_v2 where event_id=v_session.event_id;
 select value into v_station from jsonb_array_elements(coalesce(v_config->'Stations','[]'::jsonb)) where value->>'ActivityID'=v_activity.activity_id limit 1;
 v_station:=coalesce(v_station,v_activity.activity_payload->'race_station','{}'::jsonb);
 v_route:=coalesce(v_config->'TeamRoutes'->v_session.team_id,'[]'::jsonb);
 if jsonb_array_length(v_route)>0 then
  select r.value into v_current from jsonb_array_elements_text(v_route) with ordinality r(value,position)
   where not exists (select 1 from public.submissions_v2 s where s.event_id=v_session.event_id and s.team_id=v_session.team_id and s.activity_id=r.value and s.submission_status<>'REJECTED') order by r.position limit 1;
  if v_current is null then raise exception 'Configured station route is already complete'; end if;
  if v_current<>v_activity.activity_id then raise exception 'Only the configured current station can be submitted'; end if;
  select r.value into v_next from jsonb_array_elements_text(v_route) with ordinality r(value,position) where r.position=(select position+1 from jsonb_array_elements_text(v_route) with ordinality q(value,position) where q.value=v_current limit 1) limit 1;
 end if;
 v_requirement:=upper(coalesce(v_station->>'EvidenceRequirement',v_station->>'evidence_requirement','PHOTO_OPTIONAL'));
 if v_requirement='PHOTO_REQUIRED' and nullif(trim(p_storage_reference),'') is null then raise exception 'Photo evidence is required for this station'; end if;
 v_method:=upper(coalesce(v_station->>'ScoringMethod',v_station->>'scoring_method','NON_SCORING'));
 if v_method in ('LOWEST_TIME','HIGHEST_COUNT','SUCCESS_COUNT') and p_result_value is null then raise exception 'A result value is required for this scoring method'; end if;
 v_min:=nullif(v_station->>'ResultMinimum','')::numeric; v_max:=nullif(v_station->>'ResultMaximum','')::numeric;
 if p_result_value is not null and ((v_min is not null and p_result_value<v_min) or (v_max is not null and p_result_value>v_max)) then raise exception 'Result is outside the station configuration range'; end if;
 perform pg_advisory_xact_lock(hashtextextended(v_session.event_id||'|RACE_STATION|'||v_session.team_id||'|'||v_activity.activity_id,41));
 select * into v_submission from public.submissions_v2 where event_id=v_session.event_id and team_id=v_session.team_id and activity_id=v_activity.activity_id order by submitted_at desc limit 1 for update;
 if found and v_submission.submission_status<>'REJECTED' then return jsonb_build_object('SubmissionID',v_submission.submission_id::text,'Status',v_submission.submission_status,'Duplicate',true,'NextActivityID',coalesce(v_next,'')); end if;
 select count(*)+1 into v_revision from public.submissions_v2 where event_id=v_session.event_id and team_id=v_session.team_id and activity_id=v_activity.activity_id;
 v_actor:=(public.exos_v2_formula_race_captain_actor(v_session.event_id,v_session.team_id)->>'ParticipantID')::uuid;
 insert into public.submissions_v2(event_id,team_id,participant_id,activity_id,submission_key,submission_status,submission_payload)
 values(v_session.event_id,v_session.team_id,v_actor,v_activity.activity_id,'race-station|'||v_session.event_id||'|'||v_session.team_id||'|'||v_activity.activity_id||'|revision:'||v_revision,'SUBMITTED',jsonb_build_object('text_response',coalesce(p_text_response,''),'storage_reference',coalesce(p_storage_reference,''),'result_value',p_result_value,'result_unit',coalesce(p_result_unit,''),'captain_request_key',nullif(trim(p_idempotency_key),''))) returning * into v_submission;
 insert into public.submission_evidence_v2(submission_id,evidence_type,evidence_uri,evidence_payload,captured_by) values(v_submission.submission_id,case when nullif(trim(p_storage_reference),'') is null then 'TEXT' else 'PHOTO' end,nullif(trim(p_storage_reference),''),jsonb_build_object('text',coalesce(p_text_response,''),'uri',coalesce(p_storage_reference,'')),'RACE_CAPTAIN');
 return jsonb_build_object('SubmissionID',v_submission.submission_id::text,'EventID',v_session.event_id,'TeamID',v_session.team_id,'Status','SUBMITTED','Revision',v_revision,'Duplicate',false,'NextActivityID',coalesce(v_next,''));
end $$;

create or replace function public.exos_v2_formula_race_verify_station_result(
 p_submission_id uuid,p_decision text,p_reviewer text,p_official_result numeric default null,p_notes text default '',p_idempotency_key text default '')
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_submission public.submissions_v2%rowtype; v_activity public.activities_v2%rowtype; v_station jsonb:='{}'::jsonb; v_decision text; v_result numeric; v_base integer;
begin
 if nullif(trim(p_reviewer),'') is null then raise exception 'Facilitator identity is required'; end if;
 v_decision:=case upper(trim(p_decision)) when 'APPROVE' then 'APPROVE' when 'APPROVED' then 'APPROVE' when 'REJECT' then 'REJECT' when 'REQUEST_RESUBMISSION' then 'REJECT' else null end; if v_decision is null then raise exception 'Unsupported station verification decision'; end if;
 select * into v_submission from public.submissions_v2 where submission_id=p_submission_id for update; if not found then raise exception 'Submission not found'; end if;
 select * into v_activity from public.activities_v2 where activity_id=v_submission.activity_id; v_station:=coalesce(v_activity.activity_payload->'race_station','{}'::jsonb);
 if v_decision='REJECT' then update public.submissions_v2 set submission_status='REJECTED',reviewed_at=now(),reviewed_by=trim(p_reviewer),updated_at=now() where submission_id=p_submission_id; return jsonb_build_object('SubmissionID',p_submission_id::text,'Decision','REJECT'); end if;
 v_result:=coalesce(p_official_result,nullif(v_submission.submission_payload->>'result_value','')::numeric);
 if upper(coalesce(v_station->>'ScoringMethod','NON_SCORING')) in ('LOWEST_TIME','HIGHEST_COUNT','SUCCESS_COUNT') and v_result is null then raise exception 'An official result is required for this station'; end if;
 v_base:=coalesce(nullif(v_station->>'BaseCredits','')::integer,nullif(v_activity.activity_payload->>'credit_award','')::integer,nullif(v_activity.activity_payload->>'credits','')::integer,0);
 update public.submissions_v2 set submission_status='APPROVED',reviewed_at=now(),reviewed_by=trim(p_reviewer),score=v_result,submission_payload=submission_payload||jsonb_build_object('official_result',v_result,'verification_notes',coalesce(p_notes,''),'verified_by',trim(p_reviewer)),updated_at=now() where submission_id=p_submission_id;
 if v_base<>0 then insert into public.credit_transactions_v2(event_id,team_id,participant_id,transaction_type,amount,idempotency_key,reason,created_by) values(v_submission.event_id,v_submission.team_id,v_submission.participant_id,'RACE_STATION_BASE',v_base,'race-station-base|'||p_submission_id::text,'R.A.C.E. verified station base Credits',trim(p_reviewer)) on conflict(event_id,idempotency_key) do nothing; end if;
 return jsonb_build_object('SubmissionID',p_submission_id::text,'Decision','APPROVE','OfficialResult',v_result,'BaseCredits',v_base,'RankPending',true);
end $$;

create or replace function public.exos_v2_formula_race_reset_event(p_event_id text,p_confirmation text,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_event public.events_v2%rowtype; v_deleted jsonb;
begin
 if nullif(trim(p_actor),'') is null then raise exception 'Reset actor is required'; end if;
 select * into v_event from public.events_v2 where event_id=trim(p_event_id) for update; if not found then raise exception 'Event not found'; end if;
 if trim(p_confirmation)<>('RESET '||v_event.event_id) then raise exception 'Typed reset confirmation does not match the EventID'; end if;
 -- Configuration, join code, teams, team identity, marketplace catalogue, judging configuration and PIN credentials remain intact.
 delete from public.projector_state_v2 where event_id=v_event.event_id;
 delete from public.race_results_v2 where event_id=v_event.event_id;
 delete from public.judging_scores_v2 where event_id=v_event.event_id;
 delete from public.build_status_v2 where event_id=v_event.event_id;
 delete from public.marketplace_transactions_v2 where event_id=v_event.event_id;
 delete from public.credit_transactions_v2 where event_id=v_event.event_id;
 delete from public.score_transactions_v2 where event_id=v_event.event_id;
 delete from public.activity_runtime_v2 where event_id=v_event.event_id;
 delete from public.submissions_v2 where event_id=v_event.event_id;
 delete from public.team_access_sessions_v2 where event_id=v_event.event_id;
 update public.events_v2 set event_payload=event_payload||jsonb_build_object('RaceLastResetAt',now(),'RaceLastResetBy',trim(p_actor)),updated_at=now() where event_id=v_event.event_id;
 return jsonb_build_object('EventID',v_event.event_id,'Reset',true,'Preserved',jsonb_build_array('event','join code','teams','team identity','station configuration','team routes','marketplace configuration','judging configuration','PIN credentials'));
end $$;

revoke all on function public.exos_v2_formula_race_save_event_configuration(text,jsonb,text) from public;
revoke all on function public.exos_v2_formula_race_reconcile_station_ranking(text,text,text) from public;
revoke all on function public.exos_v2_formula_race_submit_station(uuid,text,text,text,text,text,numeric,text) from public;
revoke all on function public.exos_v2_formula_race_verify_station_result(uuid,text,text,numeric,text,text) from public;
revoke all on function public.exos_v2_formula_race_reset_event(text,text,text) from public;
grant execute on function public.exos_v2_formula_race_save_event_configuration(text,jsonb,text) to service_role;
grant execute on function public.exos_v2_formula_race_reconcile_station_ranking(text,text,text) to service_role;
grant execute on function public.exos_v2_formula_race_submit_station(uuid,text,text,text,text,text,numeric,text) to anon,authenticated,service_role;
grant execute on function public.exos_v2_formula_race_verify_station_result(uuid,text,text,numeric,text,text) to service_role;
grant execute on function public.exos_v2_formula_race_reset_event(text,text,text) to service_role;
COMMIT;
