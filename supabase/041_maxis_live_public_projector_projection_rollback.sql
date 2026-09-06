-- Rollback for 041_maxis_live_public_projector_projection.sql.
-- This removes only the presentation RPC.  It never alters event/runtime,
-- team, participant, submission, score, evidence or audit data.
BEGIN;

DROP FUNCTION IF EXISTS public.exos_v2_maxis_live_projector_projection();

COMMIT;
