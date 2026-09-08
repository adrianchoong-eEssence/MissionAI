-- P0-C concurrency assertions and exact fixture cleanup.
BEGIN;

DO $$
BEGIN
    IF (SELECT count(*) FROM public.score_transactions_v2
         WHERE event_id='CERT-P0C-CONC-20260908'
           AND source_reference ->> 'Operation'='TEAM_SCORE_ADJUSTMENT'
           AND source_reference ->> 'RequestIdempotencyKey'='CERT-P0C-CONC-DUP') <> 1 THEN
        RAISE EXCEPTION 'duplicate adjustment request created more than one canonical ledger transaction';
    END IF;
    IF (SELECT count(*) FROM public.score_transactions_v2
         WHERE event_id='CERT-P0C-CONC-20260908'
           AND source_reference ->> 'Operation'='TEAM_SCORE_ADJUSTMENT') <> 3 THEN
        RAISE EXCEPTION 'concurrent distinct adjustments did not preserve exactly three ledger entries';
    END IF;
    IF (SELECT count(*) FROM public.participants_v2
         WHERE event_id='CERT-P0C-CONC-20260908' AND team_id='CERT-P0C-CONC-20260908-A'
           AND is_team_formation_captain) > 1
       OR (SELECT count(*) FROM public.team_access_sessions_v2
           WHERE event_id='CERT-P0C-CONC-20260908' AND team_id='CERT-P0C-CONC-20260908-A'
             AND is_active AND team_formation_captain_participant_id IS NOT NULL) > 1 THEN
        RAISE EXCEPTION 'concurrent clear/claim created dual Captain authority';
    END IF;
END;
$$;

SELECT set_config('exos.attendance_mutation','v1',true);
SELECT set_config('exos.team_formation_write','CERT-P0C-CONC-20260908',true);
DELETE FROM public.score_transactions_v2 WHERE event_id='CERT-P0C-CONC-20260908';
DELETE FROM public.participant_attendance_v2 WHERE event_id='CERT-P0C-CONC-20260908';
DELETE FROM public.team_access_sessions_v2 WHERE event_id='CERT-P0C-CONC-20260908';
DELETE FROM public.team_access_credentials_v2 WHERE event_id='CERT-P0C-CONC-20260908';
DELETE FROM public.participant_sessions_v2 WHERE event_id='CERT-P0C-CONC-20260908';
DELETE FROM public.participants_v2 WHERE event_id='CERT-P0C-CONC-20260908';
DELETE FROM public.teams_v2 WHERE event_id='CERT-P0C-CONC-20260908';
DELETE FROM public.audit_log_v2 WHERE event_id='CERT-P0C-CONC-20260908';
DELETE FROM public.events_v2 WHERE event_id='CERT-P0C-CONC-20260908';
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id='CERT-P0C-CONC-20260908')
       OR EXISTS (SELECT 1 FROM public.audit_log_v2 WHERE event_id='CERT-P0C-CONC-20260908') THEN
        RAISE EXCEPTION 'CERT-P0C concurrency cleanup residue remains';
    END IF;
END;
$$;
COMMIT;
