-- EXOS Core v2 clean-room staging readiness verification
-- Run this immediately after executing supabase/020_exos_core_v2_schema.sql
-- Expected final row:
-- EXOS CORE V2 STAGING READY = TRUE

with required_tables as (
    select t.table_name
    from (values
        ('events_v2'),('programmes_v2'),('modules_v2'),('activities_v2'),('teams_v2'),
        ('participants_v2'),('participant_sessions_v2'),('activity_runtime_v2'),
        ('submissions_v2'),('submission_evidence_v2'),('reviews_v2'),
        ('score_transactions_v2'),('credit_transactions_v2'),('marketplace_items_v2'),
        ('marketplace_transactions_v2'),('build_status_v2'),('judging_scores_v2'),
        ('race_results_v2'),('projector_state_v2'),('location_checkpoints_v2'),
        ('location_evidence_v2'),('ai_jobs_v2'),('ai_results_v2'),('audit_log_v2')
    ) as t(table_name)
),
required_rpcs as (
    select r.routine_name
    from (values
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
    ) as r(routine_name)
),
required_indexes as (
    select i.indexname
    from (values
        ('teams_v2_event_idx'),
        ('participant_sessions_v2_event_idx'),
        ('submissions_v2_event_idx'),
        ('submissions_v2_team_idx'),
        ('score_transactions_v2_event_team_idx'),
        ('credit_transactions_v2_event_team_idx')
    ) as i(indexname)
),
legacy_candidates as (
    select t.table_name
    from (values
        ('runtime_events'),('runtime_participants'),('runtime_submissions'),('runtime_teams'),
        ('runtime_missions'),('formula_race_team_access'),('formula_race_team_checkpoints'),
        ('runtime_mission_submissions'),('runtime_mission_evidence'),('runtime_mission_status'),
        ('formula_race_results'),('formula_race_checkpoint_runtime')
    ) as t(table_name)
)
select 'pgcrypto_extension' as check_name, case
    when exists (select 1 from pg_extension e where e.extname = 'pgcrypto') then 'ok'
    else 'FAIL: missing extension'
end as status;

select 'pg_trgm_extension' as check_name, case
    when exists (select 1 from pg_extension e where e.extname = 'pg_trgm') then 'ok'
    else 'FAIL: missing extension'
end as status;

select 'table_exists' as check_type, t.table_name, case when exists(
    select 1 from information_schema.tables i where i.table_schema='public' and i.table_name=t.table_name
) then 'ok' else 'FAIL' end as status
from required_tables t
order by t.table_name;

select 'rpc_exists' as check_type, r.routine_name, case when exists(
    select 1 from information_schema.routines f where f.routine_schema='public' and f.routine_name = r.routine_name
) then 'ok' else 'FAIL' end as status
from required_rpcs r
order by r.routine_name;

select 'index_exists' as check_type, i.indexname, case when exists(
    select 1 from pg_indexes x where x.schemaname='public' and x.indexname = i.indexname
) then 'ok' else 'WARN: missing' end as status
from required_indexes i
order by i.indexname;

select 'rls_enabled' as check_type, c.relname as table_name, case when c.relrowsecurity then 'ok' else 'FAIL' end as status
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname='public'
  and c.relname in (select table_name from required_tables)
order by c.relname;

select 'constraints_present' as check_type, c.table_name, case when count(*) > 0 then 'ok' else 'FAIL: no constraints' end as status
from information_schema.table_constraints c
where c.table_schema='public'
  and c.table_name in (select table_name from required_tables)
  and c.constraint_type in ('PRIMARY KEY','UNIQUE','FOREIGN KEY','CHECK')
group by c.table_name
order by c.table_name;

select 'policy_has_service_role' as check_type, p.tablename as table_name, count(*)::text as status
from pg_policies p
where p.schemaname='public'
  and p.tablename in (select table_name from required_tables)
  and p.roles = '{service_role}'
group by p.tablename;

select 'table_permissions' as check_type, t.table_name, case
    when exists (
        select 1 from information_schema.role_table_grants g
         where g.table_schema='public' and g.table_name=t.table_name and g.grantee in ('anon','authenticated')
    )
    then 'WARN: direct grants present'
    else 'ok'
end as status
from required_tables t
order by t.table_name;

select 'function_permissions' as check_type, r.routine_name, array_agg(grantee) as grantees
from required_rpcs r
left join information_schema.routine_privileges p
    on p.specific_schema='public'
   and p.routine_name=r.routine_name
group by r.routine_name
order by r.routine_name;

select 'legacy_runtime_candidates_detected' as check_name, count(*)::text as status
from legacy_candidates l
where exists (select 1 from information_schema.tables t where t.table_schema='public' and t.table_name=l.table_name);

with ready as (
  select
    (not exists (select 1 from pg_extension e where e.extname = 'pgcrypto')) as missing_pgcrypto,
    (not exists (select 1 from pg_extension e where e.extname = 'pg_trgm')) as missing_pgtrgm,
    exists (select 1 from legacy_candidates l
            join information_schema.tables t on t.table_schema='public' and t.table_name=l.table_name) as legacy_found,
    exists (select 1 from required_tables t where not exists (
        select 1 from information_schema.table_constraints c
         where c.table_schema='public'
           and c.table_name=t.table_name
           and c.constraint_type in ('PRIMARY KEY','UNIQUE','FOREIGN KEY','CHECK')
    )) as missing_constraints,
    exists (select 1 from required_tables t where not exists (
        select 1 from information_schema.tables i where i.table_schema='public' and i.table_name=t.table_name
    )) as missing_table,
    exists (select 1 from required_rpcs r where not exists (
        select 1 from information_schema.routines f where f.routine_schema='public' and f.routine_name = r.routine_name
    )) as missing_rpc,
    exists (select 1 from required_indexes i where not exists (
        select 1 from pg_indexes x where x.schemaname='public' and x.indexname=i.indexname
    )) as missing_index
)
select
  'EXOS CORE V2 STAGING READY' as check_name,
  case
    when not missing_pgcrypto
     and not missing_pgtrgm
     and not legacy_found
     and not missing_constraints
     and not missing_table
     and not missing_rpc
     and not missing_index
    then 'TRUE'
    else 'FALSE'
  end as status
from ready;
