-- EXOS Core v2 reusable Live Location + Announcements V1.
--
-- ADDITIVE ONLY. This migration is deliberately not event-specific. It adds no
-- public projection, no score mutation, and no automatic GPS award path.
BEGIN;

CREATE TABLE IF NOT EXISTS public.event_location_configurations_v2 (
    event_id text PRIMARY KEY REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    enabled boolean NOT NULL DEFAULT false,
    tracking_mode text NOT NULL DEFAULT 'INDIVIDUAL',
    tracking_starts_at timestamptz,
    tracking_ends_at timestamptz,
    cadence_seconds integer NOT NULL DEFAULT 20,
    stale_after_seconds integer NOT NULL DEFAULT 90,
    retention_hours integer NOT NULL DEFAULT 24,
    maximum_accuracy_meters numeric(10,2) NOT NULL DEFAULT 1000,
    separation_threshold_meters numeric(10,2) NOT NULL DEFAULT 250,
    configured_by text NOT NULL,
    configured_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (tracking_mode IN ('INDIVIDUAL', 'TEAM_DESIGNATED')),
    CHECK (cadence_seconds BETWEEN 15 AND 30),
    CHECK (stale_after_seconds BETWEEN 45 AND 180),
    CHECK (retention_hours BETWEEN 1 AND 168),
    CHECK (maximum_accuracy_meters BETWEEN 1 AND 10000),
    CHECK (separation_threshold_meters BETWEEN 10 AND 10000),
    CHECK (
        (enabled = false AND tracking_starts_at IS NULL AND tracking_ends_at IS NULL)
        OR (enabled = true AND tracking_starts_at IS NOT NULL
            AND tracking_ends_at IS NOT NULL AND tracking_ends_at > tracking_starts_at)
    )
);

CREATE TABLE IF NOT EXISTS public.participant_location_consents_v2 (
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    participant_id uuid NOT NULL REFERENCES public.participants_v2(participant_id) ON DELETE CASCADE,
    consent_state text NOT NULL,
    consented_at timestamptz,
    revoked_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, participant_id),
    CHECK (consent_state IN ('ENABLED', 'DECLINED', 'STOPPED')),
    CHECK ((consent_state = 'ENABLED' AND consented_at IS NOT NULL AND revoked_at IS NULL)
        OR (consent_state IN ('DECLINED', 'STOPPED') AND revoked_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS public.participant_location_updates_v2 (
    location_update_id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    participant_id uuid NOT NULL REFERENCES public.participants_v2(participant_id) ON DELETE CASCADE,
    team_id text NOT NULL REFERENCES public.teams_v2(team_id) ON DELETE RESTRICT,
    captured_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    latitude numeric(9,6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude numeric(9,6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    accuracy_meters numeric(10,2),
    heading_degrees numeric(6,2),
    speed_mps numeric(10,3),
    device_id text NOT NULL,
    CHECK (accuracy_meters IS NULL OR accuracy_meters >= 0),
    CHECK (heading_degrees IS NULL OR heading_degrees BETWEEN 0 AND 360),
    CHECK (speed_mps IS NULL OR speed_mps >= 0)
);

CREATE INDEX IF NOT EXISTS participant_location_updates_event_participant_received_idx
    ON public.participant_location_updates_v2(event_id, participant_id, received_at DESC);
CREATE INDEX IF NOT EXISTS participant_location_updates_event_team_received_idx
    ON public.participant_location_updates_v2(event_id, team_id, received_at DESC);

CREATE TABLE IF NOT EXISTS public.event_location_checkpoints_v2 (
    checkpoint_id text PRIMARY KEY,
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    checkpoint_name text NOT NULL,
    latitude numeric(9,6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude numeric(9,6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    radius_meters numeric(10,2) NOT NULL CHECK (radius_meters BETWEEN 10 AND 10000),
    is_active boolean NOT NULL DEFAULT true,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (event_id, checkpoint_name)
);

CREATE TABLE IF NOT EXISTS public.event_announcements_v2 (
    announcement_id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    target_type text NOT NULL,
    severity text NOT NULL,
    title text,
    message text NOT NULL,
    acknowledgement_required boolean NOT NULL DEFAULT false,
    created_by text NOT NULL,
    idempotency_key text NOT NULL CHECK (length(trim(idempotency_key)) BETWEEN 1 AND 128),
    idempotency_fingerprint text NOT NULL CHECK (length(idempotency_fingerprint) = 32),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    CHECK (target_type IN ('ALL', 'TEAM', 'PARTICIPANT')),
    CHECK (severity IN ('INFO', 'IMPORTANT', 'URGENT')),
    CHECK (length(trim(message)) BETWEEN 1 AND 2000),
    CHECK (expires_at IS NULL OR expires_at > created_at),
    UNIQUE (event_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS event_announcements_event_created_idx
    ON public.event_announcements_v2(event_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.event_announcement_targets_v2 (
    announcement_id uuid NOT NULL REFERENCES public.event_announcements_v2(announcement_id) ON DELETE CASCADE,
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    target_id text NOT NULL,
    PRIMARY KEY (announcement_id, target_id)
);
CREATE INDEX IF NOT EXISTS event_announcement_targets_event_target_idx
    ON public.event_announcement_targets_v2(event_id, target_id);

CREATE TABLE IF NOT EXISTS public.participant_announcement_acknowledgements_v2 (
    announcement_id uuid NOT NULL REFERENCES public.event_announcements_v2(announcement_id) ON DELETE CASCADE,
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    participant_id uuid NOT NULL REFERENCES public.participants_v2(participant_id) ON DELETE CASCADE,
    acknowledged_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (announcement_id, participant_id)
);
CREATE INDEX IF NOT EXISTS participant_announcement_ack_event_participant_idx
    ON public.participant_announcement_acknowledgements_v2(event_id, participant_id);

ALTER TABLE public.event_location_configurations_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.participant_location_consents_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.participant_location_updates_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_location_checkpoints_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_announcements_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_announcement_targets_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.participant_announcement_acknowledgements_v2 ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.event_location_configurations_v2,
    public.participant_location_consents_v2, public.participant_location_updates_v2,
    public.event_location_checkpoints_v2, public.event_announcements_v2,
    public.event_announcement_targets_v2, public.participant_announcement_acknowledgements_v2
FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.exos_v2_configure_live_location(
    p_event_id text, p_enabled boolean, p_tracking_mode text,
    p_tracking_starts_at timestamptz, p_tracking_ends_at timestamptz,
    p_cadence_seconds integer, p_stale_after_seconds integer,
    p_retention_hours integer, p_maximum_accuracy_meters numeric,
    p_separation_threshold_meters numeric, p_actor text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_event public.events_v2%rowtype;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID and operator identity are required';
    END IF;
    IF upper(coalesce(p_tracking_mode, '')) NOT IN ('INDIVIDUAL', 'TEAM_DESIGNATED')
       OR coalesce(p_cadence_seconds, 0) NOT BETWEEN 15 AND 30
       OR coalesce(p_stale_after_seconds, 0) NOT BETWEEN 45 AND 180
       OR coalesce(p_retention_hours, 0) NOT BETWEEN 1 AND 168
       OR coalesce(p_maximum_accuracy_meters, 0) NOT BETWEEN 1 AND 10000
       OR coalesce(p_separation_threshold_meters, 0) NOT BETWEEN 10 AND 10000 THEN
        RAISE EXCEPTION 'Live location configuration is invalid';
    END IF;
    IF p_enabled AND (p_tracking_starts_at IS NULL OR p_tracking_ends_at IS NULL OR p_tracking_ends_at <= p_tracking_starts_at) THEN
        RAISE EXCEPTION 'Enabled live location requires a bounded event tracking window';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = trim(p_event_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Event not found'; END IF;
    INSERT INTO public.event_location_configurations_v2(
        event_id, enabled, tracking_mode, tracking_starts_at, tracking_ends_at,
        cadence_seconds, stale_after_seconds, retention_hours, maximum_accuracy_meters,
        separation_threshold_meters, configured_by
    ) VALUES (
        v_event.event_id, coalesce(p_enabled, false), upper(trim(p_tracking_mode)),
        CASE WHEN p_enabled THEN p_tracking_starts_at ELSE NULL END,
        CASE WHEN p_enabled THEN p_tracking_ends_at ELSE NULL END,
        p_cadence_seconds, p_stale_after_seconds, p_retention_hours,
        p_maximum_accuracy_meters, p_separation_threshold_meters, trim(p_actor)
    ) ON CONFLICT (event_id) DO UPDATE SET
        enabled = excluded.enabled, tracking_mode = excluded.tracking_mode,
        tracking_starts_at = excluded.tracking_starts_at, tracking_ends_at = excluded.tracking_ends_at,
        cadence_seconds = excluded.cadence_seconds, stale_after_seconds = excluded.stale_after_seconds,
        retention_hours = excluded.retention_hours, maximum_accuracy_meters = excluded.maximum_accuracy_meters,
        separation_threshold_meters = excluded.separation_threshold_meters,
        configured_by = excluded.configured_by, configured_at = now(), updated_at = now();
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_event.event_id, trim(p_actor), 'LIVE_LOCATION_CONFIGURED', 'event_location_configurations_v2', v_event.event_id,
        jsonb_build_object('Enabled', coalesce(p_enabled, false), 'TrackingMode', upper(trim(p_tracking_mode)),
            'CadenceSeconds', p_cadence_seconds, 'StaleAfterSeconds', p_stale_after_seconds,
            'RetentionHours', p_retention_hours));
    RETURN jsonb_build_object('EventID', v_event.event_id, 'Configured', true);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_set_live_location_consent(
    p_session_token text, p_enabled boolean
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_session public.participant_sessions_v2%rowtype; v_config public.event_location_configurations_v2%rowtype;
BEGIN
    SELECT * INTO v_session FROM public.participant_sessions_v2
     WHERE session_token::text = trim(p_session_token) AND is_active FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT * INTO v_config FROM public.event_location_configurations_v2 WHERE event_id = v_session.event_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Live location is not configured for this event'; END IF;
    IF p_enabled AND (NOT v_config.enabled OR now() < v_config.tracking_starts_at OR now() >= v_config.tracking_ends_at) THEN
        RAISE EXCEPTION 'Live location is not active for this event';
    END IF;
    INSERT INTO public.participant_location_consents_v2(event_id, participant_id, consent_state, consented_at, revoked_at)
    VALUES (v_session.event_id, v_session.participant_id,
        CASE WHEN p_enabled THEN 'ENABLED' ELSE 'STOPPED' END,
        CASE WHEN p_enabled THEN now() ELSE NULL END,
        CASE WHEN p_enabled THEN NULL ELSE now() END)
    ON CONFLICT (event_id, participant_id) DO UPDATE SET
        consent_state = excluded.consent_state, consented_at = excluded.consented_at,
        revoked_at = excluded.revoked_at, updated_at = now();
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_session.event_id, 'participant_live_location',
        CASE WHEN p_enabled THEN 'LIVE_LOCATION_CONSENTED' ELSE 'LIVE_LOCATION_STOPPED' END,
        'participants_v2', v_session.participant_id::text, jsonb_build_object('Enabled', p_enabled));
    RETURN jsonb_build_object('EventID', v_session.event_id, 'Enabled', p_enabled);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_submit_live_location(
    p_session_token text, p_device_id text, p_latitude numeric, p_longitude numeric,
    p_accuracy_meters numeric DEFAULT NULL, p_heading_degrees numeric DEFAULT NULL,
    p_speed_mps numeric DEFAULT NULL, p_captured_at timestamptz DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_session public.participant_sessions_v2%rowtype; v_config public.event_location_configurations_v2%rowtype;
        v_consent public.participant_location_consents_v2%rowtype; v_captured_at timestamptz := coalesce(p_captured_at, now()); v_id uuid;
BEGIN
    IF nullif(trim(p_device_id), '') IS NULL OR p_latitude NOT BETWEEN -90 AND 90 OR p_longitude NOT BETWEEN -180 AND 180
       OR (p_accuracy_meters IS NOT NULL AND p_accuracy_meters < 0)
       OR (p_heading_degrees IS NOT NULL AND p_heading_degrees NOT BETWEEN 0 AND 360)
       OR (p_speed_mps IS NOT NULL AND p_speed_mps < 0) THEN
        RAISE EXCEPTION 'Live location payload is invalid';
    END IF;
    SELECT * INTO v_session FROM public.participant_sessions_v2
     WHERE session_token::text = trim(p_session_token) AND is_active AND device_id = trim(p_device_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session or device is invalid'; END IF;
    SELECT * INTO v_config FROM public.event_location_configurations_v2 WHERE event_id = v_session.event_id;
    IF NOT FOUND OR NOT v_config.enabled OR now() < v_config.tracking_starts_at OR now() >= v_config.tracking_ends_at THEN
        RAISE EXCEPTION 'Live location is not active for this event';
    END IF;
    SELECT * INTO v_consent FROM public.participant_location_consents_v2
     WHERE event_id = v_session.event_id AND participant_id = v_session.participant_id AND consent_state = 'ENABLED';
    IF NOT FOUND THEN RAISE EXCEPTION 'Live location consent is required'; END IF;
    IF v_captured_at < now() - interval '10 minutes' OR v_captured_at > now() + interval '2 minutes' THEN
        RAISE EXCEPTION 'Live location timestamp is outside the accepted window';
    END IF;
    INSERT INTO public.participant_location_updates_v2(event_id, participant_id, team_id, captured_at, latitude, longitude,
        accuracy_meters, heading_degrees, speed_mps, device_id)
    SELECT v_session.event_id, v_session.participant_id, p.team_id, v_captured_at, p_latitude, p_longitude,
        p_accuracy_meters, p_heading_degrees, p_speed_mps, trim(p_device_id)
      FROM public.participants_v2 p WHERE p.participant_id = v_session.participant_id AND p.event_id = v_session.event_id
    RETURNING location_update_id INTO v_id;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_session.event_id, 'participant_live_location', 'LIVE_LOCATION_UPDATED',
        'participant_location_updates_v2', v_id::text, jsonb_build_object('CapturedAt', v_captured_at, 'AccuracyMeters', p_accuracy_meters));
    RETURN jsonb_build_object('EventID', v_session.event_id, 'LocationUpdateID', v_id::text,
        'Status', 'CURRENT', 'CapturedAt', v_captured_at, 'AccuracyMeters', p_accuracy_meters);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_live_location_participant_state(p_session_token text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_session public.participant_sessions_v2%rowtype; v_config public.event_location_configurations_v2%rowtype;
        v_consent public.participant_location_consents_v2%rowtype; v_location public.participant_location_updates_v2%rowtype; v_status text;
BEGIN
    SELECT * INTO v_session FROM public.participant_sessions_v2 WHERE session_token::text = trim(p_session_token) AND is_active;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT * INTO v_config FROM public.event_location_configurations_v2 WHERE event_id = v_session.event_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('Configured', false); END IF;
    SELECT * INTO v_consent FROM public.participant_location_consents_v2 WHERE event_id = v_session.event_id AND participant_id = v_session.participant_id;
    SELECT * INTO v_location FROM public.participant_location_updates_v2 WHERE event_id = v_session.event_id AND participant_id = v_session.participant_id ORDER BY received_at DESC LIMIT 1;
    v_status := CASE WHEN NOT v_config.enabled OR now() < v_config.tracking_starts_at OR now() >= v_config.tracking_ends_at THEN 'UNAVAILABLE'
        WHEN coalesce(v_consent.consent_state, '') <> 'ENABLED' THEN 'UNAVAILABLE'
        WHEN v_location.location_update_id IS NULL THEN 'UNAVAILABLE'
        WHEN v_location.received_at >= now() - make_interval(secs => v_config.stale_after_seconds) THEN 'CURRENT' ELSE 'STALE' END;
    RETURN jsonb_build_object('Configured', true, 'EventID', v_session.event_id, 'Enabled', v_config.enabled,
        'TrackingMode', v_config.tracking_mode, 'CadenceSeconds', v_config.cadence_seconds,
        'StaleAfterSeconds', v_config.stale_after_seconds, 'ConsentState', coalesce(v_consent.consent_state, 'DECLINED'),
        'Status', v_status, 'LastUpdate', v_location.received_at, 'CapturedAt', v_location.captured_at,
        'AccuracyMeters', v_location.accuracy_meters);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_live_location_operator_map(p_event_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_config public.event_location_configurations_v2%rowtype;
BEGIN
    SELECT * INTO v_config FROM public.event_location_configurations_v2 WHERE event_id = trim(p_event_id);
    IF NOT FOUND THEN RAISE EXCEPTION 'Live location is not configured for this event'; END IF;
    RETURN jsonb_build_object('EventID', v_config.event_id, 'Enabled', v_config.enabled,
        'CadenceSeconds', v_config.cadence_seconds, 'StaleAfterSeconds', v_config.stale_after_seconds,
        'SeparationThresholdMeters', v_config.separation_threshold_meters,
        'Participants', coalesce((
            WITH last_locations AS (
                SELECT DISTINCT ON (u.participant_id) u.* FROM public.participant_location_updates_v2 u
                 WHERE u.event_id = v_config.event_id ORDER BY u.participant_id, u.received_at DESC
            ) SELECT jsonb_agg(jsonb_build_object(
                'ParticipantID', p.participant_id::text, 'ParticipantName', p.display_name, 'TeamID', p.team_id,
                'Latitude', l.latitude, 'Longitude', l.longitude, 'AccuracyMeters', l.accuracy_meters,
                'LastUpdate', l.received_at, 'Status', CASE WHEN coalesce(c.consent_state, '') <> 'ENABLED' OR l.location_update_id IS NULL THEN 'UNAVAILABLE'
                    WHEN l.received_at >= now() - make_interval(secs => v_config.stale_after_seconds) THEN 'CURRENT' ELSE 'STALE' END
            ) ORDER BY p.team_id, p.display_name)
              FROM public.participants_v2 p
              LEFT JOIN public.participant_location_consents_v2 c ON c.event_id = p.event_id AND c.participant_id = p.participant_id
              LEFT JOIN last_locations l ON l.participant_id = p.participant_id
             WHERE p.event_id = v_config.event_id AND NOT p.is_archived AND p.merged_into_participant_id IS NULL
        ), '[]'::jsonb));
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_live_location_history(
    p_event_id text, p_participant_id uuid, p_limit integer DEFAULT 20
) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
    SELECT coalesce(jsonb_agg(jsonb_build_object('Latitude', u.latitude, 'Longitude', u.longitude,
        'CapturedAt', u.captured_at, 'ReceivedAt', u.received_at, 'AccuracyMeters', u.accuracy_meters)
        ORDER BY u.received_at DESC), '[]'::jsonb)
      FROM (SELECT * FROM public.participant_location_updates_v2
             WHERE event_id = trim(p_event_id) AND participant_id = p_participant_id
             ORDER BY received_at DESC LIMIT greatest(1, least(coalesce(p_limit, 20), 100))) u;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_upsert_live_location_checkpoint(
    p_event_id text, p_checkpoint_id text, p_name text, p_latitude numeric, p_longitude numeric,
    p_radius_meters numeric, p_active boolean, p_actor text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL OR nullif(trim(p_checkpoint_id), '') IS NULL OR nullif(trim(p_name), '') IS NULL
       OR nullif(trim(p_actor), '') IS NULL OR p_latitude NOT BETWEEN -90 AND 90 OR p_longitude NOT BETWEEN -180 AND 180
       OR p_radius_meters NOT BETWEEN 10 AND 10000 THEN RAISE EXCEPTION 'Live location checkpoint is invalid'; END IF;
    IF NOT EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = trim(p_event_id)) THEN RAISE EXCEPTION 'Event not found'; END IF;
    INSERT INTO public.event_location_checkpoints_v2(checkpoint_id, event_id, checkpoint_name, latitude, longitude, radius_meters, is_active, created_by)
    VALUES (trim(p_checkpoint_id), trim(p_event_id), trim(p_name), p_latitude, p_longitude, p_radius_meters, coalesce(p_active, true), trim(p_actor))
    ON CONFLICT (checkpoint_id) DO UPDATE SET checkpoint_name = excluded.checkpoint_name, latitude = excluded.latitude,
        longitude = excluded.longitude, radius_meters = excluded.radius_meters, is_active = excluded.is_active, updated_at = now()
    WHERE public.event_location_checkpoints_v2.event_id = excluded.event_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Checkpoint belongs to a different event'; END IF;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (trim(p_event_id), trim(p_actor), 'LIVE_LOCATION_CHECKPOINT_SAVED', 'event_location_checkpoints_v2', trim(p_checkpoint_id),
        jsonb_build_object('Active', coalesce(p_active, true), 'RadiusMeters', p_radius_meters));
    RETURN jsonb_build_object('CheckpointID', trim(p_checkpoint_id), 'Saved', true);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_live_location_checkpoint_proximity(p_session_token text)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
    WITH session_row AS (
        SELECT * FROM public.participant_sessions_v2 WHERE session_token::text = trim(p_session_token) AND is_active
    ), latest AS (
        SELECT DISTINCT ON (u.participant_id) u.* FROM public.participant_location_updates_v2 u JOIN session_row s ON s.event_id = u.event_id AND s.participant_id = u.participant_id
        ORDER BY u.participant_id, u.received_at DESC
    ), distances AS (
        SELECT c.checkpoint_id, c.checkpoint_name, c.radius_meters,
          6371000 * acos(least(1, greatest(-1,
            cos(radians(l.latitude::float8)) * cos(radians(c.latitude::float8))
              * cos(radians(c.longitude::float8) - radians(l.longitude::float8))
            + sin(radians(l.latitude::float8)) * sin(radians(c.latitude::float8))
          ))) AS distance_meters
        FROM session_row s JOIN latest l ON true
        JOIN public.event_location_checkpoints_v2 c ON c.event_id = s.event_id AND c.is_active
    ) SELECT coalesce(jsonb_agg(jsonb_build_object(
        'CheckpointID', checkpoint_id, 'Name', checkpoint_name,
        'DistanceMeters', round(distance_meters::numeric, 1), 'RadiusMeters', radius_meters,
        'State', CASE WHEN distance_meters <= radius_meters THEN 'ARRIVED'
            WHEN distance_meters <= radius_meters * 2 THEN 'NEAR' ELSE 'OUTSIDE' END
    )), '[]'::jsonb) FROM distances;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_cleanup_live_location(p_event_id text, p_actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_retention integer; v_deleted integer;
BEGIN
    IF nullif(trim(p_actor), '') IS NULL THEN RAISE EXCEPTION 'Operator identity is required'; END IF;
    SELECT retention_hours INTO v_retention FROM public.event_location_configurations_v2 WHERE event_id = trim(p_event_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Live location is not configured for this event'; END IF;
    DELETE FROM public.participant_location_updates_v2 WHERE event_id = trim(p_event_id) AND received_at < now() - make_interval(hours => v_retention);
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (trim(p_event_id), trim(p_actor), 'LIVE_LOCATION_HISTORY_CLEANED', 'participant_location_updates_v2', trim(p_event_id), jsonb_build_object('DeletedRows', v_deleted));
    RETURN jsonb_build_object('EventID', trim(p_event_id), 'DeletedRows', v_deleted, 'RetentionHours', v_retention);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_send_event_announcement(
    p_event_id text, p_target_type text, p_target_ids jsonb, p_severity text, p_title text,
    p_message text, p_expires_at timestamptz, p_acknowledgement_required boolean,
    p_actor text, p_idempotency_key text, p_confirm_all_urgent boolean DEFAULT false
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_id uuid;
    v_target text;
    v_target_count integer := 0;
    v_type text := upper(trim(p_target_type));
    v_severity text := upper(trim(p_severity));
    v_targets jsonb := '[]'::jsonb;
    v_title text := nullif(trim(coalesce(p_title, '')), '');
    v_fingerprint text;
    v_stored_fingerprint text;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL OR nullif(trim(p_actor), '') IS NULL OR length(trim(coalesce(p_message, ''))) NOT BETWEEN 1 AND 2000
       OR v_type NOT IN ('ALL', 'TEAM', 'PARTICIPANT') OR v_severity NOT IN ('INFO', 'IMPORTANT', 'URGENT')
       OR nullif(trim(p_idempotency_key), '') IS NULL OR length(trim(p_idempotency_key)) > 128
       OR (p_expires_at IS NOT NULL AND p_expires_at <= now()) THEN RAISE EXCEPTION 'Announcement is invalid'; END IF;
    IF NOT EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = trim(p_event_id)) THEN RAISE EXCEPTION 'Event not found'; END IF;
    IF v_type = 'ALL' AND v_severity = 'URGENT' AND NOT coalesce(p_confirm_all_urgent, false) THEN
        RAISE EXCEPTION 'ALL + URGENT announcements require explicit confirmation';
    END IF;
    IF v_type <> 'ALL' AND (p_target_ids IS NULL OR jsonb_typeof(p_target_ids) <> 'array' OR jsonb_array_length(p_target_ids) = 0) THEN
        RAISE EXCEPTION 'Targeted announcement requires target IDs';
    END IF;
    IF v_type <> 'ALL' THEN
        SELECT coalesce(jsonb_agg(target_id ORDER BY target_id), '[]'::jsonb)
          INTO v_targets
          FROM (SELECT DISTINCT trim(value) AS target_id
                  FROM jsonb_array_elements_text(p_target_ids) value
                 WHERE nullif(trim(value), '') IS NOT NULL) normalized_targets;
        IF jsonb_array_length(v_targets) = 0 THEN RAISE EXCEPTION 'Targeted announcement requires target IDs'; END IF;
        FOR v_target IN SELECT value FROM jsonb_array_elements_text(v_targets) value LOOP
            IF v_type = 'TEAM' AND NOT EXISTS (SELECT 1 FROM public.teams_v2 WHERE event_id = trim(p_event_id) AND team_id = v_target AND is_active) THEN
                RAISE EXCEPTION 'Announcement target team is outside this event';
            ELSIF v_type = 'PARTICIPANT' AND NOT EXISTS (SELECT 1 FROM public.participants_v2 WHERE event_id = trim(p_event_id) AND participant_id::text = v_target AND NOT is_archived) THEN
                RAISE EXCEPTION 'Announcement target participant is outside this event';
            END IF;
            v_target_count := v_target_count + 1;
        END LOOP;
    END IF;
    v_fingerprint := md5(jsonb_build_object(
        'TargetType', v_type, 'TargetIDs', v_targets, 'Severity', v_severity,
        'Title', v_title, 'Message', trim(p_message), 'ExpiresAt', p_expires_at,
        'AcknowledgementRequired', coalesce(p_acknowledgement_required, false), 'Actor', trim(p_actor)
    )::text);
    INSERT INTO public.event_announcements_v2(
        event_id, target_type, severity, title, message, acknowledgement_required,
        created_by, idempotency_key, idempotency_fingerprint, expires_at
    ) VALUES (
        trim(p_event_id), v_type, v_severity, v_title, trim(p_message), coalesce(p_acknowledgement_required, false),
        trim(p_actor), trim(p_idempotency_key), v_fingerprint, p_expires_at
    ) ON CONFLICT (event_id, idempotency_key) DO NOTHING
    RETURNING announcement_id INTO v_id;
    IF v_id IS NULL THEN
        SELECT announcement_id, idempotency_fingerprint INTO v_id, v_stored_fingerprint
          FROM public.event_announcements_v2
         WHERE event_id = trim(p_event_id) AND idempotency_key = trim(p_idempotency_key);
        IF v_stored_fingerprint IS DISTINCT FROM v_fingerprint THEN
            RAISE EXCEPTION 'Announcement idempotency key was already used for a different payload';
        END IF;
        RETURN jsonb_build_object('AnnouncementID', v_id::text, 'EventID', trim(p_event_id), 'Sent', true, 'Idempotent', true);
    END IF;
    IF v_type <> 'ALL' THEN
        FOR v_target IN SELECT value FROM jsonb_array_elements_text(v_targets) value LOOP
            INSERT INTO public.event_announcement_targets_v2(announcement_id, event_id, target_id)
            VALUES (v_id, trim(p_event_id), v_target);
        END LOOP;
    END IF;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (trim(p_event_id), trim(p_actor), 'EVENT_ANNOUNCEMENT_SENT', 'event_announcements_v2', v_id::text,
        jsonb_build_object('TargetType', v_type, 'TargetCount', v_target_count, 'Severity', v_severity, 'AcknowledgementRequired', coalesce(p_acknowledgement_required, false)));
    RETURN jsonb_build_object('AnnouncementID', v_id::text, 'EventID', trim(p_event_id), 'Sent', true, 'Idempotent', false);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_participant_announcements(p_session_token text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_session public.participant_sessions_v2%rowtype; v_team text;
BEGIN
    SELECT * INTO v_session FROM public.participant_sessions_v2 WHERE session_token::text = trim(p_session_token) AND is_active;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT team_id INTO v_team FROM public.participants_v2 WHERE participant_id = v_session.participant_id AND event_id = v_session.event_id;
    RETURN coalesce((SELECT jsonb_agg(jsonb_build_object('AnnouncementID', a.announcement_id::text, 'Severity', a.severity,
        'Title', a.title, 'Message', a.message, 'CreatedAt', a.created_at, 'ExpiresAt', a.expires_at,
        'AcknowledgementRequired', a.acknowledgement_required, 'AcknowledgedAt', ack.acknowledged_at)
        ORDER BY CASE a.severity WHEN 'URGENT' THEN 1 WHEN 'IMPORTANT' THEN 2 ELSE 3 END, a.created_at DESC)
      FROM public.event_announcements_v2 a
      LEFT JOIN public.participant_announcement_acknowledgements_v2 ack ON ack.announcement_id = a.announcement_id AND ack.participant_id = v_session.participant_id
     WHERE a.event_id = v_session.event_id AND (a.expires_at IS NULL OR a.expires_at > now())
       AND (a.target_type = 'ALL' OR (a.target_type = 'TEAM' AND EXISTS (SELECT 1 FROM public.event_announcement_targets_v2 t WHERE t.announcement_id = a.announcement_id AND t.event_id = v_session.event_id AND t.target_id = v_team))
            OR (a.target_type = 'PARTICIPANT' AND EXISTS (SELECT 1 FROM public.event_announcement_targets_v2 t WHERE t.announcement_id = a.announcement_id AND t.event_id = v_session.event_id AND t.target_id = v_session.participant_id::text)))), '[]'::jsonb);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_acknowledge_event_announcement(p_session_token text, p_announcement_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_session public.participant_sessions_v2%rowtype; v_found boolean;
BEGIN
    SELECT * INTO v_session FROM public.participant_sessions_v2 WHERE session_token::text = trim(p_session_token) AND is_active;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT EXISTS (SELECT 1 FROM jsonb_array_elements(public.exos_v2_participant_announcements(p_session_token)) row WHERE row->>'AnnouncementID' = p_announcement_id::text) INTO v_found;
    IF NOT v_found THEN RAISE EXCEPTION 'Announcement is unavailable to this participant'; END IF;
    INSERT INTO public.participant_announcement_acknowledgements_v2(announcement_id, event_id, participant_id)
    VALUES (p_announcement_id, v_session.event_id, v_session.participant_id) ON CONFLICT (announcement_id, participant_id) DO NOTHING;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_session.event_id, 'participant_announcement', 'EVENT_ANNOUNCEMENT_ACKNOWLEDGED', 'event_announcements_v2', p_announcement_id::text,
        jsonb_build_object('ParticipantID', v_session.participant_id::text));
    RETURN jsonb_build_object('AnnouncementID', p_announcement_id::text, 'Acknowledged', true);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_event_announcements(p_event_id text)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
    SELECT coalesce(jsonb_agg(jsonb_build_object('AnnouncementID', a.announcement_id::text, 'TargetType', a.target_type,
      'TargetIDs', coalesce((SELECT jsonb_agg(t.target_id ORDER BY t.target_id) FROM public.event_announcement_targets_v2 t WHERE t.announcement_id = a.announcement_id), '[]'::jsonb),
      'Severity', a.severity, 'Title', a.title, 'Message', a.message, 'CreatedBy', a.created_by, 'CreatedAt', a.created_at,
      'ExpiresAt', a.expires_at, 'AcknowledgementRequired', a.acknowledgement_required,
      'AcknowledgedCount', (SELECT count(*) FROM public.participant_announcement_acknowledgements_v2 ack WHERE ack.announcement_id = a.announcement_id)), '[]'::jsonb)
    FROM public.event_announcements_v2 a WHERE a.event_id = trim(p_event_id);
$$;

REVOKE ALL ON FUNCTION public.exos_v2_configure_live_location(text,boolean,text,timestamptz,timestamptz,integer,integer,integer,numeric,numeric,text),
    public.exos_v2_live_location_operator_map(text), public.exos_v2_live_location_history(text,uuid,integer),
    public.exos_v2_upsert_live_location_checkpoint(text,text,text,numeric,numeric,numeric,boolean,text),
    public.exos_v2_cleanup_live_location(text,text),
    public.exos_v2_send_event_announcement(text,text,jsonb,text,text,text,timestamptz,boolean,text,text,boolean),
    public.exos_v2_event_announcements(text)
FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.exos_v2_set_live_location_consent(text,boolean),
    public.exos_v2_submit_live_location(text,text,numeric,numeric,numeric,numeric,numeric,timestamptz),
    public.exos_v2_live_location_participant_state(text), public.exos_v2_live_location_checkpoint_proximity(text),
    public.exos_v2_participant_announcements(text), public.exos_v2_acknowledge_event_announcement(text,uuid)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.exos_v2_set_live_location_consent(text,boolean),
    public.exos_v2_submit_live_location(text,text,numeric,numeric,numeric,numeric,numeric,timestamptz),
    public.exos_v2_live_location_participant_state(text), public.exos_v2_live_location_checkpoint_proximity(text),
    public.exos_v2_participant_announcements(text), public.exos_v2_acknowledge_event_announcement(text,uuid)
TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.exos_v2_configure_live_location(text,boolean,text,timestamptz,timestamptz,integer,integer,integer,numeric,numeric,text),
    public.exos_v2_live_location_operator_map(text), public.exos_v2_live_location_history(text,uuid,integer),
    public.exos_v2_upsert_live_location_checkpoint(text,text,text,numeric,numeric,numeric,boolean,text),
    public.exos_v2_cleanup_live_location(text,text),
    public.exos_v2_send_event_announcement(text,text,jsonb,text,text,text,timestamptz,boolean,text,text,boolean),
    public.exos_v2_event_announcements(text)
TO service_role;

COMMIT;
