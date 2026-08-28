-- Additive privilege-only remediation for an installed 037 Theme Park Race
-- engine.  It contains no function bodies, tables, data, triggers, or event
-- changes.  Run only through the approved staging release process, before
-- installing 038.
BEGIN;

-- Revoke preserved CREATE OR REPLACE ACLs before re-granting the exact 037
-- contract.  The submission guard is trigger-internal and has no application
-- EXECUTE grant.
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_save_configuration(text,jsonb,text) FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_set_theme_park_race_runtime_phase(text,text,text) FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_submit(text,text,jsonb) FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_submission_guard() FROM anon, authenticated, service_role, PUBLIC;

GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_save_configuration(text,jsonb,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_set_theme_park_race_runtime_phase(text,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_submit(text,text,jsonb) TO anon, authenticated, service_role;

COMMIT;
