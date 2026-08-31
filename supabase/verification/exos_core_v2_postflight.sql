-- READ ONLY: EXOS Core v2 schema postflight (run after non-destructive migration validation).
select 'orphan_team' as check_name, t.team_id, t.event_id
from public.teams_v2 t
left join public.events_v2 e on e.event_id=t.event_id
where e.event_id is null;

select 'orphan_participant' as check_name, p.participant_id, p.event_id
from public.participants_v2 p
left join public.events_v2 e on e.event_id=p.event_id
where e.event_id is null;

select 'orphan_participant_session' as check_name, s.participant_session_id, s.participant_id
from public.participant_sessions_v2 s
left join public.participants_v2 p on p.participant_id=s.participant_id
where p.participant_id is null;

select 'orphan_submission' as check_name, s.submission_id, s.event_id
from public.submissions_v2 s
left join public.participants_v2 p on p.participant_id=s.participant_id
where p.participant_id is null;

select 'orphan_review_submission' as check_name, r.review_id, r.submission_id
from public.reviews_v2 r
left join public.submissions_v2 s on s.submission_id=r.submission_id
where s.submission_id is null;

select 'race_lock_violations' as check_name, race_result_id, locked
from public.race_results_v2
where locked is true and result_payload is null;

select 'gcp_keyed_checkpoint_invariants' as check_name, location_evidence_id, verification_status
from public.location_evidence_v2
where latitude is null or longitude is null or captured_at is null;

select 'ai_result_without_job' as check_name, ai_result_id, ar.ai_job_id
from public.ai_results_v2 ar
left join public.ai_jobs_v2 aj on aj.ai_job_id=ar.ai_job_id
where aj.ai_job_id is null;
