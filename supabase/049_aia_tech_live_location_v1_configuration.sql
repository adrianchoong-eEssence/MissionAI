-- AIA UAT integration for EXOS Live Location V1.
-- Apply only after 048 and only when an owner supplies the real tracking window.
BEGIN;

DO $guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = 'AIA-TECH-20261023-UAT') THEN
        RAISE EXCEPTION 'AIA UAT event is not installed';
    END IF;
    IF EXISTS (SELECT 1 FROM public.activity_runtime_v2 WHERE event_id = 'AIA-TECH-20261023-UAT')
       OR EXISTS (SELECT 1 FROM public.submissions_v2 WHERE event_id = 'AIA-TECH-20261023-UAT') THEN
        RAISE EXCEPTION 'AIA location configuration must be installed before live runtime or submissions';
    END IF;
END
$guard$;

-- Capability is configured for individual AIA participants but deliberately
-- inactive until Mission Control receives an owner-approved event window.
SELECT public.exos_v2_configure_live_location(
    'AIA-TECH-20261023-UAT', false, 'INDIVIDUAL', NULL, NULL,
    20, 90, 24, 1000, 250, 'aia_location_v1_configuration'
);

UPDATE public.events_v2
   SET event_payload = jsonb_set(
       event_payload, '{LiveLocation}',
       jsonb_build_object('SchemaVersion', 1, 'CapabilityConfigured', true,
           'TrackingMode', 'INDIVIDUAL', 'Purpose', jsonb_build_array('operations', 'participant_team_visibility', 'safety', 'team_coordination'),
           'AwardsMissionScore', false, 'WindowStatus', 'OWNER_WINDOW_REQUIRED'), true
   ), updated_at = now()
 WHERE event_id = 'AIA-TECH-20261023-UAT';

INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
VALUES ('AIA-TECH-20261023-UAT', 'aia_location_v1_configuration', 'AIA_LIVE_LOCATION_CAPABILITY_CONFIGURED',
    'events_v2', 'AIA-TECH-20261023-UAT', jsonb_build_object('TrackingMode', 'INDIVIDUAL', 'AwardsMissionScore', false));

COMMIT;
