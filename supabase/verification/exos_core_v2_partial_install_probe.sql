-- EXOS Core v2: partial-install probe (read-only)
-- Run this after any failed migration attempt before retrying installation.
-- It never mutates schema.

with enum_probe as (
    select typname as name
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    where n.nspname = 'public'
      and t.typname in (
        'exos_v2_activity_type',
        'exos_v2_scoring_mode',
        'exos_v2_submission_status',
        'exos_v2_review_decision',
        'exos_v2_build_status'
      )
      and t.typtype = 'e'
),
table_probe as (
    select table_name as name
    from information_schema.tables
    where table_schema='public'
      and table_name in (
        'events_v2','programmes_v2','modules_v2','activities_v2','teams_v2',
        'participants_v2','participant_sessions_v2','activity_runtime_v2','submissions_v2',
        'submission_evidence_v2','reviews_v2','score_transactions_v2','credit_transactions_v2',
        'marketplace_items_v2','marketplace_transactions_v2','build_status_v2','judging_scores_v2',
        'race_results_v2','projector_state_v2','location_checkpoints_v2','location_evidence_v2',
        'ai_jobs_v2','ai_results_v2','audit_log_v2'
      )
),
function_probe as (
    select routine_name as name
    from information_schema.routines
    where routine_schema='public'
      and routine_name in (
        'exos_v2_normalize_participant_name','exos_v2_next_team_id','exos_v2_identity_payload',
        'exos_v2_publish_event','exos_v2_join_event_v2','exos_v2_restore_join',
        'exos_v2_admin_recover_identity','exos_v2_admin_merge_participants',
        'exos_v2_ledger_score','exos_v2_ledger_credit'
      )
),
index_probe as (
    select indexname as name
    from pg_indexes
    where schemaname='public'
      and indexname in (
        'teams_v2_event_idx','participant_sessions_v2_event_idx',
        'submissions_v2_event_idx','submissions_v2_team_idx',
        'score_transactions_v2_event_team_idx','credit_transactions_v2_event_team_idx'
      )
),
policy_probe as (
    select tablename as name
    from pg_policies
    where schemaname='public' and tablename in (
        'events_v2','programmes_v2','modules_v2','activities_v2','teams_v2','participants_v2',
        'participant_sessions_v2','activity_runtime_v2','submissions_v2','submission_evidence_v2',
        'reviews_v2','score_transactions_v2','credit_transactions_v2','marketplace_items_v2',
        'marketplace_transactions_v2','build_status_v2','judging_scores_v2','race_results_v2',
        'projector_state_v2','location_checkpoints_v2','location_evidence_v2','ai_jobs_v2',
        'ai_results_v2','audit_log_v2'
    )
),
legacy_probe as (
    select table_name as name
    from information_schema.tables
    where table_schema='public' and table_name in (
        'runtime_events','runtime_participants','runtime_submissions','runtime_teams',
        'runtime_missions','formula_race_team_access','formula_race_team_checkpoints',
        'runtime_mission_submissions','runtime_mission_evidence','runtime_mission_status',
        'formula_race_results','formula_race_checkpoint_runtime'
    )
),
all_facts as (
    select 'enum'::text as object_type, name from enum_probe
    union all
    select 'table', name from table_probe
    union all
    select 'function', name from function_probe
    union all
    select 'index', name from index_probe
    union all
    select 'policy', name from policy_probe
)
select 'CLEAN_DATABASE' as check_name,
       case
           when not exists (select 1 from enum_probe) and
                not exists (select 1 from table_probe) and
                not exists (select 1 from function_probe) and
                not exists (select 1 from index_probe) and
                not exists (select 1 from policy_probe)
           then 'PASS'
           else 'PARTIAL CORE V2 INSTALL'
       end as status,
       null::text as details
union all
select
    object_type || '_found_' || name, 'PRESENT', name
from all_facts
union all
select
    'legacy_runtime_object' as check_name,
    'FOUND',
    name
from legacy_probe
where exists (select 1 from legacy_probe);
