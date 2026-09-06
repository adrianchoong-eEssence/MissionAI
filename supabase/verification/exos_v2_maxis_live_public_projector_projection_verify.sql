-- Read-only verification for the Maxis public projector projection.
-- Run after authorised installation of 041 only.
WITH expected AS (
    SELECT
        'public.exos_v2_maxis_live_projector_projection()'::text AS exact_signature,
        'exos_v2_maxis_live_projector_projection'::text AS proname,
        to_regprocedure('public.exos_v2_maxis_live_projector_projection()') AS function_oid
), contract AS (
    SELECT function_oid, pg_get_functiondef(function_oid) AS definition
    FROM expected
)
SELECT
    expected.exact_signature,
    expected.function_oid IS NOT NULL AS exact_signature_present,
    coalesce((SELECT p.prosecdef FROM pg_proc AS p WHERE p.oid = expected.function_oid), false) AS security_definer,
    coalesce((
        SELECT EXISTS (
            SELECT 1
            FROM unnest(p.proconfig) AS setting(value)
            WHERE setting.value IN ('search_path=', 'search_path=""')
        )
        FROM pg_proc AS p
        WHERE p.oid = expected.function_oid
    ), false) AS search_path_pinned_to_empty,
    coalesce((SELECT has_function_privilege('anon', expected.function_oid, 'EXECUTE')), false) AS anon_execute_present,
    coalesce((SELECT has_function_privilege('authenticated', expected.function_oid, 'EXECUTE')), false) AS authenticated_execute_present,
    NOT coalesce((SELECT has_function_privilege('service_role', expected.function_oid, 'EXECUTE')), false) AS service_role_execute_revoked,
    NOT coalesce((
        SELECT bool_or(acl.privilege_type = 'EXECUTE' AND acl.grantee = 0)
        FROM pg_proc AS p
        CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) AS acl
        WHERE p.oid = expected.function_oid
    ), false) AS public_execute_revoked,
    (SELECT count(*) = 1
     FROM pg_proc AS p
     JOIN pg_namespace AS n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.proname = expected.proname) AS no_unexpected_overloads,
    coalesce((SELECT position('MAXIS-20260907-MISSION-AI' IN definition) > 0 FROM contract), false) AS fixed_event_eligibility,
    coalesce((SELECT position('p_event_id' IN definition) = 0 FROM contract), false) AS no_caller_controlled_event_selector,
    coalesce((SELECT position('participant' IN lower(definition)) = 0 FROM contract), false) AS no_participant_data_query,
    coalesce((SELECT position('submissions_v2' IN definition) = 0 FROM contract), false) AS no_submission_data_query,
    coalesce((SELECT position('evidence' IN lower(definition)) = 0 FROM contract), false) AS no_evidence_data_query,
    coalesce((SELECT position('device_id' IN lower(definition)) = 0 FROM contract), false) AS no_device_data_query,
    coalesce((SELECT position('session_token' IN lower(definition)) = 0 FROM contract), false) AS no_session_data_query,
    coalesce((SELECT position('execute ' IN lower(definition)) = 0 FROM contract), false) AS no_dynamic_sql
FROM expected;

WITH projection AS (
    SELECT public.exos_v2_maxis_live_projector_projection() AS payload
), team_keys AS (
    SELECT array_agg(DISTINCT key ORDER BY key) AS keys
    FROM projection
    CROSS JOIN LATERAL jsonb_array_elements(payload -> 'Teams') AS team(value)
    CROSS JOIN LATERAL jsonb_object_keys(team.value) AS key
)
SELECT
    (SELECT payload IS NOT NULL FROM projection) AS projection_returned,
    (SELECT array_agg(key ORDER BY key) FROM projection CROSS JOIN LATERAL jsonb_object_keys(payload) AS key)
        = ARRAY['Event', 'Teams'] AS root_allow_list_exact,
    (SELECT array_agg(key ORDER BY key) FROM projection CROSS JOIN LATERAL jsonb_object_keys(payload -> 'Event') AS key)
        = ARRAY['DisplayName', 'HasAwardedScore', 'State'] AS event_allow_list_exact,
    (SELECT keys FROM team_keys) = ARRAY['Completed', 'Country', 'Flag', 'Rank', 'Score', 'Total'] AS team_allow_list_exact,
    (SELECT jsonb_array_length(payload -> 'Teams') = 6 FROM projection) AS six_teams_returned,
    (SELECT bool_and((team.value ->> 'Total')::integer = (SELECT max((value ->> 'Total')::integer) FROM jsonb_array_elements(payload -> 'Teams') AS second_team(value)))
     FROM projection CROSS JOIN LATERAL jsonb_array_elements(payload -> 'Teams') AS team(value)) AS dynamic_total_consistent;
