-- Read-only post-install verifier for 036_exos_core_v2_team_formation_v1.sql.
-- Run only after Kai has reviewed and applied the forward migration to a
-- disposable/non-protected target. It performs no DML and creates no fixture.

BEGIN READ ONLY;

SELECT c.table_name,
       c.column_name,
       c.is_nullable,
       c.data_type
  FROM information_schema.columns c
 WHERE c.table_schema = 'public'
   AND (
       (c.table_name = 'teams_v2' AND c.column_name = 'team_capacity')
       OR (c.table_name = 'participants_v2' AND c.column_name IN (
           'enrollment_credential_hash', 'is_team_formation_captain'
       ))
       OR (c.table_name = 'team_access_sessions_v2'
           AND c.column_name = 'team_formation_captain_participant_id')
   )
 ORDER BY c.table_name, c.column_name;

SELECT conrelid::regclass::text AS table_name,
       conname,
       contype,
       convalidated,
       pg_get_constraintdef(oid) AS definition
  FROM pg_constraint
 WHERE conname IN (
       'teams_v2_team_capacity_positive',
       'participants_v2_enrollment_credential_hash_format',
       'participants_v2_event_team_tf_fkey',
       'participant_sessions_v2_event_participant_tf_fkey',
       'team_access_credentials_v2_event_team_tf_fkey',
       'team_access_sessions_v2_event_team_tf_fkey',
       'team_access_sessions_v2_tf_captain_fkey'
   )
 ORDER BY conname;

SELECT indexrelid::regclass::text AS index_name,
       pg_get_indexdef(indexrelid) AS definition
  FROM pg_index
 WHERE indexrelid::regclass::text IN (
       'participants_v2_event_enrollment_credential_hash_active_uidx',
       'participants_v2_one_team_formation_captain_uidx',
       'team_access_sessions_v2_one_active_tf_captain_uidx',
       'participants_v2_team_formation_occupancy_idx'
   )
 ORDER BY indexrelid::regclass::text;

SELECT p.proname,
       pg_get_function_identity_arguments(p.oid) AS arguments,
       p.prosecdef AS security_definer,
       p.proconfig AS function_config
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public'
   AND p.proname IN (
       'exos_v2_configure_team_formation',
       'exos_v2_team_formation_credential_hash',
       'exos_v2_open_team_formation',
       'exos_v2_lock_team_formation',
       'exos_v2_open_team_captain_selection',
       'exos_v2_activate_team_formation',
       'exos_v2_team_formation_register_random',
       'exos_v2_team_formation_claim_preassigned',
       'exos_v2_recover_team_formation_participant',
       'exos_v2_claim_team_formation_captain',
       'exos_v2_recover_team_formation_captain',
       'exos_v2_transfer_team_formation_captain'
 )
 ORDER BY p.proname;

-- Show the effective explicit EXECUTE grantees so review can confirm that
-- facilitator operations remain service-role only and participant endpoints
-- are limited to the intended RPCs.
SELECT p.proname,
       coalesce(
           string_agg(
               coalesce(r.rolname, 'PUBLIC'),
               ', ' ORDER BY coalesce(r.rolname, 'PUBLIC')
           ) FILTER (WHERE acl.privilege_type = 'EXECUTE'),
           '(none)'
       ) AS execute_grantees
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  LEFT JOIN LATERAL aclexplode(
      coalesce(p.proacl, acldefault('f', p.proowner))
  ) AS acl ON true
  LEFT JOIN pg_roles r ON r.oid = acl.grantee
 WHERE n.nspname = 'public'
   AND p.proname IN (
       'exos_v2_configure_team_formation',
       'exos_v2_open_team_formation',
       'exos_v2_lock_team_formation',
       'exos_v2_open_team_captain_selection',
       'exos_v2_activate_team_formation',
       'exos_v2_team_formation_register_random',
       'exos_v2_team_formation_claim_preassigned',
       'exos_v2_recover_team_formation_participant',
       'exos_v2_claim_team_formation_captain',
       'exos_v2_recover_team_formation_captain',
       'exos_v2_transfer_team_formation_captain'
   )
 GROUP BY p.oid, p.proname
 ORDER BY p.proname;

-- Every Team Formation security-definer function must pin its search path.
-- This exposes a missing hardening control without mutating the target.
SELECT p.proname,
       p.proconfig,
       CASE
           WHEN p.prosecdef
            AND coalesce(array_to_string(p.proconfig, ','), '')
                LIKE '%search_path=%' THEN 'PINNED'
           WHEN p.prosecdef THEN 'MISSING_SEARCH_PATH_PIN'
           ELSE 'NOT_SECURITY_DEFINER'
       END AS search_path_status
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public'
   AND p.proname LIKE 'exos_v2%team%formation%'
 ORDER BY p.proname;

SELECT e.event_id,
       e.event_name,
       e.event_payload #>> '{TeamFormation,Mode}' AS mode,
       e.event_payload #>> '{TeamFormation,Phase}' AS phase,
       count(DISTINCT t.team_id) FILTER (WHERE t.is_active) AS active_teams,
       count(DISTINCT t.team_id) FILTER (
           WHERE t.is_active AND t.team_capacity IS NULL
       ) AS active_teams_missing_capacity,
       count(DISTINCT p.participant_id) FILTER (
           WHERE p.merged_into_participant_id IS NULL AND NOT p.is_archived
       ) AS canonical_participants,
       count(DISTINCT p.participant_id) FILTER (
           WHERE p.is_team_formation_captain
             AND p.merged_into_participant_id IS NULL
             AND NOT p.is_archived
       ) AS effective_captains
  FROM public.events_v2 e
  LEFT JOIN public.teams_v2 t ON t.event_id = e.event_id
  LEFT JOIN public.participants_v2 p ON p.event_id = e.event_id
 WHERE coalesce(e.event_payload #>> '{TeamFormation,SchemaVersion}', '') = '1'
 GROUP BY e.event_id, e.event_name, mode, phase
 ORDER BY e.event_id;

ROLLBACK;
