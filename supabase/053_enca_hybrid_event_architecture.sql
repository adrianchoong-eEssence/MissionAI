-- ENCA hybrid anchored event architecture.
--
-- Additive Core-v2 contract. Dependencies: 036/036a Team Formation,
-- 042 attendance, 044 Captain operations, 048/050 location and announcements,
-- and 051/052 WALK Hunt. This file creates no event, Personal Key, country,
-- route, checkpoint, mission content, score, or production data.
--
-- HYBRID_ANCHORED provisions one opaque-credential HOD anchor per team, then
-- assigns all general registrations only amongst the least occupied teams
-- below their configured capacity. Both rows are canonical participants.
BEGIN;

DO $$
DECLARE required text[] := ARRAY[
    'events_v2', 'teams_v2', 'participants_v2', 'participant_sessions_v2',
    'team_access_credentials_v2', 'participant_attendance_v2',
    'event_location_configurations_v2', 'event_hunt_configurations_v2',
    'score_transactions_v2', 'audit_log_v2'
]; item text;
BEGIN
    FOREACH item IN ARRAY required LOOP
        IF to_regclass('public.' || item) IS NULL THEN
            RAISE EXCEPTION '053 requires public.%', item;
        END IF;
    END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS public.event_competition_stages_v2 (
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    stage_id text NOT NULL CHECK (length(trim(stage_id)) BETWEEN 1 AND 80),
    stage_no integer NOT NULL CHECK (stage_no > 0),
    stage_name text NOT NULL CHECK (length(trim(stage_name)) BETWEEN 1 AND 160),
    stage_kind text NOT NULL CHECK (stage_kind IN ('STANDARD', 'HUNT')),
    is_scored boolean NOT NULL DEFAULT true,
    stage_state text NOT NULL DEFAULT 'LOCKED'
        CHECK (stage_state IN ('LOCKED', 'AVAILABLE', 'ACTIVE', 'COMPLETED')),
    hidden_until_available boolean NOT NULL DEFAULT true,
    stage_payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(stage_payload) = 'object'),
    configured_by text NOT NULL CHECK (nullif(trim(configured_by), '') IS NOT NULL),
    configured_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, stage_id),
    UNIQUE (event_id, stage_no)
);
CREATE INDEX IF NOT EXISTS event_competition_stages_v2_event_state_idx
    ON public.event_competition_stages_v2(event_id, stage_state, stage_no);

ALTER TABLE public.event_competition_stages_v2 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.event_competition_stages_v2
    FROM PUBLIC, anon, authenticated, service_role;

ALTER TABLE public.event_location_configurations_v2
    ADD COLUMN IF NOT EXISTS participant_visibility_mode text NOT NULL DEFAULT 'OFF';
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.event_location_configurations_v2'::regclass
           AND conname = 'event_location_configurations_v2_participant_visibility_mode_ck'
    ) THEN
        ALTER TABLE public.event_location_configurations_v2
            ADD CONSTRAINT event_location_configurations_v2_participant_visibility_mode_ck
            CHECK (participant_visibility_mode IN ('OFF', 'TEAM_LEADERS'));
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.exos_v2_configure_hybrid_anchored_team_formation(
    p_event_id text,
    p_team_capacities jsonb,
    p_hod_anchor_roster jsonb,
    p_actor text DEFAULT 'Facilitator'
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_team_count integer;
    v_anchor_count integer;
    v_capacity_total integer;
    v_config jsonb;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL OR nullif(trim(p_actor), '') IS NULL
       OR jsonb_typeof(p_team_capacities) IS DISTINCT FROM 'object'
       OR jsonb_typeof(p_hod_anchor_roster) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'Event, actor, TeamID capacities, and HOD anchor roster are required';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = trim(p_event_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Event not found'; END IF;
    IF v_event.event_payload ? 'RaceConfiguration'
       OR coalesce(v_event.event_payload #>> '{TeamFormation,SchemaVersion}', '') = '1' THEN
        RAISE EXCEPTION 'Hybrid Team Formation requires a fresh non-R.A.C.E. event';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41));
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);
    SELECT count(*) INTO v_team_count FROM public.teams_v2
     WHERE event_id = v_event.event_id AND is_active;
    SELECT count(*) INTO v_anchor_count FROM jsonb_array_elements(p_hod_anchor_roster);
    SELECT coalesce(sum(value::integer), 0) INTO v_capacity_total
      FROM jsonb_each_text(p_team_capacities)
     WHERE value ~ '^[1-9][0-9]*$';
    IF v_team_count = 0 OR v_anchor_count <> v_team_count
       OR (SELECT count(*) FROM jsonb_object_keys(p_team_capacities)) <> v_team_count
       OR EXISTS (SELECT 1 FROM jsonb_each_text(p_team_capacities) row(team_id, capacity)
                    WHERE row.capacity !~ '^[1-9][0-9]*$')
       OR EXISTS (SELECT 1 FROM jsonb_object_keys(p_team_capacities) id
                    WHERE NOT EXISTS (SELECT 1 FROM public.teams_v2 t
                                      WHERE t.event_id = v_event.event_id AND t.team_id = id AND t.is_active))
       OR v_capacity_total < v_anchor_count THEN
        RAISE EXCEPTION 'Hybrid formation requires one positive capacity and one HOD anchor per active team';
    END IF;
    IF EXISTS (SELECT 1 FROM public.participants_v2 WHERE event_id = v_event.event_id
                AND merged_into_participant_id IS NULL AND NOT is_archived)
       OR EXISTS (SELECT 1 FROM public.team_access_credentials_v2 WHERE event_id = v_event.event_id AND is_active) THEN
        RAISE EXCEPTION 'Hybrid Team Formation must be configured before participant or team-access records exist';
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_hod_anchor_roster) row(item)
                WHERE coalesce(row.item->>'EnrollmentCredentialHash', '') !~ '^[0-9a-f]{64}$'
                   OR nullif(trim(row.item->>'DisplayName'), '') IS NULL
                   OR nullif(trim(row.item->>'TeamID'), '') IS NULL)
       OR EXISTS (SELECT 1 FROM (SELECT item->>'EnrollmentCredentialHash' key, count(*) count
                                  FROM jsonb_array_elements(p_hod_anchor_roster) row(item) GROUP BY 1) d WHERE d.count > 1)
       OR EXISTS (SELECT 1 FROM (SELECT trim(item->>'TeamID') team_id, count(*) count
                                  FROM jsonb_array_elements(p_hod_anchor_roster) row(item) GROUP BY 1) d
                  WHERE d.count <> 1
                     OR NOT EXISTS (SELECT 1 FROM public.teams_v2 t
                                    WHERE t.event_id = v_event.event_id AND t.team_id = d.team_id AND t.is_active))
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_hod_anchor_roster) row(item)
                  JOIN public.teams_v2 t ON t.event_id = v_event.event_id AND t.team_id = trim(row.item->>'TeamID')
                  WHERE (p_team_capacities ->> t.team_id)::integer < 1) THEN
        RAISE EXCEPTION 'Each HOD anchor requires a unique opaque credential hash and distinct active team';
    END IF;
    UPDATE public.teams_v2 SET team_capacity = (p_team_capacities ->> team_id)::integer
     WHERE event_id = v_event.event_id AND is_active;
    v_config := jsonb_build_object(
        'SchemaVersion', 1, 'Mode', 'HYBRID_ANCHORED', 'Phase', 'DRAFT',
        'AnchorCount', v_anchor_count, 'ConfiguredAt', now(), 'ConfiguredBy', trim(p_actor)
    );
    UPDATE public.events_v2 SET event_payload = jsonb_set(
        coalesce(event_payload, '{}'::jsonb), '{TeamFormation}', v_config, true
    ), updated_at = now() WHERE event_id = v_event.event_id;
    INSERT INTO public.team_access_credentials_v2(event_id, team_id, credential_hash, credential_purpose, is_active, created_by)
    SELECT v_event.event_id, t.team_id,
           extensions.crypt(extensions.gen_random_uuid()::text, extensions.gen_salt('bf')),
           'TEAM_FORMATION_CAPTAIN', true, trim(p_actor)
      FROM public.teams_v2 t WHERE t.event_id = v_event.event_id AND t.is_active;
    INSERT INTO public.participants_v2(
        event_id, team_id, normalized_name, display_name, participant_payload,
        country, flag, participant_status, enrollment_credential_hash
    ) SELECT v_event.event_id, trim(row.item->>'TeamID'),
             public.exos_v2_normalize_participant_name(row.item->>'DisplayName'), trim(row.item->>'DisplayName'),
             jsonb_build_object('TeamFormation', jsonb_build_object(
                 'SchemaVersion', 1, 'Mode', 'HYBRID_ANCHORED', 'AssignmentRole', 'HOD_ANCHOR'
             )), t.country, t.team_flag, 'PREASSIGNED', row.item->>'EnrollmentCredentialHash'
        FROM jsonb_array_elements(p_hod_anchor_roster) row(item)
        JOIN public.teams_v2 t ON t.event_id = v_event.event_id AND t.team_id = trim(row.item->>'TeamID');
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_event.event_id, trim(p_actor), 'HYBRID_TEAM_FORMATION_CONFIGURED', 'events_v2', v_event.event_id,
            jsonb_build_object('TeamFormation', v_config, 'CapacityTotal', v_capacity_total));
    RETURN jsonb_build_object('EventID', v_event.event_id, 'Mode', 'HYBRID_ANCHORED',
        'Phase', 'DRAFT', 'HODAnchorCount', v_anchor_count, 'Capacity', v_capacity_total);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_open_hybrid_anchored_team_formation(
    p_event_id text, p_actor text DEFAULT 'Facilitator'
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_event public.events_v2%rowtype; v_config jsonb;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event and facilitator identity are required';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = trim(p_event_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Event not found'; END IF;
    v_config := v_event.event_payload->'TeamFormation';
    IF coalesce(v_config->>'SchemaVersion', '') <> '1'
       OR coalesce(v_config->>'Mode', '') <> 'HYBRID_ANCHORED'
       OR coalesce(v_config->>'Phase', '') <> 'DRAFT' THEN
        RAISE EXCEPTION 'Hybrid Team Formation must be configured and in DRAFT';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41));
    IF EXISTS (SELECT 1 FROM public.teams_v2 t WHERE t.event_id = v_event.event_id AND t.is_active
               AND (t.team_capacity IS NULL OR NOT EXISTS (SELECT 1 FROM public.participants_v2 p
                    WHERE p.event_id = t.event_id AND p.team_id = t.team_id
                      AND p.participant_payload #>> '{TeamFormation,AssignmentRole}' = 'HOD_ANCHOR'
                      AND NOT p.is_archived AND p.merged_into_participant_id IS NULL))) THEN
        RAISE EXCEPTION 'Every hybrid team needs capacity and one provisioned HOD anchor before registration opens';
    END IF;
    v_config := v_config || jsonb_build_object('Phase', 'REGISTRATION_OPEN', 'OpenedAt', now(), 'OpenedBy', trim(p_actor));
    UPDATE public.events_v2 SET event_payload = jsonb_set(event_payload, '{TeamFormation}', v_config, true), updated_at = now()
     WHERE event_id = v_event.event_id;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_event.event_id, trim(p_actor), 'HYBRID_TEAM_FORMATION_OPENED', 'events_v2', v_event.event_id,
            jsonb_build_object('TeamFormation', v_config));
    RETURN jsonb_build_object('EventID', v_event.event_id, 'Mode', 'HYBRID_ANCHORED', 'Phase', 'REGISTRATION_OPEN');
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_hybrid_anchored_register_random(
    p_join_code text, p_display_name text, p_device_id text, p_enrollment_credential text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_event public.events_v2%rowtype; v_hash text; v_participant public.participants_v2%rowtype;
    v_session public.participant_sessions_v2%rowtype; v_team public.teams_v2%rowtype;
    v_idempotency_key text; v_team_id text; v_occupancy integer; v_attendance text;
BEGIN
    IF nullif(trim(p_display_name), '') IS NULL OR nullif(trim(p_device_id), '') IS NULL OR p_enrollment_credential IS NULL THEN
        RAISE EXCEPTION 'Display name, device identifier, and enrollment credential are required';
    END IF;
    v_hash := public.exos_v2_team_formation_credential_hash(p_enrollment_credential);
    SELECT * INTO v_event FROM public.events_v2 WHERE join_code = upper(trim(p_join_code)) AND published_at IS NOT NULL FOR UPDATE;
    IF NOT FOUND OR coalesce(v_event.event_payload #>> '{TeamFormation,Mode}', '') <> 'HYBRID_ANCHORED'
       OR coalesce(v_event.event_payload #>> '{TeamFormation,Phase}', '') <> 'REGISTRATION_OPEN'
       OR coalesce(v_event.event_payload #>> '{Attendance,SchemaVersion}', '') <> '1' THEN
        RAISE EXCEPTION 'Hybrid registration and attendance are not open for this event';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41));
    PERFORM pg_advisory_xact_lock(hashtextextended(v_event.event_id || '|TEAM_FORMATION_ENROLLMENT|' || v_hash, 43));
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);
    SELECT * INTO v_participant FROM public.participants_v2 WHERE event_id = v_event.event_id
       AND enrollment_credential_hash = v_hash AND merged_into_participant_id IS NULL AND NOT is_archived FOR UPDATE;
    IF FOUND THEN
        IF coalesce(v_participant.participant_payload #>> '{TeamFormation,AssignmentRole}', '') <> 'GENERAL_PARTICIPANT' THEN
            RAISE EXCEPTION 'This enrollment credential is reserved for a preassigned participant';
        END IF;
        SELECT * INTO v_session FROM public.participant_sessions_v2 WHERE event_id = v_event.event_id
          AND participant_id = v_participant.participant_id AND is_active
          ORDER BY last_seen_at DESC, created_at DESC LIMIT 1 FOR UPDATE;
        SELECT coalesce(a.attendance_state, 'PREASSIGNED') INTO v_attendance FROM public.participant_attendance_v2 a
         WHERE a.event_id = v_event.event_id AND a.participant_id = v_participant.participant_id;
        IF FOUND AND lower(trim(v_session.device_id)) = lower(trim(p_device_id)) THEN
            UPDATE public.participant_sessions_v2 SET last_seen_at = now() WHERE participant_session_id = v_session.participant_session_id;
            UPDATE public.participants_v2 SET last_seen_at = now() WHERE participant_id = v_participant.participant_id;
            RETURN public.exos_v2_identity_payload(v_event.event_id, v_participant.participant_id)
                || jsonb_build_object('TeamFormationMode', 'HYBRID_ANCHORED', 'AssignmentRole', 'GENERAL_PARTICIPANT',
                                      'AttendanceState', coalesce(v_attendance, 'PRESENT'), 'Idempotent', true);
        END IF;
        RETURN (public.exos_v2_identity_payload(v_event.event_id, v_participant.participant_id) - 'SessionToken')
            || jsonb_build_object('RecoveryRequired', true, 'TeamFormationMode', 'HYBRID_ANCHORED',
                                  'AssignmentRole', 'GENERAL_PARTICIPANT');
    END IF;
    WITH occupancy AS (
        SELECT t.team_id, t.team_capacity, count(p.participant_id)::integer assigned_count
        FROM public.teams_v2 t LEFT JOIN public.participants_v2 p ON p.event_id = t.event_id AND p.team_id = t.team_id
          AND p.merged_into_participant_id IS NULL AND NOT p.is_archived
        WHERE t.event_id = v_event.event_id AND t.is_active GROUP BY t.team_id, t.team_capacity
    ), eligible AS (SELECT * FROM occupancy WHERE assigned_count < team_capacity)
    SELECT team_id, assigned_count INTO v_team_id, v_occupancy FROM eligible
      WHERE assigned_count = (SELECT min(assigned_count) FROM eligible) ORDER BY random() LIMIT 1;
    IF v_team_id IS NULL THEN RAISE EXCEPTION 'EVENT_FULL'; END IF;
    SELECT * INTO v_team FROM public.teams_v2 WHERE event_id = v_event.event_id AND team_id = v_team_id FOR UPDATE;
    v_idempotency_key := encode(extensions.digest(v_event.event_id || '|HYBRID_ANCHORED|RANDOM_ASSIGN|' || v_hash || '|' || lower(trim(p_device_id)), 'sha256'), 'hex');
    INSERT INTO public.participants_v2(event_id, team_id, normalized_name, display_name, participant_payload,
        country, flag, participant_status, enrollment_credential_hash)
    VALUES (v_event.event_id, v_team.team_id, public.exos_v2_normalize_participant_name(p_display_name), trim(p_display_name),
        jsonb_build_object('TeamFormation', jsonb_build_object('SchemaVersion', 1, 'Mode', 'HYBRID_ANCHORED', 'AssignmentRole', 'GENERAL_PARTICIPANT')),
        v_team.country, v_team.team_flag, 'REGISTERED', v_hash) RETURNING * INTO v_participant;
    INSERT INTO public.participant_sessions_v2(event_id, participant_id, device_id, idempotency_key, joined_from_client)
    VALUES (v_event.event_id, v_participant.participant_id, trim(p_device_id), v_idempotency_key, 'hybrid_anchored_random_assign')
    ON CONFLICT (event_id, idempotency_key) DO UPDATE SET participant_id = excluded.participant_id,
      device_id = excluded.device_id, last_seen_at = now(), is_active = true RETURNING * INTO v_session;
    PERFORM public.exos_v2_set_participant_attendance(v_event.event_id, v_participant.participant_id, 'PRESENT',
        'hybrid_anchored_registration', 'Automatic first-arrival attendance');
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_event.event_id, 'hybrid_anchored_registration', 'HYBRID_GENERAL_RANDOM_ASSIGNED', 'participants_v2',
        v_participant.participant_id::text, jsonb_build_object('TeamID', v_team_id, 'OccupancyBeforeAssignment', v_occupancy));
    RETURN public.exos_v2_identity_payload(v_event.event_id, v_participant.participant_id)
      || jsonb_build_object('TeamFormationMode', 'HYBRID_ANCHORED', 'AssignmentRole', 'GENERAL_PARTICIPANT',
                            'AttendanceState', 'PRESENT', 'Idempotent', false);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_hybrid_anchored_claim_personal_key(
    p_join_code text, p_enrollment_credential text, p_device_id text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_event public.events_v2%rowtype; v_hash text; v_participant public.participants_v2%rowtype;
    v_session public.participant_sessions_v2%rowtype; v_idempotency_key text; v_attendance text;
BEGIN
    IF p_enrollment_credential IS NULL OR nullif(trim(p_device_id), '') IS NULL THEN
        RAISE EXCEPTION 'Opaque Personal Key credential and device identifier are required';
    END IF;
    v_hash := public.exos_v2_team_formation_credential_hash(p_enrollment_credential);
    SELECT * INTO v_event FROM public.events_v2 WHERE join_code = upper(trim(p_join_code)) AND published_at IS NOT NULL FOR UPDATE;
    IF NOT FOUND OR coalesce(v_event.event_payload #>> '{TeamFormation,Mode}', '') <> 'HYBRID_ANCHORED'
       OR coalesce(v_event.event_payload #>> '{TeamFormation,Phase}', '') <> 'REGISTRATION_OPEN'
       OR coalesce(v_event.event_payload #>> '{Attendance,SchemaVersion}', '') <> '1' THEN
        RAISE EXCEPTION 'HOD Personal Key login and attendance are not open for this event';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(v_event.event_id || '|TEAM_FORMATION', 41));
    PERFORM pg_advisory_xact_lock(hashtextextended(v_event.event_id || '|TEAM_FORMATION_ENROLLMENT|' || v_hash, 43));
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);
    SELECT * INTO v_participant FROM public.participants_v2 WHERE event_id = v_event.event_id
       AND enrollment_credential_hash = v_hash AND participant_payload #>> '{TeamFormation,AssignmentRole}' = 'HOD_ANCHOR'
       AND merged_into_participant_id IS NULL AND NOT is_archived FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'HOD_PERSONAL_KEY_NOT_FOUND'; END IF;
    SELECT * INTO v_session FROM public.participant_sessions_v2 WHERE event_id = v_event.event_id
      AND participant_id = v_participant.participant_id AND is_active ORDER BY last_seen_at DESC, created_at DESC LIMIT 1 FOR UPDATE;
    SELECT coalesce(a.attendance_state, 'PREASSIGNED') INTO v_attendance FROM public.participant_attendance_v2 a
      WHERE a.event_id = v_event.event_id AND a.participant_id = v_participant.participant_id;
    IF FOUND AND lower(trim(v_session.device_id)) = lower(trim(p_device_id)) THEN
        UPDATE public.participant_sessions_v2 SET last_seen_at = now() WHERE participant_session_id = v_session.participant_session_id;
        UPDATE public.participants_v2 SET last_seen_at = now() WHERE participant_id = v_participant.participant_id;
        RETURN public.exos_v2_identity_payload(v_event.event_id, v_participant.participant_id)
          || jsonb_build_object('TeamFormationMode', 'HYBRID_ANCHORED', 'AssignmentRole', 'HOD_ANCHOR',
                                'AttendanceState', coalesce(v_attendance, 'PRESENT'), 'Idempotent', true);
    ELSIF FOUND THEN
        RETURN (public.exos_v2_identity_payload(v_event.event_id, v_participant.participant_id) - 'SessionToken')
          || jsonb_build_object('RecoveryRequired', true, 'TeamFormationMode', 'HYBRID_ANCHORED', 'AssignmentRole', 'HOD_ANCHOR');
    END IF;
    v_idempotency_key := encode(extensions.digest(v_event.event_id || '|HYBRID_ANCHORED|HOD|' || v_hash || '|' || lower(trim(p_device_id)), 'sha256'), 'hex');
    INSERT INTO public.participant_sessions_v2(event_id, participant_id, device_id, idempotency_key, joined_from_client)
    VALUES (v_event.event_id, v_participant.participant_id, trim(p_device_id), v_idempotency_key, 'hybrid_anchored_hod_personal_key')
    ON CONFLICT (event_id, idempotency_key) DO UPDATE SET participant_id = excluded.participant_id,
      device_id = excluded.device_id, last_seen_at = now(), is_active = true RETURNING * INTO v_session;
    UPDATE public.participants_v2 SET participant_status = 'REGISTERED', last_seen_at = now()
      WHERE participant_id = v_participant.participant_id;
    IF v_attendance IS NULL OR v_attendance = 'PREASSIGNED' THEN
        PERFORM public.exos_v2_set_participant_attendance(v_event.event_id, v_participant.participant_id, 'PRESENT',
            'hybrid_anchored_hod_login', 'Automatic first successful HOD event login');
    END IF;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_event.event_id, 'hybrid_anchored_hod_login', 'HYBRID_HOD_PERSONAL_KEY_CLAIMED', 'participants_v2',
      v_participant.participant_id::text, jsonb_build_object('TeamID', v_participant.team_id, 'AutomaticCaptain', false));
    RETURN public.exos_v2_identity_payload(v_event.event_id, v_participant.participant_id)
      || jsonb_build_object('TeamFormationMode', 'HYBRID_ANCHORED', 'AssignmentRole', 'HOD_ANCHOR',
                            'AttendanceState', 'PRESENT', 'Idempotent', false, 'AutomaticCaptain', false);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_hybrid_anchored_operator_roster(p_event_id text)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
    SELECT jsonb_build_object('EventID', trim(p_event_id), 'Participants', coalesce(jsonb_agg(
        jsonb_build_object('ParticipantID', p.participant_id::text, 'DisplayName', p.display_name,
          'TeamID', p.team_id, 'AssignmentRole', coalesce(p.participant_payload #>> '{TeamFormation,AssignmentRole}', 'GENERAL_PARTICIPANT'),
          'AttendanceState', coalesce(a.attendance_state, 'PREASSIGNED'), 'IsCaptain', p.is_team_formation_captain)
        ORDER BY p.team_id, p.created_at, p.participant_id), '[]'::jsonb))
    FROM public.participants_v2 p LEFT JOIN public.participant_attendance_v2 a
      ON a.event_id = p.event_id AND a.participant_id = p.participant_id
    WHERE p.event_id = trim(p_event_id) AND NOT p.is_archived AND p.merged_into_participant_id IS NULL;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_upsert_competition_stage(
    p_event_id text, p_stage_id text, p_stage_no integer, p_stage_name text, p_stage_kind text,
    p_is_scored boolean, p_stage_state text, p_hidden_until_available boolean,
    p_stage_payload jsonb DEFAULT '{}'::jsonb, p_actor text DEFAULT 'Facilitator'
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_kind text := upper(trim(p_stage_kind)); v_state text := upper(trim(p_stage_state));
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL OR nullif(trim(p_stage_id), '') IS NULL
       OR nullif(trim(p_stage_name), '') IS NULL OR nullif(trim(p_actor), '') IS NULL
       OR coalesce(p_stage_no, 0) < 1 OR v_kind NOT IN ('STANDARD', 'HUNT')
       OR v_state NOT IN ('LOCKED', 'AVAILABLE', 'ACTIVE', 'COMPLETED')
       OR jsonb_typeof(coalesce(p_stage_payload, '{}'::jsonb)) <> 'object'
       OR NOT EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = trim(p_event_id)) THEN
        RAISE EXCEPTION 'Competition stage is invalid';
    END IF;
    INSERT INTO public.event_competition_stages_v2(event_id, stage_id, stage_no, stage_name, stage_kind,
      is_scored, stage_state, hidden_until_available, stage_payload, configured_by)
    VALUES (trim(p_event_id), trim(p_stage_id), p_stage_no, trim(p_stage_name), v_kind,
      coalesce(p_is_scored, true), v_state, coalesce(p_hidden_until_available, true), coalesce(p_stage_payload, '{}'::jsonb), trim(p_actor))
    ON CONFLICT (event_id, stage_id) DO UPDATE SET stage_no = excluded.stage_no, stage_name = excluded.stage_name,
      stage_kind = excluded.stage_kind, is_scored = excluded.is_scored, stage_state = excluded.stage_state,
      hidden_until_available = excluded.hidden_until_available, stage_payload = excluded.stage_payload,
      configured_by = excluded.configured_by, configured_at = now(), updated_at = now();
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (trim(p_event_id), trim(p_actor), 'COMPETITION_STAGE_SAVED', 'event_competition_stages_v2', trim(p_stage_id),
      jsonb_build_object('StageNo', p_stage_no, 'StageKind', v_kind, 'Scored', coalesce(p_is_scored, true), 'State', v_state));
    RETURN jsonb_build_object('EventID', trim(p_event_id), 'StageID', trim(p_stage_id), 'Saved', true);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_set_competition_stage_state(
    p_event_id text, p_stage_id text, p_stage_state text, p_actor text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_stage public.event_competition_stages_v2%rowtype; v_state text := upper(trim(p_stage_state));
BEGIN
    IF nullif(trim(p_actor), '') IS NULL OR v_state NOT IN ('LOCKED', 'AVAILABLE', 'ACTIVE', 'COMPLETED') THEN
        RAISE EXCEPTION 'Competition stage state is invalid';
    END IF;
    SELECT * INTO v_stage FROM public.event_competition_stages_v2
      WHERE event_id = trim(p_event_id) AND stage_id = trim(p_stage_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Competition stage is not configured for this event'; END IF;
    IF v_stage.stage_state = 'COMPLETED' AND v_state <> 'COMPLETED' THEN
        RAISE EXCEPTION 'Completed competition stages are terminal';
    END IF;
    IF v_state = 'ACTIVE' AND EXISTS (SELECT 1 FROM public.event_competition_stages_v2 s
       WHERE s.event_id = v_stage.event_id AND s.stage_no < v_stage.stage_no AND s.stage_state <> 'COMPLETED') THEN
        RAISE EXCEPTION 'Prior competition stages must be completed before this stage becomes active';
    END IF;
    UPDATE public.event_competition_stages_v2 SET stage_state = v_state, updated_at = now()
      WHERE event_id = v_stage.event_id AND stage_id = v_stage.stage_id;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, before_state, after_state)
    VALUES (v_stage.event_id, trim(p_actor), 'COMPETITION_STAGE_STATE_SET', 'event_competition_stages_v2', v_stage.stage_id,
      jsonb_build_object('StageState', v_stage.stage_state), jsonb_build_object('StageState', v_state));
    RETURN jsonb_build_object('EventID', v_stage.event_id, 'StageID', v_stage.stage_id, 'StageState', v_state);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_record_competition_stage_score(
    p_event_id text, p_stage_id text, p_team_id text, p_score_delta numeric,
    p_reason text, p_actor text, p_idempotency_key text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_stage public.event_competition_stages_v2%rowtype; v_existing public.score_transactions_v2%rowtype;
        v_key text; v_id uuid;
BEGIN
    IF nullif(trim(p_reason), '') IS NULL OR nullif(trim(p_actor), '') IS NULL
       OR nullif(trim(p_idempotency_key), '') IS NULL OR coalesce(p_score_delta, 0) NOT BETWEEN -1000 AND 1000
       OR NOT EXISTS (SELECT 1 FROM public.teams_v2 WHERE event_id = trim(p_event_id) AND team_id = trim(p_team_id) AND is_active) THEN
        RAISE EXCEPTION 'Competition stage score is invalid';
    END IF;
    SELECT * INTO v_stage FROM public.event_competition_stages_v2
     WHERE event_id = trim(p_event_id) AND stage_id = trim(p_stage_id) FOR UPDATE;
    IF NOT FOUND OR NOT v_stage.is_scored OR v_stage.stage_state NOT IN ('ACTIVE', 'COMPLETED') THEN
        RAISE EXCEPTION 'A scored ACTIVE or COMPLETED competition stage is required';
    END IF;
    v_key := 'competition-stage|' || v_stage.stage_id || '|' || trim(p_idempotency_key);
    INSERT INTO public.score_transactions_v2(event_id, team_id, scoring_mode, score_delta, reason,
        idempotency_key, source_reference, created_by)
    VALUES (v_stage.event_id, trim(p_team_id), 'TEAM_COMPETITIVE', p_score_delta,
      trim(p_reason), v_key, jsonb_build_object('CompetitionStageID', v_stage.stage_id,
        'CompetitionStageName', v_stage.stage_name, 'RequestIdempotencyKey', trim(p_idempotency_key)), trim(p_actor))
    ON CONFLICT (event_id, idempotency_key) DO NOTHING RETURNING score_transaction_id INTO v_id;
    IF v_id IS NULL THEN
        SELECT * INTO v_existing FROM public.score_transactions_v2
          WHERE event_id = v_stage.event_id AND idempotency_key = v_key;
        IF NOT FOUND OR v_existing.team_id <> trim(p_team_id) OR v_existing.score_delta IS DISTINCT FROM p_score_delta
           OR v_existing.source_reference ->> 'CompetitionStageID' IS DISTINCT FROM v_stage.stage_id THEN
            RAISE EXCEPTION 'Competition stage score idempotency key conflicts with an immutable ledger entry';
        END IF;
        RETURN jsonb_build_object('EventID', v_stage.event_id, 'StageID', v_stage.stage_id,
          'TeamID', trim(p_team_id), 'Idempotent', true);
    END IF;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_stage.event_id, trim(p_actor), 'COMPETITION_STAGE_SCORE_RECORDED', 'score_transactions_v2', v_id::text,
      jsonb_build_object('StageID', v_stage.stage_id, 'TeamID', trim(p_team_id), 'ScoreDelta', p_score_delta));
    RETURN jsonb_build_object('EventID', v_stage.event_id, 'StageID', v_stage.stage_id,
      'TeamID', trim(p_team_id), 'ScoreTransactionID', v_id::text, 'Idempotent', false);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_competition_stage_snapshot(p_event_id text)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
    WITH stage_scores AS (
      SELECT source_reference ->> 'CompetitionStageID' stage_id, team_id, sum(score_delta) score
      FROM public.score_transactions_v2 WHERE event_id = trim(p_event_id)
       AND source_reference ? 'CompetitionStageID' GROUP BY 1, 2
    ), totals AS (SELECT team_id, sum(score_delta) score FROM public.score_transactions_v2
      WHERE event_id = trim(p_event_id) GROUP BY team_id)
    SELECT jsonb_build_object('EventID', trim(p_event_id),
      'Stages', coalesce((SELECT jsonb_agg(jsonb_build_object('StageID', s.stage_id, 'StageNo', s.stage_no,
        'StageName', s.stage_name, 'StageKind', s.stage_kind, 'Scored', s.is_scored, 'State', s.stage_state,
        'HiddenUntilAvailable', s.hidden_until_available) ORDER BY s.stage_no)
        FROM public.event_competition_stages_v2 s WHERE s.event_id = trim(p_event_id)), '[]'::jsonb),
      'Teams', coalesce((SELECT jsonb_agg(jsonb_build_object('TeamID', t.team_id, 'TeamName', t.team_name,
        'Score', coalesce(total.score, 0), 'StageScores', coalesce((SELECT jsonb_object_agg(ss.stage_id, ss.score)
          FROM stage_scores ss WHERE ss.team_id = t.team_id), '{}'::jsonb)) ORDER BY coalesce(total.score, 0) DESC, t.team_id)
        FROM public.teams_v2 t LEFT JOIN totals total ON total.team_id = t.team_id
        WHERE t.event_id = trim(p_event_id) AND t.is_active), '[]'::jsonb));
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_competition_public_projector_projection(p_event_id text)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
    WITH active_stage AS (
      SELECT stage_name, stage_state FROM public.event_competition_stages_v2
       WHERE event_id = trim(p_event_id) AND stage_state = 'ACTIVE' ORDER BY stage_no LIMIT 1
    ), scores AS (SELECT team_id, sum(score_delta) score FROM public.score_transactions_v2
       WHERE event_id = trim(p_event_id) GROUP BY team_id), teams AS (
      SELECT t.team_name, t.country, t.team_flag, coalesce(s.score, 0) score,
       dense_rank() OVER (ORDER BY coalesce(s.score, 0) DESC, t.team_id) rank
      FROM public.teams_v2 t LEFT JOIN scores s ON s.team_id = t.team_id
      WHERE t.event_id = trim(p_event_id) AND t.is_active
    ) SELECT jsonb_build_object('Event', jsonb_build_object('EventName', e.event_name,
       'CurrentStage', coalesce((SELECT stage_name FROM active_stage), ''),
       'CurrentStageState', coalesce((SELECT stage_state FROM active_stage), 'READY')),
       'Teams', coalesce((SELECT jsonb_agg(jsonb_build_object('Country', country, 'Flag', team_flag,
         'TeamName', team_name, 'Rank', rank, 'Score', score) ORDER BY rank, team_name) FROM teams), '[]'::jsonb))
    FROM public.events_v2 e JOIN public.event_hunt_configurations_v2 h ON h.event_id = e.event_id
     WHERE e.event_id = trim(p_event_id) AND h.projector_public_enabled;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_set_participant_location_visibility(
    p_event_id text, p_visibility_mode text, p_actor text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_config public.event_location_configurations_v2%rowtype; v_mode text := upper(trim(p_visibility_mode));
BEGIN
    IF nullif(trim(p_actor), '') IS NULL OR v_mode NOT IN ('OFF', 'TEAM_LEADERS') THEN
        RAISE EXCEPTION 'Participant location visibility must be OFF or TEAM_LEADERS';
    END IF;
    SELECT * INTO v_config FROM public.event_location_configurations_v2 WHERE event_id = trim(p_event_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Live location is not configured for this event'; END IF;
    UPDATE public.event_location_configurations_v2 SET participant_visibility_mode = v_mode, updated_at = now()
      WHERE event_id = v_config.event_id;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, before_state, after_state)
    VALUES (v_config.event_id, trim(p_actor), 'PARTICIPANT_LOCATION_VISIBILITY_SET',
      'event_location_configurations_v2', v_config.event_id,
      jsonb_build_object('ParticipantVisibilityMode', v_config.participant_visibility_mode),
      jsonb_build_object('ParticipantVisibilityMode', v_mode));
    RETURN jsonb_build_object('EventID', v_config.event_id, 'ParticipantVisibilityMode', v_mode);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_other_team_leader_locations(p_session_token text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_session public.participant_sessions_v2%rowtype; v_config public.event_location_configurations_v2%rowtype;
BEGIN
    SELECT * INTO v_session FROM public.participant_sessions_v2
      WHERE session_token::text = trim(p_session_token) AND is_active;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT * INTO v_config FROM public.event_location_configurations_v2 WHERE event_id = v_session.event_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('Configured', false, 'Locations', '[]'::jsonb); END IF;
    IF v_config.participant_visibility_mode <> 'TEAM_LEADERS' OR NOT v_config.enabled
       OR now() < v_config.tracking_starts_at OR now() >= v_config.tracking_ends_at THEN
        RETURN jsonb_build_object('Configured', true, 'VisibilityMode', v_config.participant_visibility_mode,
          'Locations', '[]'::jsonb);
    END IF;
    RETURN jsonb_build_object('Configured', true, 'VisibilityMode', 'TEAM_LEADERS', 'Locations', coalesce((
      WITH own AS (SELECT team_id FROM public.participants_v2 WHERE participant_id = v_session.participant_id),
      latest AS (SELECT DISTINCT ON (u.participant_id) u.* FROM public.participant_location_updates_v2 u
        WHERE u.event_id = v_session.event_id ORDER BY u.participant_id, u.received_at DESC)
      SELECT jsonb_agg(jsonb_build_object('TeamID', t.team_id, 'TeamName', t.team_name,
        'Country', t.country, 'Flag', t.team_flag,
        'Status', CASE WHEN l.location_update_id IS NULL THEN 'UNAVAILABLE'
          WHEN l.received_at >= now() - make_interval(secs => v_config.stale_after_seconds) THEN 'CURRENT' ELSE 'STALE' END,
        'Latitude', CASE WHEN l.received_at >= now() - make_interval(secs => v_config.stale_after_seconds) THEN l.latitude ELSE NULL END,
        'Longitude', CASE WHEN l.received_at >= now() - make_interval(secs => v_config.stale_after_seconds) THEN l.longitude ELSE NULL END,
        'LastUpdate', l.received_at) ORDER BY t.team_id)
      FROM public.teams_v2 t JOIN public.participants_v2 leader ON leader.event_id = t.event_id AND leader.team_id = t.team_id
        AND leader.is_team_formation_captain AND NOT leader.is_archived AND leader.merged_into_participant_id IS NULL
      LEFT JOIN latest l ON l.participant_id = leader.participant_id
      WHERE t.event_id = v_session.event_id AND t.team_id <> (SELECT team_id FROM own) AND t.is_active
    ), '[]'::jsonb));
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_hunt_submission_competition_stage_guard()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF NEW.submission_payload ? 'HuntMissionID'
       AND EXISTS (SELECT 1 FROM public.event_competition_stages_v2 s
         WHERE s.event_id = NEW.event_id AND s.stage_kind = 'HUNT')
       AND NOT EXISTS (SELECT 1 FROM public.event_competition_stages_v2 s
         WHERE s.event_id = NEW.event_id AND s.stage_kind = 'HUNT' AND s.stage_state = 'ACTIVE') THEN
        RAISE EXCEPTION 'Hunt submissions are unavailable until the configured Hunt competition stage is ACTIVE';
    END IF;
    RETURN NEW;
END; $$;

DROP TRIGGER IF EXISTS exos_v2_hunt_submission_competition_stage_guard_trg ON public.submissions_v2;
CREATE TRIGGER exos_v2_hunt_submission_competition_stage_guard_trg
BEFORE INSERT OR UPDATE OF submission_payload ON public.submissions_v2
FOR EACH ROW EXECUTE FUNCTION public.exos_v2_hunt_submission_competition_stage_guard();

CREATE OR REPLACE FUNCTION public.exos_v2_hybrid_anchored_hunt_workspace(p_session_token text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_session public.participant_sessions_v2%rowtype; v_workspace jsonb; v_stage public.event_competition_stages_v2%rowtype;
        v_members jsonb;
BEGIN
    SELECT * INTO v_session FROM public.participant_sessions_v2 WHERE session_token::text = trim(p_session_token) AND is_active;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    v_workspace := public.exos_v2_hunt_participant_workspace(p_session_token);
    SELECT * INTO v_stage FROM public.event_competition_stages_v2 WHERE event_id = v_session.event_id AND stage_kind = 'HUNT'
      ORDER BY stage_no LIMIT 1;
    SELECT coalesce(jsonb_agg(jsonb_build_object('ParticipantID', p.participant_id::text, 'DisplayName', p.display_name,
      'AttendanceState', coalesce(a.attendance_state, 'UNMARKED'), 'IsCaptain', p.is_team_formation_captain,
      'IsYou', p.participant_id = v_session.participant_id,
      'IsHODAnchor', coalesce(p.participant_payload #>> '{TeamFormation,AssignmentRole}', '') = 'HOD_ANCHOR') ORDER BY p.created_at), '[]'::jsonb)
      INTO v_members FROM public.participants_v2 p LEFT JOIN public.participant_attendance_v2 a
      ON a.event_id = p.event_id AND a.participant_id = p.participant_id
      WHERE p.event_id = v_session.event_id AND p.team_id = v_workspace ->> 'TeamID'
        AND NOT p.is_archived AND p.merged_into_participant_id IS NULL;
    v_workspace := jsonb_set(v_workspace, '{TeamMembers}', v_members, true)
      || jsonb_build_object('CompetitionStageID', coalesce(v_stage.stage_id, ''),
        'CompetitionStageState', coalesce(v_stage.stage_state, 'LOCKED'),
        'IsHODAnchor', coalesce((SELECT p.participant_payload #>> '{TeamFormation,AssignmentRole}' = 'HOD_ANCHOR'
          FROM public.participants_v2 p WHERE p.participant_id = v_session.participant_id), false));
    IF v_stage.stage_id IS NOT NULL AND v_stage.hidden_until_available
       AND v_stage.stage_state NOT IN ('AVAILABLE', 'ACTIVE', 'COMPLETED') THEN
        v_workspace := jsonb_set(v_workspace, '{Missions}', '[]'::jsonb, true)
          || jsonb_build_object('FutureStageHidden', true);
    END IF;
    RETURN v_workspace;
END; $$;

REVOKE ALL ON FUNCTION public.exos_v2_configure_hybrid_anchored_team_formation(text,jsonb,jsonb,text),
  public.exos_v2_open_hybrid_anchored_team_formation(text,text),
  public.exos_v2_hybrid_anchored_operator_roster(text),
  public.exos_v2_upsert_competition_stage(text,text,integer,text,text,boolean,text,boolean,jsonb,text),
  public.exos_v2_set_competition_stage_state(text,text,text,text),
  public.exos_v2_record_competition_stage_score(text,text,text,numeric,text,text,text),
  public.exos_v2_competition_stage_snapshot(text),
  public.exos_v2_set_participant_location_visibility(text,text,text),
  public.exos_v2_hunt_submission_competition_stage_guard()
FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_hybrid_anchored_register_random(text,text,text,text),
  public.exos_v2_hybrid_anchored_claim_personal_key(text,text,text),
  public.exos_v2_hybrid_anchored_hunt_workspace(text),
  public.exos_v2_other_team_leader_locations(text),
  public.exos_v2_competition_public_projector_projection(text)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.exos_v2_configure_hybrid_anchored_team_formation(text,jsonb,jsonb,text),
  public.exos_v2_open_hybrid_anchored_team_formation(text,text),
  public.exos_v2_hybrid_anchored_operator_roster(text),
  public.exos_v2_upsert_competition_stage(text,text,integer,text,text,boolean,text,boolean,jsonb,text),
  public.exos_v2_set_competition_stage_state(text,text,text,text),
  public.exos_v2_record_competition_stage_score(text,text,text,numeric,text,text,text),
  public.exos_v2_competition_stage_snapshot(text),
  public.exos_v2_set_participant_location_visibility(text,text,text)
TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_hybrid_anchored_register_random(text,text,text,text),
  public.exos_v2_hybrid_anchored_claim_personal_key(text,text,text),
  public.exos_v2_hybrid_anchored_hunt_workspace(text),
  public.exos_v2_other_team_leader_locations(text),
  public.exos_v2_competition_public_projector_projection(text)
TO anon, authenticated, service_role;

COMMIT;
