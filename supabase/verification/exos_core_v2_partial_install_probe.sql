-- EXOS Core v2: partial-install probe (read-only)
-- Run this after any failed migration attempt before retrying installation.
-- It never mutates schema.

select
    'DATABASE STATE' as check_name,
    case
        when not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace where n.nspname='public' and t.typname like 'exos_v2_%' and t.typtype='e')
         and not exists (select 1 from information_schema.tables where table_schema='public' and table_name like '%_v2')
         and not exists (select 1 from information_schema.routines where routine_schema='public' and routine_name like 'exos_v2_%')
         and not exists (select 1 from pg_indexes where schemaname='public' and indexname like '%_v2%')
         and not exists (select 1 from pg_policies where schemaname='public' and tablename like '%_v2')
         and not exists (
            select 1 from information_schema.tables
            where table_schema='public'
              and table_name in (
                'runtime_events','runtime_participants','runtime_submissions','runtime_teams',
                'runtime_missions','formula_race_team_access','formula_race_team_checkpoints',
                'runtime_mission_submissions','runtime_mission_evidence','runtime_mission_status',
                'formula_race_results','formula_race_checkpoint_runtime'
              )
        )
        then 'CLEAN_DATABASE'
        else 'PARTIAL_CORE_V2_INSTALL'
    end as status,
    null::text as details
;

select
    'exos_v2 enum types' as check_name,
    typname as name,
    'PRESENT' as status
from pg_type t
join pg_namespace n on n.oid = t.typnamespace
where n.nspname='public'
  and t.typname like 'exos_v2_%'
  and t.typtype='e'
union all
select
    'v2 tables' as check_name,
    table_name,
    'PRESENT' as status
from information_schema.tables
where table_schema='public'
  and table_name like '%_v2'
union all
select
    'exos_v2 functions' as check_name,
    routine_name,
    'PRESENT' as status
from information_schema.routines
where routine_schema='public'
  and routine_name like 'exos_v2_%'
union all
select
    'v2 indexes' as check_name,
    indexname,
    'PRESENT' as status
from pg_indexes
where schemaname='public'
  and indexname like '%_v2%'
union all
select
    'v2 policies' as check_name,
    tablename || '.' || policyname,
    'PRESENT' as status
from pg_policies
where schemaname='public'
  and tablename like '%_v2'
union all
select
    'legacy contamination' as check_name,
    table_name,
    'FOUND' as status
from information_schema.tables
where table_schema='public'
  and table_name in (
    'runtime_events','runtime_participants','runtime_submissions','runtime_teams',
    'runtime_missions','formula_race_team_access','formula_race_team_checkpoints',
    'runtime_mission_submissions','runtime_mission_evidence','runtime_mission_status',
    'formula_race_results','formula_race_checkpoint_runtime'
  );
