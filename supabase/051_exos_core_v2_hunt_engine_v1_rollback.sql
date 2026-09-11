-- Guarded rollback companion for 051.  It intentionally refuses to erase any
-- Hunt data.  Execute only after an owner verifies the dedicated target has no
-- Hunt configuration, mission, runtime, submission, snapshot, or adjustment rows.
BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.event_hunt_configurations_v2)
       OR EXISTS (SELECT 1 FROM public.event_hunt_missions_v2)
       OR EXISTS (SELECT 1 FROM public.hunt_team_checkpoint_routes_v2)
       OR EXISTS (SELECT 1 FROM public.hunt_team_mission_runtime_v2)
       OR EXISTS (SELECT 1 FROM public.hunt_scoring_snapshots_v2)
       OR EXISTS (SELECT 1 FROM public.hunt_score_adjustments_v2) THEN
        RAISE EXCEPTION '051 rollback refused: Hunt data exists. Restore a verified backup or remove only owner-approved disposable data first.';
    END IF;
END $$;
DROP FUNCTION IF EXISTS public.exos_v2_hunt_public_projector_projection(text);
DROP FUNCTION IF EXISTS public.exos_v2_hunt_operator_snapshot(text);
DROP FUNCTION IF EXISTS public.exos_v2_hunt_adjust_score(text,text,numeric,text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_hunt_review_submission(uuid,timestamptz,text,jsonb,text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_hunt_submit_mission(text,text,jsonb,jsonb,jsonb);
DROP FUNCTION IF EXISTS public.exos_v2_hunt_participant_workspace(text);
DROP FUNCTION IF EXISTS public.exos_v2_hunt_register_random(text,text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_save_hunt_team_route(text,text,jsonb,text);
DROP FUNCTION IF EXISTS public.exos_v2_set_hunt_mission_availability(text,text,text,boolean,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_upsert_hunt_mission(text,text,text,text,text,text,text,text,numeric,text,jsonb,boolean,boolean,jsonb,text);
DROP FUNCTION IF EXISTS public.exos_v2_upsert_hunt_checkpoint(text,text,text,numeric,numeric,numeric,boolean,text);
DROP FUNCTION IF EXISTS public.exos_v2_set_hunt_operational_state(text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_set_hunt_projector_visibility(text,boolean,text);
DROP FUNCTION IF EXISTS public.exos_v2_configure_hunt(text,text,text,timestamptz,timestamptz,timestamptz,timestamptz,text);
DROP TABLE IF EXISTS public.hunt_score_adjustments_v2;
DROP TABLE IF EXISTS public.hunt_scoring_snapshots_v2;
DROP TABLE IF EXISTS public.hunt_team_mission_runtime_v2;
DROP TABLE IF EXISTS public.event_hunt_missions_v2;
DROP TABLE IF EXISTS public.hunt_team_checkpoint_routes_v2;
DROP TABLE IF EXISTS public.event_hunt_configurations_v2;
COMMIT;
