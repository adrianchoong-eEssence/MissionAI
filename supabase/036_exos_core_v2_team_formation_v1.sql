-- EXOS Core v2 Team Formation V1.
--
-- Additive Sprint 2 foundation. This introduces a configuration-gated Core
-- capability only; it does not create a Genting programme, change a UI route,
-- replace an existing Standard/R.A.C.E. RPC, or alter an existing event row.
--
-- Dependencies: live Core v2 catalog from 020/021/022/026. Installation must
-- be decided from the live catalog, never from Supabase migration history.
-- Existing events remain on their present paths unless a facilitator explicitly
-- configures event_payload.TeamFormation.SchemaVersion = 1 through this file.
--
-- The TeamFormation contract is:
--   Mode  = RANDOM_ASSIGN | PREASSIGNED
--   Phase = DRAFT | REGISTRATION_OPEN | FORMATION_LOCKED |
--           CAPTAIN_SELECTION | ACTIVE
--
-- Formula R.A.C.E. access functions and result contracts are not replaced.
-- No fixture or test event is created here.

BEGIN;

DO $$
DECLARE
    v_required text[] := ARRAY[
        'events_v2',
        'teams_v2',
        'participants_v2',
        'participant_sessions_v2',
        'team_access_credentials_v2',
        'team_access_sessions_v2',
        'audit_log_v2'
    ];
    v_name text;
BEGIN
    FOREACH v_name IN ARRAY v_required LOOP
        IF to_regclass('public.' || v_name) IS NULL THEN
            RAISE EXCEPTION 'EXOS Team Formation V1 requires public.%', v_name;
        END IF;
    END LOOP;
END;
$$;

-- Existing events deliberately receive NULL capacity and no TeamFormation
-- payload. Capacity becomes mandatory only when the configuration RPC enables
-- this capability for an event.
ALTER TABLE public.teams_v2
    ADD COLUMN IF NOT EXISTS team_capacity integer;

ALTER TABLE public.participants_v2
    ADD COLUMN IF NOT EXISTS enrollment_credential_hash text,
    ADD COLUMN IF NOT EXISTS is_team_formation_captain boolean NOT NULL DEFAULT false;

ALTER TABLE public.team_access_sessions_v2
    ADD COLUMN IF NOT EXISTS team_formation_captain_participant_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.teams_v2'::regclass
           AND conname = 'teams_v2_team_capacity_positive'
    ) THEN
        ALTER TABLE public.teams_v2
            ADD CONSTRAINT teams_v2_team_capacity_positive
            CHECK (team_capacity IS NULL OR team_capacity > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.participants_v2'::regclass
           AND conname = 'participants_v2_enrollment_credential_hash_format'
    ) THEN
        ALTER TABLE public.participants_v2
            ADD CONSTRAINT participants_v2_enrollment_credential_hash_format
            CHECK (
                enrollment_credential_hash IS NULL
                OR enrollment_credential_hash ~ '^[0-9a-f]{64}$'
            );
    END IF;

    -- These composite foreign keys are deliberately NOT VALID. They leave all
    -- historical rows untouched while enforcing event/team consistency on every
    -- new or changed Team Formation boundary row after installation.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.participants_v2'::regclass
           AND conname = 'participants_v2_event_team_tf_fkey'
    ) THEN
        ALTER TABLE public.participants_v2
            ADD CONSTRAINT participants_v2_event_team_tf_fkey
            FOREIGN KEY (event_id, team_id)
            REFERENCES public.teams_v2(event_id, team_id)
            ON DELETE RESTRICT NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.participant_sessions_v2'::regclass
           AND conname = 'participant_sessions_v2_event_participant_tf_fkey'
    ) THEN
        ALTER TABLE public.participant_sessions_v2
            ADD CONSTRAINT participant_sessions_v2_event_participant_tf_fkey
            FOREIGN KEY (event_id, participant_id)
            REFERENCES public.participants_v2(event_id, participant_id)
            ON DELETE CASCADE NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.team_access_credentials_v2'::regclass
           AND conname = 'team_access_credentials_v2_event_team_tf_fkey'
    ) THEN
        ALTER TABLE public.team_access_credentials_v2
            ADD CONSTRAINT team_access_credentials_v2_event_team_tf_fkey
            FOREIGN KEY (event_id, team_id)
            REFERENCES public.teams_v2(event_id, team_id)
            ON DELETE CASCADE NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.team_access_sessions_v2'::regclass
           AND conname = 'team_access_sessions_v2_event_team_tf_fkey'
    ) THEN
        ALTER TABLE public.team_access_sessions_v2
            ADD CONSTRAINT team_access_sessions_v2_event_team_tf_fkey
            FOREIGN KEY (event_id, team_id)
            REFERENCES public.teams_v2(event_id, team_id)
            ON DELETE CASCADE NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.team_access_sessions_v2'::regclass
           AND conname = 'team_access_sessions_v2_tf_captain_fkey'
    ) THEN
        ALTER TABLE public.team_access_sessions_v2
            ADD CONSTRAINT team_access_sessions_v2_tf_captain_fkey
            FOREIGN KEY (event_id, team_formation_captain_participant_id)
            REFERENCES public.participants_v2(event_id, participant_id)
            ON DELETE RESTRICT NOT VALID;
    END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS participants_v2_event_enrollment_credential_hash_active_uidx
    ON public.participants_v2(event_id, enrollment_credential_hash)
    WHERE enrollment_credential_hash IS NOT NULL
      AND merged_into_participant_id IS NULL
      AND NOT is_archived;

CREATE UNIQUE INDEX IF NOT EXISTS participants_v2_one_team_formation_captain_uidx
    ON public.participants_v2(event_id, team_id)
    WHERE is_team_formation_captain
      AND merged_into_participant_id IS NULL
      AND NOT is_archived;

CREATE UNIQUE INDEX IF NOT EXISTS team_access_sessions_v2_one_active_tf_captain_uidx
    ON public.team_access_sessions_v2(event_id, team_id)
    WHERE is_active
      AND team_formation_captain_participant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS participants_v2_team_formation_occupancy_idx
    ON public.participants_v2(event_id, team_id)
    WHERE merged_into_participant_id IS NULL
      AND NOT is_archived;

-- The plaintext enrollment credential is a bearer recovery secret. It must be
-- generated as base64url(32 random bytes), persisted by the joining device
-- before its first registration request, and never written to a database row,
-- audit record, or RPC response. The deterministic SHA-256 digest is safe to
-- index because the accepted credential has at least 256 bits of entropy.
CREATE OR REPLACE FUNCTION public.exos_v2_team_formation_credential_hash(
    p_enrollment_credential text
)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = ''
AS $$
BEGIN
    IF p_enrollment_credential !~ '^[A-Za-z0-9_-]{43,128}$' THEN
        RAISE EXCEPTION
            'Team Formation enrollment credential must be a 43-to-128 character base64url secret';
    END IF;
    RETURN encode(extensions.digest(p_enrollment_credential, 'sha256'), 'hex');
END;
$$;

-- A configured Team Formation event cannot be mutated by legacy registration
-- or direct table writers. Approved Team Formation RPCs set this transaction-
-- local capability after they have locked the owning event.
CREATE OR REPLACE FUNCTION public.exos_v2_team_formation_participant_write_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_scope_event_id text;
    v_payload jsonb;
BEGIN
    FOR v_scope_event_id IN
        SELECT DISTINCT candidate.event_id
          FROM (
              VALUES
                  (CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN NEW.event_id ELSE NULL END),
                  (CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN OLD.event_id ELSE NULL END)
          ) AS candidate(event_id)
         WHERE candidate.event_id IS NOT NULL
    LOOP
        SELECT event_payload INTO v_payload
          FROM public.events_v2
         WHERE event_id = v_scope_event_id;

        IF coalesce(v_payload #>> '{TeamFormation,SchemaVersion}', '') = '1'
           AND current_setting('exos.team_formation_write', true)
               IS DISTINCT FROM v_scope_event_id THEN
            RAISE EXCEPTION
                'Team Formation participant records may only be changed through approved Team Formation RPCs';
        END IF;
    END LOOP;

    IF TG_OP = 'UPDATE'
       AND NEW.team_id IS DISTINCT FROM OLD.team_id THEN
        SELECT event_payload INTO v_payload
          FROM public.events_v2
         WHERE event_id = OLD.event_id;
        IF coalesce(v_payload #>> '{TeamFormation,SchemaVersion}', '') = '1' THEN
            RAISE EXCEPTION
                'Team Formation membership is immutable after assignment';
        END IF;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_team_formation_team_write_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_payload jsonb;
    v_phase text;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.team_capacity IS DISTINCT FROM OLD.team_capacity THEN
        SELECT event_payload INTO v_payload
          FROM public.events_v2
         WHERE event_id = NEW.event_id;
        v_phase := coalesce(v_payload #>> '{TeamFormation,Phase}', '');

        IF coalesce(v_payload #>> '{TeamFormation,SchemaVersion}', '') = '1'
           AND (
               current_setting('exos.team_formation_write', true)
                   IS DISTINCT FROM NEW.event_id
               OR v_phase <> 'DRAFT'
           ) THEN
            RAISE EXCEPTION
                'Team Formation capacity is immutable after registration opens';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

-- A non-null Team Formation Captain link must resolve to the same event/team
-- participant that is currently the effective Team Formation Captain. Existing
-- Formula R.A.C.E. rows retain NULL in this new column and are unaffected.
CREATE OR REPLACE FUNCTION public.exos_v2_team_formation_captain_session_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_participant public.participants_v2%rowtype;
BEGIN
    IF NEW.team_formation_captain_participant_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT * INTO v_participant
      FROM public.participants_v2
     WHERE participant_id = NEW.team_formation_captain_participant_id
       AND event_id = NEW.event_id
       AND team_id = NEW.team_id
       AND is_team_formation_captain
       AND merged_into_participant_id IS NULL
       AND NOT is_archived;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Team Formation Captain session must belong to the effective Captain of the same event team';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_team_formation_participant_write_guard_trg
    ON public.participants_v2;
CREATE TRIGGER exos_v2_team_formation_participant_write_guard_trg
BEFORE INSERT OR UPDATE OR DELETE ON public.participants_v2
FOR EACH ROW EXECUTE FUNCTION public.exos_v2_team_formation_participant_write_guard();

DROP TRIGGER IF EXISTS exos_v2_team_formation_team_write_guard_trg
    ON public.teams_v2;
CREATE TRIGGER exos_v2_team_formation_team_write_guard_trg
BEFORE UPDATE OF team_capacity ON public.teams_v2
FOR EACH ROW EXECUTE FUNCTION public.exos_v2_team_formation_team_write_guard();

DROP TRIGGER IF EXISTS exos_v2_team_formation_captain_session_guard_trg
    ON public.team_access_sessions_v2;
CREATE TRIGGER exos_v2_team_formation_captain_session_guard_trg
BEFORE INSERT OR UPDATE OF event_id, team_id, team_formation_captain_participant_id
ON public.team_access_sessions_v2
FOR EACH ROW EXECUTE FUNCTION public.exos_v2_team_formation_captain_session_guard();

CREATE OR REPLACE FUNCTION public.exos_v2_configure_team_formation(
    p_event_id text,
    p_mode text,
    p_team_capacities jsonb,
    p_preassigned_roster jsonb DEFAULT '[]'::jsonb,
    p_actor text DEFAULT 'Facilitator'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_mode text;
    v_config jsonb;
    v_team_count integer;
    v_capacity_count integer;
    v_roster_count integer := 0;
    v_existing_count integer;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL
       OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID and facilitator identity are required';
    END IF;

    v_mode := upper(trim(p_mode));
    IF v_mode NOT IN ('RANDOM_ASSIGN', 'PREASSIGNED') THEN
        RAISE EXCEPTION 'Team Formation Mode must be RANDOM_ASSIGN or PREASSIGNED';
    END IF;
    IF jsonb_typeof(p_team_capacities) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'Team capacities must be a TeamID-to-positive-integer object';
    END IF;
    IF jsonb_typeof(p_preassigned_roster) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'Preassigned roster must be an array';
    END IF;

    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id)
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event not found';
    END IF;
    IF v_event.event_payload ? 'RaceConfiguration' THEN
        RAISE EXCEPTION 'Team Formation V1 does not reconfigure Formula R.A.C.E. events';
    END IF;
    IF coalesce(v_event.event_payload #>> '{TeamFormation,SchemaVersion}', '') = '1' THEN
        RAISE EXCEPTION 'Team Formation is already configured for this event';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41)
    );
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);

    SELECT count(*) INTO v_team_count
      FROM public.teams_v2
     WHERE event_id = v_event.event_id
       AND is_active;
    IF v_team_count = 0 THEN
        RAISE EXCEPTION 'Team Formation requires at least one active team';
    END IF;

    SELECT count(*) INTO v_capacity_count
      FROM jsonb_object_keys(p_team_capacities);
    IF v_capacity_count <> v_team_count THEN
        RAISE EXCEPTION 'Every active team requires exactly one capacity';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM jsonb_each_text(p_team_capacities) AS supplied(team_id, capacity)
         WHERE supplied.capacity !~ '^[1-9][0-9]*$'
    ) THEN
        RAISE EXCEPTION 'Every team capacity must be a positive integer';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM jsonb_object_keys(p_team_capacities) AS supplied(team_id)
         WHERE NOT EXISTS (
             SELECT 1
               FROM public.teams_v2 t
              WHERE t.event_id = v_event.event_id
                AND t.team_id = supplied.team_id
                AND t.is_active
         )
    ) THEN
        RAISE EXCEPTION 'Team capacity references an inactive or foreign team';
    END IF;

    SELECT count(*) INTO v_existing_count
      FROM public.participants_v2
     WHERE event_id = v_event.event_id
       AND merged_into_participant_id IS NULL
       AND NOT is_archived;
    IF v_existing_count > 0 THEN
        RAISE EXCEPTION 'Team Formation must be configured before participant records exist';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM public.team_access_credentials_v2
         WHERE event_id = v_event.event_id
           AND is_active
    ) THEN
        RAISE EXCEPTION 'Team Formation requires an event without active team-access credentials';
    END IF;

    IF v_mode = 'RANDOM_ASSIGN' AND jsonb_array_length(p_preassigned_roster) <> 0 THEN
        RAISE EXCEPTION 'RANDOM_ASSIGN does not accept a preassigned roster';
    END IF;

    IF v_mode = 'PREASSIGNED' THEN
        SELECT count(*) INTO v_roster_count
          FROM jsonb_array_elements(p_preassigned_roster);
        IF v_roster_count = 0 THEN
            RAISE EXCEPTION 'PREASSIGNED requires at least one roster member';
        END IF;
        IF EXISTS (
            SELECT 1
              FROM jsonb_array_elements(p_preassigned_roster) AS roster(item)
             WHERE coalesce(roster.item->>'EnrollmentCredentialHash', '')
                   !~ '^[0-9a-f]{64}$'
                OR nullif(trim(roster.item->>'DisplayName'), '') IS NULL
                OR nullif(trim(roster.item->>'TeamID'), '') IS NULL
        ) THEN
            RAISE EXCEPTION
                'Each preassigned roster member requires EnrollmentCredentialHash, DisplayName, and TeamID';
        END IF;
        IF EXISTS (
            SELECT 1
              FROM (
                  SELECT roster.item->>'EnrollmentCredentialHash' AS enrollment_credential_hash,
                         count(*) AS key_count
                    FROM jsonb_array_elements(p_preassigned_roster) AS roster(item)
                   GROUP BY 1
              ) duplicates
             WHERE duplicates.key_count > 1
        ) THEN
            RAISE EXCEPTION 'Preassigned enrollment credential hashes must be unique within the event';
        END IF;
        IF EXISTS (
            SELECT 1
              FROM jsonb_array_elements(p_preassigned_roster) AS roster(item)
             WHERE NOT EXISTS (
                 SELECT 1
                   FROM public.teams_v2 t
                  WHERE t.event_id = v_event.event_id
                    AND t.team_id = trim(roster.item->>'TeamID')
                    AND t.is_active
             )
        ) THEN
            RAISE EXCEPTION 'Preassigned roster references an inactive or foreign team';
        END IF;
        IF EXISTS (
            SELECT 1
              FROM (
                  SELECT trim(roster.item->>'TeamID') AS team_id,
                         count(*) AS assigned_count
                    FROM jsonb_array_elements(p_preassigned_roster) AS roster(item)
                   GROUP BY 1
              ) allocation
              JOIN public.teams_v2 t
                ON t.event_id = v_event.event_id
               AND t.team_id = allocation.team_id
             WHERE allocation.assigned_count > (
                 p_team_capacities ->> allocation.team_id
             )::integer
        ) THEN
            RAISE EXCEPTION 'Preassigned roster exceeds at least one team capacity';
        END IF;
    END IF;

    UPDATE public.teams_v2
       SET team_capacity = (p_team_capacities ->> team_id)::integer
     WHERE event_id = v_event.event_id
       AND is_active;

    v_config := jsonb_build_object(
        'SchemaVersion', 1,
        'Mode', v_mode,
        'Phase', 'DRAFT',
        'ConfiguredAt', now(),
        'ConfiguredBy', trim(p_actor)
    );
    UPDATE public.events_v2
       SET event_payload = jsonb_set(
               coalesce(event_payload, '{}'::jsonb),
               '{TeamFormation}',
               v_config,
               true
           ),
           updated_at = now()
     WHERE event_id = v_event.event_id;

    -- The internal credential satisfies the existing team-access session
    -- foreign key. It is never exposed as a PIN or used by Formula R.A.C.E.
    INSERT INTO public.team_access_credentials_v2 (
        event_id, team_id, credential_hash, credential_purpose, is_active, created_by
    )
    SELECT v_event.event_id,
           t.team_id,
           extensions.crypt(
               extensions.gen_random_uuid()::text,
               extensions.gen_salt('bf')
           ),
           'TEAM_FORMATION_CAPTAIN',
           true,
           trim(p_actor)
      FROM public.teams_v2 t
     WHERE t.event_id = v_event.event_id
       AND t.is_active;

    IF v_mode = 'PREASSIGNED' THEN
        INSERT INTO public.participants_v2 (
            event_id,
            team_id,
            normalized_name,
            display_name,
            participant_payload,
            country,
            flag,
            participant_status,
            enrollment_credential_hash
        )
        SELECT v_event.event_id,
               trim(roster.item->>'TeamID'),
               public.exos_v2_normalize_participant_name(roster.item->>'DisplayName'),
               trim(roster.item->>'DisplayName'),
               jsonb_build_object(
                   'TeamFormation', jsonb_build_object(
                       'SchemaVersion', 1,
                       'Mode', 'PREASSIGNED'
                   )
               ),
               t.country,
               t.team_flag,
               'PREASSIGNED',
               roster.item->>'EnrollmentCredentialHash'
          FROM jsonb_array_elements(p_preassigned_roster) AS roster(item)
          JOIN public.teams_v2 t
            ON t.event_id = v_event.event_id
           AND t.team_id = trim(roster.item->>'TeamID');
    END IF;

    INSERT INTO public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, after_state
    ) VALUES (
        v_event.event_id,
        trim(p_actor),
        'TEAM_FORMATION_CONFIGURED',
        'events_v2',
        v_event.event_id,
        jsonb_build_object(
            'TeamFormation', v_config,
            'ActiveTeamCount', v_team_count,
            'PreassignedParticipantCount', v_roster_count
        )
    );

    RETURN jsonb_build_object(
        'EventID', v_event.event_id,
        'Mode', v_mode,
        'Phase', 'DRAFT',
        'ActiveTeamCount', v_team_count,
        'PreassignedParticipantCount', v_roster_count
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_open_team_formation(
    p_event_id text,
    p_actor text DEFAULT 'Facilitator'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_config jsonb;
    v_mode text;
    v_participant_count integer;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL
       OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID and facilitator identity are required';
    END IF;

    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id)
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event not found';
    END IF;
    v_config := v_event.event_payload->'TeamFormation';
    v_mode := upper(coalesce(v_config->>'Mode', ''));
    IF coalesce(v_config->>'SchemaVersion', '') <> '1'
       OR coalesce(v_config->>'Phase', '') <> 'DRAFT' THEN
        RAISE EXCEPTION 'Team Formation must be configured and in DRAFT';
    END IF;
    IF v_mode NOT IN ('RANDOM_ASSIGN', 'PREASSIGNED') THEN
        RAISE EXCEPTION 'Unsupported Team Formation Mode';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41)
    );
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);

    IF EXISTS (
        SELECT 1
          FROM public.teams_v2
         WHERE event_id = v_event.event_id
           AND is_active
           AND team_capacity IS NULL
    ) THEN
        RAISE EXCEPTION 'Every active Team Formation team requires a capacity';
    END IF;

    SELECT count(*) INTO v_participant_count
      FROM public.participants_v2
     WHERE event_id = v_event.event_id
       AND merged_into_participant_id IS NULL
       AND NOT is_archived;
    IF v_mode = 'RANDOM_ASSIGN' AND v_participant_count <> 0 THEN
        RAISE EXCEPTION 'RANDOM_ASSIGN must open before participant creation';
    END IF;
    IF v_mode = 'PREASSIGNED' AND v_participant_count = 0 THEN
        RAISE EXCEPTION 'PREASSIGNED requires provisioned participant records';
    END IF;

    v_config := v_config || jsonb_build_object(
        'Phase', 'REGISTRATION_OPEN',
        'OpenedAt', now(),
        'OpenedBy', trim(p_actor)
    );
    UPDATE public.events_v2
       SET event_payload = jsonb_set(event_payload, '{TeamFormation}', v_config, true),
           updated_at = now()
     WHERE event_id = v_event.event_id;

    INSERT INTO public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, after_state
    ) VALUES (
        v_event.event_id, trim(p_actor), 'TEAM_FORMATION_OPENED',
        'events_v2', v_event.event_id, jsonb_build_object('TeamFormation', v_config)
    );

    RETURN jsonb_build_object(
        'EventID', v_event.event_id,
        'Mode', v_mode,
        'Phase', 'REGISTRATION_OPEN'
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_lock_team_formation(
    p_event_id text,
    p_actor text DEFAULT 'Facilitator'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_config jsonb;
    v_assigned_count integer;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL
       OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID and facilitator identity are required';
    END IF;
    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id)
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event not found';
    END IF;
    v_config := v_event.event_payload->'TeamFormation';
    IF coalesce(v_config->>'SchemaVersion', '') <> '1'
       OR coalesce(v_config->>'Phase', '') <> 'REGISTRATION_OPEN' THEN
        RAISE EXCEPTION 'Team Formation must be open before it can be locked';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41)
    );
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);

    SELECT count(*) INTO v_assigned_count
      FROM public.participants_v2
     WHERE event_id = v_event.event_id
       AND merged_into_participant_id IS NULL
       AND NOT is_archived;

    v_config := v_config || jsonb_build_object(
        'Phase', 'FORMATION_LOCKED',
        'LockedAt', now(),
        'LockedBy', trim(p_actor),
        'AssignedParticipantCount', v_assigned_count
    );
    UPDATE public.events_v2
       SET event_payload = jsonb_set(event_payload, '{TeamFormation}', v_config, true),
           updated_at = now()
     WHERE event_id = v_event.event_id;

    INSERT INTO public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, after_state
    ) VALUES (
        v_event.event_id, trim(p_actor), 'TEAM_FORMATION_LOCKED',
        'events_v2', v_event.event_id, jsonb_build_object('TeamFormation', v_config)
    );

    RETURN jsonb_build_object(
        'EventID', v_event.event_id,
        'Phase', 'FORMATION_LOCKED',
        'AssignedParticipantCount', v_assigned_count
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_open_team_captain_selection(
    p_event_id text,
    p_actor text DEFAULT 'Facilitator'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_config jsonb;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL
       OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID and facilitator identity are required';
    END IF;
    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id)
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event not found';
    END IF;
    v_config := v_event.event_payload->'TeamFormation';
    IF coalesce(v_config->>'SchemaVersion', '') <> '1'
       OR coalesce(v_config->>'Phase', '') <> 'FORMATION_LOCKED' THEN
        RAISE EXCEPTION 'Team Formation must be locked before Captain selection';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM public.teams_v2 t
         WHERE t.event_id = v_event.event_id
           AND t.is_active
           AND NOT EXISTS (
               SELECT 1
                 FROM public.participants_v2 p
                WHERE p.event_id = t.event_id
                  AND p.team_id = t.team_id
                  AND p.merged_into_participant_id IS NULL
                  AND NOT p.is_archived
           )
    ) THEN
        RAISE EXCEPTION 'Every active team requires at least one participant before Captain selection';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41)
    );
    v_config := v_config || jsonb_build_object(
        'Phase', 'CAPTAIN_SELECTION',
        'CaptainSelectionOpenedAt', now(),
        'CaptainSelectionOpenedBy', trim(p_actor)
    );
    UPDATE public.events_v2
       SET event_payload = jsonb_set(event_payload, '{TeamFormation}', v_config, true),
           updated_at = now()
     WHERE event_id = v_event.event_id;

    INSERT INTO public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, after_state
    ) VALUES (
        v_event.event_id, trim(p_actor), 'TEAM_CAPTAIN_SELECTION_OPENED',
        'events_v2', v_event.event_id, jsonb_build_object('TeamFormation', v_config)
    );
    RETURN jsonb_build_object('EventID', v_event.event_id, 'Phase', 'CAPTAIN_SELECTION');
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_activate_team_formation(
    p_event_id text,
    p_actor text DEFAULT 'Facilitator'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_config jsonb;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL
       OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID and facilitator identity are required';
    END IF;
    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id)
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event not found';
    END IF;
    v_config := v_event.event_payload->'TeamFormation';
    IF coalesce(v_config->>'SchemaVersion', '') <> '1'
       OR coalesce(v_config->>'Phase', '') <> 'CAPTAIN_SELECTION' THEN
        RAISE EXCEPTION 'Team Formation must be in Captain selection before activation';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM public.teams_v2 t
         WHERE t.event_id = v_event.event_id
           AND t.is_active
           AND 1 <> (
               SELECT count(*)
                 FROM public.participants_v2 p
                WHERE p.event_id = t.event_id
                  AND p.team_id = t.team_id
                  AND p.is_team_formation_captain
                  AND p.merged_into_participant_id IS NULL
                  AND NOT p.is_archived
           )
    ) THEN
        RAISE EXCEPTION 'Every active team requires exactly one effective Captain before activation';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41)
    );
    v_config := v_config || jsonb_build_object(
        'Phase', 'ACTIVE',
        'ActivatedAt', now(),
        'ActivatedBy', trim(p_actor)
    );
    UPDATE public.events_v2
       SET event_payload = jsonb_set(event_payload, '{TeamFormation}', v_config, true),
           updated_at = now()
     WHERE event_id = v_event.event_id;
    INSERT INTO public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, after_state
    ) VALUES (
        v_event.event_id, trim(p_actor), 'TEAM_FORMATION_ACTIVATED',
        'events_v2', v_event.event_id, jsonb_build_object('TeamFormation', v_config)
    );
    RETURN jsonb_build_object('EventID', v_event.event_id, 'Phase', 'ACTIVE');
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_team_formation_register_random(
    p_join_code text,
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
    v_event public.events_v2%rowtype;
    v_config jsonb;
    v_enrollment_credential_hash text;
    v_idempotency_key text;
    v_participant public.participants_v2%rowtype;
    v_session public.participant_sessions_v2%rowtype;
    v_team public.teams_v2%rowtype;
    v_team_id text;
    v_occupancy integer;
BEGIN
    IF nullif(trim(p_display_name), '') IS NULL
       OR nullif(trim(p_device_id), '') IS NULL
       OR p_enrollment_credential IS NULL THEN
        RAISE EXCEPTION 'Display name, device identifier, and enrollment credential are required';
    END IF;
    v_enrollment_credential_hash :=
        public.exos_v2_team_formation_credential_hash(p_enrollment_credential);

    SELECT * INTO v_event
      FROM public.events_v2
     WHERE join_code = upper(trim(p_join_code))
       AND published_at IS NOT NULL
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invalid or unpublished join code';
    END IF;
    v_config := v_event.event_payload->'TeamFormation';
    IF coalesce(v_config->>'SchemaVersion', '') <> '1'
       OR coalesce(v_config->>'Mode', '') <> 'RANDOM_ASSIGN'
       OR coalesce(v_config->>'Phase', '') <> 'REGISTRATION_OPEN' THEN
        RAISE EXCEPTION 'RANDOM_ASSIGN registration is not open for this event';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41)
    );
    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            v_event.event_id || '|TEAM_FORMATION_ENROLLMENT|' || v_enrollment_credential_hash,
            43
        )
    );
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);

    v_idempotency_key := encode(
        extensions.digest(
            v_event.event_id || '|TEAM_FORMATION|RANDOM_ASSIGN|' ||
            v_enrollment_credential_hash || '|' || lower(trim(p_device_id)),
            'sha256'
        ),
        'hex'
    );

    SELECT * INTO v_participant
      FROM public.participants_v2
     WHERE event_id = v_event.event_id
       AND enrollment_credential_hash = v_enrollment_credential_hash
       AND merged_into_participant_id IS NULL
       AND NOT is_archived
     FOR UPDATE;
    IF FOUND THEN
        SELECT * INTO v_session
          FROM public.participant_sessions_v2
         WHERE event_id = v_event.event_id
           AND participant_id = v_participant.participant_id
           AND is_active
         ORDER BY last_seen_at DESC, created_at DESC
         LIMIT 1
         FOR UPDATE;
        IF FOUND AND lower(trim(v_session.device_id)) = lower(trim(p_device_id)) THEN
            UPDATE public.participant_sessions_v2
               SET last_seen_at = now()
             WHERE participant_session_id = v_session.participant_session_id;
            UPDATE public.participants_v2
               SET last_seen_at = now()
             WHERE participant_id = v_participant.participant_id;
            RETURN public.exos_v2_identity_payload(
                v_event.event_id, v_participant.participant_id
            ) || jsonb_build_object(
                'TeamFormationMode', 'RANDOM_ASSIGN',
                'Idempotent', true
            );
        END IF;
        RETURN (
            public.exos_v2_identity_payload(v_event.event_id, v_participant.participant_id)
            - 'SessionToken'
        ) || jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', false,
            'TeamFormationMode', 'RANDOM_ASSIGN',
            'Message', 'Existing Team Formation participant requires recovery on this device.'
        );
    END IF;

    WITH occupancy AS (
        SELECT t.team_id,
               t.team_capacity,
               count(p.participant_id)::integer AS assigned_count
          FROM public.teams_v2 t
          LEFT JOIN public.participants_v2 p
            ON p.event_id = t.event_id
           AND p.team_id = t.team_id
           AND p.merged_into_participant_id IS NULL
           AND NOT p.is_archived
         WHERE t.event_id = v_event.event_id
           AND t.is_active
         GROUP BY t.team_id, t.team_capacity
    ), eligible AS (
        SELECT *
          FROM occupancy
         WHERE assigned_count < team_capacity
    )
    SELECT team_id, assigned_count
      INTO v_team_id, v_occupancy
      FROM eligible
     WHERE assigned_count = (SELECT min(assigned_count) FROM eligible)
     ORDER BY random()
     LIMIT 1;

    IF v_team_id IS NULL THEN
        RAISE EXCEPTION 'EVENT_FULL';
    END IF;
    SELECT * INTO v_team
     FROM public.teams_v2
     WHERE event_id = v_event.event_id
       AND team_id = v_team_id
     FOR UPDATE;

    INSERT INTO public.participants_v2 (
        event_id, team_id, normalized_name, display_name, participant_payload,
        country, flag, participant_status, enrollment_credential_hash
    ) VALUES (
        v_event.event_id,
        v_team.team_id,
        public.exos_v2_normalize_participant_name(p_display_name),
        trim(p_display_name),
        jsonb_build_object(
            'TeamFormation', jsonb_build_object(
                'SchemaVersion', 1,
                'Mode', 'RANDOM_ASSIGN'
            )
        ),
        v_team.country,
        v_team.team_flag,
        'REGISTERED',
        v_enrollment_credential_hash
    ) RETURNING * INTO v_participant;

    INSERT INTO public.participant_sessions_v2 (
        event_id, participant_id, device_id, idempotency_key, joined_from_client
    ) VALUES (
        v_event.event_id, v_participant.participant_id, trim(p_device_id),
        v_idempotency_key, 'team_formation_random_assign'
    ) ON CONFLICT (event_id, idempotency_key) DO UPDATE
       SET participant_id = excluded.participant_id,
           device_id = excluded.device_id,
           last_seen_at = now(),
           is_active = true
    RETURNING * INTO v_session;

    INSERT INTO public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, after_state
    ) VALUES (
        v_event.event_id, 'team_formation_registration',
        'TEAM_FORMATION_RANDOM_ASSIGNED', 'participants_v2',
        v_participant.participant_id::text,
        jsonb_build_object(
            'participant_id', v_participant.participant_id,
            'team_id', v_team.team_id,
            'occupancy_before_assignment', v_occupancy,
            'mode', 'RANDOM_ASSIGN'
        )
    );

    RETURN public.exos_v2_identity_payload(
        v_event.event_id, v_participant.participant_id
    ) || jsonb_build_object(
        'TeamFormationMode', 'RANDOM_ASSIGN',
        'Idempotent', false
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_team_formation_claim_preassigned(
    p_join_code text,
    p_enrollment_credential text,
    p_device_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_config jsonb;
    v_enrollment_credential_hash text;
    v_idempotency_key text;
    v_participant public.participants_v2%rowtype;
    v_session public.participant_sessions_v2%rowtype;
BEGIN
    IF p_enrollment_credential IS NULL
       OR nullif(trim(p_device_id), '') IS NULL THEN
        RAISE EXCEPTION 'Opaque enrollment credential and device identifier are required';
    END IF;
    v_enrollment_credential_hash :=
        public.exos_v2_team_formation_credential_hash(p_enrollment_credential);

    SELECT * INTO v_event
      FROM public.events_v2
     WHERE join_code = upper(trim(p_join_code))
       AND published_at IS NOT NULL
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invalid or unpublished join code';
    END IF;
    v_config := v_event.event_payload->'TeamFormation';
    IF coalesce(v_config->>'SchemaVersion', '') <> '1'
       OR coalesce(v_config->>'Mode', '') <> 'PREASSIGNED'
       OR coalesce(v_config->>'Phase', '') <> 'REGISTRATION_OPEN' THEN
        RAISE EXCEPTION 'PREASSIGNED registration is not open for this event';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41)
    );
    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            v_event.event_id || '|TEAM_FORMATION_ENROLLMENT|' || v_enrollment_credential_hash,
            43
        )
    );
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);

    SELECT * INTO v_participant
      FROM public.participants_v2
     WHERE event_id = v_event.event_id
       AND enrollment_credential_hash = v_enrollment_credential_hash
       AND merged_into_participant_id IS NULL
       AND NOT is_archived
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PREASSIGNED_ENROLLMENT_NOT_FOUND';
    END IF;

    SELECT * INTO v_session
      FROM public.participant_sessions_v2
     WHERE event_id = v_event.event_id
       AND participant_id = v_participant.participant_id
       AND is_active
     ORDER BY last_seen_at DESC, created_at DESC
     LIMIT 1
     FOR UPDATE;
    IF FOUND AND lower(trim(v_session.device_id)) = lower(trim(p_device_id)) THEN
        UPDATE public.participant_sessions_v2
           SET last_seen_at = now()
         WHERE participant_session_id = v_session.participant_session_id;
        UPDATE public.participants_v2
           SET last_seen_at = now()
         WHERE participant_id = v_participant.participant_id;
        RETURN public.exos_v2_identity_payload(
            v_event.event_id, v_participant.participant_id
        ) || jsonb_build_object(
            'TeamFormationMode', 'PREASSIGNED',
            'Idempotent', true
        );
    END IF;
    IF FOUND THEN
        RETURN (
            public.exos_v2_identity_payload(v_event.event_id, v_participant.participant_id)
            - 'SessionToken'
        ) || jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', false,
            'TeamFormationMode', 'PREASSIGNED',
            'Message', 'Existing Team Formation participant requires recovery on this device.'
        );
    END IF;

    v_idempotency_key := encode(
        extensions.digest(
            v_event.event_id || '|TEAM_FORMATION|PREASSIGNED|' ||
            v_enrollment_credential_hash || '|' || lower(trim(p_device_id)),
            'sha256'
        ),
        'hex'
    );
    INSERT INTO public.participant_sessions_v2 (
        event_id, participant_id, device_id, idempotency_key, joined_from_client
    ) VALUES (
        v_event.event_id, v_participant.participant_id, trim(p_device_id),
        v_idempotency_key, 'team_formation_preassigned_claim'
    ) ON CONFLICT (event_id, idempotency_key) DO UPDATE
       SET participant_id = excluded.participant_id,
           device_id = excluded.device_id,
           last_seen_at = now(),
           is_active = true
    RETURNING * INTO v_session;

    UPDATE public.participants_v2
       SET participant_status = 'REGISTERED',
           last_seen_at = now()
     WHERE participant_id = v_participant.participant_id;

    INSERT INTO public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, after_state
    ) VALUES (
        v_event.event_id, 'team_formation_registration',
        'TEAM_FORMATION_PREASSIGNED_CLAIMED', 'participants_v2',
        v_participant.participant_id::text,
        jsonb_build_object(
            'participant_id', v_participant.participant_id,
            'team_id', v_participant.team_id,
            'mode', 'PREASSIGNED'
        )
    );
    RETURN public.exos_v2_identity_payload(
        v_event.event_id, v_participant.participant_id
    ) || jsonb_build_object(
        'TeamFormationMode', 'PREASSIGNED',
        'Idempotent', false
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_recover_team_formation_participant(
    p_join_code text,
    p_enrollment_credential text,
    p_device_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_config jsonb;
    v_enrollment_credential_hash text;
    v_idempotency_key text;
    v_participant public.participants_v2%rowtype;
    v_session public.participant_sessions_v2%rowtype;
BEGIN
    IF p_enrollment_credential IS NULL
       OR nullif(trim(p_device_id), '') IS NULL THEN
        RAISE EXCEPTION 'Opaque enrollment credential and device identifier are required';
    END IF;
    v_enrollment_credential_hash :=
        public.exos_v2_team_formation_credential_hash(p_enrollment_credential);

    SELECT * INTO v_event
      FROM public.events_v2
     WHERE join_code = upper(trim(p_join_code))
       AND published_at IS NOT NULL
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invalid or unpublished join code';
    END IF;
    v_config := v_event.event_payload->'TeamFormation';
    IF coalesce(v_config->>'SchemaVersion', '') <> '1'
       OR coalesce(v_config->>'Phase', '') NOT IN (
           'REGISTRATION_OPEN', 'FORMATION_LOCKED', 'CAPTAIN_SELECTION', 'ACTIVE'
       ) THEN
        RAISE EXCEPTION 'Team Formation recovery is unavailable for this event phase';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41)
    );
    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            v_event.event_id || '|TEAM_FORMATION_ENROLLMENT|' || v_enrollment_credential_hash,
            43
        )
    );
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);

    SELECT * INTO v_participant
      FROM public.participants_v2
     WHERE event_id = v_event.event_id
       AND enrollment_credential_hash = v_enrollment_credential_hash
       AND merged_into_participant_id IS NULL
       AND NOT is_archived
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TEAM_FORMATION_RECOVERY_CREDENTIAL_INVALID';
    END IF;

    v_idempotency_key := encode(
        extensions.digest(
            v_event.event_id || '|TEAM_FORMATION|RECOVERY|' ||
            v_enrollment_credential_hash || '|' || lower(trim(p_device_id)),
            'sha256'
        ),
        'hex'
    );
    UPDATE public.participant_sessions_v2
       SET is_active = false,
           last_seen_at = now()
     WHERE event_id = v_event.event_id
       AND participant_id = v_participant.participant_id
       AND idempotency_key <> v_idempotency_key;

    INSERT INTO public.participant_sessions_v2 (
        event_id, participant_id, device_id, idempotency_key, joined_from_client
    ) VALUES (
        v_event.event_id, v_participant.participant_id, trim(p_device_id),
        v_idempotency_key, 'team_formation_participant_recovery'
    ) ON CONFLICT (event_id, idempotency_key) DO UPDATE
       SET participant_id = excluded.participant_id,
           device_id = excluded.device_id,
           last_seen_at = now(),
           is_active = true
    RETURNING * INTO v_session;

    UPDATE public.participants_v2
       SET last_seen_at = now()
     WHERE participant_id = v_participant.participant_id;
    INSERT INTO public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, after_state
    ) VALUES (
        v_event.event_id, 'team_formation_participant_recovery',
        'TEAM_FORMATION_PARTICIPANT_RECOVERED', 'participants_v2',
        v_participant.participant_id::text,
        jsonb_build_object(
            'participant_id', v_participant.participant_id,
            'team_id', v_participant.team_id,
            'session_id', v_session.participant_session_id
        )
    );
    RETURN public.exos_v2_identity_payload(
        v_event.event_id, v_participant.participant_id
    ) || jsonb_build_object('TeamFormationMode', v_config->>'Mode');
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_claim_team_formation_captain(
    p_participant_session_token uuid,
    p_device_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_participant_session public.participant_sessions_v2%rowtype;
    v_participant public.participants_v2%rowtype;
    v_event public.events_v2%rowtype;
    v_config jsonb;
    v_existing_captain public.participants_v2%rowtype;
    v_credential public.team_access_credentials_v2%rowtype;
    v_existing_captain_session public.team_access_sessions_v2%rowtype;
    v_captain_session public.team_access_sessions_v2%rowtype;
BEGIN
    IF nullif(trim(p_device_id), '') IS NULL THEN
        RAISE EXCEPTION 'Device identifier is required';
    END IF;
    SELECT * INTO v_participant_session
      FROM public.participant_sessions_v2
     WHERE session_token = p_participant_session_token
       AND is_active
     FOR UPDATE;
    IF NOT FOUND OR lower(trim(v_participant_session.device_id)) <> lower(trim(p_device_id)) THEN
        RAISE EXCEPTION 'Participant session is invalid for this device';
    END IF;
    SELECT * INTO v_participant
      FROM public.participants_v2
     WHERE participant_id = v_participant_session.participant_id
       AND event_id = v_participant_session.event_id
       AND merged_into_participant_id IS NULL
       AND NOT is_archived
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Participant is unavailable';
    END IF;
    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = v_participant.event_id
     FOR UPDATE;
    v_config := v_event.event_payload->'TeamFormation';
    IF coalesce(v_config->>'SchemaVersion', '') <> '1'
       OR coalesce(v_config->>'Phase', '') <> 'CAPTAIN_SELECTION' THEN
        RAISE EXCEPTION 'Captain claim is not open for this event';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            v_event.event_id || '|TEAM_FORMATION_CAPTAIN|' || v_participant.team_id,
            47
        )
    );
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);

    SELECT * INTO v_existing_captain
      FROM public.participants_v2
     WHERE event_id = v_event.event_id
       AND team_id = v_participant.team_id
       AND is_team_formation_captain
       AND merged_into_participant_id IS NULL
       AND NOT is_archived
     FOR UPDATE;
    IF FOUND AND v_existing_captain.participant_id <> v_participant.participant_id THEN
        RETURN jsonb_build_object(
            'Claimed', false,
            'CaptainAlreadyClaimed', true,
            'EventID', v_event.event_id,
            'TeamID', v_participant.team_id
        );
    END IF;

    IF FOUND THEN
        SELECT * INTO v_existing_captain_session
          FROM public.team_access_sessions_v2
         WHERE event_id = v_event.event_id
           AND team_id = v_participant.team_id
           AND team_formation_captain_participant_id = v_participant.participant_id
           AND is_active
         ORDER BY updated_at DESC, created_at DESC
         LIMIT 1
         FOR UPDATE;
        IF FOUND AND lower(trim(v_existing_captain_session.device_id)) <> lower(trim(p_device_id)) THEN
            RETURN jsonb_build_object(
                'Claimed', false,
                'RecoveryRequired', true,
                'EventID', v_event.event_id,
                'TeamID', v_participant.team_id,
                'Message', 'Captain access is active on a different device. Recovery is required.'
            );
        END IF;
        IF FOUND THEN
            UPDATE public.team_access_sessions_v2
               SET last_seen_at = now(), updated_at = now()
             WHERE team_access_session_id = v_existing_captain_session.team_access_session_id;
            RETURN jsonb_build_object(
                'Claimed', true,
                'Idempotent', true,
                'EventID', v_event.event_id,
                'TeamID', v_participant.team_id,
                'CaptainParticipantID', v_participant.participant_id::text,
                'CaptainSessionToken', v_existing_captain_session.session_token::text
            );
        END IF;
    END IF;

    SELECT * INTO v_credential
      FROM public.team_access_credentials_v2
     WHERE event_id = v_event.event_id
       AND team_id = v_participant.team_id
       AND credential_purpose = 'TEAM_FORMATION_CAPTAIN'
       AND is_active
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Team Formation Captain access is not configured';
    END IF;

    UPDATE public.participants_v2
       SET is_team_formation_captain = true,
           is_leader = true,
           team_leader_at = now(),
           last_seen_at = now()
     WHERE participant_id = v_participant.participant_id;

    INSERT INTO public.team_access_sessions_v2 (
        event_id,
        team_id,
        team_access_credential_id,
        device_id,
        team_formation_captain_participant_id,
        created_by
    ) VALUES (
        v_event.event_id,
        v_participant.team_id,
        v_credential.team_access_credential_id,
        trim(p_device_id),
        v_participant.participant_id,
        'team_formation_captain_claim'
    ) ON CONFLICT (event_id, team_id, device_id) DO UPDATE
       SET team_access_credential_id = excluded.team_access_credential_id,
           team_formation_captain_participant_id = excluded.team_formation_captain_participant_id,
           is_active = true,
           recovery_required = false,
           last_seen_at = now(),
           updated_at = now()
    RETURNING * INTO v_captain_session;

    INSERT INTO public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, after_state
    ) VALUES (
        v_event.event_id,
        'team_formation_captain_claim',
        'TEAM_FORMATION_CAPTAIN_CLAIMED',
        'participants_v2',
        v_participant.participant_id::text,
        jsonb_build_object(
            'participant_id', v_participant.participant_id,
            'team_id', v_participant.team_id,
            'captain_session_id', v_captain_session.team_access_session_id
        )
    );

    RETURN jsonb_build_object(
        'Claimed', true,
        'Idempotent', false,
        'EventID', v_event.event_id,
        'TeamID', v_participant.team_id,
        'CaptainParticipantID', v_participant.participant_id::text,
        'CaptainSessionToken', v_captain_session.session_token::text
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_recover_team_formation_captain(
    p_join_code text,
    p_enrollment_credential text,
    p_device_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_config jsonb;
    v_enrollment_credential_hash text;
    v_participant public.participants_v2%rowtype;
    v_participant_session public.participant_sessions_v2%rowtype;
    v_credential public.team_access_credentials_v2%rowtype;
    v_captain_session public.team_access_sessions_v2%rowtype;
    v_idempotency_key text;
BEGIN
    IF p_enrollment_credential IS NULL
       OR nullif(trim(p_device_id), '') IS NULL THEN
        RAISE EXCEPTION 'Opaque enrollment credential and device identifier are required';
    END IF;
    v_enrollment_credential_hash :=
        public.exos_v2_team_formation_credential_hash(p_enrollment_credential);
    SELECT * INTO v_event
      FROM public.events_v2
     WHERE join_code = upper(trim(p_join_code))
       AND published_at IS NOT NULL
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invalid or unpublished join code';
    END IF;
    v_config := v_event.event_payload->'TeamFormation';
    IF coalesce(v_config->>'SchemaVersion', '') <> '1'
       OR coalesce(v_config->>'Phase', '') NOT IN ('CAPTAIN_SELECTION', 'ACTIVE') THEN
        RAISE EXCEPTION 'Captain recovery is unavailable for this event phase';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41)
    );
    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            v_event.event_id || '|TEAM_FORMATION_ENROLLMENT|' || v_enrollment_credential_hash,
            43
        )
    );
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);

    SELECT * INTO v_participant
      FROM public.participants_v2
     WHERE event_id = v_event.event_id
       AND enrollment_credential_hash = v_enrollment_credential_hash
       AND is_team_formation_captain
       AND merged_into_participant_id IS NULL
       AND NOT is_archived
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TEAM_FORMATION_CAPTAIN_RECOVERY_CREDENTIAL_INVALID';
    END IF;
    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            v_event.event_id || '|TEAM_FORMATION_CAPTAIN|' || v_participant.team_id,
            47
        )
    );

    v_idempotency_key := encode(
        extensions.digest(
            v_event.event_id || '|TEAM_FORMATION|CAPTAIN_RECOVERY|' ||
            v_enrollment_credential_hash || '|' || lower(trim(p_device_id)),
            'sha256'
        ),
        'hex'
    );
    UPDATE public.participant_sessions_v2
       SET is_active = false,
           last_seen_at = now()
     WHERE event_id = v_event.event_id
       AND participant_id = v_participant.participant_id
       AND idempotency_key <> v_idempotency_key;
    INSERT INTO public.participant_sessions_v2 (
        event_id, participant_id, device_id, idempotency_key, joined_from_client
    ) VALUES (
        v_event.event_id, v_participant.participant_id, trim(p_device_id),
        v_idempotency_key, 'team_formation_captain_recovery'
    ) ON CONFLICT (event_id, idempotency_key) DO UPDATE
       SET participant_id = excluded.participant_id,
           device_id = excluded.device_id,
           last_seen_at = now(),
           is_active = true
    RETURNING * INTO v_participant_session;

    SELECT * INTO v_credential
      FROM public.team_access_credentials_v2
     WHERE event_id = v_event.event_id
       AND team_id = v_participant.team_id
       AND credential_purpose = 'TEAM_FORMATION_CAPTAIN'
       AND is_active
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Team Formation Captain access is not configured';
    END IF;
    UPDATE public.team_access_sessions_v2
       SET is_active = false,
           recovery_required = true,
           updated_at = now()
     WHERE event_id = v_event.event_id
       AND team_id = v_participant.team_id
       AND team_formation_captain_participant_id = v_participant.participant_id
       AND is_active
       AND lower(trim(device_id)) <> lower(trim(p_device_id));
    INSERT INTO public.team_access_sessions_v2 (
        event_id,
        team_id,
        team_access_credential_id,
        device_id,
        team_formation_captain_participant_id,
        created_by
    ) VALUES (
        v_event.event_id,
        v_participant.team_id,
        v_credential.team_access_credential_id,
        trim(p_device_id),
        v_participant.participant_id,
        'team_formation_captain_recovery'
    ) ON CONFLICT (event_id, team_id, device_id) DO UPDATE
       SET team_access_credential_id = excluded.team_access_credential_id,
           team_formation_captain_participant_id = excluded.team_formation_captain_participant_id,
           is_active = true,
           recovery_required = false,
           last_seen_at = now(),
           updated_at = now()
    RETURNING * INTO v_captain_session;

    UPDATE public.participants_v2
       SET last_seen_at = now()
     WHERE participant_id = v_participant.participant_id;
    INSERT INTO public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, after_state
    ) VALUES (
        v_event.event_id,
        'team_formation_captain_recovery',
        'TEAM_FORMATION_CAPTAIN_RECOVERED',
        'participants_v2',
        v_participant.participant_id::text,
        jsonb_build_object(
            'participant_id', v_participant.participant_id,
            'team_id', v_participant.team_id,
            'participant_session_id', v_participant_session.participant_session_id,
            'captain_session_id', v_captain_session.team_access_session_id
        )
    );
    RETURN public.exos_v2_identity_payload(
        v_event.event_id, v_participant.participant_id
    ) || jsonb_build_object(
        'TeamFormationMode', v_config->>'Mode',
        'CaptainSessionToken', v_captain_session.session_token::text,
        'CaptainRecovered', true
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_transfer_team_formation_captain(
    p_event_id text,
    p_team_id text,
    p_target_participant_id uuid,
    p_actor text,
    p_reason text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_config jsonb;
    v_target public.participants_v2%rowtype;
    v_before jsonb;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL
       OR nullif(trim(p_team_id), '') IS NULL
       OR nullif(trim(p_actor), '') IS NULL
       OR nullif(trim(p_reason), '') IS NULL THEN
        RAISE EXCEPTION 'Event, team, facilitator, and correction reason are required';
    END IF;
    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id)
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event not found';
    END IF;
    v_config := v_event.event_payload->'TeamFormation';
    IF coalesce(v_config->>'SchemaVersion', '') <> '1'
       OR coalesce(v_config->>'Phase', '') NOT IN ('CAPTAIN_SELECTION', 'ACTIVE') THEN
        RAISE EXCEPTION 'Captain transfer is unavailable for this event phase';
    END IF;
    SELECT * INTO v_target
      FROM public.participants_v2
     WHERE participant_id = p_target_participant_id
       AND event_id = v_event.event_id
       AND team_id = trim(p_team_id)
       AND merged_into_participant_id IS NULL
       AND NOT is_archived
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Captain transfer target is not an active member of this event team';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            v_event.event_id || '|TEAM_FORMATION_CAPTAIN|' || trim(p_team_id),
            47
        )
    );
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);

    SELECT coalesce(
        jsonb_agg(
            jsonb_build_object(
                'participant_id', participant_id,
                'is_team_formation_captain', is_team_formation_captain
            )
        ),
        '[]'::jsonb
    ) INTO v_before
      FROM public.participants_v2
     WHERE event_id = v_event.event_id
       AND team_id = trim(p_team_id)
       AND merged_into_participant_id IS NULL
       AND NOT is_archived;

    UPDATE public.participants_v2
       SET is_team_formation_captain = false,
           is_leader = false,
           team_leader_at = NULL
     WHERE event_id = v_event.event_id
       AND team_id = trim(p_team_id)
       AND is_team_formation_captain
       AND merged_into_participant_id IS NULL
       AND NOT is_archived;
    UPDATE public.participants_v2
       SET is_team_formation_captain = true,
           is_leader = true,
           team_leader_at = now(),
           last_seen_at = now()
     WHERE participant_id = v_target.participant_id;
    UPDATE public.team_access_sessions_v2
       SET is_active = false,
           recovery_required = true,
           updated_at = now()
     WHERE event_id = v_event.event_id
       AND team_id = trim(p_team_id)
       AND team_formation_captain_participant_id IS NOT NULL
       AND is_active;

    INSERT INTO public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, before_state, after_state
    ) VALUES (
        v_event.event_id,
        trim(p_actor),
        'TEAM_FORMATION_CAPTAIN_TRANSFERRED',
        'participants_v2',
        v_target.participant_id::text,
        v_before,
        jsonb_build_object(
            'team_id', trim(p_team_id),
            'captain_participant_id', v_target.participant_id,
            'reason', trim(p_reason),
            'prior_captain_sessions_revoked', true
        )
    );
    RETURN jsonb_build_object(
        'Transferred', true,
        'EventID', v_event.event_id,
        'TeamID', trim(p_team_id),
        'CaptainParticipantID', v_target.participant_id::text,
        'CaptainSessionRecoveryRequired', true
    );
END;
$$;

-- Database-mutating Team Formation functions are security-definer because
-- anonymous participant routes must pass RLS-protected Core tables. Revoke
-- PUBLIC first, then grant the narrow participant/facilitator surface
-- explicitly.
REVOKE ALL ON FUNCTION public.exos_v2_team_formation_credential_hash(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_team_formation_participant_write_guard() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_team_formation_team_write_guard() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_team_formation_captain_session_guard() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_configure_team_formation(text,text,jsonb,jsonb,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_open_team_formation(text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_lock_team_formation(text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_open_team_captain_selection(text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_activate_team_formation(text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_team_formation_register_random(text,text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_team_formation_claim_preassigned(text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_recover_team_formation_participant(text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_claim_team_formation_captain(uuid,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_recover_team_formation_captain(text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_transfer_team_formation_captain(text,text,uuid,text,text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.exos_v2_configure_team_formation(text,text,jsonb,jsonb,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_open_team_formation(text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_lock_team_formation(text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_open_team_captain_selection(text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_activate_team_formation(text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_transfer_team_formation_captain(text,text,uuid,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_team_formation_register_random(text,text,text,text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_team_formation_claim_preassigned(text,text,text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_recover_team_formation_participant(text,text,text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_claim_team_formation_captain(uuid,text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_recover_team_formation_captain(text,text,text) TO anon, authenticated, service_role;

COMMIT;
