-- AIA Tech's additive, fixed-event RANDOM_ASSIGN registration endpoint.
--
-- This does not alter EXOS Core. It composes the existing, concurrency-safe
-- Team Formation RANDOM_ASSIGN RPC with the existing P0-A attendance RPC for
-- the single disposable AIA UAT event only.
BEGIN;

CREATE OR REPLACE FUNCTION public.exos_v2_aia_tech_register_random(
    p_display_name text,
    p_device_id text,
    p_enrollment_credential text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_identity jsonb;
    v_participant_id uuid;
BEGIN
    IF nullif(trim(p_device_id), '') IS NULL
       OR p_enrollment_credential IS NULL
       OR length(trim(p_display_name)) NOT BETWEEN 2 AND 120
       OR trim(p_display_name) !~ '^[[:alpha:]][[:alpha:] .''-]{1,119}$' THEN
        RAISE EXCEPTION 'Enter a valid first and last name.';
    END IF;

    -- The join code is deliberately fixed inside this AIA-only endpoint. No
    -- caller can select another event, team, attendance state, or actor.
    v_identity := public.exos_v2_team_formation_register_random(
        'AIAUAT', trim(regexp_replace(p_display_name, '[[:space:]]+', ' ', 'g')),
        trim(p_device_id), p_enrollment_credential
    );
    v_participant_id := nullif(v_identity ->> 'ParticipantID', '')::uuid;
    IF v_participant_id IS NULL
       OR coalesce(v_identity ->> 'EventID', '') <> 'AIA-TECH-20261023-UAT' THEN
        RAISE EXCEPTION 'AIA registration did not resolve a canonical participant.';
    END IF;

    -- The first registration and attendance write share one transaction. The
    -- core registration lock makes same-device retries idempotent; this guard
    -- prevents a retry from emitting a second P0-A attendance audit mutation.
    IF NOT EXISTS (
        SELECT 1 FROM public.participant_attendance_v2 a
         WHERE a.event_id = 'AIA-TECH-20261023-UAT'
           AND a.participant_id = v_participant_id
    ) THEN
        PERFORM public.exos_v2_set_participant_attendance(
            'AIA-TECH-20261023-UAT', v_participant_id, 'PRESENT',
            'aia_random_self_registration', 'SELF_REGISTRATION'
        );
    END IF;

    RETURN v_identity || jsonb_build_object('AttendanceState', 'PRESENT');
END;
$$;

REVOKE ALL ON FUNCTION public.exos_v2_aia_tech_register_random(text, text, text)
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_aia_tech_register_random(text, text, text)
    TO anon, authenticated;

COMMIT;
