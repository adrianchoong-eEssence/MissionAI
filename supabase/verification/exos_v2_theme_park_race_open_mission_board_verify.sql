-- Read-only verification for the 038 OPEN_MISSION_BOARD extension.
-- Run only after authorised installation of 037 then 038.  It creates no
-- fixtures and performs no mutation.
WITH expected(proname, exact_signature, expected_execute_grantees) AS (
    VALUES
        ('exos_v2_theme_park_race_save_configuration',
         'public.exos_v2_theme_park_race_save_configuration(text,jsonb,text)', ARRAY['service_role']::text[]),
        ('exos_v2_theme_park_race_board_set_mission_operation',
         'public.exos_v2_theme_park_race_board_set_mission_operation(text,text,text,text,text)', ARRAY['service_role']::text[]),
        ('exos_v2_theme_park_race_board_select',
         'public.exos_v2_theme_park_race_board_select(text,text)', ARRAY['anon','authenticated','service_role']::text[]),
        ('exos_v2_theme_park_race_board_record_ride_outcome',
         'public.exos_v2_theme_park_race_board_record_ride_outcome(text,text,text,jsonb)', ARRAY['anon','authenticated','service_role']::text[]),
        ('exos_v2_theme_park_race_board_submit',
         'public.exos_v2_theme_park_race_board_submit(text,text,jsonb)', ARRAY['anon','authenticated','service_role']::text[]),
        ('exos_v2_theme_park_race_submission_guard',
         'public.exos_v2_theme_park_race_submission_guard()', ARRAY[]::text[]),
        ('exos_v2_theme_park_race_score_guard',
         'public.exos_v2_theme_park_race_score_guard()', ARRAY[]::text[])
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

WITH definitions AS (
    SELECT
        to_regprocedure('public.exos_v2_theme_park_race_save_configuration(text,jsonb,text)') AS save_configuration_oid,
        to_regprocedure('public.exos_v2_theme_park_race_submission_guard()') AS submission_guard_oid,
        to_regprocedure('public.exos_v2_theme_park_race_score_guard()') AS score_guard_oid
)
SELECT
    save_configuration_oid IS NOT NULL
        AND position('OPEN_MISSION_BOARD' IN pg_get_functiondef(save_configuration_oid)) > 0
        AND position('This event is already configured for a different race engine' IN pg_get_functiondef(save_configuration_oid)) > 0
        AND position('structural configuration is frozen after authoritative runtime or submissions exist' IN pg_get_functiondef(save_configuration_oid)) > 0
        AS replaced_save_configuration_definition_installed,
    submission_guard_oid IS NOT NULL
        AND position('OPEN_MISSION_BOARD' IN pg_get_functiondef(submission_guard_oid)) > 0
        AND position('Open Mission Board submission requires an authoritative selected mission' IN pg_get_functiondef(submission_guard_oid)) > 0
        AS open_board_submission_guard_definition_installed,
    score_guard_oid IS NOT NULL
        AND position('Theme Park Race score is outside the configured maximum' IN pg_get_functiondef(score_guard_oid)) > 0
        AS score_guard_definition_installed
FROM definitions;

SELECT
    t.tgname = 'exos_v2_theme_park_race_submission_guard_trg' AS submission_guard_trigger_present,
    t.tgfoid = to_regprocedure('public.exos_v2_theme_park_race_submission_guard()') AS submission_guard_trigger_points_to_038_definition,
    t.tgrelid = 'public.submissions_v2'::regclass AS submission_guard_trigger_targets_submissions,
    NOT t.tgisinternal AS submission_guard_trigger_is_user_defined,
    pg_get_triggerdef(t.oid) AS submission_guard_trigger_definition
  FROM pg_trigger t
 WHERE t.tgname = 'exos_v2_theme_park_race_submission_guard_trg'
   AND t.tgrelid = 'public.submissions_v2'::regclass
   AND NOT t.tgisinternal;

SELECT
    t.tgname = 'exos_v2_theme_park_race_score_guard_trg' AS score_guard_trigger_present,
    t.tgfoid = to_regprocedure('public.exos_v2_theme_park_race_score_guard()') AS score_guard_trigger_points_to_expected_function,
    t.tgrelid = 'public.submissions_v2'::regclass AS score_guard_trigger_targets_submissions,
    NOT t.tgisinternal AS score_guard_trigger_is_user_defined,
    pg_get_triggerdef(t.oid) AS score_guard_trigger_definition
  FROM pg_trigger t
 WHERE t.tgname = 'exos_v2_theme_park_race_score_guard_trg'
   AND t.tgrelid = 'public.submissions_v2'::regclass
   AND NOT t.tgisinternal;

SELECT
    event_id,
    event_payload #>> '{RaceConfiguration,StrategyMode}' AS strategy_mode,
    event_payload #>> '{RaceConfiguration,RuntimePhase}' AS runtime_phase,
    (
        SELECT count(*)
          FROM jsonb_object_keys(coalesce(event_payload #> '{RaceConfiguration,MissionBoard,MissionOperations}', '{}'::jsonb))
    ) AS mission_operation_count
  FROM public.events_v2
 WHERE upper(coalesce(event_payload #>> '{RaceConfiguration,EngineKind}', '')) = 'THEME_PARK_RACE'
 ORDER BY event_id;
