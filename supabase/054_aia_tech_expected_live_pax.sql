-- AIA Tech production-candidate metadata only.
-- This does not alter team capacity, registration, attendance, identities,
-- mission content, scoring, runtime, or any event other than the disposable AIA UAT.
BEGIN;

DO $guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = 'AIA-TECH-20261023-UAT') THEN
        RAISE EXCEPTION 'AIA UAT event is not installed';
    END IF;
    IF EXISTS (SELECT 1 FROM public.activity_runtime_v2 WHERE event_id = 'AIA-TECH-20261023-UAT')
       OR EXISTS (SELECT 1 FROM public.submissions_v2 WHERE event_id = 'AIA-TECH-20261023-UAT')
       OR EXISTS (SELECT 1 FROM public.score_transactions_v2 WHERE event_id = 'AIA-TECH-20261023-UAT') THEN
        RAISE EXCEPTION 'AIA expected-pax metadata is frozen after runtime, submission, or score state exists';
    END IF;
    IF coalesce((SELECT event_payload ->> 'ExpectedParticipants'
                 FROM public.events_v2 WHERE event_id = 'AIA-TECH-20261023-UAT'), '') NOT IN ('199', '250') THEN
        RAISE EXCEPTION 'AIA expected-pax metadata has an unexpected value';
    END IF;
END
$guard$;

UPDATE public.events_v2
   SET event_payload = jsonb_set(
           jsonb_set(coalesce(event_payload, '{}'::jsonb), '{ExpectedParticipants}', '199'::jsonb, true),
           '{LoadCertificationTarget}', '250'::jsonb, true
       ) || jsonb_build_object('FinalTeamConfiguration', 'OWNER_PENDING'),
       updated_at = now()
 WHERE event_id = 'AIA-TECH-20261023-UAT';

INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
VALUES (
    'AIA-TECH-20261023-UAT', 'aia_production_hardening',
    'AIA_EXPECTED_LIVE_PAX_UPDATED', 'events_v2', 'AIA-TECH-20261023-UAT',
    jsonb_build_object('ExpectedParticipants', 199, 'LoadCertificationTarget', 250, 'FinalTeamConfiguration', 'OWNER_PENDING')
);

DO $assert$
BEGIN
    IF coalesce((SELECT event_payload ->> 'ExpectedParticipants'
                 FROM public.events_v2 WHERE event_id = 'AIA-TECH-20261023-UAT'), '') <> '199'
       OR coalesce((SELECT event_payload ->> 'LoadCertificationTarget'
                    FROM public.events_v2 WHERE event_id = 'AIA-TECH-20261023-UAT'), '') <> '250'
       OR coalesce((SELECT event_payload ->> 'FinalTeamConfiguration'
                    FROM public.events_v2 WHERE event_id = 'AIA-TECH-20261023-UAT'), '') <> 'OWNER_PENDING' THEN
        RAISE EXCEPTION 'AIA production-candidate pax metadata assertion failed';
    END IF;
END
$assert$;

COMMIT;
