-- Guarded rollback for 042_post_maxis_p0_attendance.sql.
-- It never deletes attendance, audit, participant, team or event history.
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.participant_attendance_v2)
       OR EXISTS (
           SELECT 1
             FROM public.events_v2
            WHERE coalesce(event_payload #>> '{Attendance,SchemaVersion}', '') = '1'
       )
       OR EXISTS (
           SELECT 1
             FROM public.audit_log_v2
            WHERE action IN ('ATTENDANCE_CONFIGURED', 'PARTICIPANT_ATTENDANCE_CHANGED')
       ) THEN
        RAISE EXCEPTION
            '042 rollback refused: attendance configuration, state, or audit history exists and must not be reinterpreted';
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_participant_attendance_write_guard
    ON public.participant_attendance_v2;
DROP FUNCTION IF EXISTS public.exos_v2_attendance_roster(text);
DROP FUNCTION IF EXISTS public.exos_v2_attendance_summary(text);
DROP FUNCTION IF EXISTS public.exos_v2_set_participant_attendance(text, uuid, text, text, text);
DROP FUNCTION IF EXISTS public.exos_v2_configure_attendance(text, text);
DROP FUNCTION IF EXISTS public.exos_v2_participant_attendance_write_guard();
DROP TABLE IF EXISTS public.participant_attendance_v2;

COMMIT;
