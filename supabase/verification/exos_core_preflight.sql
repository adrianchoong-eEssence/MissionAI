-- READ ONLY: execute against local/staging before any EXOS Core consolidation.
-- No DDL/DML. Fails only by returning rows for an operator to investigate.
select 'required_tables' as check_name, table_name
from (values ('runtime_events'),('runtime_teams'),('runtime_participants'),('runtime_missions'),('runtime_submissions'),('runtime_credit_transactions')) required(table_name)
where not exists (select 1 from information_schema.tables t where t.table_schema='public' and t.table_name=required.table_name);

select 'required_extensions' as check_name, extname
from (values ('pgcrypto')) required(extname)
where not exists (select 1 from pg_extension e where e.extname=required.extname);

select 'required_rpc' as check_name, routine_name
from (values ('exos_publish_event'),('exos_publish_programme'),('exos_join_event_v2'),('exos_restore_join')) required(routine_name)
where not exists (select 1 from information_schema.routines r where r.routine_schema='public' and r.routine_name=required.routine_name);

select 'duplicate_runtime_event_id' as check_name, event_id, count(*)
from public.runtime_events group by event_id having count(*) > 1;

select 'orphan_participant' as check_name, p.participant_id, p.event_id
from public.runtime_participants p left join public.runtime_events e on e.event_id=p.event_id where e.event_id is null;
