-- EXOS Core v2 standard programme runtime functions.
-- Adds no tables: live state remains in events_v2.event_payload and execution,
-- submissions, reviews and scores use the canonical v2 entities introduced by 020.
begin;

create or replace function public.exos_v2_standard_launch_activity(
    p_event_id text,
    p_activity_id text,
    p_actor text default 'Facilitator'
)
returns jsonb
language plpgsql security definer
set search_path = public as $$
declare
    v_activity public.activities_v2%rowtype;
    v_module public.modules_v2%rowtype;
    v_state jsonb;
begin
    select a.* into v_activity
      from public.activities_v2 a
      join public.programmes_v2 p on p.programme_id=a.programme_id
     where p.event_id=trim(p_event_id)
       and a.activity_id=trim(p_activity_id)
       and a.is_active and p.is_active
     limit 1;
    if not found then raise exception 'Active activity does not belong to event'; end if;

    select * into v_module from public.modules_v2 where module_id=v_activity.module_id;
    v_state := jsonb_build_object(
        'EventID', trim(p_event_id),
        'ProgrammeID', v_activity.programme_id,
        'ModuleID', v_activity.module_id,
        'ModuleName', v_module.module_name,
        'ActivityID', v_activity.activity_id,
        'StageNo', coalesce((v_activity.activity_payload->>'stage_no')::integer, v_activity.activity_order),
        'StageName', v_activity.activity_name,
        'StageType', v_activity.activity_type::text,
        'ScoringMode', v_activity.scoring_mode::text,
        'DisplayMode', coalesce(v_activity.activity_payload->>'display_mode', 'Collaboration'),
        'ParticipantMessage', coalesce(v_activity.activity_payload->>'participant_message', ''),
        'DurationMinutes', floor(v_activity.duration_seconds / 60),
        'Status', 'RUNNING',
        'LaunchedAt', now(),
        'LaunchedBy', coalesce(nullif(trim(p_actor),''), 'Facilitator'),
        'ActivityPayload', v_activity.activity_payload
    );

    update public.events_v2
       set event_payload=jsonb_set(coalesce(event_payload,'{}'::jsonb), '{live_state}', v_state, true),
           lifecycle_status='LIVE', updated_at=now()
     where event_id=trim(p_event_id);
    if not found then raise exception 'Event not found'; end if;

    insert into public.audit_log_v2(event_id,actor,action,entity_type,entity_id,after_state)
    values(trim(p_event_id),coalesce(nullif(trim(p_actor),''),'Facilitator'),'ACTIVITY_LAUNCHED',
           'activities_v2',v_activity.activity_id,v_state);
    return v_state;
end;
$$;

create or replace function public.exos_v2_standard_participant_state(p_session_token text)
returns jsonb
language plpgsql stable security definer
set search_path = public as $$
declare
    v_session public.participant_sessions_v2%rowtype;
    v_participant public.participants_v2%rowtype;
    v_event public.events_v2%rowtype;
begin
    select * into v_session from public.participant_sessions_v2
     where session_token::text=trim(p_session_token) and is_active limit 1;
    if not found then return null; end if;
    select * into v_participant from public.participants_v2
     where participant_id=v_session.participant_id and not is_archived limit 1;
    if not found then return null; end if;
    select * into v_event from public.events_v2 where event_id=v_session.event_id;
    return public.exos_v2_identity_payload(v_event.event_id,v_participant.participant_id)
      || jsonb_build_object(
          'EventPayload',v_event.event_payload,
          'Stage',coalesce(v_event.event_payload->'live_state','{}'::jsonb),
          'StateVersion',extract(epoch from v_event.updated_at)::bigint,
          'StageName',coalesce(v_event.event_payload#>>'{live_state,StageName}',''),
          'MissionID',coalesce(v_event.event_payload#>>'{live_state,ActivityID}','')
      );
end;
$$;

create or replace function public.exos_v2_standard_submit(
    p_session_token text,
    p_activity_id text,
    p_submission_key text,
    p_submission_payload jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql security definer
set search_path = public as $$
declare
    v_session public.participant_sessions_v2%rowtype;
    v_participant public.participants_v2%rowtype;
    v_activity public.activities_v2%rowtype;
    v_runtime public.activity_runtime_v2%rowtype;
    v_submission public.submissions_v2%rowtype;
    v_scope text;
    v_key text;
begin
    select * into v_session from public.participant_sessions_v2
     where session_token::text=trim(p_session_token) and is_active for update;
    if not found then raise exception 'Participant session is invalid'; end if;
    select * into v_participant from public.participants_v2
     where participant_id=v_session.participant_id and not is_archived;
    select a.* into v_activity from public.activities_v2 a
      join public.programmes_v2 p on p.programme_id=a.programme_id
     where a.activity_id=trim(p_activity_id) and p.event_id=v_session.event_id and a.is_active;
    if not found then raise exception 'Activity is not available for this event'; end if;
    if not exists(
        select 1 from public.events_v2 e
         where e.event_id=v_session.event_id
           and e.event_payload#>>'{live_state,ActivityID}'=v_activity.activity_id
           and e.event_payload#>>'{live_state,Status}'='RUNNING'
    ) then
        raise exception 'Activity is not currently launched';
    end if;

    v_scope := upper(coalesce(v_activity.activity_payload->>'participant_scope','TEAM'));
    v_key := v_session.event_id || '|' || v_activity.activity_id || '|' ||
        case when v_scope='INDIVIDUAL' then v_participant.participant_id::text else v_participant.team_id end;

    insert into public.activity_runtime_v2(
        event_id,team_id,participant_id,activity_id,session_id,state_payload,
        activity_started_at,activity_ended_at,completion_ratio,is_completed
    ) values(
        v_session.event_id,v_participant.team_id,v_participant.participant_id,v_activity.activity_id,
        v_session.participant_session_id,jsonb_build_object('SubmissionKey',v_key),now(),now(),100,true
    ) on conflict(event_id,participant_id,activity_id) do update
      set session_id=excluded.session_id,state_payload=excluded.state_payload,
          activity_ended_at=now(),completion_ratio=100,is_completed=true,updated_at=now()
    returning * into v_runtime;

    insert into public.submissions_v2(
        event_id,team_id,participant_id,activity_id,runtime_id,submission_key,
        submission_status,submission_payload,submitted_at,updated_at
    ) values(
        v_session.event_id,v_participant.team_id,v_participant.participant_id,v_activity.activity_id,
        v_runtime.runtime_id,v_key,'SUBMITTED',coalesce(p_submission_payload,'{}'::jsonb),now(),now()
    ) on conflict(event_id,submission_key) do update
      set participant_id=excluded.participant_id,runtime_id=excluded.runtime_id,
          submission_status='SUBMITTED',submission_payload=excluded.submission_payload,
          submitted_at=now(),reviewed_at=null,reviewed_by=null,score=null,updated_at=now()
    returning * into v_submission;

    return jsonb_build_object(
        'SubmissionID',v_submission.submission_id::text,
        'EventID',v_submission.event_id,
        'TeamID',v_submission.team_id,
        'ParticipantID',v_submission.participant_id::text,
        'ActivityID',v_submission.activity_id,
        'Status',v_submission.submission_status::text,
        'SubmissionKey',v_submission.submission_key,
        'SubmittedAt',v_submission.submitted_at
    );
end;
$$;

create or replace function public.exos_v2_standard_review_submission(
    p_submission_id uuid,
    p_decision public.exos_v2_review_decision,
    p_score numeric,
    p_reviewer text,
    p_rationale text default '',
    p_idempotency_key text default ''
)
returns jsonb
language plpgsql security definer
set search_path = public as $$
declare
    v_submission public.submissions_v2%rowtype;
    v_activity public.activities_v2%rowtype;
    v_status public.exos_v2_submission_status;
    v_key text;
begin
    select * into v_submission from public.submissions_v2
     where submission_id=p_submission_id for update;
    if not found then raise exception 'Submission not found'; end if;
    select * into v_activity from public.activities_v2 where activity_id=v_submission.activity_id;
    v_status := case when p_decision='APPROVE' then 'APPROVED'::public.exos_v2_submission_status
                     when p_decision='REJECT' then 'REJECTED'::public.exos_v2_submission_status
                     else 'SUBMITTED'::public.exos_v2_submission_status end;

    insert into public.reviews_v2(event_id,submission_id,reviewer,decision,score_points,rationale,reviewed_at)
    values(v_submission.event_id,p_submission_id,coalesce(nullif(trim(p_reviewer),''),'Facilitator'),
           p_decision,coalesce(p_score,0),coalesce(p_rationale,''),now())
    on conflict(submission_id,reviewer) do update
      set decision=excluded.decision,score_points=excluded.score_points,
          rationale=excluded.rationale,reviewed_at=now();

    update public.submissions_v2 set submission_status=v_status,score=coalesce(p_score,0),
        reviewed_at=now(),reviewed_by=coalesce(nullif(trim(p_reviewer),''),'Facilitator'),updated_at=now()
     where submission_id=p_submission_id returning * into v_submission;

    if v_activity.scoring_mode='TEAM_COMPETITIVE' then
        v_key := coalesce(nullif(trim(p_idempotency_key),''),'review|'||p_submission_id::text);
        insert into public.score_transactions_v2(
            event_id,team_id,submission_id,scoring_mode,score_delta,reason,
            idempotency_key,source_reference,created_by
        ) values(
            v_submission.event_id,v_submission.team_id,p_submission_id,v_activity.scoring_mode,
            case when p_decision='APPROVE' then coalesce(p_score,0) else 0 end,
            case when p_decision='APPROVE' then 'Approved standard activity submission' else 'Standard activity score withdrawn' end,v_key,
            jsonb_build_object('ActivityID',v_submission.activity_id),p_reviewer
        ) on conflict(event_id,idempotency_key) do update
          set score_delta=excluded.score_delta,reason=excluded.reason,
              source_reference=excluded.source_reference,created_by=excluded.created_by;
    end if;

    return jsonb_build_object('SubmissionID',p_submission_id::text,'Status',v_status::text,
                              'Score',coalesce(p_score,0),'Decision',p_decision::text);
end;
$$;

revoke all on function public.exos_v2_standard_launch_activity(text,text,text) from public;
revoke all on function public.exos_v2_standard_review_submission(uuid,public.exos_v2_review_decision,numeric,text,text,text) from public;
grant execute on function public.exos_v2_standard_launch_activity(text,text,text) to service_role;
grant execute on function public.exos_v2_standard_review_submission(uuid,public.exos_v2_review_decision,numeric,text,text,text) to service_role;
grant execute on function public.exos_v2_standard_participant_state(text) to anon,authenticated,service_role;
grant execute on function public.exos_v2_standard_submit(text,text,text,jsonb) to anon,authenticated,service_role;

commit;
