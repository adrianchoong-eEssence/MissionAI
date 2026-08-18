-- Formula R.A.C.E. event-configurable championship components.
-- Depends on 020, 030 and 031. R.A.C.E.-only; Standard EXOS is untouched.
BEGIN;

create table if not exists public.race_championship_team_photos_v2 (
 team_photo_id uuid primary key default extensions.gen_random_uuid(),
 event_id text not null references public.events_v2(event_id) on delete cascade,
 team_id text not null references public.teams_v2(team_id) on delete restrict,
 build_activity_id text references public.activities_v2(activity_id) on delete set null,
 storage_reference text not null,
 build_context jsonb not null default '{}'::jsonb,
 is_current boolean not null default true,
 correction_of uuid references public.race_championship_team_photos_v2(team_photo_id),
 submitted_at timestamptz not null default now(),
 submitted_by text not null
);
create unique index if not exists race_championship_team_photos_current_uidx on public.race_championship_team_photos_v2(event_id,team_id) where is_current;
create index if not exists race_championship_team_photos_event_team_idx on public.race_championship_team_photos_v2(event_id,team_id,submitted_at desc);
alter table public.race_championship_team_photos_v2 enable row level security;
revoke all on table public.race_championship_team_photos_v2 from anon,authenticated;

create or replace function public.exos_v2_formula_race_reconcile_championship(p_event_id text,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_config jsonb; v_components jsonb; v_component jsonb; v_team record; v_criterion text; v_criterion_max numeric; v_score numeric; v_score_recorded timestamptz; v_points numeric; v_rank integer; v_locked boolean; v_photo boolean; v_photo_submitted timestamptz; v_count integer:=0;
begin
 if nullif(trim(p_actor),'') is null then raise exception 'Facilitator identity is required'; end if;
 select coalesce(event_payload->'RaceConfiguration','{}'::jsonb) into v_config from public.events_v2 where event_id=trim(p_event_id) for update;
 if v_config is null then raise exception 'R.A.C.E. event not found'; end if;
 v_components:=coalesce(v_config->'ChampionshipComponents','[]'::jsonb);
 update public.score_transactions_v2 set score_delta=0,reason='R.A.C.E. championship component disabled or superseded',source_reference=source_reference||jsonb_build_object('reconciled_by',trim(p_actor),'reconciled_at',now()) where event_id=trim(p_event_id) and idempotency_key like 'race-championship-component|%';
 for v_component in select value from jsonb_array_elements(v_components) where coalesce((value->>'Enabled')::boolean,true) loop
  for v_team in select team_id from public.teams_v2 where event_id=trim(p_event_id) and is_active=true order by team_id loop
   v_points:=0; v_criterion:=coalesce(v_component->>'SourceReference','');
   if v_component->>'ComponentType' in ('JUDGING_CRITERION','TEAM_PHOTO') then
    select coalesce(nullif(value->>'MaximumScore','')::numeric,0) into v_criterion_max from jsonb_array_elements(coalesce(v_config->'JudgingCriteria','[]'::jsonb)) where value->>'CriterionName'=v_criterion and coalesce((value->>'Enabled')::boolean,true) limit 1;
    select score_value,recorded_at into v_score,v_score_recorded from public.judging_scores_v2 where event_id=trim(p_event_id) and team_id=v_team.team_id and score_dimension=v_criterion and decision='SUBMITTED' order by recorded_at desc,judging_score_id desc limit 1;
    select exists(select 1 from public.race_championship_team_photos_v2 where event_id=trim(p_event_id) and team_id=v_team.team_id and is_current),max(submitted_at) into v_photo,v_photo_submitted from public.race_championship_team_photos_v2 where event_id=trim(p_event_id) and team_id=v_team.team_id and is_current;
    if v_criterion_max>0 and v_score is not null and (v_component->>'ComponentType'<>'TEAM_PHOTO' or (v_photo and v_score_recorded>=v_photo_submitted)) then v_points:=round(least(greatest(v_score,0),v_criterion_max)/v_criterion_max*coalesce(nullif(v_component->>'MaximumChampionshipPoints','')::numeric,0),2); end if;
   elsif v_component->>'ComponentType'='RACE_RANK' then
    select r.ranking_position,r.locked into v_rank,v_locked from public.race_results_v2 r where r.event_id=trim(p_event_id) and r.team_id=v_team.team_id and r.checkpoint='Race Final' limit 1;
    if coalesce(v_locked,false) and v_rank is not null then v_points:=coalesce(nullif(v_component->'ScoringConfiguration'->'RankPoints'->>v_rank::text,'')::numeric,0); end if;
   end if;
   insert into public.score_transactions_v2(event_id,team_id,submission_id,scoring_mode,score_delta,reason,idempotency_key,source_reference,created_by)
    values(trim(p_event_id),v_team.team_id,null,'TEAM_COMPETITIVE',v_points,'R.A.C.E. championship component: '||coalesce(v_component->>'DisplayName',v_component->>'ComponentID'),'race-championship-component|'||coalesce(v_component->>'ComponentID','')||'|'||v_team.team_id,jsonb_build_object('component_id',v_component->>'ComponentID','component_type',v_component->>'ComponentType','source_reference',v_criterion,'points',v_points),trim(p_actor))
    on conflict(event_id,idempotency_key) do update set score_delta=excluded.score_delta,reason=excluded.reason,source_reference=excluded.source_reference,created_by=excluded.created_by;
   v_count:=v_count+1;
  end loop;
 end loop;
 return jsonb_build_object('Reconciled',true,'ComponentAwards',v_count);
end $$;

create or replace function public.exos_v2_formula_race_submit_team_photo(p_session_token uuid,p_device_id text,p_storage_reference text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_session public.team_access_sessions_v2%rowtype; v_previous public.race_championship_team_photos_v2%rowtype; v_build record; v_id uuid; v_replaced boolean:=false;
begin
 if nullif(trim(p_storage_reference),'') is null or p_storage_reference not like 'supabase://exos-submissions/%' then raise exception 'A private R.A.C.E. Team Photo is required'; end if;
 select * into v_session from public.team_access_sessions_v2 where session_token=p_session_token and device_id=trim(p_device_id) and is_active=true limit 1 for update;
 if not found then raise exception 'Invalid captain session'; end if;
 if not exists(select 1 from jsonb_array_elements(coalesce((select event_payload->'RaceConfiguration'->'ChampionshipComponents' from public.events_v2 where event_id=v_session.event_id),'[]'::jsonb)) c(value) where c.value->>'ComponentType'='TEAM_PHOTO' and coalesce((c.value->>'Enabled')::boolean,true)) then raise exception 'Team Photo is not enabled for this R.A.C.E. event'; end if;
 select activity_id,build_status,progress_pct into v_build from public.build_status_v2 where event_id=v_session.event_id and team_id=v_session.team_id order by last_updated desc limit 1;
 if v_build.activity_id is null or v_build.build_status<>'COMPLETED' then raise exception 'Complete the Team Garage build before submitting the Team Photo'; end if;
 select * into v_previous from public.race_championship_team_photos_v2 where event_id=v_session.event_id and team_id=v_session.team_id and is_current for update;
 if found then v_replaced:=true; update public.race_championship_team_photos_v2 set is_current=false where team_photo_id=v_previous.team_photo_id; end if;
 insert into public.race_championship_team_photos_v2(event_id,team_id,build_activity_id,storage_reference,build_context,correction_of,submitted_by) values(v_session.event_id,v_session.team_id,v_build.activity_id,trim(p_storage_reference),jsonb_build_object('BuildStatus',v_build.build_status,'Progress',v_build.progress_pct),case when v_replaced then v_previous.team_photo_id else null end,'RACE_CAPTAIN') returning team_photo_id into v_id;
 perform public.exos_v2_formula_race_reconcile_championship(v_session.event_id,'RACE_CAPTAIN TEAM PHOTO');
 return jsonb_build_object('TeamPhotoID',v_id::text,'Submitted',true,'Replaced',v_replaced);
end $$;

create or replace function public.exos_v2_formula_race_save_judging_score(p_event_id text,p_team_id text,p_judge text,p_criterion text,p_score numeric,p_reason text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_config jsonb; v_max numeric; v_activity text; v_id uuid;
begin
 if nullif(trim(p_judge),'') is null or nullif(trim(p_reason),'') is null then raise exception 'Judge identity and reason are required'; end if;
 select coalesce(event_payload->'RaceConfiguration','{}'::jsonb) into v_config from public.events_v2 where event_id=trim(p_event_id);
 select coalesce(nullif(value->>'MaximumScore','')::numeric,0) into v_max from jsonb_array_elements(coalesce(v_config->'JudgingCriteria','[]'::jsonb)) where value->>'CriterionName'=trim(p_criterion) and coalesce((value->>'Enabled')::boolean,true) limit 1;
 if v_max is null then raise exception 'Configured judging criterion is not enabled'; end if;
 if p_score is null or p_score<0 or p_score>v_max then raise exception 'Judging score is outside the configured maximum'; end if;
 select coalesce((select build_activity_id from public.race_championship_team_photos_v2 where event_id=trim(p_event_id) and team_id=trim(p_team_id) and is_current limit 1),(select activity_id from public.activities_v2 a join public.modules_v2 m on m.module_id=a.module_id join public.programmes_v2 p on p.programme_id=m.programme_id where p.event_id=trim(p_event_id) order by a.activity_order,a.activity_id limit 1)) into v_activity;
 insert into public.judging_scores_v2(event_id,team_id,activity_id,judge_name,score_dimension,score_value,decision,rationale) values(trim(p_event_id),trim(p_team_id),v_activity,trim(p_judge),trim(p_criterion),p_score,'SUBMITTED',trim(p_reason)) on conflict(event_id,team_id,activity_id,judge_name,score_dimension) do update set score_value=excluded.score_value,decision=excluded.decision,rationale=excluded.rationale,recorded_at=now() returning judging_score_id into v_id;
 perform public.exos_v2_formula_race_reconcile_championship(trim(p_event_id),trim(p_judge));
 return jsonb_build_object('JudgingScoreID',v_id::text,'Saved',true);
end $$;

create or replace function public.exos_v2_formula_race_lock_final_results(p_event_id text,p_actor text,p_reason text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_team_count integer; v_result_count integer; v_distinct_result_team_count integer; v_already_locked integer;
begin
 if nullif(trim(p_actor),'') is null or nullif(trim(p_reason),'') is null then raise exception 'Facilitator identity and lock reason are required'; end if;
 perform pg_advisory_xact_lock(hashtextextended(trim(p_event_id)||'|RACE_FINAL_RESULTS',37));
 select count(*) into v_team_count from public.teams_v2 where event_id=trim(p_event_id) and is_active=true;
 select count(*),count(distinct r.team_id) into v_result_count,v_distinct_result_team_count from public.race_results_v2 r join public.teams_v2 t on t.team_id=r.team_id and t.event_id=r.event_id where r.event_id=trim(p_event_id) and r.checkpoint='Race Final' and coalesce((r.result_payload->>'verified')::boolean,false)=true and t.is_active=true;
 if v_team_count=0 or v_result_count<>v_team_count or v_distinct_result_team_count<>v_team_count then raise exception 'Every active team requires one verified Race Final result before locking'; end if;
 select count(*) into v_already_locked from public.race_results_v2 where event_id=trim(p_event_id) and checkpoint='Race Final' and locked=true;
 if v_already_locked=v_team_count then perform public.exos_v2_formula_race_reconcile_championship(trim(p_event_id),trim(p_actor)); return jsonb_build_object('Locked',true,'EventID',trim(p_event_id),'AlreadyLocked',true); end if;
 if v_already_locked>0 then raise exception 'Race Final has a partial lock state and requires controlled reconciliation'; end if;
 with ranked as (select r.race_result_id,row_number() over(order by coalesce((r.result_payload->>'time_ms')::bigint,(r.result_payload->>'finish_time_ms')::bigint,0)+coalesce((r.result_payload->>'penalty_ms')::bigint,0),r.team_id asc) as final_rank from public.race_results_v2 r where r.event_id=trim(p_event_id) and r.checkpoint='Race Final' and coalesce((r.result_payload->>'verified')::boolean,false)=true) update public.race_results_v2 r set ranking_position=ranked.final_rank,locked=true,updated_at=now(),result_payload=r.result_payload||jsonb_build_object('locked_by',trim(p_actor),'lock_reason',trim(p_reason)) from ranked where r.race_result_id=ranked.race_result_id;
 perform public.exos_v2_formula_race_reconcile_championship(trim(p_event_id),trim(p_actor));
 return jsonb_build_object('Locked',true,'EventID',trim(p_event_id),'AlreadyLocked',false,'RankingMetric','time_ms + penalty_ms, TeamID ASC','ChampionshipReconciled',true);
end $$;

revoke all on function public.exos_v2_formula_race_reconcile_championship(text,text) from public;
revoke all on function public.exos_v2_formula_race_submit_team_photo(uuid,text,text) from public;
revoke all on function public.exos_v2_formula_race_save_judging_score(text,text,text,text,numeric,text) from public;
revoke all on function public.exos_v2_formula_race_lock_final_results(text,text,text) from public;
grant execute on function public.exos_v2_formula_race_reconcile_championship(text,text) to service_role;
grant execute on function public.exos_v2_formula_race_submit_team_photo(uuid,text,text) to service_role;
grant execute on function public.exos_v2_formula_race_save_judging_score(text,text,text,text,numeric,text) to service_role;
grant execute on function public.exos_v2_formula_race_lock_final_results(text,text,text) to service_role;
COMMIT;
