-- Guarded rollback for 036_exos_core_v2_team_formation_v1.sql.
--
-- This rollback is permitted only before any event has been configured or any
-- Team Formation data/session state exists. Once a formation has opened, the
-- safe operational rollback is to lock that event and preserve its canonical
-- participant, team, Captain, and audit history.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM public.events_v2
         WHERE coalesce(event_payload #>> '{TeamFormation,SchemaVersion}', '') = '1'
    ) THEN
        RAISE EXCEPTION
            'Rollback blocked: Team Formation events exist. Preserve data and lock the event instead.';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM public.participants_v2
         WHERE enrollment_credential_hash IS NOT NULL
            OR is_team_formation_captain
    ) THEN
        RAISE EXCEPTION
            'Rollback blocked: Team Formation participant state exists.';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM public.team_access_sessions_v2
         WHERE team_formation_captain_participant_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'Rollback blocked: Team Formation Captain session state exists.';
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_team_formation_participant_write_guard_trg
    ON public.participants_v2;
DROP TRIGGER IF EXISTS exos_v2_team_formation_team_write_guard_trg
    ON public.teams_v2;
DROP TRIGGER IF EXISTS exos_v2_team_formation_captain_session_guard_trg
    ON public.team_access_sessions_v2;

DROP FUNCTION IF EXISTS public.exos_v2_transfer_team_formation_captain(text,text,uuid,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_recover_team_formation_captain(text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_claim_team_formation_captain(uuid,text);
DROP FUNCTION IF EXISTS public.exos_v2_recover_team_formation_participant(text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_team_formation_claim_preassigned(text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_team_formation_register_random(text,text,text,text);
DROP FUNCTION IF EXISTS public.exos_v2_activate_team_formation(text,text);
DROP FUNCTION IF EXISTS public.exos_v2_open_team_captain_selection(text,text);
DROP FUNCTION IF EXISTS public.exos_v2_lock_team_formation(text,text);
DROP FUNCTION IF EXISTS public.exos_v2_open_team_formation(text,text);
DROP FUNCTION IF EXISTS public.exos_v2_configure_team_formation(text,text,jsonb,jsonb,text);
DROP FUNCTION IF EXISTS public.exos_v2_team_formation_team_write_guard();
DROP FUNCTION IF EXISTS public.exos_v2_team_formation_participant_write_guard();
DROP FUNCTION IF EXISTS public.exos_v2_team_formation_captain_session_guard();
DROP FUNCTION IF EXISTS public.exos_v2_team_formation_credential_hash(text);

DROP INDEX IF EXISTS public.team_access_sessions_v2_one_active_tf_captain_uidx;
DROP INDEX IF EXISTS public.participants_v2_one_team_formation_captain_uidx;
DROP INDEX IF EXISTS public.participants_v2_event_enrollment_credential_hash_active_uidx;
DROP INDEX IF EXISTS public.participants_v2_team_formation_occupancy_idx;

ALTER TABLE public.team_access_sessions_v2
    DROP CONSTRAINT IF EXISTS team_access_sessions_v2_tf_captain_fkey,
    DROP CONSTRAINT IF EXISTS team_access_sessions_v2_event_team_tf_fkey;
ALTER TABLE public.team_access_credentials_v2
    DROP CONSTRAINT IF EXISTS team_access_credentials_v2_event_team_tf_fkey;
ALTER TABLE public.participant_sessions_v2
    DROP CONSTRAINT IF EXISTS participant_sessions_v2_event_participant_tf_fkey;
ALTER TABLE public.participants_v2
    DROP CONSTRAINT IF EXISTS participants_v2_event_team_tf_fkey,
    DROP CONSTRAINT IF EXISTS participants_v2_enrollment_credential_hash_format;
ALTER TABLE public.teams_v2
    DROP CONSTRAINT IF EXISTS teams_v2_team_capacity_positive;

ALTER TABLE public.team_access_sessions_v2
    DROP COLUMN IF EXISTS team_formation_captain_participant_id;
ALTER TABLE public.participants_v2
    DROP COLUMN IF EXISTS is_team_formation_captain,
    DROP COLUMN IF EXISTS enrollment_credential_hash;
ALTER TABLE public.teams_v2
    DROP COLUMN IF EXISTS team_capacity;

COMMIT;
