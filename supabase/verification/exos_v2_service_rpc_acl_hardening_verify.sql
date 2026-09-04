-- Read-only verification for the additive ACL hardening migrations:
--   025a_standard_programme_runtime_acl_hardening.sql
--   026a_standard_participant_access_acl_hardening.sql
--   036a_team_formation_v1_acl_hardening.sql
--   040a_exos_core_v2_service_rpc_acl_hardening.sql
--
-- Those four migrations are privilege-only, and the Python tests that cover
-- them can only read the SQL text: they prove the migration *says* the right
-- thing, never that the privilege is actually in force in a database. This
-- file closes that gap. It is the query to run against an installed staging
-- or production catalogue to prove the grants are real.
--
-- It asserts BOTH directions, which is the point. Revoking too much is as much
-- a live-event failure as revoking too little: the five participant-facing
-- Team Formation RPCs must KEEP anon/authenticated EXECUTE, or registration,
-- reconnect and Captain claim stop working for every participant on the day.
--
-- Read-only: contains no INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, GRANT or
-- REVOKE. Safe to run against production.

-- 1. Service-role-only RPCs. anon/authenticated/PUBLIC must all be revoked.
WITH expected(exact_signature) AS (
    VALUES
        -- 025a Standard programme runtime
        ('public.exos_v2_standard_launch_activity(text,text,text)'),
        ('public.exos_v2_standard_review_submission(uuid,public.exos_v2_review_decision,numeric,text,text,text)'),
        -- 026a participant identity helper
        ('public.exos_v2_identity_payload(text,uuid)'),
        -- 036a Team Formation V1 internal helpers and facilitator lifecycle
        ('public.exos_v2_team_formation_credential_hash(text)'),
        ('public.exos_v2_team_formation_participant_write_guard()'),
        ('public.exos_v2_team_formation_team_write_guard()'),
        ('public.exos_v2_team_formation_captain_session_guard()'),
        ('public.exos_v2_configure_team_formation(text,text,jsonb,jsonb,text)'),
        ('public.exos_v2_open_team_formation(text,text)'),
        ('public.exos_v2_lock_team_formation(text,text)'),
        ('public.exos_v2_open_team_captain_selection(text,text)'),
        ('public.exos_v2_activate_team_formation(text,text)'),
        ('public.exos_v2_transfer_team_formation_captain(text,text,uuid,text,text)'),
        -- 040a Core v2 service/admin RPCs
        ('public.exos_v2_publish_event(text,text,text,jsonb,public.exos_v2_scoring_mode,text)'),
        ('public.exos_v2_admin_recover_identity(text,uuid,text,text,text)'),
        ('public.exos_v2_admin_merge_participants(text,uuid,uuid,text,text)'),
        ('public.exos_v2_ledger_score(text,text,uuid,numeric,text,public.exos_v2_scoring_mode,text)'),
        ('public.exos_v2_ledger_credit(text,text,uuid,text,integer,text,text)'),
        ('public.exos_v2_set_team_access_pin(text,text,text,text)')
), resolved AS (
    SELECT expected.*, to_regprocedure(exact_signature) AS function_oid FROM expected
)
SELECT
    'service_role_only' AS class,
    exact_signature,
    function_oid IS NOT NULL AS exact_signature_present,
    NOT coalesce((
        SELECT bool_or(acl.privilege_type = 'EXECUTE' AND acl.grantee = 0)
          FROM pg_proc p
          CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) AS acl
         WHERE p.oid = function_oid
    ), false) AS public_execute_revoked,
    NOT EXISTS (
        SELECT 1 FROM pg_proc p
        CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) AS acl
        JOIN pg_roles role_name ON role_name.oid = acl.grantee
        WHERE p.oid = function_oid AND acl.privilege_type = 'EXECUTE'
          AND role_name.rolname IN ('anon', 'authenticated')
    ) AS anon_authenticated_execute_revoked,
    coalesce((SELECT has_function_privilege('service_role', function_oid, 'EXECUTE')), false)
        AS service_role_execute_present
FROM resolved
ORDER BY exact_signature;

-- 2. Participant-facing Team Formation RPCs. These MUST retain anon and
--    authenticated EXECUTE: they are the Monday journey. Registration,
--    pre-assigned claim, participant recovery, Captain claim and Captain
--    recovery all run under the participant's own key, never service_role.
WITH expected(exact_signature) AS (
    VALUES
        ('public.exos_v2_team_formation_register_random(text,text,text,text)'),
        ('public.exos_v2_team_formation_claim_preassigned(text,text,text)'),
        ('public.exos_v2_recover_team_formation_participant(text,text,text)'),
        ('public.exos_v2_claim_team_formation_captain(uuid,text)'),
        ('public.exos_v2_recover_team_formation_captain(text,text,text)')
), resolved AS (
    SELECT expected.*, to_regprocedure(exact_signature) AS function_oid FROM expected
)
SELECT
    'participant_facing' AS class,
    exact_signature,
    function_oid IS NOT NULL AS exact_signature_present,
    coalesce((SELECT has_function_privilege('anon', function_oid, 'EXECUTE')), false)
        AS anon_execute_retained,
    coalesce((SELECT has_function_privilege('authenticated', function_oid, 'EXECUTE')), false)
        AS authenticated_execute_retained,
    coalesce((SELECT has_function_privilege('service_role', function_oid, 'EXECUTE')), false)
        AS service_role_execute_present
FROM resolved
ORDER BY exact_signature;

-- 3. Single-line pass/fail gate. Every row above must be true for this to
--    return passed = true. Use this as the certification gate.
WITH service_only(exact_signature) AS (
    VALUES
        ('public.exos_v2_standard_launch_activity(text,text,text)'),
        ('public.exos_v2_standard_review_submission(uuid,public.exos_v2_review_decision,numeric,text,text,text)'),
        ('public.exos_v2_identity_payload(text,uuid)'),
        ('public.exos_v2_team_formation_credential_hash(text)'),
        ('public.exos_v2_team_formation_participant_write_guard()'),
        ('public.exos_v2_team_formation_team_write_guard()'),
        ('public.exos_v2_team_formation_captain_session_guard()'),
        ('public.exos_v2_configure_team_formation(text,text,jsonb,jsonb,text)'),
        ('public.exos_v2_open_team_formation(text,text)'),
        ('public.exos_v2_lock_team_formation(text,text)'),
        ('public.exos_v2_open_team_captain_selection(text,text)'),
        ('public.exos_v2_activate_team_formation(text,text)'),
        ('public.exos_v2_transfer_team_formation_captain(text,text,uuid,text,text)'),
        ('public.exos_v2_publish_event(text,text,text,jsonb,public.exos_v2_scoring_mode,text)'),
        ('public.exos_v2_admin_recover_identity(text,uuid,text,text,text)'),
        ('public.exos_v2_admin_merge_participants(text,uuid,uuid,text,text)'),
        ('public.exos_v2_ledger_score(text,text,uuid,numeric,text,public.exos_v2_scoring_mode,text)'),
        ('public.exos_v2_ledger_credit(text,text,uuid,text,integer,text,text)'),
        ('public.exos_v2_set_team_access_pin(text,text,text,text)')
), participant_facing(exact_signature) AS (
    VALUES
        ('public.exos_v2_team_formation_register_random(text,text,text,text)'),
        ('public.exos_v2_team_formation_claim_preassigned(text,text,text)'),
        ('public.exos_v2_recover_team_formation_participant(text,text,text)'),
        ('public.exos_v2_claim_team_formation_captain(uuid,text)'),
        ('public.exos_v2_recover_team_formation_captain(text,text,text)')
), service_checks AS (
    SELECT bool_and(
        to_regprocedure(exact_signature) IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM pg_proc p
            CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) AS acl
            LEFT JOIN pg_roles role_name ON role_name.oid = acl.grantee
            WHERE p.oid = to_regprocedure(exact_signature)
              AND acl.privilege_type = 'EXECUTE'
              AND (acl.grantee = 0 OR role_name.rolname IN ('anon', 'authenticated'))
        )
        AND has_function_privilege('service_role', to_regprocedure(exact_signature), 'EXECUTE')
    ) AS ok FROM service_only
), participant_checks AS (
    SELECT bool_and(
        to_regprocedure(exact_signature) IS NOT NULL
        AND has_function_privilege('anon', to_regprocedure(exact_signature), 'EXECUTE')
        AND has_function_privilege('authenticated', to_regprocedure(exact_signature), 'EXECUTE')
    ) AS ok FROM participant_facing
)
SELECT
    'exos_v2_service_rpc_acl_hardening' AS verifier,
    (SELECT ok FROM service_checks) AS service_role_only_enforced,
    (SELECT ok FROM participant_checks) AS participant_journey_preserved,
    ((SELECT ok FROM service_checks) AND (SELECT ok FROM participant_checks)) AS passed;
