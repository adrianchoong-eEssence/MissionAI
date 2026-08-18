-- Formula R.A.C.E. result-entry ownership.
-- Forward migration; depends on migrations 030 and 031 being installed.
-- R.A.C.E.-only: Captain proof and the official performance result are separate.
BEGIN;

create or replace function public.exos_v2_formula_race_submit_station(
 p_session_token uuid,p_device_id text,p_activity_id text,p_text_response text default '',p_storage_reference text default '',p_idempotency_key text default '',p_result_value numeric default null,p_result_unit text default '')
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_session public.team_access_sessions_v2%rowtype; v_activity public.activities_v2%rowtype; v_submission public.submissions_v2%rowtype;
 v_config jsonb; v_station jsonb:='{}'::jsonb; v_route jsonb:='[]'::jsonb; v_current text; v_next text; v_revision integer; v_actor uuid; v_requirement text; v_method text; v_result_owner text; v_min numeric; v_max numeric;
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
 v_result_owner:=upper(coalesce(v_station->>'ResultEntryOwner',v_station->>'result_entry_owner','FACILITATOR'));
 if v_result_owner not in ('FACILITATOR','CAPTAIN') then raise exception 'Unsupported station result entry owner'; end if;
 if v_method='FACILITATOR_SCORE' then v_result_owner:='FACILITATOR'; end if;
 if v_result_owner='FACILITATOR' and p_result_value is not null then raise exception 'Official result is entered by the facilitator for this station'; end if;
 if v_result_owner='CAPTAIN' and v_method in ('LOWEST_TIME','HIGHEST_COUNT','SUCCESS_COUNT') and p_result_value is null then raise exception 'A result value is required for this Captain-entered station'; end if;
 v_min:=nullif(v_station->>'ResultMinimum','')::numeric; v_max:=nullif(v_station->>'ResultMaximum','')::numeric;
 if p_result_value is not null and ((v_min is not null and p_result_value<v_min) or (v_max is not null and p_result_value>v_max)) then raise exception 'Result is outside the station configuration range'; end if;
 perform pg_advisory_xact_lock(hashtextextended(v_session.event_id||'|RACE_STATION|'||v_session.team_id||'|'||v_activity.activity_id,41));
 select * into v_submission from public.submissions_v2 where event_id=v_session.event_id and team_id=v_session.team_id and activity_id=v_activity.activity_id order by submitted_at desc limit 1 for update;
 if found and v_submission.submission_status<>'REJECTED' then return jsonb_build_object('SubmissionID',v_submission.submission_id::text,'Status',v_submission.submission_status,'Duplicate',true,'NextActivityID',coalesce(v_next,'')); end if;
 select count(*)+1 into v_revision from public.submissions_v2 where event_id=v_session.event_id and team_id=v_session.team_id and activity_id=v_activity.activity_id;
 v_actor:=(public.exos_v2_formula_race_captain_actor(v_session.event_id,v_session.team_id)->>'ParticipantID')::uuid;
 insert into public.submissions_v2(event_id,team_id,participant_id,activity_id,submission_key,submission_status,submission_payload)
 values(v_session.event_id,v_session.team_id,v_actor,v_activity.activity_id,'race-station|'||v_session.event_id||'|'||v_session.team_id||'|'||v_activity.activity_id||'|revision:'||v_revision,'SUBMITTED',jsonb_build_object('text_response',coalesce(p_text_response,''),'storage_reference',coalesce(p_storage_reference,''),'result_value',case when v_result_owner='CAPTAIN' then p_result_value else null end,'result_unit',case when v_result_owner='CAPTAIN' then coalesce(p_result_unit,'') else '' end,'result_entry_owner',v_result_owner,'captain_request_key',nullif(trim(p_idempotency_key),''))) returning * into v_submission;
 insert into public.submission_evidence_v2(submission_id,evidence_type,evidence_uri,evidence_payload,captured_by) values(v_submission.submission_id,case when nullif(trim(p_storage_reference),'') is null then 'TEXT' else 'PHOTO' end,nullif(trim(p_storage_reference),''),jsonb_build_object('text',coalesce(p_text_response,''),'uri',coalesce(p_storage_reference,'')),'RACE_CAPTAIN');
 return jsonb_build_object('SubmissionID',v_submission.submission_id::text,'EventID',v_session.event_id,'TeamID',v_session.team_id,'Status','SUBMITTED','Revision',v_revision,'Duplicate',false,'NextActivityID',coalesce(v_next,''));
end $$;

revoke all on function public.exos_v2_formula_race_submit_station(uuid,text,text,text,text,text,numeric,text) from public;
grant execute on function public.exos_v2_formula_race_submit_station(uuid,text,text,text,text,text,numeric,text) to anon,authenticated,service_role;

COMMIT;
