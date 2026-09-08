-- P0-B concurrency assertion and exact fixture cleanup.
-- Run after two concurrent submit calls, one concurrent attendance correction,
-- and two concurrent review calls described in the certification runner.
BEGIN;

DO $$
DECLARE
    v_snapshot public.theme_park_race_scoring_snapshots_v2%rowtype;
    v_submission public.submissions_v2%rowtype;
BEGIN
    SELECT * INTO v_submission FROM public.submissions_v2
     WHERE event_id = 'CERT-P0B-CONC-20260908';
    SELECT * INTO v_snapshot FROM public.theme_park_race_scoring_snapshots_v2
     WHERE event_id = 'CERT-P0B-CONC-20260908';
    IF NOT FOUND OR v_snapshot.scoring_mode <> 'PARTICIPATION_PRORATED'
       OR v_snapshot.present_team_size NOT IN (2, 3)
       OR v_snapshot.participants_completing <> 2
       OR v_snapshot.eligible_score NOT IN (67, 101)
       OR jsonb_array_length(v_snapshot.completing_participant_ids) <> 2 THEN
        RAISE EXCEPTION 'concurrent submission/attendance snapshot is not a canonical serial outcome';
    END IF;
    IF v_submission.submission_status <> 'APPROVED'
       OR v_submission.score <> v_snapshot.eligible_score
       OR (SELECT count(*) FROM public.score_transactions_v2
            WHERE submission_id = v_submission.submission_id AND score_delta > 0) <> 1 THEN
        RAISE EXCEPTION 'concurrent review did not produce exactly one immutable competitive score';
    END IF;
END;
$$;

SELECT set_config('exos.tpr_scoring_snapshot_write', 'v1', true);
SELECT set_config('exos.attendance_mutation', 'v1', true);
SELECT set_config('exos.team_formation_write', 'CERT-P0B-CONC-20260908', true);
DELETE FROM public.theme_park_race_scoring_snapshots_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.score_transactions_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.reviews_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.submissions_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.activity_runtime_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.participant_attendance_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.team_access_sessions_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.team_access_credentials_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.participant_sessions_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.participants_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.activities_v2 WHERE programme_id = 'CERT-P0B-CONC-20260908-PROGRAMME';
DELETE FROM public.modules_v2 WHERE programme_id = 'CERT-P0B-CONC-20260908-PROGRAMME';
DELETE FROM public.programmes_v2 WHERE programme_id = 'CERT-P0B-CONC-20260908-PROGRAMME';
DELETE FROM public.teams_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.audit_log_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';
DELETE FROM public.events_v2 WHERE event_id = 'CERT-P0B-CONC-20260908';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = 'CERT-P0B-CONC-20260908')
       OR EXISTS (SELECT 1 FROM public.theme_park_race_scoring_snapshots_v2 WHERE event_id = 'CERT-P0B-CONC-20260908') THEN
        RAISE EXCEPTION 'CERT-P0B concurrency cleanup residue remains';
    END IF;
END;
$$;

COMMIT;
