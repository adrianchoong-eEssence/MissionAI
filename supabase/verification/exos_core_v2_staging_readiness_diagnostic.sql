-- EXOS Core v2: staging readiness diagnostic (read-only, single-statement UNION ALL report)
-- Returns rows: CHECK | EXPECTED | ACTUAL | PASS
-- Includes one final summary row: FAILED CHECK COUNT

with
required_extensions(ext) as (
    values ('pgcrypto'), ('pg_trgm')
),
required_enums(enum_name) as (
    values
      ('exos_v2_activity_type'),
      ('exos_v2_scoring_mode'),
      ('exos_v2_submission_status'),
      ('exos_v2_review_decision'),
      ('exos_v2_build_status')
),
required_tables(table_name) as (
    values
      ('events_v2'),('programmes_v2'),('modules_v2'),('activities_v2'),('teams_v2'),
      ('participants_v2'),('participant_sessions_v2'),('activity_runtime_v2'),
      ('submissions_v2'),('submission_evidence_v2'),('reviews_v2'),('score_transactions_v2'),
      ('credit_transactions_v2'),('marketplace_items_v2'),('marketplace_transactions_v2'),
      ('build_status_v2'),('judging_scores_v2'),('race_results_v2'),('projector_state_v2'),
      ('location_checkpoints_v2'),('location_evidence_v2'),('ai_jobs_v2'),('ai_results_v2'),('audit_log_v2')
),
required_functions(function_name) as (
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
required_indexes(index_name) as (
    values
      ('teams_v2_event_idx'),
      ('participant_sessions_v2_event_idx'),
      ('submissions_v2_event_idx'),
      ('submissions_v2_team_idx'),
      ('score_transactions_v2_event_team_idx'),
      ('credit_transactions_v2_event_team_idx')
),
required_policy_tables(table_name) as (
    values
      ('events_v2'),('programmes_v2'),('modules_v2'),('activities_v2'),('teams_v2'),('participants_v2'),
      ('participant_sessions_v2'),('activity_runtime_v2'),('submissions_v2'),('submission_evidence_v2'),
      ('reviews_v2'),('score_transactions_v2'),('credit_transactions_v2'),('marketplace_items_v2'),
      ('marketplace_transactions_v2'),('build_status_v2'),('judging_scores_v2'),('race_results_v2'),
      ('projector_state_v2'),('location_checkpoints_v2'),('location_evidence_v2'),('ai_jobs_v2'),
      ('ai_results_v2'),('audit_log_v2')
),
required_fk_checks(fk_check) as (
    values
      ('programmes_v2.event_id -> events_v2.event_id'),
      ('modules_v2.programme_id -> programmes_v2.programme_id'),
      ('activities_v2.module_id -> modules_v2.module_id'),
      ('activities_v2.programme_id -> programmes_v2.programme_id'),
      ('teams_v2.event_id -> events_v2.event_id'),
      ('participants_v2.event_id -> events_v2.event_id'),
      ('participants_v2.team_id -> teams_v2.team_id'),
      ('participant_sessions_v2.event_id -> events_v2.event_id'),
      ('participant_sessions_v2.participant_id -> participants_v2.participant_id'),
      ('submissions_v2.event_id -> events_v2.event_id'),
      ('submissions_v2.team_id -> teams_v2.team_id'),
      ('submissions_v2.participant_id -> participants_v2.participant_id'),
      ('submissions_v2.activity_id -> activities_v2.activity_id'),
      ('score_transactions_v2.event_id -> events_v2.event_id'),
      ('score_transactions_v2.team_id -> teams_v2.team_id'),
      ('credit_transactions_v2.event_id -> events_v2.event_id'),
      ('credit_transactions_v2.team_id -> teams_v2.team_id'),
      ('marketplace_transactions_v2.event_id -> events_v2.event_id'),
      ('marketplace_transactions_v2.team_id -> teams_v2.team_id')
),
legacy_tables(table_name) as (
    values
      ('runtime_events'),('runtime_participants'),('runtime_submissions'),('runtime_teams'),
      ('runtime_missions'),('formula_race_team_access'),('formula_race_team_checkpoints'),
      ('runtime_mission_submissions'),('runtime_mission_evidence'),('runtime_mission_status'),
      ('formula_race_results'),('formula_race_checkpoint_runtime')
),
checks as (
    select
        'extension ' || e.ext as check_name,
        'extension exists' as expected,
        case when exists (select 1 from pg_extension ex where ex.extname = e.ext)
            then 'present' else 'missing' end as actual,
        case when exists (select 1 from pg_extension ex where ex.extname = e.ext)
            then 'PASS' else 'FAIL' end as pass
    from required_extensions e

    union all

    select
        'enum ' || en.enum_name,
        'enum type exists',
        case when exists (
            select 1
            from pg_type t
            join pg_namespace n on n.oid=t.typnamespace
            where n.nspname='public' and t.typname=en.enum_name and t.typtype='e'
        ) then 'present' else 'missing' end,
        case when exists (
            select 1
            from pg_type t
            join pg_namespace n on n.oid=t.typnamespace
            where n.nspname='public' and t.typname=en.enum_name and t.typtype='e'
        ) then 'PASS' else 'FAIL' end
    from required_enums en

    union all

    select
        'table ' || t.table_name,
        'table exists',
        case when exists (select 1 from information_schema.tables i where i.table_schema='public' and i.table_name=t.table_name)
            then 'present' else 'missing' end,
        case when exists (select 1 from information_schema.tables i where i.table_schema='public' and i.table_name=t.table_name)
            then 'PASS' else 'FAIL' end
    from required_tables t

    union all

    select
        'function public.' || f.function_name,
        'function exists',
        case when exists (select 1 from information_schema.routines r where r.routine_schema='public' and r.routine_name=f.function_name)
            then 'present' else 'missing' end,
        case when exists (select 1 from information_schema.routines r where r.routine_schema='public' and r.routine_name=f.function_name)
            then 'PASS' else 'FAIL' end
    from required_functions f

    union all

    select
        'index ' || i.index_name,
        'index exists',
        case when exists (select 1 from pg_indexes x where x.schemaname='public' and x.indexname=i.index_name)
            then 'present' else 'missing' end,
        case when exists (select 1 from pg_indexes x where x.schemaname='public' and x.indexname=i.index_name)
            then 'PASS' else 'FAIL' end
    from required_indexes i

    union all

    select
        'constraint PK on events_v2.event_id',
        'PRIMARY KEY exists',
        case when exists (
            select 1 from pg_constraint c
            join pg_class cl on cl.oid = c.conrelid
            join pg_namespace n on n.oid = cl.relnamespace
            where n.nspname='public' and cl.relname='events_v2' and c.contype='p'
        ) then 'present' else 'missing' end,
        case when exists (
            select 1 from pg_constraint c
            join pg_class cl on cl.oid = c.conrelid
            join pg_namespace n on n.oid = cl.relnamespace
            where n.nspname='public' and cl.relname='events_v2' and c.contype='p'
        ) then 'PASS' else 'FAIL' end

    union all

    select
        'constraint unique participant session key',
        'unique(event_id, idempotency_key)',
        case when exists (
            select 1
            from pg_constraint c
            join pg_class cl on cl.oid=c.conrelid
            join pg_namespace n on n.oid=cl.relnamespace
            where n.nspname='public' and cl.relname='participant_sessions_v2'
              and c.contype='u'
              and pg_get_constraintdef(c.oid) like '%(event_id, idempotency_key)%'
        ) then 'present' else 'missing' end,
        case when exists (
            select 1
            from pg_constraint c
            join pg_class cl on cl.oid=c.conrelid
            join pg_namespace n on n.oid=cl.relnamespace
            where n.nspname='public' and cl.relname='participant_sessions_v2'
              and c.contype='u'
              and pg_get_constraintdef(c.oid) like '%(event_id, idempotency_key)%'
        ) then 'PASS' else 'FAIL' end

    union all

    select
        'constraint idempotency score tx',
        'unique(event_id, idempotency_key)',
        case when exists (
            select 1
            from pg_constraint c
            join pg_class cl on cl.oid=c.conrelid
            join pg_namespace n on n.oid=cl.relnamespace
            where n.nspname='public' and cl.relname='score_transactions_v2'
              and c.contype='u'
              and pg_get_constraintdef(c.oid) like '%(event_id, idempotency_key)%'
        ) then 'present' else 'missing' end,
        case when exists (
            select 1
            from pg_constraint c
            join pg_class cl on cl.oid=c.conrelid
            join pg_namespace n on n.oid=cl.relnamespace
            where n.nspname='public' and cl.relname='score_transactions_v2'
              and c.contype='u'
              and pg_get_constraintdef(c.oid) like '%(event_id, idempotency_key)%'
        ) then 'PASS' else 'FAIL' end

    union all

    select
        'constraint idempotency credit tx',
        'unique(event_id, idempotency_key)',
        case when exists (
            select 1
            from pg_constraint c
            join pg_class cl on cl.oid=c.conrelid
            join pg_namespace n on n.oid=cl.relnamespace
            where n.nspname='public' and cl.relname='credit_transactions_v2'
              and c.contype='u'
              and pg_get_constraintdef(c.oid) like '%(event_id, idempotency_key)%'
        ) then 'present' else 'missing' end,
        case when exists (
            select 1
            from pg_constraint c
            join pg_class cl on cl.oid=c.conrelid
            join pg_namespace n on n.oid=cl.relnamespace
            where n.nspname='public' and cl.relname='credit_transactions_v2'
              and c.contype='u'
              and pg_get_constraintdef(c.oid) like '%(event_id, idempotency_key)%'
        ) then 'PASS' else 'FAIL' end

    union all

    select
        'constraint idempotency marketplace tx',
        'unique(event_id, idempotency_key)',
        case when exists (
            select 1
            from pg_constraint c
            join pg_class cl on cl.oid=c.conrelid
            join pg_namespace n on n.oid=cl.relnamespace
            where n.nspname='public' and cl.relname='marketplace_transactions_v2'
              and c.contype='u'
              and pg_get_constraintdef(c.oid) like '%(event_id, idempotency_key)%'
        ) then 'present' else 'missing' end,
        case when exists (
            select 1
            from pg_constraint c
            join pg_class cl on cl.oid=c.conrelid
            join pg_namespace n on n.oid=cl.relnamespace
            where n.nspname='public' and cl.relname='marketplace_transactions_v2'
              and c.contype='u'
              and pg_get_constraintdef(c.oid) like '%(event_id, idempotency_key)%'
        ) then 'PASS' else 'FAIL' end

    union all

    select
        'constraint submission key uniqueness',
        'unique(event_id, submission_key)',
        case when exists (
            select 1
            from pg_constraint c
            join pg_class cl on cl.oid=c.conrelid
            join pg_namespace n on n.oid=cl.relnamespace
            where n.nspname='public' and cl.relname='submissions_v2'
              and c.contype='u'
              and pg_get_constraintdef(c.oid) like '%(event_id, submission_key)%'
        ) then 'present' else 'missing' end,
        case when exists (
            select 1
            from pg_constraint c
            join pg_class cl on cl.oid=c.conrelid
            join pg_namespace n on n.oid=cl.relnamespace
            where n.nspname='public' and cl.relname='submissions_v2'
              and c.contype='u'
              and pg_get_constraintdef(c.oid) like '%(event_id, submission_key)%'
        ) then 'PASS' else 'FAIL' end

    union all

    select
        'RLS enabled on ' || rt.table_name,
        'relrowsecurity = true',
        case when exists (
            select 1
            from pg_class c
            join pg_namespace n on n.oid=c.relnamespace
            where n.nspname='public' and c.relname=rt.table_name and c.relrowsecurity = true
        ) then 'enabled' else 'disabled/missing' end,
        case when exists (
            select 1
            from pg_class c
            join pg_namespace n on n.oid=c.relnamespace
            where n.nspname='public' and c.relname=rt.table_name and c.relrowsecurity = true
        ) then 'PASS' else 'FAIL' end
    from required_tables rt

    union all

    select
        'RLS policy on ' || rpt.table_name,
        'service_role policy exists',
        case when exists (
            select 1
            from pg_policies p
            where p.schemaname='public'
              and p.tablename=rpt.table_name
              and coalesce(array_to_string(p.roles, ','), '') like '%service_role%'
        ) then 'present' else 'missing' end,
        case when exists (
            select 1
            from pg_policies p
            where p.schemaname='public'
              and p.tablename=rpt.table_name
              and coalesce(array_to_string(p.roles, ','), '') like '%service_role%'
        ) then 'PASS' else 'FAIL' end
    from required_policy_tables rpt

    union all

    select
        'table grants | ' || rt.table_name,
        'no direct anon/auth grants',
        case when exists (
            select 1
            from information_schema.role_table_grants g
            where g.table_schema='public'
              and g.table_name=rt.table_name
              and g.grantee in ('anon','authenticated')
        ) then 'found' else 'none' end,
        case when not exists (
            select 1
            from information_schema.role_table_grants g
            where g.table_schema='public'
              and g.table_name=rt.table_name
              and g.grantee in ('anon','authenticated')
        ) then 'PASS' else 'FAIL' end
    from required_tables rt

    union all

    select
        'function exec grant: exos_v2_join_event_v2 -> anon',
        'EXECUTE granted',
        case when exists (
            select 1 from information_schema.routine_privileges rp
            where rp.specific_schema='public'
              and rp.routine_name='exos_v2_join_event_v2'
              and rp.grantee='anon'
              and rp.privilege_type='EXECUTE'
        ) then 'granted' else 'missing' end,
        case when exists (
            select 1 from information_schema.routine_privileges rp
            where rp.specific_schema='public'
              and rp.routine_name='exos_v2_join_event_v2'
              and rp.grantee='anon'
              and rp.privilege_type='EXECUTE'
        ) then 'PASS' else 'FAIL' end

    union all

    select
        'function exec grant: exos_v2_restore_join -> anon',
        'EXECUTE granted',
        case when exists (
            select 1 from information_schema.routine_privileges rp
            where rp.specific_schema='public'
              and rp.routine_name='exos_v2_restore_join'
              and rp.grantee='anon'
              and rp.privilege_type='EXECUTE'
        ) then 'granted' else 'missing' end,
        case when exists (
            select 1 from information_schema.routine_privileges rp
            where rp.specific_schema='public'
              and rp.routine_name='exos_v2_restore_join'
              and rp.grantee='anon'
              and rp.privilege_type='EXECUTE'
        ) then 'PASS' else 'FAIL' end

    union all

    select
        'function exec grant: exos_v2_publish_event -> service_role',
        'EXECUTE granted',
        case when exists (
            select 1 from information_schema.routine_privileges rp
            where rp.specific_schema='public'
              and rp.routine_name='exos_v2_publish_event'
              and rp.grantee='service_role'
              and rp.privilege_type='EXECUTE'
        ) then 'granted' else 'missing' end,
        case when exists (
            select 1 from information_schema.routine_privileges rp
            where rp.specific_schema='public'
              and rp.routine_name='exos_v2_publish_event'
              and rp.grantee='service_role'
              and rp.privilege_type='EXECUTE'
        ) then 'PASS' else 'FAIL' end

    union all

    select
        'function exec grant: exos_v2_ledger_score -> service_role',
        'EXECUTE granted',
        case when exists (
            select 1 from information_schema.routine_privileges rp
            where rp.specific_schema='public'
              and rp.routine_name='exos_v2_ledger_score'
              and rp.grantee='service_role'
              and rp.privilege_type='EXECUTE'
        ) then 'granted' else 'missing' end,
        case when exists (
            select 1 from information_schema.routine_privileges rp
            where rp.specific_schema='public'
              and rp.routine_name='exos_v2_ledger_score'
              and rp.grantee='service_role'
              and rp.privilege_type='EXECUTE'
        ) then 'PASS' else 'FAIL' end

    union all

    select
        'function exec grant: exos_v2_ledger_credit -> service_role',
        'EXECUTE granted',
        case when exists (
            select 1 from information_schema.routine_privileges rp
            where rp.specific_schema='public'
              and rp.routine_name='exos_v2_ledger_credit'
              and rp.grantee='service_role'
              and rp.privilege_type='EXECUTE'
        ) then 'granted' else 'missing' end,
        case when exists (
            select 1 from information_schema.routine_privileges rp
            where rp.specific_schema='public'
              and rp.routine_name='exos_v2_ledger_credit'
              and rp.grantee='service_role'
              and rp.privilege_type='EXECUTE'
        ) then 'PASS' else 'FAIL' end

    union all

    select
        'legacy contamination: ' || l.table_name,
        'absent',
        case when exists (select 1 from information_schema.tables t where t.table_schema='public' and t.table_name=l.table_name)
            then 'present' else 'absent' end,
        case when not exists (select 1 from information_schema.tables t where t.table_schema='public' and t.table_name=l.table_name)
            then 'PASS' else 'FAIL' end
    from legacy_tables l

    union all

    select
        'hierarchy FK ' || fk.fk_check,
        'FOREIGN KEY exists',
        case
            when fk.fk_check = 'programmes_v2.event_id -> events_v2.event_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='programmes_v2' and cr.relname='events_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'modules_v2.programme_id -> programmes_v2.programme_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='modules_v2' and cr.relname='programmes_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(programme_id) REFERENCES public.programmes_v2(programme_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'activities_v2.module_id -> modules_v2.module_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='activities_v2' and cr.relname='modules_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(module_id) REFERENCES public.modules_v2(module_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'activities_v2.programme_id -> programmes_v2.programme_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='activities_v2' and cr.relname='programmes_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(programme_id) REFERENCES public.programmes_v2(programme_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'teams_v2.event_id -> events_v2.event_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='teams_v2' and cr.relname='events_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'participants_v2.event_id -> events_v2.event_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='participants_v2' and cr.relname='events_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'participants_v2.team_id -> teams_v2.team_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='participants_v2' and cr.relname='teams_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(team_id) REFERENCES public.teams_v2(team_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'participant_sessions_v2.event_id -> events_v2.event_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='participant_sessions_v2' and cr.relname='events_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'participant_sessions_v2.participant_id -> participants_v2.participant_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='participant_sessions_v2' and cr.relname='participants_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(participant_id) REFERENCES public.participants_v2(participant_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'submissions_v2.event_id -> events_v2.event_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='submissions_v2' and cr.relname='events_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'submissions_v2.team_id -> teams_v2.team_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='submissions_v2' and cr.relname='teams_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(team_id) REFERENCES public.teams_v2(team_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'submissions_v2.participant_id -> participants_v2.participant_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='submissions_v2' and cr.relname='participants_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(participant_id) REFERENCES public.participants_v2(participant_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'submissions_v2.activity_id -> activities_v2.activity_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='submissions_v2' and cr.relname='activities_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(activity_id) REFERENCES public.activities_v2(activity_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'score_transactions_v2.event_id -> events_v2.event_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='score_transactions_v2' and cr.relname='events_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'score_transactions_v2.team_id -> teams_v2.team_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='score_transactions_v2' and cr.relname='teams_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(team_id) REFERENCES public.teams_v2(team_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'credit_transactions_v2.event_id -> events_v2.event_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='credit_transactions_v2' and cr.relname='events_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'credit_transactions_v2.team_id -> teams_v2.team_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='credit_transactions_v2' and cr.relname='teams_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(team_id) REFERENCES public.teams_v2(team_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'marketplace_transactions_v2.event_id -> events_v2.event_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='marketplace_transactions_v2' and cr.relname='events_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
                ) then 'present' else 'missing' end
            when fk.fk_check = 'marketplace_transactions_v2.team_id -> teams_v2.team_id' then
                case when exists (
                    select 1
                    from pg_constraint c
                    join pg_class cl on cl.oid=c.conrelid
                    join pg_namespace n on n.oid=cl.relnamespace
                    join pg_class cr on cr.oid=c.confrelid
                    where n.nspname='public' and cl.relname='marketplace_transactions_v2' and cr.relname='teams_v2'
                      and c.contype='f' and pg_get_constraintdef(c.oid) like '%(team_id) REFERENCES public.teams_v2(team_id)%'
                ) then 'present' else 'missing' end
            else 'unsupported-check'
        end as actual,
        case
            when fk.fk_check like 'programmes_v2.event_id -> events_v2.event_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='programmes_v2' and cr.relname='events_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
            ) then 'PASS'
            when fk.fk_check like 'modules_v2.programme_id -> programmes_v2.programme_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='modules_v2' and cr.relname='programmes_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(programme_id) REFERENCES public.programmes_v2(programme_id)%'
            ) then 'PASS'
            when fk.fk_check like 'activities_v2.module_id -> modules_v2.module_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='activities_v2' and cr.relname='modules_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(module_id) REFERENCES public.modules_v2(module_id)%'
            ) then 'PASS'
            when fk.fk_check like 'activities_v2.programme_id -> programmes_v2.programme_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='activities_v2' and cr.relname='programmes_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(programme_id) REFERENCES public.programmes_v2(programme_id)%'
            ) then 'PASS'
            when fk.fk_check like 'teams_v2.event_id -> events_v2.event_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='teams_v2' and cr.relname='events_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
            ) then 'PASS'
            when fk.fk_check like 'participants_v2.event_id -> events_v2.event_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='participants_v2' and cr.relname='events_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
            ) then 'PASS'
            when fk.fk_check like 'participants_v2.team_id -> teams_v2.team_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='participants_v2' and cr.relname='teams_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(team_id) REFERENCES public.teams_v2(team_id)%'
            ) then 'PASS'
            when fk.fk_check like 'participant_sessions_v2.event_id -> events_v2.event_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='participant_sessions_v2' and cr.relname='events_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
            ) then 'PASS'
            when fk.fk_check like 'participant_sessions_v2.participant_id -> participants_v2.participant_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='participant_sessions_v2' and cr.relname='participants_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(participant_id) REFERENCES public.participants_v2(participant_id)%'
            ) then 'PASS'
            when fk.fk_check like 'submissions_v2.event_id -> events_v2.event_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='submissions_v2' and cr.relname='events_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
            ) then 'PASS'
            when fk.fk_check like 'submissions_v2.team_id -> teams_v2.team_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='submissions_v2' and cr.relname='teams_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(team_id) REFERENCES public.teams_v2(team_id)%'
            ) then 'PASS'
            when fk.fk_check like 'submissions_v2.participant_id -> participants_v2.participant_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='submissions_v2' and cr.relname='participants_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(participant_id) REFERENCES public.participants_v2(participant_id)%'
            ) then 'PASS'
            when fk.fk_check like 'submissions_v2.activity_id -> activities_v2.activity_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='submissions_v2' and cr.relname='activities_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(activity_id) REFERENCES public.activities_v2(activity_id)%'
            ) then 'PASS'
            when fk.fk_check like 'score_transactions_v2.event_id -> events_v2.event_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='score_transactions_v2' and cr.relname='events_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
            ) then 'PASS'
            when fk.fk_check like 'score_transactions_v2.team_id -> teams_v2.team_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='score_transactions_v2' and cr.relname='teams_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(team_id) REFERENCES public.teams_v2(team_id)%'
            ) then 'PASS'
            when fk.fk_check like 'credit_transactions_v2.event_id -> events_v2.event_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='credit_transactions_v2' and cr.relname='events_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
            ) then 'PASS'
            when fk.fk_check like 'credit_transactions_v2.team_id -> teams_v2.team_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='credit_transactions_v2' and cr.relname='teams_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(team_id) REFERENCES public.teams_v2(team_id)%'
            ) then 'PASS'
            when fk.fk_check like 'marketplace_transactions_v2.event_id -> events_v2.event_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='marketplace_transactions_v2' and cr.relname='events_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(event_id) REFERENCES public.events_v2(event_id)%'
            ) then 'PASS'
            when fk.fk_check like 'marketplace_transactions_v2.team_id -> teams_v2.team_id' and exists (
                select 1
                from pg_constraint c
                join pg_class cl on cl.oid=c.conrelid
                join pg_namespace n on n.oid=cl.relnamespace
                join pg_class cr on cr.oid=c.confrelid
                where n.nspname='public' and cl.relname='marketplace_transactions_v2' and cr.relname='teams_v2'
                  and c.contype='f' and pg_get_constraintdef(c.oid) like '%(team_id) REFERENCES public.teams_v2(team_id)%'
            ) then 'PASS'
            else 'FAIL'
        end as pass
    from required_fk_checks fk
)

select check_name as "CHECK", expected as "EXPECTED", actual as "ACTUAL", pass as "PASS"
from checks

union all

select
    'FAILED CHECK COUNT',
    'number of rows where PASS = FAIL',
    count(*) filter (where pass = 'FAIL')::text,
    case when count(*) filter (where pass='FAIL') = 0 then 'PASS' else 'FAIL' end
from checks;
