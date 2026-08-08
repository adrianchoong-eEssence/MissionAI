-- READ ONLY: EXOS Core v2 schema preflight.
-- Fails only by returning rows for an operator to investigate.
select 'required_extensions' as check_name, extname
from (values ('pgcrypto'),('pg_trgm')) required(extname)
where not exists (select 1 from pg_extension e where e.extname=required.extname);

select 'required_tables' as check_name, table_name
from (values
    ('events_v2'),('programmes_v2'),('modules_v2'),('activities_v2'),('teams_v2'),
    ('participants_v2'),('participant_sessions_v2'),('activity_runtime_v2'),
    ('submissions_v2'),('submission_evidence_v2'),('reviews_v2'),
    ('score_transactions_v2'),('credit_transactions_v2'),('marketplace_items_v2'),
    ('marketplace_transactions_v2'),('build_status_v2'),('judging_scores_v2'),
    ('race_results_v2'),('projector_state_v2'),('location_checkpoints_v2'),
    ('location_evidence_v2'),('ai_jobs_v2'),('ai_results_v2'),('audit_log_v2')
) required(table_name)
where not exists (select 1 from information_schema.tables t where t.table_schema='public' and t.table_name=required.table_name);

select 'required_rpcs' as check_name, routine_name
from (values
    ('exos_v2_publish_event'),('exos_v2_join_event_v2'),('exos_v2_restore_join'),
    ('exos_v2_ledger_score'),('exos_v2_ledger_credit')
) required(routine_name)
where not exists (select 1 from information_schema.routines r where r.routine_schema='public' and r.routine_name=required.routine_name);

select 'duplicate_participant_event_team' as check_name, event_id, participant_id, count(*)
from public.participants_v2
group by event_id, participant_id
having count(*) > 1;

select 'missing_event_in_teams' as check_name, team_id, event_id
from public.teams_v2 t
left join public.events_v2 e on e.event_id=t.event_id
where e.event_id is null;

select 'missing_team_in_participants' as check_name, participant_id, event_id, team_id
from public.participants_v2 p
left join public.teams_v2 t on t.team_id=p.team_id and t.event_id=p.event_id
where t.team_id is null;

select 'submission_cross_event_team' as check_name, s.submission_id, s.event_id, s.team_id
from public.submissions_v2 s
left join public.teams_v2 t on t.team_id=s.team_id
where t.event_id is null or t.event_id <> s.event_id;

select 'noncompetitive_tx_in_scoreboard_path' as check_name, score_transaction_id, scoring_mode
from public.score_transactions_v2
where scoring_mode <> 'TEAM_COMPETITIVE';
