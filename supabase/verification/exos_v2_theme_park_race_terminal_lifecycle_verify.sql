-- Read-only verification for 040 Theme Park Race terminal lifecycle.
-- Run only after authorised installation of 037, 037a, 038, 039, then 040.
WITH expected(proname, exact_signature) AS (
    VALUES
        ('exos_v2_set_theme_park_race_runtime_phase',
         'public.exos_v2_set_theme_park_race_runtime_phase(text,text,text)'),
        ('exos_v2_theme_park_race_board_set_mission_operation',
         'public.exos_v2_theme_park_race_board_set_mission_operation(text,text,text,text,text)')
), resolved AS (
    SELECT expected.*, to_regprocedure(exact_signature) AS function_oid FROM expected
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
    NOT coalesce((
        SELECT bool_or(acl.privilege_type = 'EXECUTE' AND acl.grantee = 0)
          FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) AS acl
         WHERE p.oid = function_oid
    ), false) AS public_execute_revoked,
    NOT EXISTS (
        SELECT 1 FROM pg_proc p
        CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) AS acl
        JOIN pg_roles role_name ON role_name.oid = acl.grantee
        WHERE p.oid = function_oid AND acl.privilege_type = 'EXECUTE'
          AND role_name.rolname IN ('anon', 'authenticated')
    ) AS anon_authenticated_execute_revoked,
    coalesce((
        SELECT has_function_privilege('service_role', function_oid, 'EXECUTE')
    ), false) AS service_role_execute_present,
    (SELECT count(*) = 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'public' AND p.proname = resolved.proname) AS no_unexpected_overloads
FROM resolved
ORDER BY exact_signature;

WITH definitions AS (
    SELECT
        to_regprocedure('public.exos_v2_set_theme_park_race_runtime_phase(text,text,text)') AS runtime_phase_oid,
        to_regprocedure('public.exos_v2_theme_park_race_board_set_mission_operation(text,text,text,text,text)') AS operation_oid
)
SELECT
    runtime_phase_oid IS NOT NULL
        AND position('''HELD''' IN pg_get_functiondef(runtime_phase_oid)) > 0
        AND position('Mission is ended and cannot be restarted' IN pg_get_functiondef(runtime_phase_oid)) > 0
        AND position('''Lifecycle''' IN pg_get_functiondef(runtime_phase_oid)) > 0
        AS held_and_terminal_runtime_definition_installed,
    operation_oid IS NOT NULL
        AND position('operational mission controls are closed' IN pg_get_functiondef(operation_oid)) > 0
        AS ended_operation_guard_definition_installed
FROM definitions;

SELECT
    event_id,
    event_payload #>> '{RaceConfiguration,RuntimePhase}' AS persisted_runtime_phase,
    CASE WHEN upper(coalesce(event_payload #>> '{RaceConfiguration,RuntimePhase}', 'READY')) = 'CLOSED'
         THEN 'ENDED'
         ELSE upper(coalesce(event_payload #>> '{RaceConfiguration,RuntimePhase}', 'READY')) END AS projected_lifecycle
FROM public.events_v2
WHERE upper(coalesce(event_payload #>> '{RaceConfiguration,EngineKind}', '')) = 'THEME_PARK_RACE'
ORDER BY event_id;
