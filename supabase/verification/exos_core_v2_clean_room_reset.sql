-- EXOS Core v2 clean-room reset (disposable staging only).
-- Run ONLY when Core v2 install partially created objects and must be re-tried.

do $$
declare
    v_legacy boolean;
    v_any_v2 boolean;
    t text;
    f text;
    r text;
begin
    select exists(
        select 1
          from information_schema.tables t
         where t.table_schema='public'
           and t.table_name in (
             'runtime_events','runtime_participants','runtime_submissions','runtime_teams',
             'runtime_missions','formula_race_team_access','formula_race_team_checkpoints',
             'runtime_mission_submissions','runtime_mission_evidence','runtime_mission_status',
             'formula_race_results','formula_race_checkpoint_runtime'
           )
    ) into v_legacy;

    if v_legacy then
        raise exception 'CLEAN-ROOM RESET BLOCKED: legacy runtime tables detected. This is not a disposable clean staging project.';
    end if;

    select exists(
        select 1
          from pg_class c
          join pg_namespace n on n.oid = c.relnamespace
         where n.nspname='public'
           and (
               c.relname in (
                 'events_v2','programmes_v2','modules_v2','activities_v2','teams_v2',
                 'participants_v2','participant_sessions_v2','activity_runtime_v2','submissions_v2',
                 'submission_evidence_v2','reviews_v2','score_transactions_v2','credit_transactions_v2',
                 'marketplace_items_v2','marketplace_transactions_v2','build_status_v2','judging_scores_v2',
                 'race_results_v2','projector_state_v2','location_checkpoints_v2','location_evidence_v2',
                 'ai_jobs_v2','ai_results_v2','audit_log_v2'
               )
               or c.relname like 'exos_v2_%'
               or c.relname like 'audit_log_v2'
           )
    ) into v_any_v2;

    if not v_any_v2 then
        raise notice 'No Core v2 objects detected. Reset skipped.';
        return;
    end if;

    foreach t in array[
        'events_v2','programmes_v2','modules_v2','activities_v2','teams_v2',
        'participants_v2','participant_sessions_v2','activity_runtime_v2','submissions_v2',
        'submission_evidence_v2','reviews_v2','score_transactions_v2','credit_transactions_v2',
        'marketplace_items_v2','marketplace_transactions_v2','build_status_v2','judging_scores_v2',
        'race_results_v2','projector_state_v2','location_checkpoints_v2','location_evidence_v2',
        'ai_jobs_v2','ai_results_v2','audit_log_v2'
    ] loop
        execute format('drop table if exists public.%I cascade', t);
    end loop;

    foreach f in array[
        'exos_v2_normalize_participant_name(text)',
        'exos_v2_next_team_id(text)',
        'exos_v2_identity_payload(text,uuid)',
        'exos_v2_publish_event(text,text,text,jsonb,public.exos_v2_scoring_mode,text)',
        'exos_v2_join_event_v2(text,text,text,text)',
        'exos_v2_restore_join(text,text,text)',
        'exos_v2_admin_recover_identity(text,uuid,text,text,text)',
        'exos_v2_admin_merge_participants(text,uuid,uuid,text,text)',
        'exos_v2_ledger_score(text,text,uuid,numeric,text,public.exos_v2_scoring_mode,text)',
        'exos_v2_ledger_credit(text,text,uuid,text,integer,text,text)'
    ] loop
        execute format('drop function if exists public.%s', f);
    end loop;

    foreach r in array[
        'exos_v2_activity_type','exos_v2_scoring_mode','exos_v2_submission_status',
        'exos_v2_review_decision','exos_v2_build_status'
    ] loop
        execute format('drop type if exists public.%I cascade', r);
    end loop;

    raise notice 'Core v2 clean-room reset completed.';
end $$;
