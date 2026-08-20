-- EXOS result status, manual placement and deterministic final ranking.
--
-- Additive and non-destructive: no table, column, constraint or row is altered.
-- race_results_v2.result_payload is already jsonb, so status and placement need
-- no schema change; only the two functions that write and rank results do.
--
-- Backward compatibility: a row with no result_status is read as FINISHED, so
-- historical rows keep their exact meaning and previously locked events would
-- reproduce the identical ranking under the new ordering.
--
-- Depends on 020, 029 and 032. R.A.C.E.-only; Standard EXOS is untouched.
BEGIN;

-- The signature gains two defaulted parameters.  The old nine-argument
-- function must be removed rather than left beside the new one, or PostgREST
-- sees two candidates and every call fails as ambiguous (PGRST203).  Dropping
-- a function touches no data.
drop function if exists public.exos_v2_formula_race_save_result(text,text,text,integer,integer,numeric,boolean,text,text);

create or replace function public.exos_v2_formula_race_save_result(
 p_event_id text,p_team_id text,p_activity_id text,p_time_ms integer,p_penalty_ms integer,
 p_bonus numeric,p_verified boolean,p_reason text,p_actor text,
 p_result_status text default 'FINISHED',p_manual_placement integer default null
)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_result public.race_results_v2%rowtype; v_before jsonb; v_after jsonb; v_action text;
 v_status text; v_time integer; v_penalty integer; v_placement integer; v_payload jsonb;
begin
 v_status:=upper(coalesce(nullif(trim(p_result_status),''),'FINISHED'));
 if v_status not in ('FINISHED','DNF','DNS','DISQUALIFIED') then raise exception 'Unsupported result status'; end if;
 if p_bonus is null or p_bonus<0 then raise exception 'Bonus must be zero or greater'; end if;
 if nullif(trim(p_reason),'') is null then raise exception 'Result or correction reason is required'; end if;
 if nullif(trim(p_actor),'') is null then raise exception 'Facilitator identity is required'; end if;
 if not exists(select 1 from public.teams_v2 where event_id=trim(p_event_id) and team_id=trim(p_team_id)) then raise exception 'R.A.C.E. team is not part of this event'; end if;
 if not exists(select 1 from public.activities_v2 where activity_id=trim(p_activity_id)) then raise exception 'R.A.C.E. result activity was not found'; end if;

 if v_status='FINISHED' then
  if p_time_ms is null or p_time_ms<0 then raise exception 'Finish time must be zero or greater'; end if;
  if p_penalty_ms is null or p_penalty_ms<0 then raise exception 'Penalty must be zero or greater'; end if;
  if p_manual_placement is not null then raise exception 'A finished result is ranked by its time, not by manual placement'; end if;
  v_time:=p_time_ms; v_penalty:=p_penalty_ms; v_placement:=null;
 else
  -- A non-finisher must never carry a fabricated time in order to be rankable.
  if coalesce(p_time_ms,0)<>0 then raise exception 'A non-finished result must not carry a finish time'; end if;
  if p_manual_placement is not null and p_manual_placement<1 then raise exception 'Manual placement must be 1 or greater'; end if;
  v_time:=null; v_penalty:=0; v_placement:=p_manual_placement;
 end if;

 perform pg_advisory_xact_lock(hashtextextended(trim(p_event_id)||'|RACE_FINAL_RESULTS',37));

 if v_placement is not null and exists(
  select 1 from public.race_results_v2 r
  where r.event_id=trim(p_event_id) and r.checkpoint='Race Final'
    and r.team_id<>trim(p_team_id)
    and coalesce((r.result_payload->>'manual_placement')::integer,0)=v_placement
 ) then raise exception 'Manual placement % is already assigned in this event',v_placement; end if;

 select * into v_result from public.race_results_v2
  where event_id=trim(p_event_id) and team_id=trim(p_team_id) and activity_id=trim(p_activity_id) and checkpoint='Race Final'
  for update;
 if found and v_result.locked then raise exception 'Race result is locked and immutable until explicit unlock.'; end if;

 v_payload:=jsonb_build_object(
  'time_ms',v_time,'penalty_ms',v_penalty,'bonus',p_bonus,'verified',coalesce(p_verified,false),
  'reason',trim(p_reason),'judge',trim(p_actor),'result_status',v_status,'manual_placement',v_placement);

 if found then
  v_before:=to_jsonb(v_result);
  update public.race_results_v2 set result_payload=v_payload,updated_at=now()
   where race_result_id=v_result.race_result_id returning to_jsonb(race_results_v2) into v_after;
  v_action:='RACE_RESULT_CORRECTED';
 else
  insert into public.race_results_v2(event_id,team_id,activity_id,checkpoint,result_payload,locked)
   values(trim(p_event_id),trim(p_team_id),trim(p_activity_id),'Race Final',v_payload,false)
   returning to_jsonb(race_results_v2) into v_after;
  v_before:='{}'::jsonb; v_action:='RACE_RESULT_RECORDED';
 end if;

 insert into public.audit_log_v2(event_id,actor,action,entity_type,entity_id,before_state,after_state)
  values(trim(p_event_id),trim(p_actor),v_action,'race_results_v2',v_after->>'race_result_id',v_before,v_after);
 return jsonb_build_object('RaceResultID',v_after->>'race_result_id','Corrected',v_action='RACE_RESULT_CORRECTED',
  'ResultStatus',v_status,'ManualPlacement',v_placement);
end $$;

-- The lock keeps every existing guarantee and only replaces its ordering with
-- the contract in engines/exos_result_contract.py: finished results by adjusted
-- time, then explicitly placed non-finishers, then the remainder by status,
-- with team_id as the final deterministic tie-break.
create or replace function public.exos_v2_formula_race_lock_final_results(p_event_id text,p_actor text,p_reason text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_team_count integer; v_result_count integer; v_distinct_result_team_count integer; v_already_locked integer; v_duplicate integer;
begin
 if nullif(trim(p_actor),'') is null or nullif(trim(p_reason),'') is null then raise exception 'Facilitator identity and lock reason are required'; end if;
 perform pg_advisory_xact_lock(hashtextextended(trim(p_event_id)||'|RACE_FINAL_RESULTS',37));
 select count(*) into v_team_count from public.teams_v2 where event_id=trim(p_event_id) and is_active=true;
 select count(*),count(distinct r.team_id) into v_result_count,v_distinct_result_team_count from public.race_results_v2 r join public.teams_v2 t on t.team_id=r.team_id and t.event_id=r.event_id where r.event_id=trim(p_event_id) and r.checkpoint='Race Final' and coalesce((r.result_payload->>'verified')::boolean,false)=true and t.is_active=true;
 if v_team_count=0 or v_result_count<>v_team_count or v_distinct_result_team_count<>v_team_count then raise exception 'Every active team requires one verified Race Final result before locking'; end if;
 select count(*) into v_duplicate from (
  select (r.result_payload->>'manual_placement')::integer as placement
  from public.race_results_v2 r where r.event_id=trim(p_event_id) and r.checkpoint='Race Final'
   and nullif(r.result_payload->>'manual_placement','') is not null
  group by 1 having count(*)>1) d;
 if v_duplicate>0 then raise exception 'Manual placement must be unique before the final ranking can be locked'; end if;
 select count(*) into v_already_locked from public.race_results_v2 where event_id=trim(p_event_id) and checkpoint='Race Final' and locked=true;
 if v_already_locked=v_team_count then perform public.exos_v2_formula_race_reconcile_championship(trim(p_event_id),trim(p_actor)); return jsonb_build_object('Locked',true,'EventID',trim(p_event_id),'AlreadyLocked',true); end if;
 if v_already_locked>0 then raise exception 'Race Final has a partial lock state and requires controlled reconciliation'; end if;
 with ranked as (
  select r.race_result_id,
   row_number() over(order by
    case when coalesce(r.result_payload->>'result_status','FINISHED')='FINISHED' then 0 else 1 end,
    case when coalesce(r.result_payload->>'result_status','FINISHED')='FINISHED'
     then coalesce((r.result_payload->>'time_ms')::bigint,(r.result_payload->>'finish_time_ms')::bigint,0)
          +coalesce((r.result_payload->>'penalty_ms')::bigint,0) else null end asc nulls last,
    coalesce((r.result_payload->>'manual_placement')::integer,2147483647) asc,
    case coalesce(r.result_payload->>'result_status','FINISHED')
     when 'FINISHED' then 0 when 'DNF' then 1 when 'DNS' then 2 when 'DISQUALIFIED' then 3 else 4 end,
    r.team_id asc) as final_rank
  from public.race_results_v2 r
  where r.event_id=trim(p_event_id) and r.checkpoint='Race Final' and coalesce((r.result_payload->>'verified')::boolean,false)=true)
 update public.race_results_v2 r set ranking_position=ranked.final_rank,locked=true,updated_at=now(),
  result_payload=r.result_payload||jsonb_build_object('locked_by',trim(p_actor),'lock_reason',trim(p_reason))
 from ranked where r.race_result_id=ranked.race_result_id;
 perform public.exos_v2_formula_race_reconcile_championship(trim(p_event_id),trim(p_actor));
 return jsonb_build_object('Locked',true,'EventID',trim(p_event_id),'AlreadyLocked',false,
  'RankingMetric','FINISHED by time_ms + penalty_ms, then manual_placement, then status, TeamID ASC',
  'ChampionshipReconciled',true);
end $$;

revoke all on function public.exos_v2_formula_race_save_result(text,text,text,integer,integer,numeric,boolean,text,text,text,integer) from public;
grant execute on function public.exos_v2_formula_race_save_result(text,text,text,integer,integer,numeric,boolean,text,text,text,integer) to service_role;
revoke all on function public.exos_v2_formula_race_lock_final_results(text,text,text) from public;
grant execute on function public.exos_v2_formula_race_lock_final_results(text,text,text) to service_role;

COMMIT;
