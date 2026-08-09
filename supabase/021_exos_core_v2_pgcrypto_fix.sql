BEGIN;

create extension if not exists pgcrypto with schema extensions;

DO $guard$
begin
    if not exists (
        select 1
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'extensions'
           and p.proname = 'digest'
    ) then
        raise exception 'pgcrypto digest() is not available in extensions schema.';
    end if;

    if not exists (
        select 1
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'extensions'
           and p.proname = 'gen_random_uuid'
    ) then
        raise exception 'pgcrypto gen_random_uuid() is not available in extensions schema.';
    end if;
end;
$guard$;

CREATE OR REPLACE FUNCTION public.exos_v2_join_event_v2(
    p_join_code text,
    p_participant_name text,
    p_device_id text,
    p_requested_team_id text default ''
) 
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $function$
declare
    v_event public.events_v2%rowtype;
    v_normalized text;
    v_idempotency_key text;
    v_team_id text;
    v_existing_id uuid;
    v_count integer;
    v_participant public.participants_v2%rowtype;
    v_session public.participant_sessions_v2%rowtype;
    v_event_lock bigint;
    v_identity_lock bigint;
    v_next_participant_id uuid := extensions.gen_random_uuid();
begin
    if nullif(trim(p_participant_name),'') is null then raise exception 'Participant full name is required'; end if;
    if nullif(trim(p_device_id),'') is null then raise exception 'Device identifier is required'; end if;

    select * into v_event from public.events_v2
     where join_code=upper(trim(p_join_code)) and published_at is not null
     for update;
    if not found then raise exception 'Invalid or unpublished join code'; end if;

    v_normalized := public.exos_v2_normalize_participant_name(p_participant_name);
    v_idempotency_key := encode(
        extensions.digest(
            v_event.event_id || '|' || v_normalized || '|' || lower(trim(p_device_id)),
            'sha256'
        ),
        'hex'
    );
    v_event_lock := hashtextextended(v_event.event_id, 11);
    v_identity_lock := hashtextextended(v_event.event_id || '|' || v_normalized, 17);
    perform pg_advisory_xact_lock(v_event_lock);
    perform pg_advisory_xact_lock(v_identity_lock);

    select participant_id into v_existing_id
      from public.participant_sessions_v2 s
      where s.event_id=v_event.event_id and s.idempotency_key=v_idempotency_key and s.is_active
      order by s.created_at desc limit 1;

    if v_existing_id is not null then
        select * into v_participant from public.participants_v2 where participant_id=v_existing_id;
        if v_participant.participant_id is null or v_participant.merged_into_participant_id is not null then
            return jsonb_build_object(
                'RecoveryRequired', true,
                'Ambiguous', false,
                'EventID', v_event.event_id,
                'Name', trim(p_participant_name),
                'Message', 'Identity is merged. Recovery required with facilitator.'
            );
        end if;
        select * into v_session from public.participant_sessions_v2
          where participant_id=v_existing_id and event_id=v_event.event_id and idempotency_key=v_idempotency_key
          order by created_at desc limit 1;
        if v_session.participant_session_id is not null then
            update public.participant_sessions_v2
               set last_seen_at = now(), is_active = true
             where participant_session_id = v_session.participant_session_id;
            update public.participants_v2
               set last_seen_at = now()
             where participant_id = v_existing_id;
            return public.exos_v2_identity_payload(v_event.event_id, v_existing_id);
        end if;
    end if;

    select count(*) into v_count
      from public.participants_v2 p
     where p.event_id=v_event.event_id and p.normalized_name=v_normalized and p.merged_into_participant_id is null;

    if v_count >= 1 then
        return jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', v_count > 1,
            'EventID', v_event.event_id,
            'Name', trim(p_participant_name),
            'Message', 'Same name exists for different device/session. Reconnect with original device or recover with facilitator.'
        );
    end if;

    if nullif(trim(p_requested_team_id),'') is not null then
        select team_id into v_team_id from public.teams_v2
          where event_id=v_event.event_id and team_id=trim(p_requested_team_id);
        if v_team_id is null then raise exception 'Requested team is not valid for this event'; end if;
    else
        v_team_id := public.exos_v2_next_team_id(v_event.event_id);
    end if;

    if v_team_id is null then raise exception 'No teams are published for this event'; end if;

    insert into public.participants_v2 (
        participant_id,event_id,team_id,normalized_name,display_name,country,flag,participant_payload
    )
    values (
        v_next_participant_id,v_event.event_id,v_team_id,v_normalized,trim(p_participant_name),
        (select country from public.teams_v2 where team_id=v_team_id),
        (select team_flag from public.teams_v2 where team_id=v_team_id),
        '{}'::jsonb
    )
    returning * into v_participant;

    insert into public.participant_sessions_v2 (
        event_id,participant_id,device_id,idempotency_key
    ) values (
        v_event.event_id,v_participant.participant_id,trim(p_device_id),v_idempotency_key
    ) on conflict (event_id, idempotency_key) do update
      set device_id = excluded.device_id,
          last_seen_at = now(),
          is_active = true
    returning * into v_session;

    if v_session.participant_id is distinct from v_participant.participant_id then
        delete from public.participants_v2 where participant_id = v_next_participant_id;
        select * into v_participant from public.participants_v2 where participant_id = v_session.participant_id;
        select * into v_session from public.participant_sessions_v2
          where participant_session_id = v_session.participant_session_id;
        update public.participant_sessions_v2
           set last_seen_at = now(), is_active = true
         where participant_session_id = v_session.participant_session_id;
        update public.participants_v2
           set last_seen_at = now()
         where participant_id = v_session.participant_id;
        return public.exos_v2_identity_payload(v_event.event_id, v_session.participant_id);
    end if;

    insert into public.audit_log_v2 (event_id,actor,action,entity_type,entity_id,before_state,after_state)
    values (v_event.event_id, 'system', 'PARTICIPANT_REGISTERED', 'participants_v2', v_participant.participant_id::text, '{}'::jsonb, to_jsonb(v_participant));

    return public.exos_v2_identity_payload(v_event.event_id, v_participant.participant_id);
end;
$function$;

CREATE OR REPLACE FUNCTION public.exos_v2_ledger_score(
    p_event_id text,
    p_team_id text,
    p_submission_id uuid,
    p_amount numeric,
    p_reason text,
    p_scoring_mode public.exos_v2_scoring_mode default 'TEAM_COMPETITIVE',
    p_idempotency_key text default ''
)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=public
AS $function$
declare
    v_tx_id uuid;
    v_key text;
begin
    if p_scoring_mode <> 'TEAM_COMPETITIVE' then
        raise exception 'Only TEAM_COMPETITIVE scores contribute to leaderboard';
    end if;
    v_key := nullif(trim(p_idempotency_key),'');
    if v_key is null then
        v_key := encode(
            extensions.digest(
                trim(p_event_id)||'|'||trim(p_team_id)||'|'||coalesce(p_submission_id::text,'')||'|'||coalesce(trim(p_reason), ''),
                'sha256'
            ),
            'hex'
        );
    end if;
    insert into public.score_transactions_v2 (
        event_id,team_id,submission_id,scoring_mode,score_delta,reason,idempotency_key
    ) values (
        trim(p_event_id),trim(p_team_id),p_submission_id,p_scoring_mode,p_amount,p_reason,v_key
    ) on conflict(event_id,idempotency_key) do update
      set score_delta = EXCLUDED.score_delta,
          reason = EXCLUDED.reason,
          created_at = now()
      returning score_transaction_id into v_tx_id;
    return v_tx_id;
end;
$function$;

ALTER TABLE public.participants_v2 ALTER COLUMN participant_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.participant_sessions_v2 ALTER COLUMN participant_session_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.participant_sessions_v2 ALTER COLUMN session_token SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.activity_runtime_v2 ALTER COLUMN runtime_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.submissions_v2 ALTER COLUMN submission_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.submission_evidence_v2 ALTER COLUMN evidence_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.reviews_v2 ALTER COLUMN review_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.score_transactions_v2 ALTER COLUMN score_transaction_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.credit_transactions_v2 ALTER COLUMN credit_transaction_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.marketplace_transactions_v2 ALTER COLUMN marketplace_transaction_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.judging_scores_v2 ALTER COLUMN judging_score_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.race_results_v2 ALTER COLUMN race_result_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.location_evidence_v2 ALTER COLUMN location_evidence_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.ai_jobs_v2 ALTER COLUMN ai_job_id SET DEFAULT extensions.gen_random_uuid();
ALTER TABLE public.ai_results_v2 ALTER COLUMN ai_result_id SET DEFAULT extensions.gen_random_uuid();

COMMIT;
