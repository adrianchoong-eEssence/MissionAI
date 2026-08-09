-- EXOS Core v2: partial-install probe (read-only)
-- Run after a failed migration attempt before cleanup/retry.

with required_ext as (
    values ('pgcrypto'), ('pg_trgm')
),
required_types as (
    values
        ('exos_v2_activity_type'),
        ('exos_v2_scoring_mode'),
        ('exos_v2_submission_status'),
        ('exos_v2_review_decision'),
        ('exos_v2_build_status')
),
required_tables as (
    values
        ('events_v2'),('programmes_v2'),('modules_v2'),('activities_v2'),('teams_v2'),
        ('participants_v2'),('participant_sessions_v2'),('activity_runtime_v2'),('submissions_v2'),
        ('submission_evidence_v2'),('reviews_v2'),('score_transactions_v2'),('credit_transactions_v2'),
        ('marketplace_items_v2'),('marketplace_transactions_v2'),('build_status_v2'),('judging_scores_v2'),
        ('race_results_v2'),('projector_state_v2'),('location_checkpoints_v2'),('location_evidence_v2'),
        ('ai_jobs_v2'),('ai_results_v2'),('audit_log_v2')
),
required_functions as (
    values
        ('exos_v2_normalize_participant_name'),
        ('exos_v2_next_team_id'),
        ('exos_v2_identity_payload'),
        ('exos_v2_publish_event'),
        ('exos_v2_join_event_v2'),
        ('exos_v2_restore_join'),
        ('exos_v2_admin_recover_identity'),
        ('exos_v2_admin_merge_participants'),
        ('exos_v2_ledger_score'),
        ('exos_v2_ledger_credit')
),
legacy_objects as (
    values
        ('runtime_events'),('runtime_participants'),('runtime_submissions'),('runtime_teams'),
        ('runtime_missions'),('runtime_teams_v2'),('runtime_participants_v2'),('runtime_submissions_v2'),
        ('formula_race_team_access'),('formula_race_team_checkpoints'),('runtime_mission_submissions'),
        ('runtime_mission_evidence'),('runtime_mission_status'),('formula_race_results'),
        ('formula_race_checkpoint_runtime')
)
select
    'DATABASE STATE' as "CHECK",
    'CLEAN_DATABASE/PARTIAL_CORE_V2_INSTALL' as "EXPECTED",
    case
        when count(*) filter (where is_present = false) = 0
         and count(*) filter (where kind = 'legacy_contamination') = 0
        then 'CLEAN_DATABASE'
        else 'PARTIAL_CORE_V2_INSTALL'
    end as "ACTUAL",
    case
        when count(*) filter (where is_present = false) = 0
         and count(*) filter (where kind = 'legacy_contamination') = 0
        then 'PASS' else 'FAIL'
    end as "PASS"
from (
    select 'ext'::text as kind, e.column1 as name,
           exists (select 1 from pg_extension x where x.extname = e.column1) as is_present
    from required_ext e
    union all
    select 'type', t.column1,
           exists (
               select 1
               from pg_type ty
               join pg_namespace ns on ns.oid = ty.typnamespace
               where ns.nspname='public' and ty.typname=t.column1 and ty.typtype='e'
           )
    from required_types t
    union all
    select 'table', tb.column1,
           exists (
               select 1 from information_schema.tables
               where table_schema='public' and table_name = tb.column1
           )
    from required_tables tb
    union all
    select 'function', f.column1,
           exists (
           select 1
           from information_schema.routines r
           where r.routine_schema='public' and r.routine_name = f.column1
           )
    from required_functions f
    union all
    select 'legacy_contamination', l.column1,
           exists (
             select 1
             from information_schema.tables
             where table_schema='public' and table_name = l.column1
           )
    from legacy_objects l
) probe_rows

union all

select
    'extension ' || e.column1,
    'installed',
    case when exists (select 1 from pg_extension x where x.extname = e.column1) then 'present' else 'missing' end,
    case when exists (select 1 from pg_extension x where x.extname = e.column1) then 'PASS' else 'FAIL' end
from required_ext e

union all

select
    'enum type ' || t.column1,
    'created',
    case when exists (
        select 1
        from pg_type ty
        join pg_namespace ns on ns.oid = ty.typnamespace
        where ns.nspname='public' and ty.typname=t.column1 and ty.typtype='e'
    ) then 'present' else 'missing' end,
    case when exists (
        select 1
        from pg_type ty
        join pg_namespace ns on ns.oid = ty.typnamespace
        where ns.nspname='public' and ty.typname=t.column1 and ty.typtype='e'
    ) then 'PASS' else 'FAIL' end
from required_types t

union all

select
    'table ' || tb.column1,
    'created',
    case when exists (select 1 from information_schema.tables where table_schema='public' and table_name=tb.column1) then 'present' else 'missing' end,
    case when exists (select 1 from information_schema.tables where table_schema='public' and table_name=tb.column1) then 'PASS' else 'FAIL' end
from required_tables tb

union all

select
    'function ' || f.column1,
    'created',
    case when exists (
           select 1
           from information_schema.routines r
           where r.routine_schema='public' and r.routine_name = f.column1
           ) then 'present' else 'missing' end,
   case when exists (
        select 1
        from information_schema.routines r
           where r.routine_schema='public' and r.routine_name = f.column1
    ) then 'PASS' else 'FAIL' end
from required_functions f;
