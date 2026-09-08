-- Guarded rollback for 044_post_maxis_p0_live_operations.sql.
--
-- This rollback is data-preserving.  It never deletes or rewrites events,
-- participants, teams, attendance, submissions, reviews, score transactions,
-- Captain sessions, or audit history.  It refuses to remove a contract once
-- its immutable history exists, or once attendance-enabled Captain eligibility
-- could be reinterpreted for a live Theme Park Race event.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM public.score_transactions_v2 s
         WHERE s.source_reference ->> 'Contract' = 'THEME_PARK_RACE_LIVE_OPERATIONS_044'
            OR s.source_reference ->> 'Operation' = 'TEAM_SCORE_ADJUSTMENT'
    )
       OR EXISTS (
           SELECT 1 FROM public.audit_log_v2
            WHERE action = 'TEAM_FORMATION_CAPTAIN_CLEARED'
       )
       OR EXISTS (
           SELECT 1 FROM public.events_v2 e
            WHERE upper(coalesce(e.event_payload #>> '{RaceConfiguration,EngineKind}', '')) = 'THEME_PARK_RACE'
              AND coalesce(e.event_payload #>> '{Attendance,SchemaVersion}', '') = '1'
       ) THEN
        RAISE EXCEPTION
            '044 rollback refused: live-operation ledger/audit history or attendance-enabled Theme Park Captain eligibility exists and must not be reinterpreted';
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_team_formation_captain_attendance_guard_trg
    ON public.participants_v2;
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_operator_status(text);
DROP FUNCTION IF EXISTS public.exos_v2_clear_team_formation_captain(text,text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_score_adjustments(text,integer);
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_adjust_team_score(text,text,numeric,text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_team_formation_captain_attendance_guard();

COMMIT;
