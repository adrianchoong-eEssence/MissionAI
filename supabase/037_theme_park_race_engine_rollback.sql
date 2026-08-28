-- Guarded rollback companion to 037_theme_park_race_engine.sql.
-- This intentionally refuses to remove the server guard while any configured
-- Theme Park Race event exists. It does not delete events, teams,
-- participants, submissions, evidence, reviews or ledger history.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM public.events_v2
         WHERE upper(coalesce(event_payload #>> '{RaceConfiguration,EngineKind}', '')) = 'THEME_PARK_RACE'
    ) THEN
        RAISE EXCEPTION 'Rollback blocked: Theme Park Race event configuration still exists';
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_theme_park_race_submission_guard_trg
    ON public.submissions_v2;
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_submission_guard();
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_submit(text,text,jsonb);
DROP FUNCTION IF EXISTS public.exos_v2_set_theme_park_race_runtime_phase(text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_save_configuration(text,jsonb,text);

COMMIT;
