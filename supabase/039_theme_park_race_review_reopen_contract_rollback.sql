-- Guarded rollback for 039. It never deletes operational data.
BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.audit_log_v2 WHERE action = 'THEME_PARK_RACE_BOARD_REVIEWED')
       OR EXISTS (SELECT 1 FROM public.score_transactions_v2 WHERE source_reference @> '{"Contract":"THEME_PARK_RACE_BOARD_REVIEW_039"}'::jsonb) THEN
        RAISE EXCEPTION 'Rollback blocked: Theme Park Race board review/reopen state exists';
    END IF;
END;
$$;
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_board_review(uuid,timestamptz,public.exos_v2_review_decision,numeric,text,text,text);
COMMIT;
