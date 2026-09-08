-- Read-only verification for 044_post_maxis_p0_live_operations.sql.
-- This verifier creates no fixtures and performs no mutation.

WITH expected(proname, exact_signature, service_execute) AS (
    VALUES
        ('exos_v2_team_formation_captain_attendance_guard',
         'public.exos_v2_team_formation_captain_attendance_guard()', false),
        ('exos_v2_theme_park_race_adjust_team_score',
         'public.exos_v2_theme_park_race_adjust_team_score(text,text,numeric,text,text,text)', true),
        ('exos_v2_theme_park_race_score_adjustments',
         'public.exos_v2_theme_park_race_score_adjustments(text,integer)', true),
        ('exos_v2_clear_team_formation_captain',
         'public.exos_v2_clear_team_formation_captain(text,text,text,text)', true),
        ('exos_v2_theme_park_race_operator_status',
         'public.exos_v2_theme_park_race_operator_status(text)', true)
), resolved AS (
    SELECT expected.*, to_regprocedure(exact_signature) AS function_oid
      FROM expected
)
SELECT
    exact_signature,
    function_oid IS NOT NULL AS exact_signature_present,
    coalesce((SELECT p.prosecdef FROM pg_proc p WHERE p.oid = function_oid), false)
        AS security_definer,
    coalesce((
        SELECT EXISTS (
            SELECT 1 FROM unnest(p.proconfig) setting(value)
             WHERE value IN ('search_path=', 'search_path=""')
        ) FROM pg_proc p WHERE p.oid = function_oid
    ), false) AS search_path_pinned_to_empty,
    NOT coalesce((
        SELECT bool_or(acl.privilege_type = 'EXECUTE' AND acl.grantee = 0)
          FROM pg_proc p
          CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
         WHERE p.oid = function_oid
    ), false) AS public_execute_revoked,
    NOT EXISTS (
        SELECT 1 FROM pg_proc p
         CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
         JOIN pg_roles r ON r.oid = acl.grantee
        WHERE p.oid = function_oid AND acl.privilege_type = 'EXECUTE'
          AND r.rolname IN ('anon', 'authenticated')
    ) AS anon_authenticated_revoked,
    CASE WHEN service_execute THEN
        coalesce(has_function_privilege('service_role', function_oid, 'EXECUTE'), false)
      ELSE
        NOT coalesce(has_function_privilege('service_role', function_oid, 'EXECUTE'), false)
    END AS service_role_matrix_correct,
    (SELECT count(*) = 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'public' AND p.proname = resolved.proname) AS no_unexpected_overloads
FROM resolved
ORDER BY exact_signature;

SELECT
    EXISTS (SELECT 1 FROM pg_trigger t
             WHERE t.tgrelid = 'public.participants_v2'::regclass
               AND t.tgname = 'exos_v2_team_formation_captain_attendance_guard_trg'
               AND NOT t.tgisinternal) AS present_captain_guard_trigger_present,
    to_regprocedure('public.exos_v2_set_participant_attendance(text,uuid,text,text,text)') IS NOT NULL
        AS attendance_dependency_present,
    to_regprocedure('public.exos_v2_claim_team_formation_captain(uuid,text)') IS NOT NULL
        AS captain_claim_dependency_present,
    to_regprocedure('public.exos_v2_theme_park_race_board_review(uuid,timestamptz,public.exos_v2_review_decision,numeric,text,text,text)') IS NOT NULL
        AS board_review_dependency_present,
    to_regprocedure('public.exos_v2_set_theme_park_race_runtime_phase(text,text,text)') IS NOT NULL
        AS runtime_phase_dependency_present;

WITH definitions AS (
    SELECT
        to_regprocedure('public.exos_v2_team_formation_captain_attendance_guard()') AS attendance_guard_oid,
        to_regprocedure('public.exos_v2_theme_park_race_adjust_team_score(text,text,numeric,text,text,text)') AS adjustment_oid,
        to_regprocedure('public.exos_v2_clear_team_formation_captain(text,text,text,text)') AS clear_oid,
        to_regprocedure('public.exos_v2_theme_park_race_operator_status(text)') AS status_oid
)
SELECT
    attendance_guard_oid IS NOT NULL
        AND position('participant_attendance_v2' IN pg_get_functiondef(attendance_guard_oid)) > 0
        AND position('PRESENT' IN pg_get_functiondef(attendance_guard_oid)) > 0
        AS present_only_captain_guard_installed,
    adjustment_oid IS NOT NULL
        AND position('THEME_PARK_RACE_SCORE_ADJUSTMENT' IN pg_get_functiondef(adjustment_oid)) > 0
        AND position('ON CONFLICT (event_id, idempotency_key) DO NOTHING' IN pg_get_functiondef(adjustment_oid)) > 0
        AND position('THEME_PARK_RACE_TEAM_SCORE_ADJUSTED' IN pg_get_functiondef(adjustment_oid)) > 0
        AND position('pg_advisory_xact_lock' IN pg_get_functiondef(adjustment_oid)) > 0
        AND position('DO UPDATE' IN pg_get_functiondef(adjustment_oid)) = 0
        AS immutable_adjustment_contract_installed,
    clear_oid IS NOT NULL
        AND position('TEAM_FORMATION_CAPTAIN_CLEARED' IN pg_get_functiondef(clear_oid)) > 0
        AND position('team_access_sessions_v2' IN pg_get_functiondef(clear_oid)) > 0
        AND position('is_team_formation_captain = false' IN pg_get_functiondef(clear_oid)) > 0
        AND position('pg_advisory_xact_lock' IN pg_get_functiondef(clear_oid)) > 0
        AS captain_clear_and_session_revocation_installed,
    status_oid IS NOT NULL
        AND position('PENDING_REVIEW_SUMMARY' IN pg_get_functiondef(status_oid)) > 0
        AND position('TEAM_SCORE_ADJUSTMENT' IN pg_get_functiondef(status_oid)) > 0
        AS canonical_operator_projection_installed
FROM definitions;

-- Read-only inventory of P0-C adjustments, if any.  It is intentionally an
-- audit/listing query and never interprets older ledger rows as adjustments.
SELECT s.event_id, s.team_id, s.score_delta, s.reason, s.created_by, s.created_at,
       s.source_reference ->> 'RequestIdempotencyKey' AS request_idempotency_key
  FROM public.score_transactions_v2 s
 WHERE s.source_reference ->> 'Contract' = 'THEME_PARK_RACE_LIVE_OPERATIONS_044'
   AND s.source_reference ->> 'Operation' = 'TEAM_SCORE_ADJUSTMENT'
 ORDER BY s.created_at DESC, s.score_transaction_id DESC;
