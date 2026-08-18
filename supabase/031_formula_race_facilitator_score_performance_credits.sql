-- Formula R.A.C.E. facilitator-score performance Credits.
-- Forward migration; depends on migration 030 being installed.
-- R.A.C.E.-only: extends event-scoped PerformanceCredits and does not alter
-- Standard EXOS, Captain submission semantics, or rank/success scoring rules.
BEGIN;

create or replace function public.exos_v2_formula_race_reconcile_station_ranking(p_event_id text,p_activity_id text,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_station jsonb:='{}'::jsonb; v_method text; v_team_count integer; v_verified_count integer; v_awarded integer:=0; v_row record; v_credits integer;
begin
 if nullif(trim(p_actor),'') is null then raise exception 'Facilitator identity is required'; end if;
 select coalesce(activity_payload->'race_station','{}'::jsonb) into v_station from public.activities_v2 where activity_id=trim(p_activity_id);
 if not found then raise exception 'Station not found'; end if;
 v_method:=upper(coalesce(v_station->>'ScoringMethod','NON_SCORING'));
 if v_method not in ('FACILITATOR_SCORE','LOWEST_TIME','HIGHEST_COUNT','SUCCESS_COUNT') then return jsonb_build_object('Ranked',false,'Reason','This scoring method does not award verified performance Credits'); end if;
 select count(*) into v_team_count from public.teams_v2 where event_id=trim(p_event_id) and is_active=true;
 select count(distinct team_id) into v_verified_count from public.submissions_v2 where event_id=trim(p_event_id) and activity_id=trim(p_activity_id) and submission_status='APPROVED';
 if v_method<>'FACILITATOR_SCORE' and (v_team_count=0 or v_verified_count<>v_team_count) then return jsonb_build_object('Ranked',false,'RankPending',true,'VerifiedTeams',v_verified_count,'ActiveTeams',v_team_count); end if;
 for v_row in
  select s.submission_id,s.team_id,s.participant_id,
   case when v_method='FACILITATOR_SCORE' then null::bigint else rank() over(order by case when v_method='LOWEST_TIME' then coalesce((s.submission_payload->>'official_result')::numeric,s.score) end asc nulls last,case when v_method in ('HIGHEST_COUNT','SUCCESS_COUNT') then coalesce((s.submission_payload->>'official_result')::numeric,s.score) end desc nulls last,s.team_id asc) end as placement,
   coalesce((s.submission_payload->>'official_result')::numeric,s.score,0) as official_result
  from public.submissions_v2 s where s.event_id=trim(p_event_id) and s.activity_id=trim(p_activity_id) and s.submission_status='APPROVED'
 loop
  v_credits:=case when v_method='FACILITATOR_SCORE' then floor(greatest(v_row.official_result,0)*greatest(coalesce(nullif(v_station->'PerformanceCredits'->>'PerScorePoint','')::numeric,0),0))::integer else coalesce(nullif(v_station->'PerformanceCredits'->'RankCredits'->>v_row.placement::text,'')::integer,case when v_method='SUCCESS_COUNT' then coalesce(nullif(v_station->'PerformanceCredits'->>'PerSuccess','')::integer,0)*v_row.official_result::integer else 0 end) end;
  update public.submissions_v2 set submission_payload=submission_payload||jsonb_build_object('official_result',v_row.official_result,'official_rank',v_row.placement,'rank_status','CREDITS_AWARDED'),updated_at=now() where submission_id=v_row.submission_id;
  if v_credits<>0 then
   insert into public.credit_transactions_v2(event_id,team_id,participant_id,transaction_type,amount,idempotency_key,reason,created_by) values(trim(p_event_id),v_row.team_id,v_row.participant_id,'RACE_STATION_PERFORMANCE',v_credits,'race-station-performance|'||trim(p_activity_id)||'|'||v_row.team_id,'R.A.C.E. verified station performance Credits',trim(p_actor)) on conflict(event_id,idempotency_key) do update set amount=excluded.amount,reason=excluded.reason;
  elsif v_method='FACILITATOR_SCORE' then
   delete from public.credit_transactions_v2 where event_id=trim(p_event_id) and idempotency_key='race-station-performance|'||trim(p_activity_id)||'|'||v_row.team_id;
  end if;
  v_awarded:=v_awarded+1;
 end loop;
 if v_method='FACILITATOR_SCORE' then return jsonb_build_object('Ranked',false,'PerformanceCreditsReconciled',true,'VerifiedTeams',v_verified_count,'Teams',v_awarded); end if;
 return jsonb_build_object('Ranked',true,'RankPending',false,'Teams',v_awarded,'TiePolicy','RANK() with TeamID deterministic display order');
end $$;

revoke all on function public.exos_v2_formula_race_reconcile_station_ranking(text,text,text) from public;
grant execute on function public.exos_v2_formula_race_reconcile_station_ranking(text,text,text) to service_role;

COMMIT;
