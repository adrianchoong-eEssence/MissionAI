-- EXOS Core v2 Team Access verification (run after applying 022_exos_core_v2_team_access.sql)
-- One row per requirement: CHECK | EXPECTED | ACTUAL | PASS

with requirements(check_name, expected) as (
    values
    ('pgcrypto_extension', 'exists'),
    ('table:team_access_credentials_v2', 'exists'),
    ('table:team_access_sessions_v2', 'exists'),
    ('rpc:exos_v2_set_team_access_pin', 'exists'),
    ('rpc:exos_v2_team_access_login', 'exists'),
    ('rpc:exos_v2_restore_team_access', 'exists'),
    ('policy:team_access_credentials_v2 sr', 'exists'),
    ('policy:team_access_sessions_v2 sr', 'exists'),
    ('legacy table:formula_race_team_access', 'absent'),
    ('legacy rpc:exos_formula_race', 'absent'),
    ('legacy rpc:exos_set_formula_race', 'absent'),
    ('legacy table runtime_events', 'absent'),
    ('index:team_access_sessions_v2_event_team_idx', 'exists'),
    ('fk:team_access_credentials_v2.event_id', 'fk->events_v2(event_id)'),
    ('fk:team_access_credentials_v2.team_id', 'fk->teams_v2(team_id)'),
    ('fk:team_access_sessions_v2.credential', 'fk->team_access_credentials_v2(team_access_credential_id)'),
    ('fk:team_access_sessions_v2.team', 'fk->teams_v2(team_id)')
),
results as (
    select
        'pgcrypto_extension' as check_name,
        'exists' as expected,
        case when exists(select 1 from pg_extension e where e.extname='pgcrypto') then 'exists' else 'FAIL' end as actual,
        case when exists(select 1 from pg_extension e where e.extname='pgcrypto') then true else false end as pass
    union all
    select
        'table:team_access_credentials_v2',
        'exists',
        case when exists(select 1 from information_schema.tables t where t.table_schema='public' and t.table_name='team_access_credentials_v2') then 'exists' else 'FAIL' end,
        exists(select 1 from information_schema.tables t where t.table_schema='public' and t.table_name='team_access_credentials_v2')
    union all
    select
        'table:team_access_sessions_v2',
        'exists',
        case when exists(select 1 from information_schema.tables t where t.table_schema='public' and t.table_name='team_access_sessions_v2') then 'exists' else 'FAIL' end,
        exists(select 1 from information_schema.tables t where t.table_schema='public' and t.table_name='team_access_sessions_v2')
    union all
    select
        'rpc:exos_v2_set_team_access_pin',
        'exists',
        case when exists(select 1 from information_schema.routines r where r.specific_schema='public' and r.routine_name='exos_v2_set_team_access_pin') then 'exists' else 'FAIL' end,
        exists(select 1 from information_schema.routines r where r.specific_schema='public' and r.routine_name='exos_v2_set_team_access_pin')
    union all
    select
        'rpc:exos_v2_team_access_login',
        'exists',
        case when exists(select 1 from information_schema.routines r where r.specific_schema='public' and r.routine_name='exos_v2_team_access_login') then 'exists' else 'FAIL' end,
        exists(select 1 from information_schema.routines r where r.specific_schema='public' and r.routine_name='exos_v2_team_access_login')
    union all
    select
        'rpc:exos_v2_restore_team_access',
        'exists',
        case when exists(select 1 from information_schema.routines r where r.specific_schema='public' and r.routine_name='exos_v2_restore_team_access') then 'exists' else 'FAIL' end,
        exists(select 1 from information_schema.routines r where r.specific_schema='public' and r.routine_name='exos_v2_restore_team_access')
    union all
    select
        'policy:team_access_credentials_v2 sr',
        'exists',
        case when exists(select 1 from pg_policies p where p.schemaname='public' and p.tablename='team_access_credentials_v2' and p.roles='{service_role}') then 'exists' else 'FAIL' end,
        exists(select 1 from pg_policies p where p.schemaname='public' and p.tablename='team_access_credentials_v2' and p.roles='{service_role}')
    union all
    select
        'policy:team_access_sessions_v2 sr',
        'exists',
        case when exists(select 1 from pg_policies p where p.schemaname='public' and p.tablename='team_access_sessions_v2' and p.roles='{service_role}') then 'exists' else 'FAIL' end,
        exists(select 1 from pg_policies p where p.schemaname='public' and p.tablename='team_access_sessions_v2' and p.roles='{service_role}')
    union all
    select
        'legacy table:formula_race_team_access',
        'absent',
        case when exists(select 1 from information_schema.tables t where t.table_schema='public' and t.table_name='formula_race_team_access') then 'PRESENT' else 'absent' end,
        not exists(select 1 from information_schema.tables t where t.table_schema='public' and t.table_name='formula_race_team_access')
    union all
    select
        'legacy rpc:exos_formula_race',
        'absent',
        case when exists(select 1 from information_schema.routines r where r.specific_schema='public' and r.routine_name like 'exos_formula_race_%') then 'PRESENT' else 'absent' end,
        not exists(select 1 from information_schema.routines r where r.specific_schema='public' and r.routine_name like 'exos_formula_race_%')
    union all
    select
        'legacy rpc:exos_set_formula_race',
        'absent',
        case when exists(select 1 from information_schema.routines r where r.specific_schema='public' and r.routine_name like 'exos_set_formula_race%') then 'PRESENT' else 'absent' end,
        not exists(select 1 from information_schema.routines r where r.specific_schema='public' and r.routine_name like 'exos_set_formula_race%')
    union all
    select
        'legacy table runtime_events',
        'absent',
        case when exists(select 1 from information_schema.tables t where t.table_schema='public' and t.table_name='runtime_events') then 'PRESENT' else 'absent' end,
        not exists(select 1 from information_schema.tables t where t.table_schema='public' and t.table_name='runtime_events')
    union all
    select
        'index:team_access_sessions_v2_event_team_idx',
        'exists',
        case when exists(select 1 from pg_indexes i where i.schemaname='public' and i.indexname='team_access_sessions_v2_event_team_idx') then 'exists' else 'FAIL' end,
        exists(select 1 from pg_indexes i where i.schemaname='public' and i.indexname='team_access_sessions_v2_event_team_idx')
    union all
    select
        'fk:team_access_credentials_v2.event_id',
        'fk->events_v2(event_id)',
        case
            when exists(
                select 1
                  from information_schema.table_constraints c
                 where c.table_schema='public'
                   and c.table_name='team_access_credentials_v2'
                   and c.constraint_type='FOREIGN KEY'
                   and c.constraint_name like '%event_id%'
            ) then 'exists'
            else 'FAIL'
        end,
        exists(
            select 1
              from information_schema.table_constraints c
             where c.table_schema='public'
               and c.table_name='team_access_credentials_v2'
               and c.constraint_type='FOREIGN KEY'
               and c.constraint_name like '%event_id%'
        )
    union all
    select
        'fk:team_access_credentials_v2.team_id',
        'fk->teams_v2(team_id)',
        case
            when exists(
                select 1
                  from information_schema.table_constraints c
                 where c.table_schema='public'
                   and c.table_name='team_access_credentials_v2'
                   and c.constraint_type='FOREIGN KEY'
                   and c.constraint_name like '%team_id%'
            ) then 'exists'
            else 'FAIL'
        end,
        exists(
            select 1
              from information_schema.table_constraints c
             where c.table_schema='public'
               and c.table_name='team_access_credentials_v2'
               and c.constraint_type='FOREIGN KEY'
               and c.constraint_name like '%team_id%'
        )
    union all
    select
        'fk:team_access_sessions_v2.credential',
        'fk->team_access_credentials_v2(team_access_credential_id)',
        case
            when exists(
                select 1
                  from information_schema.table_constraints c
                 where c.table_schema='public'
                   and c.table_name='team_access_sessions_v2'
                   and c.constraint_type='FOREIGN KEY'
                   and c.constraint_name like '%team_access_credential_id%'
            ) then 'exists'
            else 'FAIL'
        end,
        exists(
            select 1
              from information_schema.table_constraints c
             where c.table_schema='public'
               and c.table_name='team_access_sessions_v2'
               and c.constraint_type='FOREIGN KEY'
               and c.constraint_name like '%team_access_credential_id%'
        )
    union all
    select
        'fk:team_access_sessions_v2.team',
        'fk->teams_v2(team_id)',
        case
            when exists(
                select 1
                  from information_schema.table_constraints c
                 where c.table_schema='public'
                   and c.table_name='team_access_sessions_v2'
                   and c.constraint_type='FOREIGN KEY'
                   and c.constraint_name like '%team_id%'
            ) then 'exists'
            else 'FAIL'
        end,
        exists(
            select 1
              from information_schema.table_constraints c
             where c.table_schema='public'
               and c.table_name='team_access_sessions_v2'
               and c.constraint_type='FOREIGN KEY'
               and c.constraint_name like '%team_id%'
        )
)
select
    check_name as check,
    expected,
    actual,
    case when pass then 'PASS' else 'FAIL' end as result
from results
order by check_name;

select
    'TEAM_ACCESS_CLEAN' as status_key,
    case when exists(select 1 from results where not pass) then 'FALSE' else 'TRUE' end as status;
