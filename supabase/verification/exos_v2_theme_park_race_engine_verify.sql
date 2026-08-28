-- Read-only verification for Theme Park Race engine migration 037.
-- Run only after confirming the target environment and migration history.
-- This script creates no fixtures and makes no mutation.
WITH expected(proname, exact_signature, expected_execute_grantees) AS (
    VALUES
        ('exos_v2_theme_park_race_save_configuration',
         'public.exos_v2_theme_park_race_save_configuration(text,jsonb,text)', ARRAY['service_role']::text[]),
        ('exos_v2_set_theme_park_race_runtime_phase',
         'public.exos_v2_set_theme_park_race_runtime_phase(text,text,text)', ARRAY['service_role']::text[]),
        ('exos_v2_theme_park_race_submit',
         'public.exos_v2_theme_park_race_submit(text,text,jsonb)', ARRAY['anon','authenticated','service_role']::text[]),
        ('exos_v2_theme_park_race_submission_guard',
         'public.exos_v2_theme_park_race_submission_guard()', ARRAY[]::text[])
), resolved AS (
    SELECT e.*, to_regprocedure(e.exact_signature) AS function_oid
      FROM expected e
)
SELECT
    exact_signature,
    function_oid IS NOT NULL AS exact_signature_present,
    coalesce((SELECT p.prosecdef FROM pg_proc p WHERE p.oid = function_oid), false) AS security_definer,
    coalesce((
        SELECT EXISTS (
            SELECT 1 FROM unnest(p.proconfig) AS setting(value)
             WHERE setting.value IN ('search_path=', 'search_path=""')
        ) FROM pg_proc p WHERE p.oid = function_oid
    ), false) AS search_path_pinned_to_empty,
    coalesce((
        SELECT array_agg(grant_role ORDER BY grant_role)
          FROM (
              SELECT DISTINCT role_name.rolname::text AS grant_role
                FROM pg_proc p
                CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) AS acl
                JOIN pg_roles role_name ON role_name.oid = acl.grantee
               WHERE p.oid = function_oid
                 AND acl.privilege_type = 'EXECUTE'
                 AND acl.grantee <> 0
                 AND acl.grantee <> p.proowner
          ) grants
    ), ARRAY[]::text[]) = expected_execute_grantees AS exact_execute_grants,
    NOT coalesce((
        SELECT bool_or(acl.grantee = 0 AND acl.privilege_type = 'EXECUTE')
          FROM pg_proc p
          CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) AS acl
         WHERE p.oid = function_oid
    ), false) AS public_execute_revoked,
    NOT EXISTS (
        SELECT 1
          FROM pg_proc p
          CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) AS acl
          JOIN pg_roles role_name ON role_name.oid = acl.grantee
         WHERE p.oid = function_oid
           AND acl.privilege_type = 'EXECUTE'
           AND role_name.rolname IN ('anon', 'authenticated')
           AND NOT (role_name.rolname::text = ANY(resolved.expected_execute_grantees))
    ) AS no_unintended_anon_authenticated_execute,
    (SELECT count(*) = 1
       FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'public' AND p.proname = resolved.proname) AS no_unexpected_overloads
FROM resolved
ORDER BY exact_signature;

SELECT
    t.tgname = 'exos_v2_theme_park_race_submission_guard_trg' AS trigger_present,
    t.tgrelid = 'public.submissions_v2'::regclass AS trigger_targets_submissions,
    t.tgfoid = to_regprocedure('public.exos_v2_theme_park_race_submission_guard()') AS trigger_points_to_037_guard,
    NOT t.tgisinternal AS trigger_is_user_defined,
    pg_get_triggerdef(t.oid) AS trigger_definition
  FROM pg_trigger t
 WHERE t.tgname = 'exos_v2_theme_park_race_submission_guard_trg'
   AND t.tgrelid = 'public.submissions_v2'::regclass
   AND NOT t.tgisinternal;

SELECT
    event_id,
    event_payload #>> '{RaceConfiguration,SchemaVersion}' AS schema_version,
    event_payload #>> '{RaceConfiguration,RuntimePhase}' AS runtime_phase,
    event_payload #>> '{TeamFormation,Phase}' AS team_formation_phase,
    (
        SELECT count(*)
          FROM jsonb_object_keys(coalesce(event_payload #> '{RaceConfiguration,TeamRoutes}', '{}'::jsonb))
    ) AS route_count
FROM public.events_v2
WHERE upper(coalesce(event_payload #>> '{RaceConfiguration,EngineKind}', '')) = 'THEME_PARK_RACE'
ORDER BY event_id;
