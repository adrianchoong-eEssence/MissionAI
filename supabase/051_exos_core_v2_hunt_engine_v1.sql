-- EXOS Core v2 reusable Hunt Engine V1.
--
-- ADDITIVE ONLY.  WALK is implemented in this release; ROAD is a valid
-- configuration value reserved for a later engine implementation.  Every
-- table, RPC, and ledger row carries EventID.  GPS proximity remains a fact
-- supplied by 048 and never calls a score-mutating function here.
BEGIN;

CREATE TABLE IF NOT EXISTS public.event_hunt_configurations_v2 (
    event_id text PRIMARY KEY REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    engine_kind text NOT NULL DEFAULT 'HUNT' CHECK (engine_kind = 'HUNT'),
    hunt_mode text NOT NULL CHECK (hunt_mode IN ('WALK', 'ROAD')),
    route_mode text NOT NULL DEFAULT 'OPEN_HUNT' CHECK (route_mode IN ('OPEN_HUNT', 'CONFIGURED_ROUTE')),
    operational_state text NOT NULL DEFAULT 'READY' CHECK (operational_state IN ('READY', 'LIVE', 'HOLD', 'RETURN_NOW', 'CLOSED')),
    projector_public_enabled boolean NOT NULL DEFAULT false,
    start_window_opens_at timestamptz,
    start_window_closes_at timestamptz,
    return_window_opens_at timestamptz,
    return_window_closes_at timestamptz,
    configured_by text NOT NULL,
    configured_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (start_window_closes_at IS NULL OR start_window_opens_at IS NOT NULL),
    CHECK (start_window_opens_at IS NULL OR start_window_closes_at > start_window_opens_at),
    CHECK (return_window_closes_at IS NULL OR return_window_opens_at IS NOT NULL),
    CHECK (return_window_opens_at IS NULL OR return_window_closes_at > return_window_opens_at)
);

CREATE TABLE IF NOT EXISTS public.event_hunt_missions_v2 (
    mission_id text PRIMARY KEY,
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    activity_id text NOT NULL REFERENCES public.activities_v2(activity_id) ON DELETE RESTRICT,
    mission_name text NOT NULL,
    mission_type text NOT NULL CHECK (mission_type IN ('CHECKPOINT', 'OBSERVATION', 'PHOTO', 'VIDEO', 'AI', 'CREATIVE', 'COLLABORATION', 'SECRET')),
    checkpoint_id text REFERENCES public.event_location_checkpoints_v2(checkpoint_id) ON DELETE SET NULL,
    evidence_type text NOT NULL DEFAULT 'NONE' CHECK (evidence_type IN ('NONE', 'TEXT', 'PHOTO', 'VIDEO', 'PHOTO_OR_VIDEO')),
    scoring_mode text NOT NULL DEFAULT 'TEAM_FULL' CHECK (scoring_mode IN ('TEAM_FULL', 'PARTICIPATION_PRORATED', 'FACILITATOR_RUBRIC')),
    maximum_score numeric(12,2) NOT NULL DEFAULT 0 CHECK (maximum_score >= 0 AND maximum_score <= 1000),
    participant_instruction text NOT NULL DEFAULT '',
    rubric jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(rubric) = 'array'),
    is_secret boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    mission_payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(mission_payload) = 'object'),
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (event_id, mission_id),
    UNIQUE (event_id, activity_id)
);
CREATE INDEX IF NOT EXISTS event_hunt_missions_event_idx ON public.event_hunt_missions_v2(event_id, is_active, mission_id);

CREATE TABLE IF NOT EXISTS public.hunt_team_checkpoint_routes_v2 (
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    team_id text NOT NULL REFERENCES public.teams_v2(team_id) ON DELETE CASCADE,
    checkpoint_id text NOT NULL REFERENCES public.event_location_checkpoints_v2(checkpoint_id) ON DELETE CASCADE,
    route_position integer NOT NULL CHECK (route_position > 0),
    configured_by text NOT NULL,
    configured_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, team_id, checkpoint_id),
    UNIQUE (event_id, team_id, route_position)
);
CREATE INDEX IF NOT EXISTS hunt_team_checkpoint_routes_event_team_idx ON public.hunt_team_checkpoint_routes_v2(event_id, team_id, route_position);

CREATE TABLE IF NOT EXISTS public.hunt_team_mission_runtime_v2 (
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    team_id text NOT NULL REFERENCES public.teams_v2(team_id) ON DELETE CASCADE,
    mission_id text NOT NULL REFERENCES public.event_hunt_missions_v2(mission_id) ON DELETE CASCADE,
    mission_state text NOT NULL DEFAULT 'AVAILABLE' CHECK (mission_state IN ('AVAILABLE', 'IN_PROGRESS', 'PENDING_REVIEW', 'RETURNED', 'COMPLETED')),
    is_released boolean NOT NULL DEFAULT false,
    updated_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, team_id, mission_id)
);
CREATE INDEX IF NOT EXISTS hunt_team_mission_runtime_event_team_idx ON public.hunt_team_mission_runtime_v2(event_id, team_id, mission_state);

CREATE TABLE IF NOT EXISTS public.hunt_scoring_snapshots_v2 (
    submission_id uuid NOT NULL REFERENCES public.submissions_v2(submission_id) ON DELETE CASCADE,
    submitted_at timestamptz NOT NULL,
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    team_id text NOT NULL REFERENCES public.teams_v2(team_id) ON DELETE RESTRICT,
    mission_id text NOT NULL REFERENCES public.event_hunt_missions_v2(mission_id) ON DELETE RESTRICT,
    scoring_mode text NOT NULL CHECK (scoring_mode IN ('TEAM_FULL', 'PARTICIPATION_PRORATED', 'FACILITATOR_RUBRIC')),
    mission_maximum numeric(12,2) NOT NULL CHECK (mission_maximum >= 0),
    present_participant_ids jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(present_participant_ids) = 'array'),
    completing_participant_ids jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(completing_participant_ids) = 'array'),
    eligible_score numeric(12,2) NOT NULL DEFAULT 0 CHECK (eligible_score >= 0),
    rubric jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(rubric) = 'array'),
    rubric_scores jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(rubric_scores) = 'object'),
    captured_by text NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (submission_id, submitted_at)
);
CREATE INDEX IF NOT EXISTS hunt_scoring_snapshots_event_submission_idx ON public.hunt_scoring_snapshots_v2(event_id, submission_id, submitted_at DESC);

CREATE TABLE IF NOT EXISTS public.hunt_score_adjustments_v2 (
    adjustment_id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE CASCADE,
    team_id text NOT NULL REFERENCES public.teams_v2(team_id) ON DELETE RESTRICT,
    score_delta numeric(12,2) NOT NULL CHECK (score_delta BETWEEN -1000 AND 1000 AND score_delta <> 0),
    reason text NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 1000),
    actor text NOT NULL,
    idempotency_key text NOT NULL CHECK (length(trim(idempotency_key)) BETWEEN 1 AND 128),
    idempotency_fingerprint text NOT NULL CHECK (length(idempotency_fingerprint) = 32),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (event_id, idempotency_key)
);

ALTER TABLE public.event_hunt_configurations_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_hunt_missions_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hunt_team_checkpoint_routes_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hunt_team_mission_runtime_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hunt_scoring_snapshots_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hunt_score_adjustments_v2 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.event_hunt_configurations_v2, public.event_hunt_missions_v2, public.hunt_team_checkpoint_routes_v2,
    public.hunt_team_mission_runtime_v2, public.hunt_scoring_snapshots_v2,
    public.hunt_score_adjustments_v2 FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.exos_v2_configure_hunt(
    p_event_id text, p_hunt_mode text, p_route_mode text,
    p_start_window_opens_at timestamptz, p_start_window_closes_at timestamptz,
    p_return_window_opens_at timestamptz, p_return_window_closes_at timestamptz,
    p_actor text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_event public.events_v2%rowtype; v_mode text := upper(trim(p_hunt_mode)); v_route text := upper(trim(p_route_mode));
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL OR nullif(trim(p_actor), '') IS NULL
       OR v_mode NOT IN ('WALK', 'ROAD') OR v_route NOT IN ('OPEN_HUNT', 'CONFIGURED_ROUTE')
       OR (p_start_window_opens_at IS NOT NULL AND (p_start_window_closes_at IS NULL OR p_start_window_closes_at <= p_start_window_opens_at))
       OR (p_return_window_opens_at IS NOT NULL AND (p_return_window_closes_at IS NULL OR p_return_window_closes_at <= p_return_window_opens_at)) THEN
        RAISE EXCEPTION 'Hunt configuration is invalid';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = trim(p_event_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Event not found'; END IF;
    INSERT INTO public.event_hunt_configurations_v2(
        event_id, hunt_mode, route_mode, start_window_opens_at, start_window_closes_at,
        return_window_opens_at, return_window_closes_at, configured_by
    ) VALUES (v_event.event_id, v_mode, v_route, p_start_window_opens_at, p_start_window_closes_at,
        p_return_window_opens_at, p_return_window_closes_at, trim(p_actor))
    ON CONFLICT (event_id) DO UPDATE SET hunt_mode = excluded.hunt_mode, route_mode = excluded.route_mode,
        start_window_opens_at = excluded.start_window_opens_at, start_window_closes_at = excluded.start_window_closes_at,
        return_window_opens_at = excluded.return_window_opens_at, return_window_closes_at = excluded.return_window_closes_at,
        configured_by = excluded.configured_by, configured_at = now(), updated_at = now()
    WHERE public.event_hunt_configurations_v2.operational_state <> 'CLOSED';
    IF NOT FOUND THEN RAISE EXCEPTION 'Closed Hunt configuration cannot be changed'; END IF;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_event.event_id, trim(p_actor), 'HUNT_CONFIGURED', 'event_hunt_configurations_v2', v_event.event_id,
        jsonb_build_object('HuntMode', v_mode, 'RouteMode', v_route));
    RETURN jsonb_build_object('EventID', v_event.event_id, 'HuntMode', v_mode, 'RouteMode', v_route, 'Configured', true);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_set_hunt_operational_state(
    p_event_id text, p_operational_state text, p_actor text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_config public.event_hunt_configurations_v2%rowtype; v_state text := upper(trim(p_operational_state));
BEGIN
    IF nullif(trim(p_actor), '') IS NULL OR v_state NOT IN ('READY', 'LIVE', 'HOLD', 'RETURN_NOW', 'CLOSED') THEN
        RAISE EXCEPTION 'Hunt operational state is invalid';
    END IF;
    SELECT * INTO v_config FROM public.event_hunt_configurations_v2 WHERE event_id = trim(p_event_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Hunt is not configured for this event'; END IF;
    IF v_config.operational_state = 'CLOSED' AND v_state <> 'CLOSED' THEN
        RAISE EXCEPTION 'CLOSED is terminal and requires an explicit new event configuration';
    END IF;
    UPDATE public.event_hunt_configurations_v2 SET operational_state = v_state, updated_at = now() WHERE event_id = v_config.event_id;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, before_state, after_state)
    VALUES (v_config.event_id, trim(p_actor), 'HUNT_OPERATIONAL_STATE_SET', 'event_hunt_configurations_v2', v_config.event_id,
        jsonb_build_object('OperationalState', v_config.operational_state), jsonb_build_object('OperationalState', v_state));
    RETURN jsonb_build_object('EventID', v_config.event_id, 'OperationalState', v_state);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_set_hunt_projector_visibility(
    p_event_id text, p_enabled boolean, p_actor text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_config public.event_hunt_configurations_v2%rowtype;
BEGIN
    IF nullif(trim(p_actor), '') IS NULL THEN RAISE EXCEPTION 'Operator identity is required'; END IF;
    SELECT * INTO v_config FROM public.event_hunt_configurations_v2 WHERE event_id = trim(p_event_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Hunt is not configured for this event'; END IF;
    UPDATE public.event_hunt_configurations_v2 SET projector_public_enabled = coalesce(p_enabled, false), updated_at = now()
      WHERE event_id = v_config.event_id;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, before_state, after_state)
    VALUES (v_config.event_id, trim(p_actor), 'HUNT_PROJECTOR_VISIBILITY_SET', 'event_hunt_configurations_v2', v_config.event_id,
        jsonb_build_object('PublicProjectorEnabled', v_config.projector_public_enabled),
        jsonb_build_object('PublicProjectorEnabled', coalesce(p_enabled, false)));
    RETURN jsonb_build_object('EventID', v_config.event_id, 'PublicProjectorEnabled', coalesce(p_enabled, false));
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_upsert_hunt_checkpoint(
    p_event_id text, p_checkpoint_id text, p_name text, p_latitude numeric, p_longitude numeric,
    p_radius_meters numeric, p_active boolean, p_actor text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_result jsonb;
BEGIN
    -- This delegates coordinate/radius validation and event ownership to the
    -- certified 048 checkpoint authority; Hunt adds no score path.
    v_result := public.exos_v2_upsert_live_location_checkpoint(
        p_event_id, p_checkpoint_id, p_name, p_latitude, p_longitude, p_radius_meters, p_active, p_actor
    );
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (trim(p_event_id), trim(p_actor), 'HUNT_CHECKPOINT_SAVED', 'event_location_checkpoints_v2', trim(p_checkpoint_id),
        jsonb_build_object('GPSScoring', false));
    RETURN v_result || jsonb_build_object('GPSScoring', false);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_upsert_hunt_mission(
    p_event_id text, p_mission_id text, p_activity_id text, p_mission_name text, p_mission_type text,
    p_checkpoint_id text, p_evidence_type text, p_scoring_mode text, p_maximum_score numeric,
    p_participant_instruction text, p_rubric jsonb, p_is_secret boolean, p_is_active boolean,
    p_mission_payload jsonb, p_actor text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_existing public.event_hunt_missions_v2%rowtype; v_type text := upper(trim(p_mission_type));
        v_evidence text := upper(trim(p_evidence_type)); v_scoring text := upper(trim(p_scoring_mode));
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL OR nullif(trim(p_mission_id), '') IS NULL
       OR nullif(trim(p_activity_id), '') IS NULL OR nullif(trim(p_mission_name), '') IS NULL OR nullif(trim(p_actor), '') IS NULL
       OR v_type NOT IN ('CHECKPOINT', 'OBSERVATION', 'PHOTO', 'VIDEO', 'AI', 'CREATIVE', 'COLLABORATION', 'SECRET')
       OR v_evidence NOT IN ('NONE', 'TEXT', 'PHOTO', 'VIDEO', 'PHOTO_OR_VIDEO')
       OR v_scoring NOT IN ('TEAM_FULL', 'PARTICIPATION_PRORATED', 'FACILITATOR_RUBRIC')
       OR coalesce(p_maximum_score, -1) NOT BETWEEN 0 AND 1000
       OR jsonb_typeof(coalesce(p_rubric, '[]'::jsonb)) <> 'array'
       OR jsonb_typeof(coalesce(p_mission_payload, '{}'::jsonb)) <> 'object' THEN
        RAISE EXCEPTION 'Hunt mission is invalid';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.event_hunt_configurations_v2 WHERE event_id = trim(p_event_id)) THEN
        RAISE EXCEPTION 'Hunt is not configured for this event';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.activities_v2 a JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
                   WHERE p.event_id = trim(p_event_id) AND a.activity_id = trim(p_activity_id) AND a.is_active) THEN
        RAISE EXCEPTION 'Hunt activity is outside this event';
    END IF;
    IF nullif(trim(coalesce(p_checkpoint_id, '')), '') IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.event_location_checkpoints_v2 WHERE checkpoint_id = trim(p_checkpoint_id) AND event_id = trim(p_event_id)
    ) THEN RAISE EXCEPTION 'Hunt checkpoint is outside this event'; END IF;
    SELECT * INTO v_existing FROM public.event_hunt_missions_v2 WHERE mission_id = trim(p_mission_id) FOR UPDATE;
    IF FOUND AND v_existing.event_id <> trim(p_event_id) THEN RAISE EXCEPTION 'Mission belongs to a different event'; END IF;
    INSERT INTO public.event_hunt_missions_v2(
        mission_id, event_id, activity_id, mission_name, mission_type, checkpoint_id, evidence_type,
        scoring_mode, maximum_score, participant_instruction, rubric, is_secret, is_active, mission_payload, created_by
    ) VALUES (trim(p_mission_id), trim(p_event_id), trim(p_activity_id), trim(p_mission_name), v_type,
        nullif(trim(coalesce(p_checkpoint_id, '')), ''), v_evidence, v_scoring, p_maximum_score,
        coalesce(p_participant_instruction, ''), coalesce(p_rubric, '[]'::jsonb), coalesce(p_is_secret, false),
        coalesce(p_is_active, true), coalesce(p_mission_payload, '{}'::jsonb), trim(p_actor))
    ON CONFLICT (mission_id) DO UPDATE SET activity_id = excluded.activity_id, mission_name = excluded.mission_name,
        mission_type = excluded.mission_type, checkpoint_id = excluded.checkpoint_id, evidence_type = excluded.evidence_type,
        scoring_mode = excluded.scoring_mode, maximum_score = excluded.maximum_score,
        participant_instruction = excluded.participant_instruction, rubric = excluded.rubric,
        is_secret = excluded.is_secret, is_active = excluded.is_active, mission_payload = excluded.mission_payload,
        updated_at = now()
    WHERE public.event_hunt_missions_v2.event_id = excluded.event_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Mission ID is already bound to another event'; END IF;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (trim(p_event_id), trim(p_actor), 'HUNT_MISSION_SAVED', 'event_hunt_missions_v2', trim(p_mission_id),
        jsonb_build_object('MissionType', v_type, 'ScoringMode', v_scoring, 'GPSScoring', false));
    RETURN jsonb_build_object('EventID', trim(p_event_id), 'MissionID', trim(p_mission_id), 'Saved', true);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_set_hunt_mission_availability(
    p_event_id text, p_team_id text, p_mission_id text, p_released boolean, p_mission_state text, p_actor text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_state text := upper(trim(p_mission_state));
BEGIN
    IF nullif(trim(p_actor), '') IS NULL OR v_state NOT IN ('AVAILABLE', 'IN_PROGRESS', 'PENDING_REVIEW', 'RETURNED', 'COMPLETED') THEN
        RAISE EXCEPTION 'Hunt mission availability is invalid';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.teams_v2 WHERE event_id = trim(p_event_id) AND team_id = trim(p_team_id))
       OR NOT EXISTS (SELECT 1 FROM public.event_hunt_missions_v2 WHERE event_id = trim(p_event_id) AND mission_id = trim(p_mission_id)) THEN
        RAISE EXCEPTION 'Hunt team or mission is outside this event';
    END IF;
    INSERT INTO public.hunt_team_mission_runtime_v2(event_id, team_id, mission_id, mission_state, is_released, updated_by)
    VALUES (trim(p_event_id), trim(p_team_id), trim(p_mission_id), v_state, coalesce(p_released, false), trim(p_actor))
    ON CONFLICT (event_id, team_id, mission_id) DO UPDATE SET mission_state = excluded.mission_state,
        is_released = excluded.is_released, updated_by = excluded.updated_by, updated_at = now();
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (trim(p_event_id), trim(p_actor), 'HUNT_MISSION_AVAILABILITY_SET', 'hunt_team_mission_runtime_v2',
        trim(p_team_id) || '|' || trim(p_mission_id), jsonb_build_object('Released', coalesce(p_released, false), 'MissionState', v_state));
    RETURN jsonb_build_object('EventID', trim(p_event_id), 'TeamID', trim(p_team_id), 'MissionID', trim(p_mission_id), 'Released', coalesce(p_released, false), 'MissionState', v_state);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_hunt_register_random(
    p_join_code text, p_display_name text, p_device_id text, p_enrollment_credential text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_event public.events_v2%rowtype; v_identity jsonb; v_participant_id uuid;
BEGIN
    -- Prerequisites are checked first, so a missing attendance contract cannot
    -- create a participant who was not atomically marked PRESENT. The opaque
    -- Team Formation credential stays canonical identity; display names never
    -- become a merge or recovery key.
    SELECT * INTO v_event FROM public.events_v2 WHERE join_code = upper(trim(p_join_code)) AND published_at IS NOT NULL FOR UPDATE;
    IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM public.event_hunt_configurations_v2 c
       WHERE c.event_id = v_event.event_id AND c.hunt_mode = 'WALK')
       OR coalesce(v_event.event_payload #>> '{Attendance,SchemaVersion}', '') <> '1' THEN
        RAISE EXCEPTION 'WALK Hunt registration and attendance are not configured for this event';
    END IF;
    v_identity := public.exos_v2_team_formation_register_random(p_join_code, p_display_name, p_device_id, p_enrollment_credential);
    v_participant_id := nullif(v_identity ->> 'ParticipantID', '')::uuid;
    IF v_participant_id IS NULL THEN RAISE EXCEPTION 'Hunt registration did not return a canonical participant'; END IF;
    IF NOT coalesce((v_identity ->> 'Idempotent')::boolean, false) THEN
        PERFORM public.exos_v2_set_participant_attendance(v_event.event_id, v_participant_id, 'PRESENT',
            'hunt_registration', 'Automatic first-arrival attendance');
    END IF;
    RETURN v_identity || jsonb_build_object('AttendanceState', 'PRESENT', 'RegistrationMode', 'RANDOM_ASSIGN');
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_save_hunt_team_route(
    p_event_id text, p_team_id text, p_checkpoint_ids jsonb, p_actor text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_config public.event_hunt_configurations_v2%rowtype; v_checkpoint_id text; v_count integer;
BEGIN
    IF nullif(trim(p_actor), '') IS NULL OR jsonb_typeof(coalesce(p_checkpoint_ids, 'null'::jsonb)) <> 'array'
       OR NOT EXISTS (SELECT 1 FROM public.teams_v2 WHERE event_id = trim(p_event_id) AND team_id = trim(p_team_id)) THEN
        RAISE EXCEPTION 'Hunt route is invalid';
    END IF;
    SELECT * INTO v_config FROM public.event_hunt_configurations_v2 WHERE event_id = trim(p_event_id) FOR UPDATE;
    IF NOT FOUND OR v_config.route_mode <> 'CONFIGURED_ROUTE' THEN RAISE EXCEPTION 'Configured routes are not enabled for this event'; END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements_text(p_checkpoint_ids) value
       WHERE NOT EXISTS (SELECT 1 FROM public.event_location_checkpoints_v2 c WHERE c.event_id = trim(p_event_id)
                         AND c.checkpoint_id = trim(value) AND c.is_active)) THEN
        RAISE EXCEPTION 'Configured route includes a checkpoint outside this event';
    END IF;
    IF (SELECT count(*) FROM jsonb_array_elements_text(p_checkpoint_ids)) <>
       (SELECT count(DISTINCT trim(value)) FROM jsonb_array_elements_text(p_checkpoint_ids) value) THEN
        RAISE EXCEPTION 'Configured route cannot repeat a checkpoint';
    END IF;
    DELETE FROM public.hunt_team_checkpoint_routes_v2 WHERE event_id = trim(p_event_id) AND team_id = trim(p_team_id);
    INSERT INTO public.hunt_team_checkpoint_routes_v2(event_id, team_id, checkpoint_id, route_position, configured_by)
    SELECT trim(p_event_id), trim(p_team_id), trim(value), ordinal::integer, trim(p_actor)
      FROM jsonb_array_elements_text(p_checkpoint_ids) WITH ORDINALITY route(value, ordinal)
     WHERE nullif(trim(value), '') IS NOT NULL;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (trim(p_event_id), trim(p_actor), 'HUNT_TEAM_ROUTE_SAVED', 'hunt_team_checkpoint_routes_v2', trim(p_team_id),
        jsonb_build_object('CheckpointCount', v_count));
    RETURN jsonb_build_object('EventID', trim(p_event_id), 'TeamID', trim(p_team_id), 'ConfiguredCheckpoints', v_count);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_hunt_participant_workspace(p_session_token text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_session public.participant_sessions_v2%rowtype; v_participant public.participants_v2%rowtype;
        v_event public.events_v2%rowtype; v_config public.event_hunt_configurations_v2%rowtype;
        v_captain public.participants_v2%rowtype; v_members jsonb; v_missions jsonb; v_progress jsonb;
BEGIN
    SELECT * INTO v_session FROM public.participant_sessions_v2 WHERE session_token::text = trim(p_session_token) AND is_active;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT * INTO v_participant FROM public.participants_v2 WHERE participant_id = v_session.participant_id
      AND event_id = v_session.event_id AND NOT is_archived AND merged_into_participant_id IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant is unavailable'; END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = v_session.event_id;
    SELECT * INTO v_config FROM public.event_hunt_configurations_v2 WHERE event_id = v_session.event_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Hunt is not configured for this event'; END IF;
    SELECT * INTO v_captain FROM public.participants_v2 WHERE event_id = v_session.event_id AND team_id = v_participant.team_id
      AND is_team_formation_captain AND NOT is_archived AND merged_into_participant_id IS NULL LIMIT 1;
    SELECT coalesce(jsonb_agg(jsonb_build_object('ParticipantID', p.participant_id::text, 'DisplayName', p.display_name,
        'AttendanceState', coalesce(a.attendance_state, 'UNMARKED'), 'IsCaptain', p.is_team_formation_captain) ORDER BY p.created_at), '[]'::jsonb)
      INTO v_members FROM public.participants_v2 p LEFT JOIN public.participant_attendance_v2 a
        ON a.event_id = p.event_id AND a.participant_id = p.participant_id
     WHERE p.event_id = v_session.event_id AND p.team_id = v_participant.team_id AND NOT p.is_archived AND p.merged_into_participant_id IS NULL;
    SELECT coalesce(jsonb_agg(jsonb_build_object('MissionID', m.mission_id, 'ActivityID', m.activity_id,
        'Name', m.mission_name, 'MissionType', m.mission_type, 'CheckpointID', m.checkpoint_id,
        'EvidenceType', m.evidence_type, 'ScoringMode', m.scoring_mode, 'MaximumScore', m.maximum_score,
        'Instructions', m.participant_instruction, 'Rubric', m.rubric, 'Secret', m.is_secret,
        'MissionState', coalesce(r.mission_state, 'AVAILABLE'),
        'Visible', (NOT m.is_secret OR coalesce(r.is_released, false)))
        ORDER BY coalesce(route.route_position, 2147483647), m.mission_id), '[]'::jsonb)
      INTO v_missions FROM public.event_hunt_missions_v2 m LEFT JOIN public.hunt_team_mission_runtime_v2 r
        ON r.event_id = m.event_id AND r.team_id = v_participant.team_id AND r.mission_id = m.mission_id
      LEFT JOIN public.hunt_team_checkpoint_routes_v2 route ON route.event_id = m.event_id AND route.team_id = v_participant.team_id
        AND route.checkpoint_id = m.checkpoint_id
     WHERE m.event_id = v_session.event_id AND m.is_active;
    SELECT jsonb_build_object('Completed', count(*) FILTER (WHERE mission_state = 'COMPLETED'),
        'PendingReview', count(*) FILTER (WHERE mission_state = 'PENDING_REVIEW'),
        'Total', count(*)) INTO v_progress FROM public.hunt_team_mission_runtime_v2
     WHERE event_id = v_session.event_id AND team_id = v_participant.team_id;
    RETURN jsonb_build_object('EventID', v_session.event_id, 'EventName', v_event.event_name,
        'ParticipantID', v_participant.participant_id::text, 'ParticipantName', v_participant.display_name,
        'TeamID', v_participant.team_id, 'TeamName', (SELECT team_name FROM public.teams_v2 WHERE team_id = v_participant.team_id),
        'IsCaptain', v_participant.is_team_formation_captain, 'CaptainName', v_captain.display_name,
        'TeamMembers', v_members, 'HuntMode', v_config.hunt_mode, 'RouteMode', v_config.route_mode,
        'OperationalState', v_config.operational_state, 'TeamFormationPhase', coalesce(v_event.event_payload #>> '{TeamFormation,Phase}', 'DRAFT'),
        'Route', coalesce((SELECT jsonb_agg(jsonb_build_object('CheckpointID', checkpoint_id, 'Position', route_position) ORDER BY route_position)
            FROM public.hunt_team_checkpoint_routes_v2 WHERE event_id = v_session.event_id AND team_id = v_participant.team_id), '[]'::jsonb),
        'Missions', v_missions, 'Progress', coalesce(v_progress, jsonb_build_object('Completed', 0, 'PendingReview', 0, 'Total', jsonb_array_length(v_missions))));
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_hunt_submit_mission(
    p_session_token text, p_mission_id text, p_submission_payload jsonb DEFAULT '{}'::jsonb,
    p_evidence jsonb DEFAULT '{}'::jsonb, p_completing_participant_ids jsonb DEFAULT '[]'::jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_session public.participant_sessions_v2%rowtype; v_participant public.participants_v2%rowtype;
        v_config public.event_hunt_configurations_v2%rowtype; v_mission public.event_hunt_missions_v2%rowtype;
        v_runtime public.hunt_team_mission_runtime_v2%rowtype; v_activity_runtime public.activity_runtime_v2%rowtype;
        v_submission public.submissions_v2%rowtype; v_present jsonb := '[]'::jsonb; v_selected jsonb := '[]'::jsonb;
        v_present_count integer := 0; v_selected_count integer := 0; v_eligible numeric := 0;
        v_evidence_type text; v_file_size numeric; v_key text;
BEGIN
    IF jsonb_typeof(coalesce(p_submission_payload, '{}'::jsonb)) <> 'object'
       OR jsonb_typeof(coalesce(p_evidence, '{}'::jsonb)) <> 'object'
       OR jsonb_typeof(coalesce(p_completing_participant_ids, '[]'::jsonb)) <> 'array' THEN
        RAISE EXCEPTION 'Hunt submission payload is invalid';
    END IF;
    SELECT * INTO v_session FROM public.participant_sessions_v2 WHERE session_token::text = trim(p_session_token) AND is_active FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT * INTO v_participant FROM public.participants_v2 WHERE participant_id = v_session.participant_id
      AND event_id = v_session.event_id AND is_team_formation_captain AND NOT is_archived AND merged_into_participant_id IS NULL;
    IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM public.team_access_sessions_v2 s WHERE s.event_id = v_session.event_id
        AND s.team_id = v_participant.team_id AND s.team_formation_captain_participant_id = v_participant.participant_id
        AND s.device_id = v_session.device_id AND s.is_active) THEN
        RAISE EXCEPTION 'Only the effective Captain with an active Captain session may submit Hunt evidence';
    END IF;
    SELECT * INTO v_config FROM public.event_hunt_configurations_v2 WHERE event_id = v_session.event_id FOR UPDATE;
    IF NOT FOUND OR v_config.hunt_mode <> 'WALK' THEN RAISE EXCEPTION 'WALK Hunt is not configured for this event'; END IF;
    IF v_config.operational_state <> 'LIVE' THEN RAISE EXCEPTION 'Hunt submissions are unavailable while the Hunt is not LIVE'; END IF;
    SELECT * INTO v_mission FROM public.event_hunt_missions_v2 WHERE event_id = v_session.event_id
      AND mission_id = trim(p_mission_id) AND is_active FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Hunt mission is unavailable for this event'; END IF;
    SELECT * INTO v_runtime FROM public.hunt_team_mission_runtime_v2 WHERE event_id = v_session.event_id
      AND team_id = v_participant.team_id AND mission_id = v_mission.mission_id FOR UPDATE;
    IF v_mission.is_secret AND (NOT FOUND OR NOT v_runtime.is_released) THEN RAISE EXCEPTION 'Secret Hunt mission is not released for this team'; END IF;
    IF FOUND AND v_runtime.mission_state IN ('PENDING_REVIEW', 'COMPLETED') THEN RAISE EXCEPTION 'Hunt mission is already submitted or completed'; END IF;
    v_evidence_type := upper(coalesce(p_evidence ->> 'EvidenceType', 'NONE'));
    v_file_size := nullif(p_evidence ->> 'FileSizeBytes', '')::numeric;
    IF (v_mission.evidence_type = 'PHOTO' AND v_evidence_type <> 'PHOTO')
       OR (v_mission.evidence_type = 'VIDEO' AND v_evidence_type <> 'VIDEO')
       OR (v_mission.evidence_type = 'PHOTO_OR_VIDEO' AND v_evidence_type NOT IN ('PHOTO', 'VIDEO'))
       OR (v_mission.evidence_type IN ('PHOTO', 'VIDEO', 'PHOTO_OR_VIDEO') AND nullif(trim(coalesce(p_evidence ->> 'StorageReference', '')), '') IS NULL)
       OR p_evidence ? 'PublicURL' OR lower(coalesce(p_evidence ->> 'StorageReference', '')) LIKE 'http%'
       OR (v_file_size IS NOT NULL AND v_file_size > 52428800) THEN
        RAISE EXCEPTION 'Hunt evidence is invalid or exceeds the private 50 MB ceiling';
    END IF;
    IF v_mission.scoring_mode = 'PARTICIPATION_PRORATED' THEN
        IF coalesce((SELECT e.event_payload #>> '{Attendance,SchemaVersion}' FROM public.events_v2 e WHERE e.event_id = v_session.event_id), '') <> '1' THEN
            RAISE EXCEPTION 'Attendance is required for participation-prorated scoring';
        END IF;
        SELECT coalesce(jsonb_agg(p.participant_id::text ORDER BY p.participant_id), '[]'::jsonb), count(*)::integer
          INTO v_present, v_present_count FROM public.participants_v2 p JOIN public.participant_attendance_v2 a
            ON a.event_id = p.event_id AND a.participant_id = p.participant_id
         WHERE p.event_id = v_session.event_id AND p.team_id = v_participant.team_id AND a.attendance_state = 'PRESENT'
           AND NOT p.is_archived AND p.merged_into_participant_id IS NULL;
        IF v_present_count = 0 THEN RAISE EXCEPTION 'No PRESENT participants are available for this team'; END IF;
        SELECT coalesce(jsonb_agg(value ORDER BY value), '[]'::jsonb), count(*)::integer INTO v_selected, v_selected_count
          FROM (SELECT DISTINCT trim(value) AS value FROM jsonb_array_elements_text(p_completing_participant_ids) value
                WHERE nullif(trim(value), '') IS NOT NULL) selected
         WHERE selected.value IN (SELECT value FROM jsonb_array_elements_text(v_present) value);
        IF v_selected_count <> jsonb_array_length(p_completing_participant_ids) OR v_selected_count = 0 THEN
            RAISE EXCEPTION 'Completing participants must be distinct canonical PRESENT members of this team';
        END IF;
        v_eligible := round((v_mission.maximum_score * v_selected_count::numeric / v_present_count::numeric)::numeric, 2);
    END IF;
    INSERT INTO public.activity_runtime_v2(event_id, team_id, participant_id, activity_id, session_id, state_payload,
        activity_started_at, activity_ended_at, completion_ratio, is_completed)
    VALUES (v_session.event_id, v_participant.team_id, v_participant.participant_id, v_mission.activity_id,
        v_session.participant_session_id, jsonb_build_object('HuntMissionID', v_mission.mission_id), now(), now(), 100, true)
    ON CONFLICT (event_id, participant_id, activity_id) DO UPDATE SET session_id = excluded.session_id,
        state_payload = excluded.state_payload, activity_ended_at = now(), completion_ratio = 100, is_completed = true, updated_at = now()
    RETURNING * INTO v_activity_runtime;
    v_key := 'hunt|' || v_session.event_id || '|' || v_participant.team_id || '|' || v_mission.mission_id;
    INSERT INTO public.submissions_v2(event_id, team_id, participant_id, activity_id, runtime_id, submission_key,
        submission_status, submission_payload, submitted_at, updated_at)
    VALUES (v_session.event_id, v_participant.team_id, v_participant.participant_id, v_mission.activity_id,
        v_activity_runtime.runtime_id, v_key, 'SUBMITTED', coalesce(p_submission_payload, '{}'::jsonb) ||
        jsonb_build_object('HuntMissionID', v_mission.mission_id, 'Evidence', p_evidence, 'CompletingParticipantIDs', v_selected), now(), now())
    ON CONFLICT (event_id, submission_key) DO UPDATE SET participant_id = excluded.participant_id, runtime_id = excluded.runtime_id,
        submission_status = 'SUBMITTED', submission_payload = excluded.submission_payload, submitted_at = now(),
        reviewed_at = NULL, reviewed_by = NULL, score = NULL, updated_at = now()
    RETURNING * INTO v_submission;
    INSERT INTO public.hunt_scoring_snapshots_v2(submission_id, submitted_at, event_id, team_id, mission_id,
        scoring_mode, mission_maximum, present_participant_ids, completing_participant_ids, eligible_score, rubric, captured_by)
    VALUES (v_submission.submission_id, v_submission.submitted_at, v_session.event_id, v_participant.team_id, v_mission.mission_id,
        v_mission.scoring_mode, v_mission.maximum_score, v_present, v_selected, v_eligible, v_mission.rubric, v_participant.participant_id::text);
    INSERT INTO public.hunt_team_mission_runtime_v2(event_id, team_id, mission_id, mission_state, is_released, updated_by)
    VALUES (v_session.event_id, v_participant.team_id, v_mission.mission_id, 'PENDING_REVIEW', NOT v_mission.is_secret OR coalesce(v_runtime.is_released, false), v_participant.participant_id::text)
    ON CONFLICT (event_id, team_id, mission_id) DO UPDATE SET mission_state = 'PENDING_REVIEW', updated_by = excluded.updated_by, updated_at = now();
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_session.event_id, v_participant.participant_id::text, 'HUNT_MISSION_SUBMITTED', 'submissions_v2', v_submission.submission_id::text,
        jsonb_build_object('MissionID', v_mission.mission_id, 'ScoringMode', v_mission.scoring_mode, 'GPSScoring', false));
    RETURN jsonb_build_object('EventID', v_session.event_id, 'TeamID', v_participant.team_id, 'MissionID', v_mission.mission_id,
        'SubmissionID', v_submission.submission_id::text, 'Status', 'PENDING_REVIEW', 'EligibleScore', v_eligible);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_hunt_review_submission(
    p_submission_id uuid, p_expected_submitted_at timestamptz, p_decision text,
    p_rubric_scores jsonb DEFAULT '{}'::jsonb, p_actor text DEFAULT '', p_reason text DEFAULT '', p_idempotency_key text DEFAULT ''
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_submission public.submissions_v2%rowtype; v_mission public.event_hunt_missions_v2%rowtype;
        v_snapshot public.hunt_scoring_snapshots_v2%rowtype; v_decision text := upper(trim(p_decision));
        v_score numeric := 0; v_criterion jsonb; v_criterion_id text; v_criterion_max numeric; v_value numeric;
        v_key text;
BEGIN
    IF nullif(trim(p_actor), '') IS NULL OR v_decision NOT IN ('APPROVE', 'RETURN')
       OR jsonb_typeof(coalesce(p_rubric_scores, '{}'::jsonb)) <> 'object' THEN
        RAISE EXCEPTION 'Hunt review is invalid';
    END IF;
    SELECT * INTO v_submission FROM public.submissions_v2 WHERE submission_id = p_submission_id FOR UPDATE;
    IF NOT FOUND OR v_submission.submission_status <> 'SUBMITTED' OR v_submission.submitted_at <> p_expected_submitted_at THEN
        RAISE EXCEPTION 'Hunt submission is no longer the current review revision';
    END IF;
    SELECT * INTO v_mission FROM public.event_hunt_missions_v2 WHERE event_id = v_submission.event_id AND activity_id = v_submission.activity_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Submission is not a Hunt mission'; END IF;
    SELECT * INTO v_snapshot FROM public.hunt_scoring_snapshots_v2 WHERE submission_id = v_submission.submission_id
      AND submitted_at = v_submission.submitted_at FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Hunt scoring snapshot is unavailable'; END IF;
    IF v_decision = 'APPROVE' THEN
        IF v_snapshot.scoring_mode = 'TEAM_FULL' THEN
            v_score := v_snapshot.mission_maximum;
        ELSIF v_snapshot.scoring_mode = 'PARTICIPATION_PRORATED' THEN
            v_score := v_snapshot.eligible_score;
        ELSE
            FOR v_criterion IN SELECT value FROM jsonb_array_elements(v_snapshot.rubric) LOOP
                v_criterion_id := trim(coalesce(v_criterion ->> 'ID', ''));
                v_criterion_max := nullif(v_criterion ->> 'Maximum', '')::numeric;
                IF v_criterion_id = '' OR v_criterion_max IS NULL OR v_criterion_max < 0
                   OR coalesce(p_rubric_scores ->> v_criterion_id, '') !~ '^([0-9]+)(\\.[0-9]+)?$' THEN
                    RAISE EXCEPTION 'Facilitator rubric scores must cover every configured criterion';
                END IF;
                v_value := (p_rubric_scores ->> v_criterion_id)::numeric;
                IF v_value < 0 OR v_value > v_criterion_max THEN RAISE EXCEPTION 'Rubric score is outside its configured maximum'; END IF;
                v_score := v_score + v_value;
            END LOOP;
            IF v_score > v_snapshot.mission_maximum THEN RAISE EXCEPTION 'Rubric total exceeds Hunt mission maximum'; END IF;
        END IF;
    END IF;
    UPDATE public.submissions_v2 SET submission_status = CASE WHEN v_decision = 'APPROVE' THEN 'APPROVED' ELSE 'REJECTED' END,
        score = CASE WHEN v_decision = 'APPROVE' THEN v_score ELSE 0 END, reviewed_at = now(), reviewed_by = trim(p_actor), updated_at = now()
    WHERE submission_id = v_submission.submission_id;
    INSERT INTO public.reviews_v2(event_id, submission_id, reviewer, decision, score_points, rationale, reviewed_at)
    VALUES (v_submission.event_id, v_submission.submission_id, trim(p_actor), CASE WHEN v_decision = 'APPROVE' THEN 'APPROVE'::public.exos_v2_review_decision ELSE 'REJECT'::public.exos_v2_review_decision END,
        CASE WHEN v_decision = 'APPROVE' THEN v_score ELSE 0 END, coalesce(p_reason, ''), now())
    ON CONFLICT (submission_id, reviewer) DO UPDATE SET decision = excluded.decision, score_points = excluded.score_points,
        rationale = excluded.rationale, reviewed_at = now();
    IF v_decision = 'APPROVE' THEN
        v_key := coalesce(nullif(trim(p_idempotency_key), ''), 'hunt-review|' || v_submission.submission_id::text || '|' || v_submission.submitted_at::text);
        INSERT INTO public.score_transactions_v2(event_id, team_id, submission_id, scoring_mode, score_delta, reason, idempotency_key, source_reference, created_by)
        VALUES (v_submission.event_id, v_submission.team_id, v_submission.submission_id, 'TEAM_COMPETITIVE', v_score,
            'Approved Hunt mission', v_key, jsonb_build_object('HuntMissionID', v_mission.mission_id, 'ScoringMode', v_snapshot.scoring_mode), trim(p_actor))
        ON CONFLICT (event_id, idempotency_key) DO UPDATE SET score_delta = excluded.score_delta, reason = excluded.reason,
            source_reference = excluded.source_reference, created_by = excluded.created_by;
    END IF;
    UPDATE public.hunt_scoring_snapshots_v2 SET rubric_scores = p_rubric_scores WHERE submission_id = v_submission.submission_id AND submitted_at = v_submission.submitted_at;
    UPDATE public.hunt_team_mission_runtime_v2 SET mission_state = CASE WHEN v_decision = 'APPROVE' THEN 'COMPLETED' ELSE 'RETURNED' END,
        updated_by = trim(p_actor), updated_at = now() WHERE event_id = v_submission.event_id AND team_id = v_submission.team_id AND mission_id = v_mission.mission_id;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_submission.event_id, trim(p_actor), 'HUNT_MISSION_REVIEWED', 'submissions_v2', v_submission.submission_id::text,
        jsonb_build_object('MissionID', v_mission.mission_id, 'Decision', v_decision, 'Score', v_score));
    RETURN jsonb_build_object('SubmissionID', v_submission.submission_id::text, 'MissionID', v_mission.mission_id,
        'Status', CASE WHEN v_decision = 'APPROVE' THEN 'COMPLETED' ELSE 'RETURNED' END, 'Score', v_score);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_hunt_adjust_score(
    p_event_id text, p_team_id text, p_score_delta numeric, p_reason text, p_actor text, p_idempotency_key text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_adjustment_id uuid; v_fingerprint text; v_existing text;
BEGIN
    IF nullif(trim(p_actor), '') IS NULL OR nullif(trim(p_reason), '') IS NULL OR nullif(trim(p_idempotency_key), '') IS NULL
       OR coalesce(p_score_delta, 0) = 0 OR p_score_delta NOT BETWEEN -1000 AND 1000
       OR NOT EXISTS (SELECT 1 FROM public.teams_v2 WHERE event_id = trim(p_event_id) AND team_id = trim(p_team_id)) THEN
        RAISE EXCEPTION 'Hunt score adjustment is invalid';
    END IF;
    v_fingerprint := md5(jsonb_build_object('TeamID', trim(p_team_id), 'ScoreDelta', p_score_delta, 'Reason', trim(p_reason), 'Actor', trim(p_actor))::text);
    INSERT INTO public.hunt_score_adjustments_v2(event_id, team_id, score_delta, reason, actor, idempotency_key, idempotency_fingerprint)
    VALUES (trim(p_event_id), trim(p_team_id), p_score_delta, trim(p_reason), trim(p_actor), trim(p_idempotency_key), v_fingerprint)
    ON CONFLICT (event_id, idempotency_key) DO NOTHING RETURNING adjustment_id INTO v_adjustment_id;
    IF v_adjustment_id IS NULL THEN
        SELECT idempotency_fingerprint INTO v_existing FROM public.hunt_score_adjustments_v2 WHERE event_id = trim(p_event_id) AND idempotency_key = trim(p_idempotency_key);
        IF v_existing IS DISTINCT FROM v_fingerprint THEN RAISE EXCEPTION 'Hunt adjustment idempotency key was reused with different content'; END IF;
        RETURN jsonb_build_object('EventID', trim(p_event_id), 'TeamID', trim(p_team_id), 'Adjusted', true, 'Idempotent', true);
    END IF;
    INSERT INTO public.score_transactions_v2(event_id, team_id, scoring_mode, score_delta, reason, idempotency_key, source_reference, created_by)
    VALUES (trim(p_event_id), trim(p_team_id), 'TEAM_COMPETITIVE', p_score_delta, trim(p_reason), 'hunt-adjustment|' || v_adjustment_id::text,
        jsonb_build_object('AdjustmentID', v_adjustment_id::text), trim(p_actor));
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (trim(p_event_id), trim(p_actor), 'HUNT_SCORE_ADJUSTED', 'hunt_score_adjustments_v2', v_adjustment_id::text,
        jsonb_build_object('TeamID', trim(p_team_id), 'ScoreDelta', p_score_delta, 'Reason', trim(p_reason)));
    RETURN jsonb_build_object('EventID', trim(p_event_id), 'TeamID', trim(p_team_id), 'Adjusted', true, 'Idempotent', false);
END; $$;

CREATE OR REPLACE FUNCTION public.exos_v2_hunt_operator_snapshot(p_event_id text)
RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
    WITH config AS (SELECT * FROM public.event_hunt_configurations_v2 WHERE event_id = trim(p_event_id)),
    missions AS (SELECT * FROM public.event_hunt_missions_v2 WHERE event_id = trim(p_event_id) AND is_active),
    scores AS (SELECT team_id, coalesce(sum(score_delta), 0) AS score FROM public.score_transactions_v2 WHERE event_id = trim(p_event_id) GROUP BY team_id),
    progress AS (SELECT team_id, count(*) FILTER (WHERE mission_state = 'COMPLETED') AS completed,
        count(*) FILTER (WHERE mission_state = 'PENDING_REVIEW') AS pending FROM public.hunt_team_mission_runtime_v2 WHERE event_id = trim(p_event_id) GROUP BY team_id)
    SELECT jsonb_build_object('EventID', trim(p_event_id),
        'Configuration', coalesce((SELECT jsonb_build_object('HuntMode', hunt_mode, 'RouteMode', route_mode, 'OperationalState', operational_state,
            'StartWindowOpensAt', start_window_opens_at, 'StartWindowClosesAt', start_window_closes_at,
            'ReturnWindowOpensAt', return_window_opens_at, 'ReturnWindowClosesAt', return_window_closes_at) FROM config), '{}'::jsonb),
        'Checkpoints', coalesce((SELECT jsonb_agg(jsonb_build_object('CheckpointID', checkpoint_id, 'Name', checkpoint_name,
            'Latitude', latitude, 'Longitude', longitude, 'RadiusMeters', radius_meters, 'Active', is_active) ORDER BY checkpoint_name)
            FROM public.event_location_checkpoints_v2 WHERE event_id = trim(p_event_id)), '[]'::jsonb),
        'Missions', coalesce((SELECT jsonb_agg(jsonb_build_object('MissionID', mission_id, 'ActivityID', activity_id, 'Name', mission_name,
            'MissionType', mission_type, 'CheckpointID', checkpoint_id, 'EvidenceType', evidence_type, 'ScoringMode', scoring_mode,
            'MaximumScore', maximum_score, 'Secret', is_secret, 'Active', is_active) ORDER BY mission_id) FROM missions), '[]'::jsonb),
        'Teams', coalesce((SELECT jsonb_agg(jsonb_build_object('TeamID', t.team_id, 'TeamName', t.team_name, 'Score', coalesce(s.score, 0),
            'Completed', coalesce(p.completed, 0), 'PendingReview', coalesce(p.pending, 0), 'Total', (SELECT count(*) FROM missions))
            ORDER BY coalesce(s.score, 0) DESC, t.team_id) FROM public.teams_v2 t LEFT JOIN scores s ON s.team_id = t.team_id
            LEFT JOIN progress p ON p.team_id = t.team_id WHERE t.event_id = trim(p_event_id) AND t.is_active), '[]'::jsonb),
        'PendingReviews', coalesce((SELECT jsonb_agg(jsonb_build_object('SubmissionID', s.submission_id::text, 'MissionID', m.mission_id,
            'MissionName', m.mission_name, 'TeamID', s.team_id, 'SubmittedAt', s.submitted_at, 'ScoringMode', m.scoring_mode,
            'MaximumScore', m.maximum_score, 'Evidence', s.submission_payload -> 'Evidence') ORDER BY s.submitted_at)
            FROM public.submissions_v2 s JOIN public.event_hunt_missions_v2 m ON m.event_id = s.event_id AND m.activity_id = s.activity_id
            WHERE s.event_id = trim(p_event_id) AND s.submission_status = 'SUBMITTED'), '[]'::jsonb)
    );
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_hunt_public_projector_projection(p_event_id text)
RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
    WITH config AS (SELECT * FROM public.event_hunt_configurations_v2 WHERE event_id = trim(p_event_id)),
    missions AS (SELECT count(*)::integer AS total FROM public.event_hunt_missions_v2 WHERE event_id = trim(p_event_id) AND is_active),
    scores AS (SELECT team_id, coalesce(sum(score_delta), 0) AS score FROM public.score_transactions_v2 WHERE event_id = trim(p_event_id) GROUP BY team_id),
    progress AS (SELECT team_id, count(*) FILTER (WHERE mission_state = 'COMPLETED')::integer AS completed FROM public.hunt_team_mission_runtime_v2 WHERE event_id = trim(p_event_id) GROUP BY team_id),
    teams AS (SELECT t.team_id, t.team_name, coalesce(s.score, 0) AS score, coalesce(p.completed, 0) AS completed, m.total,
        dense_rank() OVER (ORDER BY coalesce(s.score, 0) DESC, t.team_id) AS rank FROM public.teams_v2 t CROSS JOIN missions m
        LEFT JOIN scores s ON s.team_id = t.team_id LEFT JOIN progress p ON p.team_id = t.team_id
        WHERE t.event_id = trim(p_event_id) AND t.is_active)
    SELECT jsonb_build_object('Event', jsonb_build_object('EventID', e.event_id, 'EventName', e.event_name,
        'HuntMode', c.hunt_mode, 'State', c.operational_state), 'Teams', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'TeamID', team_id, 'TeamName', team_name, 'Rank', rank, 'Score', score, 'Completed', completed, 'Total', total) ORDER BY rank, team_id) FROM teams), '[]'::jsonb))
    FROM public.events_v2 e JOIN config c ON c.event_id = e.event_id
     WHERE e.event_id = trim(p_event_id) AND c.projector_public_enabled;
$$;

REVOKE ALL ON FUNCTION public.exos_v2_configure_hunt(text,text,text,timestamptz,timestamptz,timestamptz,timestamptz,text),
    public.exos_v2_set_hunt_operational_state(text,text,text), public.exos_v2_set_hunt_projector_visibility(text,boolean,text), public.exos_v2_upsert_hunt_checkpoint(text,text,text,numeric,numeric,numeric,boolean,text),
    public.exos_v2_upsert_hunt_mission(text,text,text,text,text,text,text,text,numeric,text,jsonb,boolean,boolean,jsonb,text),
    public.exos_v2_set_hunt_mission_availability(text,text,text,boolean,text,text), public.exos_v2_save_hunt_team_route(text,text,jsonb,text),
    public.exos_v2_hunt_review_submission(uuid,timestamptz,text,jsonb,text,text,text),
    public.exos_v2_hunt_adjust_score(text,text,numeric,text,text,text), public.exos_v2_hunt_operator_snapshot(text)
FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.exos_v2_hunt_register_random(text,text,text,text), public.exos_v2_hunt_participant_workspace(text), public.exos_v2_hunt_submit_mission(text,text,jsonb,jsonb,jsonb),
    public.exos_v2_hunt_public_projector_projection(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.exos_v2_hunt_register_random(text,text,text,text), public.exos_v2_hunt_participant_workspace(text), public.exos_v2_hunt_submit_mission(text,text,jsonb,jsonb,jsonb)
TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_configure_hunt(text,text,text,timestamptz,timestamptz,timestamptz,timestamptz,text),
    public.exos_v2_set_hunt_operational_state(text,text,text), public.exos_v2_set_hunt_projector_visibility(text,boolean,text), public.exos_v2_upsert_hunt_checkpoint(text,text,text,numeric,numeric,numeric,boolean,text),
    public.exos_v2_upsert_hunt_mission(text,text,text,text,text,text,text,text,numeric,text,jsonb,boolean,boolean,jsonb,text),
    public.exos_v2_set_hunt_mission_availability(text,text,text,boolean,text,text), public.exos_v2_save_hunt_team_route(text,text,jsonb,text),
    public.exos_v2_hunt_review_submission(uuid,timestamptz,text,jsonb,text,text,text),
    public.exos_v2_hunt_adjust_score(text,text,numeric,text,text,text), public.exos_v2_hunt_operator_snapshot(text)
TO service_role;
-- The projector grants no map, participant, evidence, or trail access.
GRANT EXECUTE ON FUNCTION public.exos_v2_hunt_public_projector_projection(text) TO anon, authenticated, service_role;

COMMIT;
