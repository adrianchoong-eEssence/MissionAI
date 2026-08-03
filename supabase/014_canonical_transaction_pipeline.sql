begin;

create table if not exists public.canonical_submissions (
  submission_id text primary key,
  event_id text not null references public.runtime_events(event_id) on delete restrict,
  team_id text not null, participant_id uuid not null references public.runtime_participants(participant_id),
  programme_id text not null, module_id text not null, activity_id text not null,
  experience_definition_id text not null, experience_assignment_id text not null,
  definition_version integer not null, assignment_version integer not null,
  submission_type text not null, evidence_type text not null default 'NONE',
  text_response text not null default '', media_asset_id text, storage_reference text,
  qr_result jsonb, gps_result jsonb, submitted_at timestamptz not null default now(),
  status text not null default 'PENDING_REVIEW' check (status in
    ('DRAFT','SUBMITTED','PENDING_REVIEW','APPROVED','REJECTED','RETURNED_FOR_REVISION','CANCELLED')),
  idempotency_key text not null, created_by text not null, last_updated_at timestamptz not null default now(),
  allows_multiple boolean not null default false, audit_metadata jsonb not null default '{}'::jsonb,
  unique (event_id, idempotency_key)
);
create unique index if not exists canonical_submission_one_team_assignment_idx
  on public.canonical_submissions(event_id, team_id, experience_assignment_id)
  where not allows_multiple and status <> 'CANCELLED';

create table if not exists public.review_decisions (
  review_decision_id text primary key, submission_id text not null references public.canonical_submissions(submission_id),
  event_id text not null, team_id text not null, reviewer_id text not null,
  decision text not null check (decision in ('APPROVE','REJECT','RETURN_FOR_REVISION','VOID','CORRECT_PREVIOUS_DECISION')),
  score numeric not null default 0, credits numeric not null default 0,
  reviewer_notes text not null default '', rejection_reason text not null default '',
  decided_at timestamptz not null default now(), idempotency_key text not null,
  supersedes_decision_id text references public.review_decisions(review_decision_id),
  audit_metadata jsonb not null default '{}'::jsonb,
  unique(event_id, idempotency_key)
);

create table if not exists public.award_transactions (
  award_transaction_id text primary key, event_id text not null, team_id text not null,
  submission_id text references public.canonical_submissions(submission_id),
  review_decision_id text references public.review_decisions(review_decision_id),
  activity_id text, award_type text not null check (award_type in
    ('INTELLIGENCE_CREDITS','SCORE','BONUS','PENALTY','MANUAL_ADJUSTMENT','MARKETPLACE_SPEND','REFUND','CORRECTION')),
  amount numeric not null, source text not null, reason text not null, idempotency_key text not null,
  created_by text not null, created_at timestamptz not null default now(),
  reversal_of_transaction_id text references public.award_transactions(award_transaction_id),
  audit_metadata jsonb not null default '{}'::jsonb,
  unique(event_id, idempotency_key)
);

create table if not exists public.judging_configurations (
  judging_configuration_id text primary key, event_id text not null, activity_id text not null,
  version integer not null, criteria jsonb not null default '[]'::jsonb,
  required_judge_count integer not null default 1, aggregation_method text not null default 'AVERAGE',
  exclude_highest_lowest boolean not null default false, tie_break_method text not null default 'STABLE_TEAM_ID',
  finalisation_rule text not null default 'MANUAL', created_at timestamptz not null default now(),
  unique(event_id, activity_id, version)
);
create table if not exists public.judge_scores (
  judge_score_id text primary key, event_id text not null, team_id text not null,
  activity_id text not null, experience_assignment_id text, judge_id text not null,
  criterion_id text not null, raw_score numeric not null, weight numeric not null default 1,
  submitted_at timestamptz not null default now(), locked_at timestamptz,
  idempotency_key text not null, audit_metadata jsonb not null default '{}'::jsonb,
  unique(event_id, idempotency_key)
);
create table if not exists public.scoring_locks (
  scoring_lock_id text primary key, event_id text not null, scope_type text not null,
  scope_id text not null, locked boolean not null default true, locked_by text not null,
  locked_at timestamptz not null default now(), reason text not null,
  audit_metadata jsonb not null default '{}'::jsonb,
  unique(event_id, scope_type, scope_id)
);

create or replace view public.team_balance_projection as
select event_id, team_id,
  coalesce(sum(amount) filter (where award_type in ('INTELLIGENCE_CREDITS','MANUAL_ADJUSTMENT','CORRECTION','REFUND')),0) intelligence_credits,
  coalesce(sum(amount) filter (where award_type='SCORE'),0) score,
  coalesce(sum(amount) filter (where award_type='BONUS'),0) bonuses,
  coalesce(sum(amount) filter (where award_type='PENALTY'),0) penalties,
  coalesce(sum(amount) filter (where award_type='MARKETPLACE_SPEND'),0) marketplace_spend,
  coalesce(sum(amount) filter (where award_type in ('INTELLIGENCE_CREDITS','MANUAL_ADJUSTMENT','CORRECTION','REFUND','BONUS','PENALTY','MARKETPLACE_SPEND')),0) available_balance
from public.award_transactions group by event_id, team_id;

create or replace view public.leaderboard_projection as
select *, rank() over (partition by event_id order by score desc, team_id asc) as rank
from public.team_balance_projection;

create or replace function public.exos_create_canonical_submission(
  p_session_token text, p_experience_assignment_id text, p_submission_id text,
  p_idempotency_key text, p_submission_type text, p_evidence_type text default 'NONE',
  p_text_response text default '', p_media_asset_id text default null,
  p_storage_reference text default null, p_qr_result jsonb default null, p_gps_result jsonb default null
) returns jsonb language plpgsql security definer set search_path=public as $$
declare
  v_participant public.runtime_participants%rowtype;
  v_assignment public.event_experience_assignments%rowtype;
  v_submission public.canonical_submissions%rowtype;
  v_allowed boolean := false;
begin
  select * into v_participant from public.runtime_participants
   where session_token::text=trim(p_session_token) and merged_into_participant_id is null for share;
  if not found then raise exception 'Participant session is invalid'; end if;
  select * into v_assignment from public.event_experience_assignments
   where experience_assignment_id=trim(p_experience_assignment_id)
     and event_id=v_participant.event_id and active and runtime_eligible for share;
  if not found then raise exception 'Active Experience Assignment is unavailable'; end if;
  if not exists(select 1 from public.runtime_events
    where event_id=v_participant.event_id
      and stage_payload->>'ExperienceAssignmentID'=v_assignment.experience_assignment_id) then
    raise exception 'Experience Assignment is not current';
  end if;
  v_allowed := position('|LEADER' in v_participant.status)>0
    or v_assignment.submission_rule in ('ANY_MEMBER','MULTIPLE')
    or exists(select 1 from public.runtime_submission_overrides
      where event_id=v_participant.event_id and allow_any_member
        and team_id in ('*',coalesce(v_participant.team_id,'')));
  if not v_allowed then raise exception 'Participant is not authorised to submit'; end if;
  if upper(coalesce(p_evidence_type,'NONE'))<>'NONE'
     and nullif(p_media_asset_id,'') is null and nullif(p_storage_reference,'') is null
     and p_qr_result is null and p_gps_result is null then
    raise exception 'Evidence metadata must exist before submission';
  end if;
  select * into v_submission from public.canonical_submissions
   where event_id=v_participant.event_id and (
     idempotency_key=trim(p_idempotency_key) or
     (team_id=v_participant.team_id and experience_assignment_id=v_assignment.experience_assignment_id
      and not allows_multiple and status<>'CANCELLED'))
   order by submitted_at limit 1;
  if found then
    if v_submission.status='RETURNED_FOR_REVISION' then
      update public.canonical_submissions set text_response=coalesce(p_text_response,''),
        media_asset_id=nullif(p_media_asset_id,''),storage_reference=nullif(p_storage_reference,''),
        qr_result=p_qr_result,gps_result=p_gps_result,status='PENDING_REVIEW',last_updated_at=now(),
        audit_metadata=audit_metadata||jsonb_build_object('RevisionResubmittedAt',now())
      where submission_id=v_submission.submission_id returning * into v_submission;
    end if;
    return to_jsonb(v_submission);
  end if;
  insert into public.canonical_submissions(
    submission_id,event_id,team_id,participant_id,programme_id,module_id,activity_id,
    experience_definition_id,experience_assignment_id,definition_version,assignment_version,
    submission_type,evidence_type,text_response,media_asset_id,storage_reference,qr_result,gps_result,
    status,idempotency_key,created_by,allows_multiple,audit_metadata
  ) values (
    trim(p_submission_id),v_participant.event_id,v_participant.team_id,v_participant.participant_id,
    v_assignment.programme_id,v_assignment.module_id,v_assignment.activity_id,
    v_assignment.experience_definition_id,v_assignment.experience_assignment_id,
    v_assignment.definition_version,v_assignment.assignment_version,upper(p_submission_type),
    upper(coalesce(p_evidence_type,'NONE')),coalesce(p_text_response,''),nullif(p_media_asset_id,''),
    nullif(p_storage_reference,''),p_qr_result,p_gps_result,'PENDING_REVIEW',trim(p_idempotency_key),
    v_participant.participant_id::text,v_assignment.allows_multiple_submissions,
    jsonb_build_object('LeaderAtSubmit',position('|LEADER' in v_participant.status)>0)
  ) returning * into v_submission;
  return to_jsonb(v_submission);
exception when unique_violation then
  select * into v_submission from public.canonical_submissions
   where event_id=v_participant.event_id and (idempotency_key=trim(p_idempotency_key)
     or (team_id=v_participant.team_id and experience_assignment_id=v_assignment.experience_assignment_id))
   order by submitted_at limit 1;
  return to_jsonb(v_submission);
end $$;

create or replace function public.exos_decide_canonical_submission(
  p_submission_id text,p_decision text,p_reviewer_id text,p_score numeric default 0,
  p_credits numeric default 0,p_notes text default '',p_rejection_reason text default '',
  p_idempotency_key text default '',p_supersedes_decision_id text default ''
) returns jsonb language plpgsql security definer set search_path=public as $$
declare v_submission public.canonical_submissions%rowtype; v_decision public.review_decisions%rowtype;
begin
  select * into v_submission from public.canonical_submissions
   where submission_id=trim(p_submission_id) for update;
  if not found then raise exception 'Submission not found'; end if;
  if exists(select 1 from public.scoring_locks where event_id=v_submission.event_id and locked
    and scope_type in ('EVENT','MODULE','ACTIVITY')
    and scope_id in (v_submission.event_id,v_submission.module_id,v_submission.activity_id))
    and nullif(trim(p_supersedes_decision_id),'') is null then
    raise exception 'Scoring is final-locked; correction required';
  end if;
  insert into public.review_decisions(
    review_decision_id,submission_id,event_id,team_id,reviewer_id,decision,score,credits,
    reviewer_notes,rejection_reason,idempotency_key,supersedes_decision_id,audit_metadata
  ) values (
    gen_random_uuid()::text,v_submission.submission_id,v_submission.event_id,v_submission.team_id,
    trim(p_reviewer_id),upper(trim(p_decision)),coalesce(p_score,0),coalesce(p_credits,0),
    coalesce(p_notes,''),coalesce(p_rejection_reason,''),trim(p_idempotency_key),
    nullif(trim(p_supersedes_decision_id),''),jsonb_build_object('Actor',trim(p_reviewer_id))
  ) on conflict(event_id,idempotency_key) do update set idempotency_key=excluded.idempotency_key
  returning * into v_decision;
  if v_decision.decision in ('APPROVE','CORRECT_PREVIOUS_DECISION') then
    if v_decision.score<>0 then insert into public.award_transactions(
      award_transaction_id,event_id,team_id,submission_id,review_decision_id,activity_id,
      award_type,amount,source,reason,idempotency_key,created_by)
      values(gen_random_uuid()::text,v_decision.event_id,v_decision.team_id,v_submission.submission_id,
      v_decision.review_decision_id,v_submission.activity_id,'SCORE',v_decision.score,'REVIEW',v_decision.decision,
      trim(p_idempotency_key)||':SCORE',trim(p_reviewer_id)) on conflict(event_id,idempotency_key) do nothing; end if;
    if v_decision.credits<>0 then insert into public.award_transactions(
      award_transaction_id,event_id,team_id,submission_id,review_decision_id,activity_id,
      award_type,amount,source,reason,idempotency_key,created_by)
      values(gen_random_uuid()::text,v_decision.event_id,v_decision.team_id,v_submission.submission_id,
      v_decision.review_decision_id,v_submission.activity_id,'INTELLIGENCE_CREDITS',v_decision.credits,
      'REVIEW',v_decision.decision,trim(p_idempotency_key)||':CREDITS',trim(p_reviewer_id))
      on conflict(event_id,idempotency_key) do nothing; end if;
  end if;
  update public.canonical_submissions set status=case v_decision.decision
    when 'APPROVE' then 'APPROVED' when 'REJECT' then 'REJECTED'
    when 'RETURN_FOR_REVISION' then 'RETURNED_FOR_REVISION' else status end,
    last_updated_at=now() where submission_id=v_submission.submission_id;
  return jsonb_build_object('ReviewDecision',to_jsonb(v_decision));
end $$;

alter table public.canonical_submissions enable row level security;
alter table public.review_decisions enable row level security;
alter table public.award_transactions enable row level security;
alter table public.judging_configurations enable row level security;
alter table public.judge_scores enable row level security;
alter table public.scoring_locks enable row level security;
revoke all on public.canonical_submissions, public.review_decisions, public.award_transactions,
  public.judging_configurations, public.judge_scores, public.scoring_locks from anon, authenticated;
revoke all on function public.exos_create_canonical_submission(text,text,text,text,text,text,text,text,text,jsonb,jsonb) from public;
revoke all on function public.exos_decide_canonical_submission(text,text,text,numeric,numeric,text,text,text,text) from public;
grant execute on function public.exos_create_canonical_submission(text,text,text,text,text,text,text,text,text,jsonb,jsonb) to anon, authenticated;
grant execute on function public.exos_decide_canonical_submission(text,text,text,numeric,numeric,text,text,text,text) to service_role;

commit;
