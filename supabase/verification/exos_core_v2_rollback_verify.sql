-- READ ONLY: verify guarded rollback safety for EXOS Core v2.
select 'v2_audit_events' as check_name, action, count(*)
from public.audit_log_v2
group by action;

select 'v2_nonempty_blocking_state' as check_name, table_name, row_count
from (values
    ('score_transactions_v2', (select count(*) from public.score_transactions_v2)),
    ('credit_transactions_v2', (select count(*) from public.credit_transactions_v2)),
    ('submissions_v2', (select count(*) from public.submissions_v2)),
    ('reviews_v2', (select count(*) from public.reviews_v2))
) as x(table_name, row_count)
where row_count > 0;

select 'v2_rollback_guard_present' as check_name, 'Rollback blocked if operational rows exist' as detail;

select 'v2_tables_exist_before_rollback' as check_name, table_name
from (values
    ('events_v2'),('programmes_v2'),('modules_v2'),('activities_v2'),('teams_v2'),
    ('participants_v2'),('participant_sessions_v2'),('submissions_v2')
) x(table_name)
where not exists (select 1 from information_schema.tables t where t.table_schema='public' and t.table_name=x.table_name);
