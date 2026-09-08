-- Read-only verification for 043_post_maxis_p0_participation_rubric_scoring.sql.
-- No fixtures and no mutations are created by this verifier.

WITH expected(proname, exact_signature, participant_execute, service_execute) AS (
    VALUES
        ('exos_v2_theme_park_race_scoring_snapshot_write_guard',
         'public.exos_v2_theme_park_race_scoring_snapshot_write_guard()', false, false),
        ('exos_v2_theme_park_race_scored_submission_guard',
         'public.exos_v2_theme_park_race_scored_submission_guard()', false, false),
        ('exos_v2_theme_park_race_scored_review_guard',
         'public.exos_v2_theme_park_race_scored_review_guard()', false, false),
        ('exos_v2_theme_park_race_participation_preview',
         'public.exos_v2_theme_park_race_participation_preview(text,text)', true, true),
        ('exos_v2_theme_park_race_submit_participation',
         'public.exos_v2_theme_park_race_submit_participation(text,text,jsonb,jsonb)', true, true),
        ('exos_v2_theme_park_race_review_scored_submission',
         'public.exos_v2_theme_park_race_review_scored_submission(uuid,timestamptz,public.exos_v2_review_decision,jsonb,text,text,text)', false, true)
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
    ) = NOT participant_execute AS anon_authenticated_matrix_correct,
    CASE WHEN participant_execute THEN
        coalesce(has_function_privilege('anon', function_oid, 'EXECUTE'), false)
        AND coalesce(has_function_privilege('authenticated', function_oid, 'EXECUTE'), false)
      ELSE
        NOT coalesce(has_function_privilege('anon', function_oid, 'EXECUTE'), false)
        AND NOT coalesce(has_function_privilege('authenticated', function_oid, 'EXECUTE'), false)
    END AS participant_execute_matrix_correct,
    CASE WHEN service_execute THEN coalesce(has_function_privilege('service_role', function_oid, 'EXECUTE'), false)
         ELSE NOT coalesce(has_function_privilege('service_role', function_oid, 'EXECUTE'), false)
    END AS service_role_matrix_correct,
    (SELECT count(*) = 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'public' AND p.proname = resolved.proname) AS no_unexpected_overloads
FROM resolved
ORDER BY exact_signature;

SELECT
    to_regclass('public.theme_park_race_scoring_snapshots_v2') IS NOT NULL AS snapshot_table_present,
    coalesce((SELECT c.relrowsecurity FROM pg_class c
               WHERE c.oid = 'public.theme_park_race_scoring_snapshots_v2'::regclass), false)
        AS snapshot_rls_enabled,
    NOT coalesce(has_table_privilege('anon', 'public.theme_park_race_scoring_snapshots_v2', 'SELECT'), false)
        AS anon_table_access_revoked,
    NOT coalesce(has_table_privilege('authenticated', 'public.theme_park_race_scoring_snapshots_v2', 'SELECT'), false)
        AS authenticated_table_access_revoked,
    NOT coalesce(has_table_privilege('service_role', 'public.theme_park_race_scoring_snapshots_v2', 'INSERT'), false)
        AS service_role_direct_mutation_revoked,
    EXISTS (SELECT 1 FROM pg_trigger t WHERE t.tgrelid = 'public.theme_park_race_scoring_snapshots_v2'::regclass
              AND t.tgname = 'exos_v2_theme_park_race_scoring_snapshot_write_guard_trg' AND NOT t.tgisinternal)
        AS snapshot_guard_trigger_present,
    EXISTS (SELECT 1 FROM pg_trigger t WHERE t.tgrelid = 'public.submissions_v2'::regclass
              AND t.tgname = 'exos_v2_theme_park_race_scored_submission_guard_trg' AND NOT t.tgisinternal)
        AS participation_submission_guard_present,
    EXISTS (SELECT 1 FROM pg_trigger t WHERE t.tgrelid = 'public.submissions_v2'::regclass
              AND t.tgname = 'exos_v2_theme_park_race_scored_review_guard_trg' AND NOT t.tgisinternal)
        AS scored_review_guard_present;

WITH definitions AS (
    SELECT
        to_regprocedure('public.exos_v2_theme_park_race_submit_participation(text,text,jsonb,jsonb)') AS submit_oid,
        to_regprocedure('public.exos_v2_theme_park_race_review_scored_submission(uuid,timestamptz,public.exos_v2_review_decision,jsonb,text,text,text)') AS review_oid,
        to_regprocedure('public.exos_v2_theme_park_race_scored_submission_guard()') AS submission_guard_oid,
        to_regprocedure('public.exos_v2_theme_park_race_scored_review_guard()') AS review_guard_oid
)
SELECT
    submit_oid IS NOT NULL
        AND position('participant_attendance_v2' IN pg_get_functiondef(submit_oid)) > 0
        AND position('pg_advisory_xact_lock' IN pg_get_functiondef(submit_oid)) > 0
        AND position('theme_park_race_scoring_snapshots_v2' IN pg_get_functiondef(submit_oid)) > 0
        AND position('exos_v2_theme_park_race_board_submit' IN pg_get_functiondef(submit_oid)) > 0
        AND position('round(v_maximum * v_selected_count::numeric / v_present_count::numeric, 0)' IN pg_get_functiondef(submit_oid)) > 0
        AS canonical_participation_snapshot_installed,
    review_oid IS NOT NULL
        AND position('exos_v2_theme_park_race_board_review' IN pg_get_functiondef(review_oid)) > 0
        AND position('FACILITATOR_RUBRIC' IN pg_get_functiondef(review_oid)) > 0
        AND position('PARTICIPATION_PRORATED' IN pg_get_functiondef(review_oid)) > 0
        AND position('Submission revision is stale' IN pg_get_functiondef(review_oid)) > 0
        AS canonical_scored_review_installed,
    submission_guard_oid IS NOT NULL
        AND position('PARTICIPATION_PRORATED' IN pg_get_functiondef(submission_guard_oid)) > 0
        AND position('exos.tpr_participation_submission' IN pg_get_functiondef(submission_guard_oid)) > 0
        AND position('set_config(''exos.tpr_participation_submission'', '''', true)' IN pg_get_functiondef(submission_guard_oid)) > 0
        AS direct_submission_bypass_blocked,
    review_guard_oid IS NOT NULL
        AND position('FACILITATOR_RUBRIC' IN pg_get_functiondef(review_guard_oid)) > 0
        AND position('exos.tpr_scored_review' IN pg_get_functiondef(review_guard_oid)) > 0
        AND position('set_config(''exos.tpr_scored_review'', '''', true)' IN pg_get_functiondef(review_guard_oid)) > 0
        AS direct_review_bypass_blocked
FROM definitions;

-- Read-only inventory: only explicitly configured activities are shown.
SELECT p.event_id, a.activity_id,
       a.activity_payload #>> '{race_station,Scoring,Mode}' AS scoring_mode,
       a.activity_payload #>> '{race_station,Scoring,Maximum}' AS scoring_maximum
  FROM public.activities_v2 a
  JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
 WHERE upper(coalesce(a.activity_payload #>> '{race_station,Scoring,Mode}', ''))
       IN ('PARTICIPATION_PRORATED', 'FACILITATOR_RUBRIC')
 ORDER BY p.event_id, a.activity_id;
