-- Read-only post-install verification for 051.  Run against the dedicated
-- target after owner-authorised installation; this script makes no mutations.
SELECT table_name FROM information_schema.tables
 WHERE table_schema = 'public' AND table_name IN ('event_hunt_configurations_v2', 'event_hunt_missions_v2',
 'hunt_team_mission_runtime_v2', 'hunt_scoring_snapshots_v2', 'hunt_score_adjustments_v2') ORDER BY table_name;
SELECT routine_name FROM information_schema.routines
 WHERE routine_schema = 'public' AND routine_name IN ('exos_v2_hunt_participant_workspace', 'exos_v2_hunt_submit_mission',
 'exos_v2_hunt_review_submission', 'exos_v2_hunt_operator_snapshot', 'exos_v2_hunt_public_projector_projection') ORDER BY routine_name;
SELECT grantee, routine_name FROM information_schema.role_routine_grants
 WHERE specific_schema = 'public' AND routine_name IN ('exos_v2_hunt_operator_snapshot', 'exos_v2_hunt_public_projector_projection')
 ORDER BY routine_name, grantee;
-- Expected: only the public projector projection is granted to anon/authenticated.
