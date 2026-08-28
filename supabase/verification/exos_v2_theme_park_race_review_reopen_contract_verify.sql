-- Read-only verifier for 039 Theme Park Race board review/reopen contract.
WITH target AS (
    SELECT to_regprocedure('public.exos_v2_theme_park_race_board_review(uuid,timestamp with time zone,public.exos_v2_review_decision,numeric,text,text,text)') AS oid
)
SELECT oid IS NOT NULL AS exact_signature_present,
       coalesce((SELECT prosecdef FROM pg_proc WHERE oid=target.oid), false) AS security_definer,
       coalesce((SELECT EXISTS (SELECT 1 FROM unnest(proconfig) AS x(setting) WHERE x.setting IN ('search_path=', 'search_path=""')) FROM pg_proc WHERE oid=target.oid), false) AS search_path_pinned_to_empty,
       NOT coalesce((SELECT bool_or(a.grantee=0 AND a.privilege_type='EXECUTE') FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE p.oid=target.oid), false) AS public_execute_revoked,
       NOT EXISTS (SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a JOIN pg_roles r ON r.oid=a.grantee WHERE p.oid=target.oid AND a.privilege_type='EXECUTE' AND r.rolname IN ('anon','authenticated')) AS no_anon_authenticated_execute,
       coalesce((SELECT has_function_privilege('service_role', target.oid, 'EXECUTE')), false) AS service_role_execute_present,
       (SELECT count(*)=1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='exos_v2_theme_park_race_board_review') AS no_unexpected_overloads,
       to_regprocedure('public.exos_v2_theme_park_race_board_submit(text,text,jsonb)') IS NOT NULL AS board_submit_present,
       to_regprocedure('public.exos_v2_standard_review_submission(uuid,public.exos_v2_review_decision,numeric,text,text,text)') IS NOT NULL AS standard_review_present,
       to_regprocedure('public.exos_v2_theme_park_race_save_configuration(text,jsonb,text)') IS NOT NULL AS migration_037_038_configuration_present
FROM target;
