begin;

create or replace function public.exos_v2_formula_race_save_result(
 p_event_id text,p_team_id text,p_activity_id text,p_time_ms integer,p_penalty_ms integer,
 p_bonus numeric,p_verified boolean,p_reason text,p_actor text
)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_result public.race_results_v2%rowtype; v_before jsonb; v_after jsonb; v_action text;
begin
 if p_time_ms is null or p_time_ms<0 then raise exception 'Finish time must be zero or greater'; end if;
 if p_penalty_ms is null or p_penalty_ms<0 then raise exception 'Penalty must be zero or greater'; end if;
 if p_bonus is null or p_bonus<0 then raise exception 'Bonus must be zero or greater'; end if;
 if nullif(trim(p_reason),'') is null then raise exception 'Result or correction reason is required'; end if;
 if nullif(trim(p_actor),'') is null then raise exception 'Facilitator identity is required'; end if;
 if not exists(select 1 from public.teams_v2 where event_id=trim(p_event_id) and team_id=trim(p_team_id)) then raise exception 'R.A.C.E. team is not part of this event'; end if;
 if not exists(select 1 from public.activities_v2 where activity_id=trim(p_activity_id)) then raise exception 'R.A.C.E. result activity was not found'; end if;

 perform pg_advisory_xact_lock(hashtextextended(trim(p_event_id)||'|RACE_FINAL_RESULTS',37));
 select * into v_result from public.race_results_v2
  where event_id=trim(p_event_id) and team_id=trim(p_team_id) and activity_id=trim(p_activity_id) and checkpoint='Race Final'
  for update;

 if found and v_result.locked then raise exception 'Race result is locked and immutable until explicit unlock.'; end if;
 if found then
  v_before:=to_jsonb(v_result);
  update public.race_results_v2 set
   result_payload=jsonb_build_object('time_ms',p_time_ms,'penalty_ms',p_penalty_ms,'bonus',p_bonus,'verified',coalesce(p_verified,false),'reason',trim(p_reason),'judge',trim(p_actor)),
   updated_at=now()
  where race_result_id=v_result.race_result_id
  returning to_jsonb(race_results_v2) into v_after;
  v_action:='RACE_RESULT_CORRECTED';
 else
  insert into public.race_results_v2(event_id,team_id,activity_id,checkpoint,result_payload,locked)
   values(trim(p_event_id),trim(p_team_id),trim(p_activity_id),'Race Final',
    jsonb_build_object('time_ms',p_time_ms,'penalty_ms',p_penalty_ms,'bonus',p_bonus,'verified',coalesce(p_verified,false),'reason',trim(p_reason),'judge',trim(p_actor)),false)
   returning to_jsonb(race_results_v2) into v_after;
  v_before:='{}'::jsonb;
  v_action:='RACE_RESULT_RECORDED';
 end if;

 insert into public.audit_log_v2(event_id,actor,action,entity_type,entity_id,before_state,after_state)
  values(trim(p_event_id),trim(p_actor),v_action,'race_results_v2',v_after->>'race_result_id',v_before,v_after);
 return jsonb_build_object('RaceResultID',v_after->>'race_result_id','Corrected',v_action='RACE_RESULT_CORRECTED');
end $$;

revoke all on function public.exos_v2_formula_race_save_result(text,text,text,integer,integer,numeric,boolean,text,text) from public;
grant execute on function public.exos_v2_formula_race_save_result(text,text,text,integer,integer,numeric,boolean,text,text) to service_role;

commit;
