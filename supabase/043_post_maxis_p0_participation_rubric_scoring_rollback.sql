-- Guarded rollback for 043_post_maxis_p0_participation_rubric_scoring.sql.
--
-- This rollback is deliberately data-preserving.  It refuses to remove an
-- installed contract after an event has opted in, a score snapshot exists, or
-- a P0-B audit record exists.  It never deletes or rewrites event, team,
-- participant, submission, review, score, credit, or audit history.
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.theme_park_race_scoring_snapshots_v2)
       OR EXISTS (
           SELECT 1
             FROM public.activities_v2 a
             JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
            WHERE upper(coalesce(a.activity_payload #>> '{race_station,Scoring,Mode}', ''))
                  IN ('PARTICIPATION_PRORATED', 'FACILITATOR_RUBRIC')
       )
       OR EXISTS (
           SELECT 1 FROM public.audit_log_v2
            WHERE action IN (
                'THEME_PARK_RACE_PARTICIPATION_SUBMITTED',
                'THEME_PARK_RACE_SCORED_REVIEWED'
            )
       ) THEN
        RAISE EXCEPTION
            '043 rollback refused: configured scoring, immutable snapshots, or P0-B audit history exists and must not be reinterpreted';
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_theme_park_race_scored_review_guard_trg
    ON public.submissions_v2;
DROP TRIGGER IF EXISTS exos_v2_theme_park_race_scored_submission_guard_trg
    ON public.submissions_v2;
DROP TRIGGER IF EXISTS exos_v2_theme_park_race_scoring_snapshot_write_guard_trg
    ON public.theme_park_race_scoring_snapshots_v2;

DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_review_scored_submission(
    uuid, timestamptz, public.exos_v2_review_decision, jsonb, text, text, text
);
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_submit_participation(text, text, jsonb, jsonb);
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_participation_preview(text, text);
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_scored_review_guard();
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_scored_submission_guard();
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_scoring_snapshot_write_guard();
DROP TABLE IF EXISTS public.theme_park_race_scoring_snapshots_v2;

COMMIT;
