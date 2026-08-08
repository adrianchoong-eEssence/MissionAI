-- READ ONLY: run after a non-destructive migration in local/staging.
select 'orphan_team' as check_name, t.event_id, t.team_id from public.runtime_teams t left join public.runtime_events e on e.event_id=t.event_id where e.event_id is null;
select 'orphan_participant' as check_name, p.participant_id, p.event_id from public.runtime_participants p left join public.runtime_events e on e.event_id=p.event_id where e.event_id is null;
select 'orphan_submission' as check_name, s.submission_id, s.event_id from public.runtime_submissions s left join public.runtime_events e on e.event_id=s.event_id where e.event_id is null;
select 'duplicate_event_team_id' as check_name, event_id, team_id, count(*) from public.runtime_teams group by event_id, team_id having count(*) > 1;
select 'duplicate_event_participant_identity' as check_name, event_id, normalized_name, count(*) from public.runtime_participants where merged_into_participant_id is null group by event_id, normalized_name having count(*) > 1;
select 'unpublished_runtime_mission' as check_name, m.event_id, m.mission_id from public.runtime_missions m left join public.runtime_events e on e.event_id=m.event_id where e.event_id is null;
select 'publication_without_teams' as check_name, e.event_id from public.runtime_events e left join public.runtime_teams t on t.event_id=e.event_id group by e.event_id having count(t.team_id)=0;
select 'cross_event_submission_team' as check_name, s.submission_id, s.event_id, s.team_name from public.runtime_submissions s left join public.runtime_teams t on t.event_id=s.event_id and t.team_name=s.team_name where s.team_name <> '' and t.team_id is null;
