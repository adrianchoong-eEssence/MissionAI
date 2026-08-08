-- Guarded rollback for EXOS Core v2 foundation.
-- Rollback is blocked unless all v2 operational entities are empty.
do $$
declare
    v_rows integer;
begin
    select count(*) into v_rows from public.score_transactions_v2;
    if v_rows > 0 then
        raise exception 'Rollback blocked: score_transactions_v2 is not empty';
    end if;

    select count(*) into v_rows from public.credit_transactions_v2;
    if v_rows > 0 then
        raise exception 'Rollback blocked: credit_transactions_v2 is not empty';
    end if;

    select count(*) into v_rows from public.reviews_v2;
    if v_rows > 0 then
        raise exception 'Rollback blocked: reviews_v2 is not empty';
    end if;

    select count(*) into v_rows from public.submissions_v2;
    if v_rows > 0 then
        raise exception 'Rollback blocked: submissions_v2 is not empty';
    end if;

    select count(*) into v_rows from public.participant_sessions_v2;
    if v_rows > 0 then
        raise exception 'Rollback blocked: participant_sessions_v2 is not empty';
    end if;

    insert into public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, before_state, after_state
    ) values (
        null, 'service_role', 'ROLLBACK_INITIATED', 'migration', '020_exos_core_v2_schema',
        '{}'::jsonb, '{}'::jsonb
    );

    drop function if exists public.exos_v2_join_event_v2(text,text,text,text);
    drop function if exists public.exos_v2_restore_join(text,text,text);
    drop function if exists public.exos_v2_publish_event(text,text,text,jsonb,public.exos_v2_scoring_mode,text);
    drop function if exists public.exos_v2_next_team_id(text);
    drop function if exists public.exos_v2_normalize_participant_name(text);
    drop function if exists public.exos_v2_identity_payload(text,uuid);
    drop function if exists public.exos_v2_ledger_score(text,text,uuid,numeric,text,public.exos_v2_scoring_mode,text);
    drop function if exists public.exos_v2_ledger_credit(text,text,uuid,text,integer,text,text);
    drop function if exists public.exos_v2_admin_recover_identity(text,uuid,text,text,text);
    drop function if exists public.exos_v2_admin_merge_participants(text,uuid,uuid,text,text);

    drop table if exists public.audit_log_v2;
    drop table if exists public.ai_results_v2;
    drop table if exists public.ai_jobs_v2;
    drop table if exists public.location_evidence_v2;
    drop table if exists public.location_checkpoints_v2;
    drop table if exists public.projector_state_v2;
    drop table if exists public.race_results_v2;
    drop table if exists public.judging_scores_v2;
    drop table if exists public.build_status_v2;
    drop table if exists public.marketplace_transactions_v2;
    drop table if exists public.marketplace_items_v2;
    drop table if exists public.credit_transactions_v2;
    drop table if exists public.score_transactions_v2;
    drop table if exists public.reviews_v2;
    drop table if exists public.submission_evidence_v2;
    drop table if exists public.submissions_v2;
    drop table if exists public.activity_runtime_v2;
    drop table if exists public.participant_sessions_v2;
    drop table if exists public.participants_v2;
    drop table if exists public.teams_v2;
    drop table if exists public.activities_v2;
    drop table if exists public.modules_v2;
    drop table if exists public.programmes_v2;
    drop table if exists public.events_v2;

    drop type if exists public.exos_v2_build_status;
    drop type if exists public.exos_v2_review_decision;
    drop type if exists public.exos_v2_submission_status;
    drop type if exists public.exos_v2_scoring_mode;
    drop type if exists public.exos_v2_activity_type;
end;
$$;
