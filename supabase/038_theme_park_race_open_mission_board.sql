-- EXOS Theme Park Race OPEN_MISSION_BOARD strategy extension.
-- LOCAL SOURCE ONLY. Do not install without an approved migration review.
-- Depends on 020/025, 036, and the unmodified 037 Theme Park Race engine.
-- It adds no tables: selection/ride attempt state uses activity_runtime_v2;
-- evidence/review uses submissions_v2/reviews_v2; operational board state uses
-- the existing event RaceConfiguration payload; scores remain score-ledger rows.
BEGIN;

-- 037 intentionally remains unchanged.  This replacement is installed only as
-- a later migration so the original CONFIGURED_TEAM_ROUTE implementation stays
-- source-compatible while OPEN_MISSION_BOARD is an opt-in configuration mode.
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
    v_configuration jsonb := coalesce(p_configuration, '{}'::jsonb);
    v_existing_configuration jsonb;
    v_existing_structural jsonb;
    v_incoming_structural jsonb;
    v_has_authoritative_play_state boolean := false;
    v_strategy text;
    v_team_id text;
    v_route jsonb;
    v_activity_id text;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID and facilitator identity are required';
    END IF;
    IF jsonb_typeof(v_configuration) <> 'object'
       OR coalesce(v_configuration->>'SchemaVersion', '') <> '1'
       OR upper(coalesce(v_configuration->>'EngineKind', '')) <> 'THEME_PARK_RACE' THEN
        RAISE EXCEPTION 'Theme Park Race requires SchemaVersion 1 and EngineKind THEME_PARK_RACE';
    END IF;
    v_strategy := upper(coalesce(v_configuration->>'StrategyMode', v_configuration->>'RouteStrategy', 'CONFIGURED_TEAM_ROUTE'));
    IF v_strategy NOT IN ('CONFIGURED_TEAM_ROUTE', 'OPEN_MISSION_BOARD') THEN
        RAISE EXCEPTION 'Theme Park Race StrategyMode is invalid';
    END IF;
    IF upper(coalesce(v_configuration->>'RuntimePhase', 'READY')) NOT IN ('READY', 'ACTIVE', 'CLOSED') THEN
        RAISE EXCEPTION 'Theme Park Race RuntimePhase must be READY, ACTIVE, or CLOSED';
    END IF;

    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = trim(p_event_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Event not found'; END IF;
    -- Preserve the 037 architectural boundary exactly: a Theme Park Race
    -- configuration RPC can never take ownership of an event selected for a
    -- different engine.
    IF coalesce(v_event.event_payload #>> '{RaceConfiguration,EngineKind}', '')
       NOT IN ('', 'THEME_PARK_RACE') THEN
        RAISE EXCEPTION 'This event is already configured for a different race engine';
    END IF;
    v_existing_configuration := coalesce(v_event.event_payload->'RaceConfiguration', '{}'::jsonb);
    v_formation := coalesce(v_event.event_payload->'TeamFormation', '{}'::jsonb);
    IF coalesce(v_formation->>'SchemaVersion', '') <> '1' THEN
        RAISE EXCEPTION 'Theme Park Race requires configured Team Formation V1';
    END IF;
    IF upper(coalesce(v_configuration->>'RuntimePhase', 'READY')) = 'ACTIVE'
       AND coalesce(v_formation->>'Phase', '') <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Team Formation must be ACTIVE before a Theme Park Race can start';
    END IF;

    -- Freeze the game contract at the first authoritative Theme Park runtime
    -- or submission.  The boundary is deliberately event-scoped and joins the
    -- event's active race_station activities, so generic activity state cannot
    -- accidentally freeze another engine.  Mission operations and runtime
    -- phase retain their dedicated RPCs; save_configuration may not alter them
    -- after play begins.
    IF upper(coalesce(v_existing_configuration->>'EngineKind', '')) = 'THEME_PARK_RACE' THEN
        SELECT EXISTS (
            SELECT 1
              FROM public.activity_runtime_v2 r
              JOIN public.activities_v2 a ON a.activity_id = r.activity_id
              JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
             WHERE r.event_id = v_event.event_id
               AND p.event_id = v_event.event_id
               AND a.activity_payload ? 'race_station'
        ) OR EXISTS (
            SELECT 1
              FROM public.submissions_v2 s
              JOIN public.activities_v2 a ON a.activity_id = s.activity_id
              JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
             WHERE s.event_id = v_event.event_id
               AND p.event_id = v_event.event_id
               AND a.activity_payload ? 'race_station'
        )
        INTO v_has_authoritative_play_state;
    END IF;
    IF v_has_authoritative_play_state THEN
        v_existing_structural := v_existing_configuration
            - ARRAY['RuntimePhase', 'Projector', 'UpdatedAt', 'UpdatedBy'];
        v_incoming_structural := (v_configuration || jsonb_build_object(
            'SchemaVersion', 1,
            'EngineKind', 'THEME_PARK_RACE',
            'StrategyMode', v_strategy
        )) - ARRAY['RuntimePhase', 'Projector', 'UpdatedAt', 'UpdatedBy'];
        IF v_existing_structural IS DISTINCT FROM v_incoming_structural THEN
            RAISE EXCEPTION 'Theme Park Race structural configuration is frozen after authoritative runtime or submissions exist';
        END IF;
        IF upper(coalesce(v_configuration->>'RuntimePhase', 'READY'))
           IS DISTINCT FROM upper(coalesce(v_existing_configuration->>'RuntimePhase', 'READY')) THEN
            RAISE EXCEPTION 'Theme Park Race RuntimePhase must be changed through its dedicated runtime RPC after play begins';
        END IF;
    END IF;

    IF v_strategy = 'CONFIGURED_TEAM_ROUTE' THEN
        IF upper(coalesce(v_configuration->>'RouteStrategy', '')) <> 'CONFIGURED_TEAM_ROUTE'
           OR jsonb_typeof(coalesce(v_configuration->'TeamRoutes', 'null'::jsonb)) <> 'object' THEN
            RAISE EXCEPTION 'Configured route strategy requires canonical TeamRoutes';
        END IF;
        FOR v_team_id IN SELECT team_id FROM public.teams_v2 WHERE event_id=v_event.event_id AND is_active LOOP
            v_route := v_configuration->'TeamRoutes'->v_team_id;
            IF jsonb_typeof(v_route) <> 'array' OR jsonb_array_length(v_route)=0 THEN
                RAISE EXCEPTION 'Every active team requires a non-empty configured route';
            END IF;
            IF jsonb_array_length(v_route) <> (
                SELECT count(*) FROM public.activities_v2 a JOIN public.programmes_v2 p ON p.programme_id=a.programme_id
                 WHERE p.event_id=v_event.event_id AND a.is_active AND a.activity_payload ? 'race_station'
                   AND coalesce((a.activity_payload->'race_station'->>'Enabled')::boolean, true)
            ) OR EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(v_route) route(activity_id)
                 WHERE NOT EXISTS (
                    SELECT 1 FROM public.activities_v2 a JOIN public.programmes_v2 p ON p.programme_id=a.programme_id
                     WHERE p.event_id=v_event.event_id AND a.activity_id=route.activity_id AND a.is_active
                       AND a.activity_payload ? 'race_station'
                 )
            ) OR (SELECT count(*) FROM jsonb_array_elements_text(v_route))
                 <> (SELECT count(DISTINCT activity_id) FROM jsonb_array_elements_text(v_route) route(activity_id)) THEN
                RAISE EXCEPTION 'Every configured route must contain each enabled mission exactly once';
            END IF;
        END LOOP;
        IF EXISTS (SELECT 1 FROM jsonb_object_keys(v_configuration->'TeamRoutes') key(team_id)
                    WHERE NOT EXISTS (SELECT 1 FROM public.teams_v2 t WHERE t.event_id=v_event.event_id AND t.team_id=key.team_id AND t.is_active)) THEN
            RAISE EXCEPTION 'Theme Park Race route belongs to an inactive or foreign team';
        END IF;
        IF EXISTS (SELECT 1 FROM public.submissions_v2 WHERE event_id=v_event.event_id)
           AND coalesce(v_event.event_payload->'RaceConfiguration'->'TeamRoutes','{}'::jsonb)
               IS DISTINCT FROM coalesce(v_configuration->'TeamRoutes','{}'::jsonb) THEN
            RAISE EXCEPTION 'Theme Park Race routes are locked after the first submission';
        END IF;
    ELSE
        IF jsonb_typeof(coalesce(v_configuration->'MissionBoard', 'null'::jsonb)) <> 'object' THEN
            RAISE EXCEPTION 'OPEN_MISSION_BOARD requires a MissionBoard object';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public.activities_v2 a JOIN public.programmes_v2 p ON p.programme_id=a.programme_id
             WHERE p.event_id=v_event.event_id AND a.is_active AND a.activity_payload ? 'race_station'
        ) THEN
            RAISE EXCEPTION 'OPEN_MISSION_BOARD requires at least one enabled activity race_station';
        END IF;
        FOR v_activity_id IN SELECT a.activity_id FROM public.activities_v2 a JOIN public.programmes_v2 p ON p.programme_id=a.programme_id
                                WHERE p.event_id=v_event.event_id AND a.is_active AND a.activity_payload ? 'race_station' LOOP
            IF upper(coalesce((SELECT a.activity_payload->'race_station'->>'MissionClass' FROM public.activities_v2 a WHERE a.activity_id=v_activity_id), 'STANDARD')) = 'RIDE'
               AND (coalesce((SELECT (a.activity_payload->'race_station'->'RideParticipation'->>'RequiredPercent')::numeric FROM public.activities_v2 a WHERE a.activity_id=v_activity_id), 0) <= 0
                    OR coalesce((SELECT (a.activity_payload->'race_station'->'RideParticipation'->>'RequiredPercent')::numeric FROM public.activities_v2 a WHERE a.activity_id=v_activity_id), 0) > 100) THEN
                RAISE EXCEPTION 'Ride missions require a participation threshold between 1 and 100';
            END IF;
        END LOOP;
    END IF;

    v_configuration := v_configuration || jsonb_build_object(
        'SchemaVersion', 1, 'EngineKind', 'THEME_PARK_RACE', 'StrategyMode', v_strategy,
        'RuntimePhase', upper(coalesce(v_configuration->>'RuntimePhase', 'READY')),
        'UpdatedAt', now(), 'UpdatedBy', trim(p_actor)
    );
    UPDATE public.events_v2 SET event_payload=jsonb_set(event_payload, '{RaceConfiguration}', v_configuration, true), updated_at=now()
     WHERE event_id=v_event.event_id;
    INSERT INTO public.audit_log_v2(event_id,actor,action,entity_type,entity_id,after_state)
    VALUES(v_event.event_id,trim(p_actor),'THEME_PARK_RACE_CONFIGURATION_SAVED','events_v2',v_event.event_id,jsonb_build_object('RaceConfiguration',v_configuration));
    RETURN jsonb_build_object('EventID',v_event.event_id,'EngineKind','THEME_PARK_RACE','StrategyMode',v_strategy,'Saved',true);
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_board_set_mission_operation(
    p_event_id text,
    p_activity_id text,
    p_operational_status text,
    p_secret_state text,
    p_actor text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_configuration jsonb;
    v_operations jsonb;
    v_status text := upper(trim(p_operational_status));
    v_secret text := upper(trim(p_secret_state));
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL
       OR nullif(trim(p_activity_id), '') IS NULL
       OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID, mission ActivityID, and facilitator identity are required';
    END IF;
    IF v_status NOT IN ('AVAILABLE','TEMPORARILY_UNAVAILABLE','CLOSED') OR v_secret NOT IN ('LOCKED','RELEASED') THEN
        RAISE EXCEPTION 'Mission operational or secret state is invalid';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id=trim(p_event_id) FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Event not found'; END IF;
    v_configuration := coalesce(v_event.event_payload->'RaceConfiguration','{}'::jsonb);
    IF upper(coalesce(v_configuration->>'EngineKind','')) <> 'THEME_PARK_RACE'
       OR upper(coalesce(v_configuration->>'StrategyMode','')) <> 'OPEN_MISSION_BOARD' THEN
        RAISE EXCEPTION 'Event is not configured for OPEN_MISSION_BOARD';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.activities_v2 a JOIN public.programmes_v2 p ON p.programme_id=a.programme_id
                   WHERE p.event_id=v_event.event_id AND a.activity_id=trim(p_activity_id) AND a.is_active AND a.activity_payload ? 'race_station') THEN
        RAISE EXCEPTION 'Mission is unavailable for this event';
    END IF;
    v_operations := coalesce(v_configuration#>'{MissionBoard,MissionOperations}','{}'::jsonb);
    v_operations := jsonb_set(v_operations, ARRAY[trim(p_activity_id)], jsonb_build_object('OperationalStatus',v_status,'SecretState',v_secret,'UpdatedAt',now(),'UpdatedBy',trim(p_actor)), true);
    v_configuration := jsonb_set(v_configuration, '{MissionBoard}', coalesce(v_configuration->'MissionBoard','{}'::jsonb) || jsonb_build_object('MissionOperations',v_operations), true);
    UPDATE public.events_v2 SET event_payload=jsonb_set(event_payload,'{RaceConfiguration}',v_configuration,true),updated_at=now() WHERE event_id=v_event.event_id;
    INSERT INTO public.audit_log_v2(event_id,actor,action,entity_type,entity_id,after_state)
    VALUES(v_event.event_id,trim(p_actor),'THEME_PARK_RACE_MISSION_OPERATION_CHANGED','activities_v2',trim(p_activity_id),jsonb_build_object('OperationalStatus',v_status,'SecretState',v_secret));
    RETURN jsonb_build_object('EventID',v_event.event_id,'ActivityID',trim(p_activity_id),'OperationalStatus',v_status,'SecretState',v_secret);
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_board_select(
    p_session_token text,
    p_activity_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_session public.participant_sessions_v2%rowtype;
    v_participant public.participants_v2%rowtype;
    v_event public.events_v2%rowtype;
    v_station jsonb;
    v_operation jsonb;
    v_runtime public.activity_runtime_v2%rowtype;
    v_selected_count integer;
    v_limit integer;
BEGIN
    SELECT * INTO v_session FROM public.participant_sessions_v2 WHERE session_token::text=trim(p_session_token) AND is_active FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT * INTO v_participant FROM public.participants_v2 WHERE participant_id=v_session.participant_id AND event_id=v_session.event_id
      AND is_team_formation_captain AND NOT is_archived AND merged_into_participant_id IS NULL;
    IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM public.team_access_sessions_v2 s WHERE s.event_id=v_session.event_id AND s.team_id=v_participant.team_id
        AND s.team_formation_captain_participant_id=v_participant.participant_id AND s.device_id=v_session.device_id AND s.is_active) THEN
        RAISE EXCEPTION 'Only the effective Theme Park Race Captain with an active Captain session may select a mission';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id=v_session.event_id FOR UPDATE;
    IF coalesce(v_event.event_payload#>>'{TeamFormation,Phase}','') <> 'ACTIVE'
       OR upper(coalesce(v_event.event_payload#>>'{RaceConfiguration,RuntimePhase}','READY')) <> 'ACTIVE'
       OR upper(coalesce(v_event.event_payload#>>'{RaceConfiguration,StrategyMode}','')) <> 'OPEN_MISSION_BOARD' THEN
        RAISE EXCEPTION 'OPEN_MISSION_BOARD is not active';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(v_event.event_id || '|OPEN_MISSION_BOARD|' || v_participant.team_id, 61));
    SELECT a.activity_payload->'race_station' INTO v_station FROM public.activities_v2 a JOIN public.programmes_v2 p ON p.programme_id=a.programme_id
     WHERE p.event_id=v_event.event_id AND a.activity_id=trim(p_activity_id) AND a.is_active;
    IF v_station IS NULL OR coalesce((v_station->>'Enabled')::boolean,true) IS NOT TRUE THEN RAISE EXCEPTION 'Mission is unavailable'; END IF;
    v_operation := coalesce((v_event.event_payload #> '{RaceConfiguration,MissionBoard,MissionOperations}') -> trim(p_activity_id),'{}'::jsonb);
    IF upper(coalesce(v_operation->>'OperationalStatus','AVAILABLE')) <> 'AVAILABLE' THEN RAISE EXCEPTION 'Mission is not available for selection'; END IF;
    IF upper(coalesce(v_station->>'MissionClass','STANDARD'))='SECRET' AND upper(coalesce(v_operation->>'SecretState','LOCKED')) <> 'RELEASED' THEN
        RAISE EXCEPTION 'Secret mission is locked';
    END IF;
    SELECT count(*) INTO v_selected_count FROM public.activity_runtime_v2 r
     WHERE r.event_id=v_event.event_id AND r.team_id=v_participant.team_id AND coalesce(r.state_payload->>'MissionState','')='SELECTED';
    v_limit := greatest(coalesce((v_event.event_payload#>>'{RaceConfiguration,MissionBoard,MaximumConcurrentSelections}')::integer,1),1);
    SELECT * INTO v_runtime FROM public.activity_runtime_v2 r WHERE r.event_id=v_event.event_id AND r.team_id=v_participant.team_id AND r.activity_id=trim(p_activity_id)
     ORDER BY r.updated_at DESC LIMIT 1 FOR UPDATE;
    IF FOUND AND coalesce(v_runtime.state_payload->>'MissionState','')='SELECTED' THEN
        RETURN jsonb_build_object('EventID',v_event.event_id,'TeamID',v_participant.team_id,'ActivityID',trim(p_activity_id),'MissionState','SELECTED','Idempotent',true);
    END IF;
    IF v_selected_count >= v_limit THEN RAISE EXCEPTION 'Maximum concurrent mission selections reached'; END IF;
    IF FOUND THEN
        UPDATE public.activity_runtime_v2 SET participant_id=v_participant.participant_id,session_id=v_session.participant_session_id,
          state_payload=jsonb_build_object('EngineKind','THEME_PARK_RACE','StrategyMode','OPEN_MISSION_BOARD','MissionState','SELECTED','SelectedAt',now()),
          activity_started_at=now(),activity_ended_at=null,completion_ratio=0,is_completed=false,updated_at=now() WHERE runtime_id=v_runtime.runtime_id RETURNING * INTO v_runtime;
    ELSE
        INSERT INTO public.activity_runtime_v2(event_id,team_id,participant_id,activity_id,session_id,state_payload,activity_started_at,completion_ratio,is_completed)
        VALUES(v_event.event_id,v_participant.team_id,v_participant.participant_id,trim(p_activity_id),v_session.participant_session_id,
          jsonb_build_object('EngineKind','THEME_PARK_RACE','StrategyMode','OPEN_MISSION_BOARD','MissionState','SELECTED','SelectedAt',now()),now(),0,false)
        RETURNING * INTO v_runtime;
    END IF;
    RETURN jsonb_build_object('EventID',v_event.event_id,'TeamID',v_participant.team_id,'ActivityID',trim(p_activity_id),'MissionState','SELECTED','RuntimeID',v_runtime.runtime_id::text);
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_board_record_ride_outcome(
    p_session_token text,
    p_activity_id text,
    p_ride_attempt_status text,
    p_payload jsonb DEFAULT '{}'::jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_session public.participant_sessions_v2%rowtype;
    v_participant public.participants_v2%rowtype;
    v_event public.events_v2%rowtype;
    v_runtime public.activity_runtime_v2%rowtype;
    v_station jsonb;
    v_attempt text := upper(trim(p_ride_attempt_status));
BEGIN
    IF v_attempt NOT IN ('ATTEMPTED','COMPLETED','ABORTED_BY_ATTRACTION','TEAM_WITHDREW') THEN RAISE EXCEPTION 'Ride attempt status is invalid'; END IF;
    SELECT * INTO v_session FROM public.participant_sessions_v2 WHERE session_token::text=trim(p_session_token) AND is_active FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT * INTO v_participant FROM public.participants_v2 WHERE participant_id=v_session.participant_id AND event_id=v_session.event_id AND is_team_formation_captain AND NOT is_archived AND merged_into_participant_id IS NULL;
    IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM public.team_access_sessions_v2 s WHERE s.event_id=v_session.event_id AND s.team_id=v_participant.team_id AND s.team_formation_captain_participant_id=v_participant.participant_id AND s.device_id=v_session.device_id AND s.is_active) THEN
        RAISE EXCEPTION 'Only the effective Theme Park Race Captain with an active Captain session may record a ride outcome';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id=v_session.event_id FOR UPDATE;
    IF NOT FOUND OR coalesce(v_event.event_payload#>>'{TeamFormation,Phase}','') <> 'ACTIVE' OR upper(coalesce(v_event.event_payload#>>'{RaceConfiguration,RuntimePhase}','READY')) <> 'ACTIVE' OR upper(coalesce(v_event.event_payload#>>'{RaceConfiguration,StrategyMode}','')) <> 'OPEN_MISSION_BOARD' THEN RAISE EXCEPTION 'OPEN_MISSION_BOARD is not active'; END IF;
    SELECT a.activity_payload->'race_station' INTO v_station FROM public.activities_v2 a JOIN public.programmes_v2 p ON p.programme_id=a.programme_id WHERE p.event_id=v_event.event_id AND a.activity_id=trim(p_activity_id) AND a.is_active;
    IF v_station IS NULL OR upper(coalesce(v_station->>'MissionClass','')) <> 'RIDE' THEN RAISE EXCEPTION 'Mission is not a configured ride mission'; END IF;
    SELECT * INTO v_runtime FROM public.activity_runtime_v2 WHERE event_id=v_event.event_id AND team_id=v_participant.team_id AND activity_id=trim(p_activity_id) ORDER BY updated_at DESC LIMIT 1 FOR UPDATE;
    IF NOT FOUND OR coalesce(v_runtime.state_payload->>'MissionState','') <> 'SELECTED' THEN RAISE EXCEPTION 'Ride mission must be selected before recording an outcome'; END IF;
    UPDATE public.activity_runtime_v2 SET state_payload=v_runtime.state_payload || coalesce(p_payload,'{}'::jsonb)
       || jsonb_build_object('RideAttemptStatus',v_attempt,'MissionState',CASE WHEN v_attempt IN ('ABORTED_BY_ATTRACTION','TEAM_WITHDREW') THEN 'AVAILABLE' ELSE 'SELECTED' END,'UpdatedAt',now()),updated_at=now()
     WHERE runtime_id=v_runtime.runtime_id;
    RETURN jsonb_build_object('EventID',v_event.event_id,'TeamID',v_participant.team_id,'ActivityID',trim(p_activity_id),'RideAttemptStatus',v_attempt);
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_board_submit(
    p_session_token text,
    p_activity_id text,
    p_submission_payload jsonb DEFAULT '{}'::jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_session public.participant_sessions_v2%rowtype;
    v_participant public.participants_v2%rowtype;
    v_event public.events_v2%rowtype;
    v_activity public.activities_v2%rowtype;
    v_runtime public.activity_runtime_v2%rowtype;
    v_submission public.submissions_v2%rowtype;
    v_station jsonb;
    v_members integer;
    v_required integer;
    v_riders integer;
    v_path text;
    v_attempt text;
    v_key text;
BEGIN
    SELECT * INTO v_session FROM public.participant_sessions_v2 WHERE session_token::text=trim(p_session_token) AND is_active FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT * INTO v_participant FROM public.participants_v2 WHERE participant_id=v_session.participant_id AND event_id=v_session.event_id AND is_team_formation_captain AND NOT is_archived AND merged_into_participant_id IS NULL;
    IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM public.team_access_sessions_v2 s WHERE s.event_id=v_session.event_id AND s.team_id=v_participant.team_id AND s.team_formation_captain_participant_id=v_participant.participant_id AND s.device_id=v_session.device_id AND s.is_active) THEN
        RAISE EXCEPTION 'Only the effective Theme Park Race Captain with an active Captain session may submit';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id=v_session.event_id FOR UPDATE;
    IF coalesce(v_event.event_payload#>>'{TeamFormation,Phase}','') <> 'ACTIVE' OR upper(coalesce(v_event.event_payload#>>'{RaceConfiguration,RuntimePhase}','READY')) <> 'ACTIVE' OR upper(coalesce(v_event.event_payload#>>'{RaceConfiguration,StrategyMode}','')) <> 'OPEN_MISSION_BOARD' THEN RAISE EXCEPTION 'OPEN_MISSION_BOARD is not active'; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(v_event.event_id || '|OPEN_MISSION_BOARD|' || v_participant.team_id, 61));
    SELECT a.* INTO v_activity FROM public.activities_v2 a JOIN public.programmes_v2 p ON p.programme_id=a.programme_id WHERE p.event_id=v_event.event_id AND a.activity_id=trim(p_activity_id) AND a.is_active AND a.activity_payload ? 'race_station';
    IF NOT FOUND THEN RAISE EXCEPTION 'Mission is unavailable'; END IF;
    v_station := v_activity.activity_payload->'race_station';
    SELECT * INTO v_runtime FROM public.activity_runtime_v2 WHERE event_id=v_event.event_id AND team_id=v_participant.team_id AND activity_id=v_activity.activity_id ORDER BY updated_at DESC LIMIT 1 FOR UPDATE;
    IF NOT FOUND OR coalesce(v_runtime.state_payload->>'MissionState','') NOT IN ('SELECTED','REJECTED') THEN RAISE EXCEPTION 'Mission must be selected before submission'; END IF;
    IF coalesce((v_station#>>'{Evidence,Text,Required}')::boolean,false) AND nullif(trim(p_submission_payload->>'Remarks'),'') IS NULL THEN RAISE EXCEPTION 'Text evidence is required'; END IF;
    IF upper(coalesce(v_station->>'MissionClass','STANDARD')) = 'RIDE' THEN
        v_attempt := upper(coalesce(p_submission_payload->>'RideAttemptStatus',''));
        v_path := upper(coalesce(p_submission_payload->>'RideEvidencePathway',''));
        IF v_attempt <> 'COMPLETED' THEN RAISE EXCEPTION 'Only COMPLETED ride attempts create a mission submission'; END IF;
        IF v_path NOT IN ('GROUND_CONTROL','FULL_TEAM','FACILITATOR_VERIFIED') THEN RAISE EXCEPTION 'Ride evidence pathway is invalid'; END IF;
        SELECT count(*) INTO v_members FROM public.participants_v2 WHERE event_id=v_event.event_id AND team_id=v_participant.team_id AND NOT is_archived AND merged_into_participant_id IS NULL;
        v_required := ceil(v_members * coalesce((v_station#>>'{RideParticipation,RequiredPercent}')::numeric,80) / 100.0);
        IF jsonb_typeof(coalesce(p_submission_payload->'RiderParticipantIDs','null'::jsonb)) <> 'array' THEN RAISE EXCEPTION 'Ride submission requires canonical RiderParticipantIDs'; END IF;
        SELECT count(*) INTO v_riders FROM public.participants_v2 p WHERE p.event_id=v_event.event_id AND p.team_id=v_participant.team_id AND NOT p.is_archived AND p.merged_into_participant_id IS NULL
          AND p.participant_id::text IN (SELECT value FROM jsonb_array_elements_text(p_submission_payload->'RiderParticipantIDs') value);
        IF v_riders <> jsonb_array_length(p_submission_payload->'RiderParticipantIDs') OR v_riders < v_required THEN RAISE EXCEPTION 'Ride completion does not meet the canonical participation threshold'; END IF;
        IF v_path IN ('GROUND_CONTROL','FULL_TEAM') AND (nullif(trim(p_submission_payload->>'QueueEntryEvidence'),'') IS NULL OR nullif(trim(p_submission_payload->>'PostRideEvidence'),'') IS NULL) THEN
            RAISE EXCEPTION 'Official queue-entry and post-ride evidence are required; an attraction exterior is insufficient';
        END IF;
        IF v_path='FULL_TEAM' AND v_riders <> v_members THEN RAISE EXCEPTION 'FULL_TEAM requires every current canonical team member'; END IF;
        IF v_path='FACILITATOR_VERIFIED' AND nullif(trim(p_submission_payload->>'FacilitatorVerificationRequest'),'') IS NULL THEN RAISE EXCEPTION 'Facilitator verification request is required'; END IF;
    ELSIF coalesce((v_station#>>'{Evidence,Photo,Required}')::boolean,false) AND nullif(trim(coalesce(p_submission_payload->>'ImageURL',p_submission_payload->>'DriveFileID')),'') IS NULL THEN
        RAISE EXCEPTION 'Private photo evidence is required';
    END IF;
    v_key := v_event.event_id || '|' || v_activity.activity_id || '|' || v_participant.team_id;
    UPDATE public.activity_runtime_v2 SET participant_id=v_participant.participant_id,session_id=v_session.participant_session_id,
      state_payload=v_runtime.state_payload || jsonb_build_object('MissionState','SUBMITTED','RideAttemptStatus',coalesce(nullif(v_attempt,''),v_runtime.state_payload->>'RideAttemptStatus'),'CanonicalTeamMemberCount',coalesce(v_members,0),'RequiredRideParticipants',coalesce(v_required,0)),
      activity_ended_at=now(),completion_ratio=100,is_completed=true,updated_at=now() WHERE runtime_id=v_runtime.runtime_id RETURNING * INTO v_runtime;
    INSERT INTO public.submissions_v2(event_id,team_id,participant_id,activity_id,runtime_id,submission_key,submission_status,submission_payload,submitted_at,updated_at)
    VALUES(v_event.event_id,v_participant.team_id,v_participant.participant_id,v_activity.activity_id,v_runtime.runtime_id,v_key,'SUBMITTED',coalesce(p_submission_payload,'{}'::jsonb) || jsonb_build_object('CanonicalTeamMemberCount',coalesce(v_members,0),'RequiredRideParticipants',coalesce(v_required,0)),now(),now())
    ON CONFLICT(event_id,submission_key) DO UPDATE SET participant_id=excluded.participant_id,runtime_id=excluded.runtime_id,submission_status='SUBMITTED',submission_payload=excluded.submission_payload,submitted_at=now(),reviewed_at=null,reviewed_by=null,score=null,updated_at=now()
    RETURNING * INTO v_submission;
    RETURN jsonb_build_object('SubmissionID',v_submission.submission_id::text,'EventID',v_submission.event_id,'TeamID',v_submission.team_id,'ActivityID',v_submission.activity_id,'Status',v_submission.submission_status::text);
END;
$$;

-- Replace the 037 trigger implementation, not its source file. It retains
-- CONFIGURED_TEAM_ROUTE behavior and refuses a direct Standard submission for
-- an open-board mission unless an authoritative board selection/runtime exists.
CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_submission_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_configuration jsonb;
    v_strategy text;
    v_runtime public.activity_runtime_v2%rowtype;
    v_participant public.participants_v2%rowtype;
    v_runtime_session public.participant_sessions_v2%rowtype;
    v_station jsonb;
    v_current_activity_id text;
    v_minimum numeric;
    v_maximum numeric;
    v_numeric text;
BEGIN
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id=NEW.event_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Theme Park Race submission event is unavailable'; END IF;
    v_configuration := coalesce(v_event.event_payload->'RaceConfiguration','{}'::jsonb);
    IF upper(coalesce(v_configuration->>'EngineKind','')) <> 'THEME_PARK_RACE' THEN RETURN NEW; END IF;
    v_strategy := upper(coalesce(v_configuration->>'StrategyMode',v_configuration->>'RouteStrategy','CONFIGURED_TEAM_ROUTE'));
    IF v_strategy = 'CONFIGURED_TEAM_ROUTE' THEN
        IF coalesce(v_configuration->>'SchemaVersion','') <> '1'
           OR upper(coalesce(v_configuration->>'RouteStrategy','')) <> 'CONFIGURED_TEAM_ROUTE'
           OR coalesce(v_event.event_payload#>>'{TeamFormation,Phase}','') <> 'ACTIVE'
           OR upper(coalesce(v_configuration->>'RuntimePhase','READY')) <> 'ACTIVE' THEN
            RAISE EXCEPTION 'Theme Park Race configuration is invalid or inactive';
        END IF;
        IF TG_OP='UPDATE' AND NEW.submission_status <> 'SUBMITTED' THEN RETURN NEW; END IF;
        IF TG_OP='UPDATE' AND OLD.submission_status='SUBMITTED' AND NEW.submission_status='SUBMITTED'
           AND NEW.submission_payload=OLD.submission_payload AND NEW.activity_id=OLD.activity_id
           AND NEW.participant_id=OLD.participant_id AND NEW.team_id=OLD.team_id THEN RETURN NEW; END IF;
        IF NEW.submission_status <> 'SUBMITTED' THEN RETURN NEW; END IF;
        SELECT * INTO v_participant FROM public.participants_v2 p WHERE p.participant_id=NEW.participant_id
          AND p.event_id=NEW.event_id AND p.team_id=NEW.team_id AND p.is_team_formation_captain
          AND NOT p.is_archived AND p.merged_into_participant_id IS NULL;
        IF NOT FOUND THEN RAISE EXCEPTION 'Only the effective Theme Park Race Captain may submit'; END IF;
        SELECT s.* INTO v_runtime_session FROM public.activity_runtime_v2 r JOIN public.participant_sessions_v2 s ON s.participant_session_id=r.session_id
         WHERE r.runtime_id=NEW.runtime_id AND r.event_id=NEW.event_id AND r.participant_id=NEW.participant_id AND s.is_active LIMIT 1;
        IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM public.team_access_sessions_v2 captain_session WHERE captain_session.event_id=NEW.event_id
           AND captain_session.team_id=NEW.team_id AND captain_session.team_formation_captain_participant_id=NEW.participant_id
           AND captain_session.device_id=v_runtime_session.device_id AND captain_session.is_active) THEN
            RAISE EXCEPTION 'An active participant-linked Captain session is required';
        END IF;
        SELECT a.activity_payload->'race_station' INTO v_station FROM public.activities_v2 a JOIN public.programmes_v2 p ON p.programme_id=a.programme_id
         WHERE a.activity_id=NEW.activity_id AND p.event_id=NEW.event_id AND a.is_active;
        IF v_station IS NULL OR coalesce((v_station->>'Enabled')::boolean,true) IS NOT TRUE THEN RAISE EXCEPTION 'Activity is not an enabled Theme Park Race mission'; END IF;
        SELECT route.activity_id INTO v_current_activity_id
          FROM jsonb_array_elements_text(coalesce(v_configuration->'TeamRoutes'->NEW.team_id,'[]'::jsonb)) WITH ORDINALITY route(activity_id,position)
         WHERE NOT EXISTS (SELECT 1 FROM public.submissions_v2 submitted WHERE submitted.event_id=NEW.event_id AND submitted.team_id=NEW.team_id
                             AND submitted.activity_id=route.activity_id AND submitted.submission_status NOT IN ('REJECTED','WITHDRAWN'))
         ORDER BY route.position LIMIT 1;
        IF v_current_activity_id IS NULL THEN RAISE EXCEPTION 'Configured Theme Park Race route is complete'; END IF;
        IF v_current_activity_id <> NEW.activity_id THEN RAISE EXCEPTION 'Only the configured current Theme Park Race mission can be submitted'; END IF;
        IF coalesce((v_station#>>'{Evidence,Text,Required}')::boolean,false) AND nullif(trim(NEW.submission_payload->>'Remarks'),'') IS NULL THEN RAISE EXCEPTION 'Text evidence is required for this mission'; END IF;
        IF coalesce((v_station#>>'{Evidence,Photo,Required}')::boolean,false) AND nullif(trim(coalesce(NEW.submission_payload->>'ImageURL',NEW.submission_payload->>'DriveFileID')),'') IS NULL THEN RAISE EXCEPTION 'Private photo evidence is required for this mission'; END IF;
        IF coalesce((v_station#>>'{Evidence,NumericResult,Required}')::boolean,false) AND nullif(trim(NEW.submission_payload->>'Metric1'),'') IS NULL THEN RAISE EXCEPTION 'A numeric result is required for this mission'; END IF;
        v_numeric := nullif(trim(NEW.submission_payload->>'Metric1'),'');
        IF v_numeric IS NOT NULL AND v_numeric !~ '^-?[0-9]+(\\.[0-9]+)?$' THEN RAISE EXCEPTION 'Numeric result must be a number'; END IF;
        v_minimum := nullif(v_station#>>'{Evidence,NumericResult,Minimum}','')::numeric;
        v_maximum := nullif(v_station#>>'{Evidence,NumericResult,Maximum}','')::numeric;
        IF v_numeric IS NOT NULL AND ((v_minimum IS NOT NULL AND v_numeric::numeric<v_minimum) OR (v_maximum IS NOT NULL AND v_numeric::numeric>v_maximum)) THEN RAISE EXCEPTION 'Numeric result is outside the configured mission range'; END IF;
        RETURN NEW;
    END IF;
    IF v_strategy <> 'OPEN_MISSION_BOARD' THEN RAISE EXCEPTION 'Theme Park Race configuration is invalid'; END IF;
    IF TG_OP='UPDATE' AND NEW.submission_status <> 'SUBMITTED' THEN RETURN NEW; END IF;
    IF NEW.submission_status <> 'SUBMITTED' THEN RETURN NEW; END IF;
    IF coalesce(v_event.event_payload#>>'{TeamFormation,Phase}','') <> 'ACTIVE'
       OR upper(coalesce(v_configuration->>'RuntimePhase','READY')) <> 'ACTIVE' THEN RAISE EXCEPTION 'OPEN_MISSION_BOARD is not active'; END IF;
    SELECT * INTO v_participant FROM public.participants_v2 p WHERE p.participant_id=NEW.participant_id
      AND p.event_id=NEW.event_id AND p.team_id=NEW.team_id AND p.is_team_formation_captain
      AND NOT p.is_archived AND p.merged_into_participant_id IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'Only the effective Theme Park Race Captain may submit'; END IF;
    SELECT s.* INTO v_runtime_session FROM public.activity_runtime_v2 r JOIN public.participant_sessions_v2 s ON s.participant_session_id=r.session_id
     WHERE r.runtime_id=NEW.runtime_id AND r.event_id=NEW.event_id AND r.participant_id=NEW.participant_id AND s.is_active LIMIT 1;
    IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM public.team_access_sessions_v2 captain_session WHERE captain_session.event_id=NEW.event_id
       AND captain_session.team_id=NEW.team_id AND captain_session.team_formation_captain_participant_id=NEW.participant_id
       AND captain_session.device_id=v_runtime_session.device_id AND captain_session.is_active) THEN RAISE EXCEPTION 'An active participant-linked Captain session is required'; END IF;
    SELECT * INTO v_runtime FROM public.activity_runtime_v2 WHERE runtime_id=NEW.runtime_id AND event_id=NEW.event_id AND team_id=NEW.team_id AND activity_id=NEW.activity_id;
    IF NOT FOUND OR coalesce(v_runtime.state_payload->>'StrategyMode','') <> 'OPEN_MISSION_BOARD' OR coalesce(v_runtime.state_payload->>'MissionState','') NOT IN ('SELECTED','SUBMITTED','REJECTED') THEN
        RAISE EXCEPTION 'Open Mission Board submission requires an authoritative selected mission';
    END IF;
    SELECT a.activity_payload->'race_station' INTO v_station FROM public.activities_v2 a JOIN public.programmes_v2 p ON p.programme_id=a.programme_id WHERE p.event_id=NEW.event_id AND a.activity_id=NEW.activity_id;
    IF v_station IS NULL THEN RAISE EXCEPTION 'Theme Park Race mission is unavailable'; END IF;
    IF upper(coalesce(v_configuration#>>ARRAY['MissionBoard','MissionOperations',NEW.activity_id,'OperationalStatus'],'AVAILABLE')) <> 'AVAILABLE' THEN
        RAISE EXCEPTION 'Mission is not available for submission';
    END IF;
    IF upper(coalesce(v_station->>'MissionClass','STANDARD'))='RIDE'
       AND (upper(coalesce(NEW.submission_payload->>'RideAttemptStatus','')) <> 'COMPLETED' OR nullif(trim(NEW.submission_payload->>'QueueEntryEvidence'),'') IS NULL) THEN
        RAISE EXCEPTION 'Ride completion requires completed official queue-entry evidence; exterior-only evidence is insufficient';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_score_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_configuration jsonb;
    v_maximum numeric;
BEGIN
    SELECT event_payload->'RaceConfiguration' INTO v_configuration FROM public.events_v2 WHERE event_id=NEW.event_id;
    IF upper(coalesce(v_configuration->>'EngineKind','')) <> 'THEME_PARK_RACE' OR NEW.score IS NULL THEN RETURN NEW; END IF;
    SELECT nullif(a.activity_payload#>>'{race_station,Scoring,Maximum}','')::numeric INTO v_maximum
      FROM public.activities_v2 a WHERE a.activity_id=NEW.activity_id;
    IF v_maximum IS NOT NULL AND (NEW.score<0 OR NEW.score>v_maximum) THEN RAISE EXCEPTION 'Theme Park Race score is outside the configured maximum'; END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_theme_park_race_score_guard_trg ON public.submissions_v2;
CREATE TRIGGER exos_v2_theme_park_race_score_guard_trg
BEFORE UPDATE OF score ON public.submissions_v2
FOR EACH ROW EXECUTE FUNCTION public.exos_v2_theme_park_race_score_guard();

-- CREATE OR REPLACE preserves explicit ACLs.  Revoke every application role
-- first, then grant the exact RPC contract below.
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_save_configuration(text,jsonb,text) FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_board_set_mission_operation(text,text,text,text,text) FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_board_select(text,text) FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_board_record_ride_outcome(text,text,text,jsonb) FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_board_submit(text,text,jsonb) FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_submission_guard() FROM anon, authenticated, service_role, PUBLIC;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_score_guard() FROM anon, authenticated, service_role, PUBLIC;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_save_configuration(text,jsonb,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_board_set_mission_operation(text,text,text,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_board_select(text,text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_board_record_ride_outcome(text,text,text,jsonb) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_board_submit(text,text,jsonb) TO anon, authenticated, service_role;

COMMIT;
