-- Guarded rollback companion to 038_theme_park_race_open_mission_board.sql.
-- 037 is the reviewed baseline installed immediately before 038.  This
-- rollback is intentionally safe only when no OPEN_MISSION_BOARD
-- configuration, runtime, submission lineage, or audit history exists.  It
-- never deletes event, participant, team, submission, review, score, or audit
-- rows; it removes only the 038 extension contract and restores the exact 037
-- definitions that 038 replaces.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM public.events_v2
         WHERE upper(coalesce(event_payload #>> '{RaceConfiguration,EngineKind}', '')) = 'THEME_PARK_RACE'
           AND upper(coalesce(event_payload #>> '{RaceConfiguration,StrategyMode}', '')) = 'OPEN_MISSION_BOARD'
    ) OR EXISTS (
        SELECT 1
          FROM public.activity_runtime_v2 r
         WHERE upper(coalesce(r.state_payload->>'EngineKind', '')) = 'THEME_PARK_RACE'
           AND upper(coalesce(r.state_payload->>'StrategyMode', '')) = 'OPEN_MISSION_BOARD'
    ) OR EXISTS (
        SELECT 1
          FROM public.submissions_v2 s
          JOIN public.activity_runtime_v2 r ON r.runtime_id = s.runtime_id
         WHERE upper(coalesce(r.state_payload->>'EngineKind', '')) = 'THEME_PARK_RACE'
           AND upper(coalesce(r.state_payload->>'StrategyMode', '')) = 'OPEN_MISSION_BOARD'
    ) OR EXISTS (
        SELECT 1
          FROM public.audit_log_v2 a
         WHERE a.action IN ('THEME_PARK_RACE_MISSION_OPERATION_CHANGED')
            OR (
                a.action = 'THEME_PARK_RACE_CONFIGURATION_SAVED'
                AND upper(coalesce(a.after_state #>> '{RaceConfiguration,StrategyMode}', '')) = 'OPEN_MISSION_BOARD'
            )
    ) THEN
        RAISE EXCEPTION 'Rollback blocked: OPEN_MISSION_BOARD configuration, runtime, submission lineage, or audit history exists';
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_theme_park_race_score_guard_trg
    ON public.submissions_v2;
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_score_guard();
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_board_submit(text,text,jsonb);
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_board_record_ride_outcome(text,text,text,jsonb);
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_board_select(text,text);
DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_board_set_mission_operation(text,text,text,text,text);

-- Exact 037 baseline: public.exos_v2_theme_park_race_save_configuration.
CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_save_configuration(
    p_event_id text,
    p_configuration jsonb,
    p_actor text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_formation jsonb;
    v_configuration jsonb;
    v_team_id text;
    v_route jsonb;
    v_activity_id text;
    v_submission_count integer;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID and facilitator identity are required';
    END IF;
    IF jsonb_typeof(coalesce(p_configuration, 'null'::jsonb)) <> 'object' THEN
        RAISE EXCEPTION 'Theme Park Race configuration must be a JSON object';
    END IF;
    IF coalesce(p_configuration->>'SchemaVersion', '') <> '1'
       OR upper(coalesce(p_configuration->>'EngineKind', '')) <> 'THEME_PARK_RACE'
       OR upper(coalesce(p_configuration->>'RouteStrategy', '')) <> 'CONFIGURED_TEAM_ROUTE' THEN
        RAISE EXCEPTION 'Theme Park Race requires SchemaVersion 1, EngineKind THEME_PARK_RACE, and CONFIGURED_TEAM_ROUTE';
    END IF;
    IF upper(coalesce(p_configuration->>'RuntimePhase', 'READY')) NOT IN ('READY', 'ACTIVE', 'CLOSED') THEN
        RAISE EXCEPTION 'Theme Park Race RuntimePhase must be READY, ACTIVE, or CLOSED';
    END IF;
    IF jsonb_typeof(coalesce(p_configuration->'TeamRoutes', 'null'::jsonb)) <> 'object' THEN
        RAISE EXCEPTION 'Theme Park Race requires TeamRoutes keyed by canonical TeamID';
    END IF;

    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id)
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event not found';
    END IF;
    IF coalesce(v_event.event_payload #>> '{RaceConfiguration,EngineKind}', '')
       NOT IN ('', 'THEME_PARK_RACE') THEN
        RAISE EXCEPTION 'This event is already configured for a different race engine';
    END IF;
    v_formation := coalesce(v_event.event_payload->'TeamFormation', '{}'::jsonb);
    IF coalesce(v_formation->>'SchemaVersion', '') <> '1' THEN
        RAISE EXCEPTION 'Theme Park Race requires configured Team Formation V1';
    END IF;
    IF upper(coalesce(p_configuration->>'RuntimePhase', 'READY')) = 'ACTIVE'
       AND coalesce(v_formation->>'Phase', '') <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Team Formation must be ACTIVE before a Theme Park Race can start';
    END IF;

    FOR v_team_id IN
        SELECT team_id
          FROM public.teams_v2
         WHERE event_id = v_event.event_id AND is_active
         ORDER BY team_id
    LOOP
        v_route := p_configuration->'TeamRoutes'->v_team_id;
        IF jsonb_typeof(v_route) <> 'array' OR jsonb_array_length(v_route) = 0 THEN
            RAISE EXCEPTION 'Every active team requires a non-empty configured route';
        END IF;
        IF jsonb_array_length(v_route) <> (
            SELECT count(*)
             FROM public.activities_v2 a
              JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
             WHERE p.event_id = v_event.event_id
               AND a.is_active
               AND a.activity_payload ? 'race_station'
               AND coalesce((a.activity_payload->'race_station'->>'Enabled')::boolean, true)
        ) THEN
            RAISE EXCEPTION 'Every team route must contain every enabled Theme Park mission exactly once';
        END IF;
        IF EXISTS (
            SELECT 1
              FROM jsonb_array_elements_text(v_route) AS route(activity_id)
             WHERE nullif(trim(route.activity_id), '') IS NULL
                OR NOT EXISTS (
                    SELECT 1
                      FROM public.activities_v2 a
                      JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
                     WHERE p.event_id = v_event.event_id
                       AND a.activity_id = route.activity_id
                       AND a.is_active
                       AND a.activity_payload ? 'race_station'
                       AND coalesce((a.activity_payload->'race_station'->>'Enabled')::boolean, true)
                )
        ) THEN
            RAISE EXCEPTION 'A team route contains an unavailable Theme Park mission';
        END IF;
        IF (SELECT count(*) FROM jsonb_array_elements_text(v_route))
           <> (SELECT count(DISTINCT activity_id) FROM jsonb_array_elements_text(v_route) AS route(activity_id)) THEN
            RAISE EXCEPTION 'A team route cannot repeat a mission';
        END IF;
    END LOOP;
    IF EXISTS (
        SELECT 1
          FROM jsonb_object_keys(p_configuration->'TeamRoutes') AS configured(team_id)
         WHERE NOT EXISTS (
            SELECT 1 FROM public.teams_v2 t
             WHERE t.event_id = v_event.event_id AND t.team_id = configured.team_id AND t.is_active
         )
    ) THEN
        RAISE EXCEPTION 'Theme Park Race route belongs to an inactive or foreign team';
    END IF;

    SELECT count(*) INTO v_submission_count
      FROM public.submissions_v2
     WHERE event_id = v_event.event_id;
    IF v_submission_count > 0
       AND coalesce(v_event.event_payload->'RaceConfiguration'->'TeamRoutes', '{}'::jsonb)
           IS DISTINCT FROM coalesce(p_configuration->'TeamRoutes', '{}'::jsonb) THEN
        RAISE EXCEPTION 'Theme Park Race routes are locked after the first submission';
    END IF;

    v_configuration := p_configuration || jsonb_build_object(
        'SchemaVersion', 1,
        'EngineKind', 'THEME_PARK_RACE',
        'RouteStrategy', 'CONFIGURED_TEAM_ROUTE',
        'RuntimePhase', upper(coalesce(p_configuration->>'RuntimePhase', 'READY')),
        'UpdatedAt', now(),
        'UpdatedBy', trim(p_actor)
    );
    UPDATE public.events_v2
       SET event_payload = jsonb_set(event_payload, '{RaceConfiguration}', v_configuration, true),
           updated_at = now()
     WHERE event_id = v_event.event_id;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (
        v_event.event_id, trim(p_actor), 'THEME_PARK_RACE_CONFIGURATION_SAVED',
        'events_v2', v_event.event_id, jsonb_build_object('RaceConfiguration', v_configuration)
    );
    RETURN jsonb_build_object(
        'EventID', v_event.event_id,
        'EngineKind', 'THEME_PARK_RACE',
        'RuntimePhase', v_configuration->>'RuntimePhase',
        'Saved', true
    );
END;
$$;

-- Exact 037 baseline: public.exos_v2_theme_park_race_submission_guard.
CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_submission_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_configuration jsonb;
    v_station jsonb;
    v_current_activity_id text;
    v_runtime_session public.participant_sessions_v2%rowtype;
    v_participant public.participants_v2%rowtype;
    v_minimum numeric;
    v_maximum numeric;
    v_numeric text;
BEGIN
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = NEW.event_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Theme Park Race submission event is unavailable';
    END IF;
    v_configuration := coalesce(v_event.event_payload->'RaceConfiguration', '{}'::jsonb);
    IF upper(coalesce(v_configuration->>'EngineKind', '')) <> 'THEME_PARK_RACE' THEN
        RETURN NEW;
    END IF;
    IF coalesce(v_configuration->>'SchemaVersion', '') <> '1'
       OR upper(coalesce(v_configuration->>'RouteStrategy', '')) <> 'CONFIGURED_TEAM_ROUTE' THEN
        RAISE EXCEPTION 'Theme Park Race configuration is invalid';
    END IF;
    IF coalesce(v_event.event_payload #>> '{TeamFormation,Phase}', '') <> 'ACTIVE'
       OR upper(coalesce(v_configuration->>'RuntimePhase', 'READY')) <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Theme Park Race is not active';
    END IF;

    -- Facilitator review writes are not participant submissions.  An exact
    -- repeated submission remains idempotent after the initial route advance.
    IF TG_OP = 'UPDATE'
       AND NEW.submission_status <> 'SUBMITTED' THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.submission_status = 'SUBMITTED'
       AND NEW.submission_status = 'SUBMITTED'
       AND NEW.submission_payload = OLD.submission_payload
       AND NEW.activity_id = OLD.activity_id
       AND NEW.participant_id = OLD.participant_id
       AND NEW.team_id = OLD.team_id THEN
        RETURN NEW;
    END IF;
    IF NEW.submission_status <> 'SUBMITTED' THEN
        RETURN NEW;
    END IF;

    SELECT p.* INTO v_participant
      FROM public.participants_v2 p
     WHERE p.participant_id = NEW.participant_id
       AND p.event_id = NEW.event_id
       AND p.team_id = NEW.team_id
       AND p.is_team_formation_captain
       AND NOT p.is_archived
       AND p.merged_into_participant_id IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Only the effective Theme Park Race Captain may submit';
    END IF;
    SELECT s.* INTO v_runtime_session
      FROM public.activity_runtime_v2 r
      JOIN public.participant_sessions_v2 s ON s.participant_session_id = r.session_id
     WHERE r.runtime_id = NEW.runtime_id
       AND r.event_id = NEW.event_id
       AND r.participant_id = NEW.participant_id
       AND s.is_active
     LIMIT 1;
    IF NOT FOUND OR NOT EXISTS (
        SELECT 1
          FROM public.team_access_sessions_v2 captain_session
         WHERE captain_session.event_id = NEW.event_id
           AND captain_session.team_id = NEW.team_id
           AND captain_session.team_formation_captain_participant_id = NEW.participant_id
           AND captain_session.device_id = v_runtime_session.device_id
           AND captain_session.is_active
    ) THEN
        RAISE EXCEPTION 'An active participant-linked Captain session is required';
    END IF;
    SELECT a.activity_payload->'race_station' INTO v_station
      FROM public.activities_v2 a
      JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
     WHERE a.activity_id = NEW.activity_id
       AND p.event_id = NEW.event_id
       AND a.is_active;
    IF v_station IS NULL OR coalesce((v_station->>'Enabled')::boolean, true) IS NOT TRUE THEN
        RAISE EXCEPTION 'Activity is not an enabled Theme Park Race mission';
    END IF;
    SELECT route.activity_id INTO v_current_activity_id
      FROM jsonb_array_elements_text(coalesce(v_configuration->'TeamRoutes'->NEW.team_id, '[]'::jsonb))
           WITH ORDINALITY AS route(activity_id, position)
     WHERE NOT EXISTS (
        SELECT 1
          FROM public.submissions_v2 submitted
         WHERE submitted.event_id = NEW.event_id
           AND submitted.team_id = NEW.team_id
           AND submitted.activity_id = route.activity_id
           AND submitted.submission_status NOT IN ('REJECTED', 'WITHDRAWN')
     )
     ORDER BY route.position
     LIMIT 1;
    IF v_current_activity_id IS NULL THEN
        RAISE EXCEPTION 'Configured Theme Park Race route is complete';
    END IF;
    IF v_current_activity_id <> NEW.activity_id THEN
        RAISE EXCEPTION 'Only the configured current Theme Park Race mission can be submitted';
    END IF;
    IF coalesce((v_station #>> '{Evidence,Text,Required}')::boolean, false)
       AND nullif(trim(NEW.submission_payload->>'Remarks'), '') IS NULL THEN
        RAISE EXCEPTION 'Text evidence is required for this mission';
    END IF;
    IF coalesce((v_station #>> '{Evidence,Photo,Required}')::boolean, false)
       AND nullif(trim(coalesce(NEW.submission_payload->>'ImageURL', NEW.submission_payload->>'DriveFileID')), '') IS NULL THEN
        RAISE EXCEPTION 'Private photo evidence is required for this mission';
    END IF;
    IF coalesce((v_station #>> '{Evidence,NumericResult,Required}')::boolean, false)
       AND nullif(trim(NEW.submission_payload->>'Metric1'), '') IS NULL THEN
        RAISE EXCEPTION 'A numeric result is required for this mission';
    END IF;
    v_numeric := nullif(trim(NEW.submission_payload->>'Metric1'), '');
    IF v_numeric IS NOT NULL AND v_numeric !~ '^-?[0-9]+(\\.[0-9]+)?$' THEN
        RAISE EXCEPTION 'Numeric result must be a number';
    END IF;
    v_minimum := nullif(v_station #>> '{Evidence,NumericResult,Minimum}', '')::numeric;
    v_maximum := nullif(v_station #>> '{Evidence,NumericResult,Maximum}', '')::numeric;
    IF v_numeric IS NOT NULL
       AND ((v_minimum IS NOT NULL AND v_numeric::numeric < v_minimum)
         OR (v_maximum IS NOT NULL AND v_numeric::numeric > v_maximum)) THEN
        RAISE EXCEPTION 'Numeric result is outside the configured mission range';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_theme_park_race_submission_guard_trg
    ON public.submissions_v2;
CREATE TRIGGER exos_v2_theme_park_race_submission_guard_trg
BEFORE INSERT OR UPDATE OF submission_status, submission_payload, runtime_id,
    participant_id, team_id, activity_id
ON public.submissions_v2
FOR EACH ROW EXECUTE FUNCTION public.exos_v2_theme_park_race_submission_guard();

REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_save_configuration(text,jsonb,text) FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_set_theme_park_race_runtime_phase(text,text,text) FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_submit(text,text,jsonb) FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_submission_guard() FROM anon, authenticated, service_role, PUBLIC;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_save_configuration(text,jsonb,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_set_theme_park_race_runtime_phase(text,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_submit(text,text,jsonb) TO anon, authenticated, service_role;

COMMIT;
