-- Formula R.A.C.E. Core v2 repair. Function-only; depends on 020, 022, 023, and 024.
-- It does not alter Standard EXOS tables, RPCs, or runtime behaviour.
BEGIN;

create or replace function public.exos_v2_formula_race_captain_actor(p_event_id text, p_team_id text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_team public.teams_v2%rowtype; v_participant_id uuid;
begin
 select * into v_team from public.teams_v2 where event_id=trim(p_event_id) and team_id=trim(p_team_id) limit 1;
 if not found then raise exception 'Team does not belong to this R.A.C.E. event'; end if;
 perform pg_advisory_xact_lock(hashtextextended(v_team.event_id||'|RACE_CAPTAIN_ACTOR|'||v_team.team_id,27));
 select participant_id into v_participant_id from public.participants_v2
  where event_id=v_team.event_id and team_id=v_team.team_id
    and participant_payload->>'identity_kind'='RACE_CAPTAIN_TECHNICAL_ACTOR'
  order by created_at asc limit 1;
 if v_participant_id is null then
  insert into public.participants_v2(event_id,team_id,normalized_name,display_name,participant_payload,country,flag,participant_status,is_leader)
  values(v_team.event_id,v_team.team_id,lower('race-captain-actor:'||v_team.team_id),'R.A.C.E. Captain Technical Actor',
   jsonb_build_object('identity_kind','RACE_CAPTAIN_TECHNICAL_ACTOR','team_id',v_team.team_id),
   v_team.country,v_team.team_flag,'SYSTEM_ACTOR',false) returning participant_id into v_participant_id;
 end if;
 return jsonb_build_object('ParticipantID',v_participant_id::text,'IdentityKind','RACE_CAPTAIN_TECHNICAL_ACTOR');
end $$;

create or replace function public.exos_v2_formula_race_submit_checkpoint(
 p_session_token uuid,p_device_id text,p_activity_id text,p_text_response text default '',p_storage_reference text default '',p_idempotency_key text default '')
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_session public.team_access_sessions_v2%rowtype; v_submission public.submissions_v2%rowtype;
 v_activity_id text; v_participant_id uuid; v_revision integer; v_submission_key text;
begin
 select * into v_session from public.team_access_sessions_v2 where session_token=p_session_token and device_id=trim(p_device_id) and is_active=true limit 1 for update;
 if not found then raise exception 'Invalid captain session'; end if;
 select a.activity_id into v_activity_id from public.activities_v2 a join public.modules_v2 m on m.module_id=a.module_id join public.programmes_v2 p on p.programme_id=m.programme_id
  where a.activity_id=trim(p_activity_id) and p.event_id=v_session.event_id limit 1;
 if v_activity_id is null then raise exception 'Checkpoint does not belong to this event'; end if;
 perform pg_advisory_xact_lock(hashtextextended(v_session.event_id||'|RACE_SUBMISSION|'||v_session.team_id||'|'||v_activity_id,29));
 select * into v_submission from public.submissions_v2 where event_id=v_session.event_id and team_id=v_session.team_id and activity_id=v_activity_id
  order by submitted_at desc,created_at desc limit 1 for update;
 if found and v_submission.submission_status<>'REJECTED' then
  return jsonb_build_object('SubmissionID',v_submission.submission_id::text,'EventID',v_session.event_id,'TeamID',v_session.team_id,'Status',v_submission.submission_status,'Duplicate',true);
 end if;
 select count(*)+1 into v_revision from public.submissions_v2 where event_id=v_session.event_id and team_id=v_session.team_id and activity_id=v_activity_id;
 v_submission_key:='race-captain|'||v_session.event_id||'|'||v_session.team_id||'|'||v_activity_id||'|revision:'||v_revision;
 v_participant_id:=(public.exos_v2_formula_race_captain_actor(v_session.event_id,v_session.team_id)->>'ParticipantID')::uuid;
 insert into public.submissions_v2(event_id,team_id,participant_id,activity_id,submission_key,submission_status,submission_payload)
  values(v_session.event_id,v_session.team_id,v_participant_id,v_activity_id,v_submission_key,'SUBMITTED',
   jsonb_build_object('text_response',coalesce(p_text_response,''),'storage_reference',coalesce(p_storage_reference,''),'captain_request_key',nullif(trim(p_idempotency_key),''))) returning * into v_submission;
 insert into public.submission_evidence_v2(submission_id,evidence_type,evidence_uri,evidence_payload,captured_by)
  values(v_submission.submission_id,case when nullif(trim(p_storage_reference),'') is null then 'TEXT' else 'PHOTO' end,nullif(trim(p_storage_reference),''),
   jsonb_build_object('text',coalesce(p_text_response,''),'uri',coalesce(p_storage_reference,'')),'RACE_CAPTAIN');
 return jsonb_build_object('SubmissionID',v_submission.submission_id::text,'EventID',v_session.event_id,'TeamID',v_session.team_id,'Status',v_submission.submission_status,'Revision',v_revision,'Duplicate',false);
end $$;

create or replace function public.exos_v2_formula_race_review_checkpoint(
 p_submission_id uuid,p_decision text,p_reviewer text,p_notes text default '',p_reason text default '',p_idempotency_key text default '')
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_submission public.submissions_v2%rowtype; v_activity public.activities_v2%rowtype; v_decision text;
 v_score_award numeric:=0; v_credit_award integer:=0; v_review_id uuid;
begin
 if nullif(trim(p_reviewer),'') is null then raise exception 'Facilitator identity is required'; end if;
 v_decision:=case upper(trim(p_decision)) when 'APPROVE' then 'APPROVE' when 'APPROVED' then 'APPROVE' when 'REJECT' then 'REJECT' when 'REQUEST_RESUBMISSION' then 'REJECT' else null end;
 if v_decision is null then raise exception 'Unsupported R.A.C.E. review decision'; end if;
 select * into v_submission from public.submissions_v2 where submission_id=p_submission_id for update;
 if not found then raise exception 'Submission not found'; end if;
 select * into v_activity from public.activities_v2 where activity_id=v_submission.activity_id limit 1;
 if not found then raise exception 'Checkpoint activity not found'; end if;
 if v_submission.submission_status='APPROVED' and v_decision<>'APPROVE' then raise exception 'Approved checkpoint requires a new revision instead of mutation'; end if;
 insert into public.reviews_v2(event_id,submission_id,reviewer,decision,score_points,rationale,reviewed_at)
  values(v_submission.event_id,p_submission_id,trim(p_reviewer),v_decision::public.exos_v2_review_decision,0,coalesce(nullif(trim(p_reason),''),nullif(trim(p_notes),''),''),now())
  on conflict(submission_id,reviewer) do update set decision=excluded.decision,rationale=excluded.rationale,reviewed_at=excluded.reviewed_at returning review_id into v_review_id;
 if v_decision='APPROVE' then
  v_score_award:=coalesce(nullif(v_activity.activity_payload->>'score_award','')::numeric,nullif(v_activity.activity_payload->>'max_score','')::numeric,0);
  v_credit_award:=coalesce(nullif(v_activity.activity_payload->>'credit_award','')::integer,nullif(v_activity.activity_payload->>'credits','')::integer,0);
  if v_activity.scoring_mode='TEAM_COMPETITIVE' and v_score_award<>0 then
   insert into public.score_transactions_v2(event_id,team_id,submission_id,scoring_mode,score_delta,reason,idempotency_key,source_reference,created_by)
    values(v_submission.event_id,v_submission.team_id,p_submission_id,'TEAM_COMPETITIVE',v_score_award,'R.A.C.E. checkpoint approved','race-checkpoint-score|'||p_submission_id::text,
     jsonb_build_object('award_source','activity_payload','request_key',nullif(trim(p_idempotency_key),'')),trim(p_reviewer))
    on conflict(event_id,idempotency_key) do update set score_delta=excluded.score_delta,reason=excluded.reason;
  end if;
  if v_credit_award<>0 then
   insert into public.credit_transactions_v2(event_id,team_id,participant_id,transaction_type,amount,idempotency_key,reason,created_by)
    values(v_submission.event_id,v_submission.team_id,v_submission.participant_id,'RACE_CHECKPOINT_AWARD',v_credit_award,'race-checkpoint-credit|'||p_submission_id::text,'R.A.C.E. checkpoint approved',trim(p_reviewer))
    on conflict(event_id,idempotency_key) do update set amount=excluded.amount,reason=excluded.reason;
  end if;
  update public.submissions_v2 set submission_status='APPROVED',score=v_score_award,reviewed_at=now(),reviewed_by=trim(p_reviewer),updated_at=now() where submission_id=p_submission_id;
 else
  update public.submissions_v2 set submission_status='REJECTED',reviewed_at=now(),reviewed_by=trim(p_reviewer),updated_at=now() where submission_id=p_submission_id;
 end if;
 return jsonb_build_object('ReviewID',v_review_id::text,'SubmissionID',p_submission_id::text,'Decision',v_decision,'ChampionshipScoreAward',v_score_award,'CreditAward',v_credit_award);
end $$;

create or replace function public.exos_v2_formula_race_purchase(p_session_token uuid,p_device_id text,p_item_id text,p_quantity integer,p_idempotency_key text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_session public.team_access_sessions_v2%rowtype; v_item public.marketplace_items_v2%rowtype; v_purchase public.marketplace_transactions_v2%rowtype;
 v_credit_id uuid; v_cost integer; v_balance integer; v_reserved integer;
begin
 if p_quantity is null or p_quantity<1 then raise exception 'Quantity must be at least 1'; end if;
 if nullif(trim(p_idempotency_key),'') is null then raise exception 'Stable purchase idempotency key is required'; end if;
 select * into v_session from public.team_access_sessions_v2 where session_token=p_session_token and device_id=trim(p_device_id) and is_active=true limit 1 for update;
 if not found then raise exception 'Invalid captain session'; end if;
 perform pg_advisory_xact_lock(hashtextextended(v_session.event_id||'|RACE_WALLET|'||v_session.team_id,31));
 select * into v_purchase from public.marketplace_transactions_v2 where event_id=v_session.event_id and idempotency_key=trim(p_idempotency_key) limit 1 for update;
 if found then
  select coalesce(sum(amount),0)::integer into v_balance from public.credit_transactions_v2 where event_id=v_session.event_id and team_id=v_session.team_id;
  return jsonb_build_object('PurchaseResult','SUCCESS','Duplicate',true,'PurchaseID',v_purchase.marketplace_transaction_id::text,'Balance',v_balance);
 end if;
 select * into v_item from public.marketplace_items_v2 where event_id=v_session.event_id and item_id=trim(p_item_id) limit 1 for update;
 if not found or not v_item.is_active then raise exception 'Marketplace item is not active for this event'; end if;
 select coalesce(sum(quantity),0)::integer into v_reserved from public.marketplace_transactions_v2 where event_id=v_session.event_id and item_id=v_item.item_id and status='COMPLETED';
 if v_item.stock_limit is not null and v_reserved+p_quantity>v_item.stock_limit then raise exception 'Insufficient stock'; end if;
 v_cost:=v_item.unit_cost_credits*p_quantity;
 select coalesce(sum(amount),0)::integer into v_balance from public.credit_transactions_v2 where event_id=v_session.event_id and team_id=v_session.team_id;
 if v_balance<v_cost then raise exception 'Insufficient credits'; end if;
 insert into public.credit_transactions_v2(event_id,team_id,participant_id,transaction_type,amount,idempotency_key,reason,created_by)
  values(v_session.event_id,v_session.team_id,null,'PURCHASE',-v_cost,'race-purchase-credit|'||trim(p_idempotency_key),v_item.item_name||' purchase','RACE_CAPTAIN') returning credit_transaction_id into v_credit_id;
 insert into public.marketplace_transactions_v2(event_id,team_id,item_id,credit_transaction_id,quantity,amount_paid,status,idempotency_key)
  values(v_session.event_id,v_session.team_id,v_item.item_id,v_credit_id,p_quantity,v_cost,'COMPLETED',trim(p_idempotency_key)) returning * into v_purchase;
 return jsonb_build_object('PurchaseResult','SUCCESS','Duplicate',false,'PurchaseID',v_purchase.marketplace_transaction_id::text,'Balance',v_balance-v_cost);
end $$;

create or replace function public.exos_v2_formula_race_lock_final_results(p_event_id text,p_actor text,p_reason text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_team_count integer; v_result_count integer; v_already_locked integer;
begin
 if nullif(trim(p_actor),'') is null or nullif(trim(p_reason),'') is null then raise exception 'Facilitator identity and lock reason are required'; end if;
 perform pg_advisory_xact_lock(hashtextextended(trim(p_event_id)||'|RACE_FINAL_RESULTS',37));
 select count(*) into v_team_count from public.teams_v2 where event_id=trim(p_event_id) and is_active=true;
 select count(*) into v_result_count from public.race_results_v2 r join public.teams_v2 t on t.team_id=r.team_id and t.event_id=r.event_id
  where r.event_id=trim(p_event_id) and r.checkpoint='Race Final' and coalesce((r.result_payload->>'verified')::boolean,false)=true and t.is_active=true;
 if v_team_count=0 or v_result_count<>v_team_count then raise exception 'Every active team requires one verified Race Final result before locking'; end if;
 select count(*) into v_already_locked from public.race_results_v2 where event_id=trim(p_event_id) and checkpoint='Race Final' and locked=true;
 if v_already_locked=v_team_count then return jsonb_build_object('Locked',true,'EventID',trim(p_event_id),'AlreadyLocked',true); end if;
 if v_already_locked>0 then raise exception 'Race Final has a partial lock state and requires controlled reconciliation'; end if;
 with ranked as (
  select r.race_result_id,row_number() over(order by coalesce((r.result_payload->>'time_ms')::bigint,(r.result_payload->>'finish_time_ms')::bigint,0)+coalesce((r.result_payload->>'penalty_ms')::bigint,0),r.team_id asc) as final_rank
  from public.race_results_v2 r where r.event_id=trim(p_event_id) and r.checkpoint='Race Final' and coalesce((r.result_payload->>'verified')::boolean,false)=true
 ) update public.race_results_v2 r set ranking_position=ranked.final_rank,locked=true,updated_at=now(),result_payload=r.result_payload||jsonb_build_object('locked_by',trim(p_actor),'lock_reason',trim(p_reason)) from ranked where r.race_result_id=ranked.race_result_id;
 return jsonb_build_object('Locked',true,'EventID',trim(p_event_id),'AlreadyLocked',false,'RankingMetric','time_ms + penalty_ms, TeamID ASC');
end $$;

revoke all on function public.exos_v2_formula_race_captain_actor(text,text) from public;
revoke all on function public.exos_v2_formula_race_submit_checkpoint(uuid,text,text,text,text,text) from public;
revoke all on function public.exos_v2_formula_race_review_checkpoint(uuid,text,text,text,text,text) from public;
revoke all on function public.exos_v2_formula_race_purchase(uuid,text,text,integer,text) from public;
revoke all on function public.exos_v2_formula_race_lock_final_results(text,text,text) from public;
grant execute on function public.exos_v2_formula_race_captain_actor(text,text) to service_role;
grant execute on function public.exos_v2_formula_race_submit_checkpoint(uuid,text,text,text,text,text) to anon,authenticated,service_role;
grant execute on function public.exos_v2_formula_race_review_checkpoint(uuid,text,text,text,text,text) to service_role;
grant execute on function public.exos_v2_formula_race_purchase(uuid,text,text,integer,text) to anon,authenticated,service_role;
grant execute on function public.exos_v2_formula_race_lock_final_results(text,text,text) to service_role;
COMMIT;
