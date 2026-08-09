with checks as (
    select 'extensions_schema_exists' as check_name,
           exists(
               select 1
                 from pg_namespace
                where nspname = 'extensions'
           ) as passed
    union all
    select 'extensions_digest_available', exists(
        select 1
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'extensions'
           and p.proname = 'digest'
           and p.prorettype = 'bytea'::regtype
    )
    union all
    select 'extensions_gen_random_uuid_available', exists(
        select 1
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'extensions'
           and p.proname = 'gen_random_uuid'
           and p.prorettype = 'uuid'::regtype
    )
    union all
    select 'exos_v2_join_event_v2_uses_extensions_digest', exists(
        select 1
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public'
           and p.proname = 'exos_v2_join_event_v2'
           and pg_get_functiondef(p.oid) like '%extensions.digest%'
    )
    union all
    select 'exos_v2_join_event_v2_uses_extensions_gen_random_uuid', exists(
        select 1
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public'
           and p.proname = 'exos_v2_join_event_v2'
           and pg_get_functiondef(p.oid) like '%extensions.gen_random_uuid%'
    )
    union all
    select 'exos_v2_ledger_score_uses_extensions_digest', exists(
        select 1
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public'
           and p.proname = 'exos_v2_ledger_score'
           and pg_get_functiondef(p.oid) like '%extensions.digest%'
    )
),
status_rows as (
    select check_name, case when passed then 'PASS' else 'FAIL' end as status
    from checks
)
select * from status_rows
union all
select 'FAILED_CHECK_COUNT', (count(*) filter (where status = 'FAIL'))::text
from status_rows;
