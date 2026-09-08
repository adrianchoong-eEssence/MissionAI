-- Read-only verification for 042_post_maxis_p0_attendance.sql.
-- This script creates no fixture and performs no mutation.

WITH expected(proname, exact_signature, service_execute) AS (
    VALUES
        ('exos_v2_participant_attendance_write_guard',
         'public.exos_v2_participant_attendance_write_guard()', false),
        ('exos_v2_configure_attendance',
         'public.exos_v2_configure_attendance(text,text)', true),
        ('exos_v2_set_participant_attendance',
         'public.exos_v2_set_participant_attendance(text,uuid,text,text,text)', true),
        ('exos_v2_attendance_summary',
         'public.exos_v2_attendance_summary(text)', true),
        ('exos_v2_attendance_roster',
         'public.exos_v2_attendance_roster(text)', true)
), resolved AS (
    SELECT expected.*, to_regprocedure(exact_signature) AS function_oid
      FROM expected
)
SELECT
    exact_signature,
    function_oid IS NOT NULL AS exact_signature_present,
    coalesce((
        SELECT p.prosecdef FROM pg_proc p WHERE p.oid = function_oid
    ), false) AS security_definer,
    coalesce((
        SELECT EXISTS (
            SELECT 1 FROM unnest(p.proconfig) AS setting(value)
             WHERE setting.value IN ('search_path=', 'search_path=""')
        ) FROM pg_proc p WHERE p.oid = function_oid
    ), false) AS search_path_pinned_to_empty,
    NOT coalesce((
        SELECT bool_or(acl.privilege_type = 'EXECUTE' AND acl.grantee = 0)
          FROM pg_proc p
          CROSS JOIN LATERAL aclexplode(
              coalesce(p.proacl, acldefault('f', p.proowner))
          ) AS acl
         WHERE p.oid = function_oid
    ), false) AS public_execute_revoked,
    NOT EXISTS (
        SELECT 1
          FROM pg_proc p
          CROSS JOIN LATERAL aclexplode(
              coalesce(p.proacl, acldefault('f', p.proowner))
          ) AS acl
          JOIN pg_roles role_name ON role_name.oid = acl.grantee
         WHERE p.oid = function_oid
           AND acl.privilege_type = 'EXECUTE'
           AND role_name.rolname IN ('anon', 'authenticated')
    ) AS anon_authenticated_execute_revoked,
    CASE WHEN service_execute
        THEN coalesce(has_function_privilege('service_role', function_oid, 'EXECUTE'), false)
        ELSE NOT coalesce(has_function_privilege('service_role', function_oid, 'EXECUTE'), false)
    END AS service_role_matrix_correct,
    (
        SELECT count(*) = 1
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname = resolved.proname
    ) AS no_unexpected_overloads
FROM resolved
ORDER BY exact_signature;

SELECT
    to_regclass('public.participant_attendance_v2') IS NOT NULL
        AS attendance_table_present,
    coalesce((
        SELECT c.relrowsecurity
          FROM pg_class c
         WHERE c.oid = 'public.participant_attendance_v2'::regclass
    ), false) AS attendance_rls_enabled,
    NOT coalesce(has_table_privilege('anon', 'public.participant_attendance_v2', 'SELECT'), false)
        AS anon_table_access_revoked,
    NOT coalesce(has_table_privilege('authenticated', 'public.participant_attendance_v2', 'SELECT'), false)
        AS authenticated_table_access_revoked,
    NOT coalesce(has_table_privilege('service_role', 'public.participant_attendance_v2', 'INSERT'), false)
        AS service_role_direct_mutation_revoked,
    EXISTS (
        SELECT 1 FROM pg_trigger t
         WHERE t.tgrelid = 'public.participant_attendance_v2'::regclass
           AND t.tgname = 'exos_v2_participant_attendance_write_guard'
           AND NOT t.tgisinternal
    ) AS canonical_write_guard_trigger_present;

WITH definitions AS (
    SELECT
        to_regprocedure('public.exos_v2_configure_attendance(text,text)') AS configure_oid,
        to_regprocedure('public.exos_v2_set_participant_attendance(text,uuid,text,text,text)') AS set_oid,
        to_regprocedure('public.exos_v2_attendance_summary(text)') AS summary_oid
)
SELECT
    configure_oid IS NOT NULL
        AND position('{Attendance}' IN pg_get_functiondef(configure_oid)) > 0
        AND position('ATTENDANCE_CONFIGURED' IN pg_get_functiondef(configure_oid)) > 0
        AS explicit_event_opt_in_installed,
    set_oid IS NOT NULL
        AND position('pg_advisory_xact_lock' IN pg_get_functiondef(set_oid)) > 0
        AND position('PARTICIPANT_ATTENDANCE_CHANGED' IN pg_get_functiondef(set_oid)) > 0
        AND position('exos.attendance_mutation' IN pg_get_functiondef(set_oid)) > 0
        AS canonical_audited_mutation_installed,
    summary_oid IS NOT NULL
        AND position('PresentTeamSize' IN pg_get_functiondef(summary_oid)) > 0
        AND position('PREASSIGNED' IN pg_get_functiondef(summary_oid)) > 0
        AS canonical_counts_and_present_team_size_installed
FROM definitions;

-- Read-only inventory. Existing events appear only after an explicit service
-- configuration; the migration itself does not opt any event in.
SELECT
    event_id,
    event_name,
    event_payload #>> '{Attendance,SchemaVersion}' AS attendance_schema_version,
    event_payload #>> '{Attendance,ConfiguredBy}' AS configured_by,
    event_payload #>> '{Attendance,ConfiguredAt}' AS configured_at
FROM public.events_v2
WHERE coalesce(event_payload #>> '{Attendance,SchemaVersion}', '') = '1'
ORDER BY event_id;
