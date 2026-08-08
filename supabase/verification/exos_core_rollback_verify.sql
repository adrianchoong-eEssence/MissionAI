-- READ ONLY: verify a guarded rollback did not orphan published runtime data.
select 'runtime_event_count' as check_name, count(*) as value from public.runtime_events;
select 'identity_without_team' as check_name, p.participant_id, p.event_id from public.runtime_participants p left join public.runtime_teams t on t.event_id=p.event_id and t.team_id=p.team_id where p.team_id is not null and t.team_id is null;
select 'submission_without_identity' as check_name, s.submission_id, s.event_id from public.runtime_submissions s left join public.runtime_events e on e.event_id=s.event_id where e.event_id is null;
select 'non_guarded_rollback' as check_name, routine_name from information_schema.routines where routine_schema='public' and routine_name in ('exos_join_event_v2','exos_publish_event');
