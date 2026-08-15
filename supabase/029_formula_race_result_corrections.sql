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

begin;

-- Replaces the 023 lock function so the current 029 chain rejects duplicate
-- Race Final rows as well as missing active-team rows before any lock write.
create or replace function public.exos_v2_formula_race_lock_final_results(p_event_id text,p_actor text,p_reason text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_team_count integer; v_result_count integer; v_distinct_result_team_count integer; v_already_locked integer;
begin
 if nullif(trim(p_actor),'') is null or nullif(trim(p_reason),'') is null then raise exception 'Facilitator identity and lock reason are required'; end if;
 perform pg_advisory_xact_lock(hashtextextended(trim(p_event_id)||'|RACE_FINAL_RESULTS',37));
 select count(*) into v_team_count from public.teams_v2 where event_id=trim(p_event_id) and is_active=true;
 select count(*),count(distinct r.team_id) into v_result_count,v_distinct_result_team_count
 from public.race_results_v2 r join public.teams_v2 t on t.team_id=r.team_id and t.event_id=r.event_id
 where r.event_id=trim(p_event_id) and r.checkpoint='Race Final' and coalesce((r.result_payload->>'verified')::boolean,false)=true and t.is_active=true;
 if v_team_count=0 or v_result_count<>v_team_count or v_distinct_result_team_count<>v_team_count then raise exception 'Every active team requires one verified Race Final result before locking'; end if;
 select count(*) into v_already_locked from public.race_results_v2 where event_id=trim(p_event_id) and checkpoint='Race Final' and locked=true;
 if v_already_locked=v_team_count then return jsonb_build_object('Locked',true,'EventID',trim(p_event_id),'AlreadyLocked',true); end if;
 if v_already_locked>0 then raise exception 'Race Final has a partial lock state and requires controlled reconciliation'; end if;
 with ranked as (
  select r.race_result_id,row_number() over(order by coalesce((r.result_payload->>'time_ms')::bigint,(r.result_payload->>'finish_time_ms')::bigint,0)+coalesce((r.result_payload->>'penalty_ms')::bigint,0),r.team_id asc) as final_rank
  from public.race_results_v2 r where r.event_id=trim(p_event_id) and r.checkpoint='Race Final' and coalesce((r.result_payload->>'verified')::boolean,false)=true
 ) update public.race_results_v2 r set ranking_position=ranked.final_rank,locked=true,updated_at=now(),result_payload=r.result_payload||jsonb_build_object('locked_by',trim(p_actor),'lock_reason',trim(p_reason)) from ranked where r.race_result_id=ranked.race_result_id;
 return jsonb_build_object('Locked',true,'EventID',trim(p_event_id),'AlreadyLocked',false,'RankingMetric','time_ms + penalty_ms, TeamID ASC');
end $$;

revoke all on function public.exos_v2_formula_race_lock_final_results(text,text,text) from public;
grant execute on function public.exos_v2_formula_race_lock_final_results(text,text,text) to service_role;

commit;
