-- Read-only post-install verification for authorised staging only.
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'
  AND table_name IN ('event_competition_stages_v2', 'event_location_configurations_v2') ORDER BY table_name;
SELECT column_name, column_default, is_nullable FROM information_schema.columns
 WHERE table_schema = 'public' AND table_name = 'event_location_configurations_v2'
   AND column_name = 'participant_visibility_mode';
SELECT routine_name FROM information_schema.routines WHERE routine_schema = 'public'
  AND routine_name IN ('exos_v2_configure_hybrid_anchored_team_formation',
    'exos_v2_hybrid_anchored_register_random', 'exos_v2_hybrid_anchored_claim_personal_key',
    'exos_v2_competition_stage_snapshot', 'exos_v2_other_team_leader_locations',
    'exos_v2_competition_public_projector_projection') ORDER BY routine_name;
SELECT grantee, routine_name FROM information_schema.role_routine_grants
 WHERE specific_schema = 'public' AND routine_name IN ('exos_v2_hybrid_anchored_register_random',
   'exos_v2_hybrid_anchored_claim_personal_key', 'exos_v2_other_team_leader_locations',
   'exos_v2_competition_public_projector_projection') ORDER BY routine_name, grantee;
-- Expected: only the explicit participant-safe and public projection RPCs are
-- granted to anon/authenticated; service operations remain service_role-only.
