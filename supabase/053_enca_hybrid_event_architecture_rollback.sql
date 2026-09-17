-- Guarded rollback companion for 053. It refuses to remove any configured
-- competition stage or hybrid event. Execute only after a verified empty
-- disposable target gate; 053 installs no production fixture by itself.
BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.event_competition_stages_v2)
       OR EXISTS (SELECT 1 FROM public.events_v2
                  WHERE event_payload #>> '{TeamFormation,Mode}' = 'HYBRID_ANCHORED')
       OR EXISTS (SELECT 1 FROM public.event_location_configurations_v2
                  WHERE participant_visibility_mode <> 'OFF') THEN
        RAISE EXCEPTION '053 rollback refused: competition-stage, hybrid event, or participant visibility data exists.';
    END IF;
END $$;
DROP TRIGGER IF EXISTS exos_v2_hunt_submission_competition_stage_guard_trg ON public.submissions_v2;
DROP FUNCTION IF EXISTS public.exos_v2_hybrid_anchored_hunt_workspace(text);
DROP FUNCTION IF EXISTS public.exos_v2_hunt_submission_competition_stage_guard();
DROP FUNCTION IF EXISTS public.exos_v2_other_team_leader_locations(text);
DROP FUNCTION IF EXISTS public.exos_v2_set_participant_location_visibility(text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_competition_public_projector_projection(text);
DROP FUNCTION IF EXISTS public.exos_v2_competition_stage_snapshot(text);
DROP FUNCTION IF EXISTS public.exos_v2_record_competition_stage_score(text,text,text,numeric,text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_set_competition_stage_state(text,text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_upsert_competition_stage(text,text,integer,text,text,boolean,text,boolean,jsonb,text);
DROP FUNCTION IF EXISTS public.exos_v2_hybrid_anchored_operator_roster(text);
DROP FUNCTION IF EXISTS public.exos_v2_hybrid_anchored_claim_personal_key(text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_hybrid_anchored_register_random(text,text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_open_hybrid_anchored_team_formation(text,text);
DROP FUNCTION IF EXISTS public.exos_v2_configure_hybrid_anchored_team_formation(text,jsonb,jsonb,text);
DROP TABLE IF EXISTS public.event_competition_stages_v2;
ALTER TABLE public.event_location_configurations_v2 DROP CONSTRAINT IF EXISTS event_location_configurations_v2_participant_visibility_mode_ck;
ALTER TABLE public.event_location_configurations_v2 DROP COLUMN IF EXISTS participant_visibility_mode;
COMMIT;
