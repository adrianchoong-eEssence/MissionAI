-- Theme Park Race terminal lifecycle hardening.
-- Additive only; depends on installed 037, 037a, 038 and 039.
-- It adds no tables and preserves the existing CLOSED persisted terminal value:
-- Core projections map CLOSED to the participant/facilitator/projector ENDED state.
BEGIN;

CREATE OR REPLACE FUNCTION public.exos_v2_set_theme_park_race_runtime_phase(
    p_event_id text,
    p_runtime_phase text,
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
    v_phase text;
    v_current_phase text;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID and facilitator identity are required';
    END IF;
    v_phase := upper(trim(p_runtime_phase));
    IF v_phase NOT IN ('READY', 'ACTIVE', 'HELD', 'CLOSED') THEN
        RAISE EXCEPTION 'Theme Park Race RuntimePhase must be READY, ACTIVE, HELD, or CLOSED';
    END IF;
    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id)
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event not found';
    END IF;
    v_configuration := coalesce(v_event.event_payload->'RaceConfiguration', '{}'::jsonb);
    IF coalesce(v_configuration->>'SchemaVersion', '') <> '1'
       OR upper(coalesce(v_configuration->>'EngineKind', '')) <> 'THEME_PARK_RACE' THEN
        RAISE EXCEPTION 'Event is not configured for Theme Park Race';
    END IF;
    v_current_phase := upper(coalesce(v_configuration->>'RuntimePhase', 'READY'));
    IF v_current_phase = 'CLOSED' AND v_phase <> 'CLOSED' THEN
        RAISE EXCEPTION 'Theme Park Race Mission is ended and cannot be restarted';
    END IF;
    IF v_current_phase IN ('ACTIVE', 'HELD') AND v_phase = 'READY' THEN
        RAISE EXCEPTION 'Theme Park Race Mission cannot be reset to READY after it has started';
    END IF;
    IF v_phase = 'ACTIVE'
       AND coalesce(v_event.event_payload #>> '{TeamFormation,Phase}', '') <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Team Formation must be ACTIVE before a Theme Park Race Mission can start';
    END IF;
    v_configuration := v_configuration || jsonb_build_object(
        'RuntimePhase', v_phase,
        'RuntimePhaseChangedAt', now(),
        'RuntimePhaseChangedBy', trim(p_actor)
    );
    UPDATE public.events_v2
       SET event_payload = jsonb_set(event_payload, '{RaceConfiguration}', v_configuration, true),
           updated_at = now()
     WHERE event_id = v_event.event_id;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (
        v_event.event_id, trim(p_actor), 'THEME_PARK_RACE_RUNTIME_PHASE_CHANGED',
        'events_v2', v_event.event_id, jsonb_build_object('RuntimePhase', v_phase)
    );
    RETURN jsonb_build_object(
        'EventID', v_event.event_id,
        'RuntimePhase', v_phase,
        'Lifecycle', CASE WHEN v_phase = 'CLOSED' THEN 'ENDED' ELSE v_phase END
    );
END;
$$;

-- Operational board controls remain mutable during a live Mission, but are
-- permanently blocked once the canonical terminal phase is CLOSED/ENDED.
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
    IF upper(coalesce(v_configuration->>'RuntimePhase', 'READY')) = 'CLOSED' THEN
        RAISE EXCEPTION 'Theme Park Race Mission is ended; operational mission controls are closed';
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

REVOKE ALL ON FUNCTION public.exos_v2_set_theme_park_race_runtime_phase(text,text,text) FROM anon, authenticated, service_role, PUBLIC;
GRANT EXECUTE ON FUNCTION public.exos_v2_set_theme_park_race_runtime_phase(text,text,text) TO service_role;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_board_set_mission_operation(text,text,text,text,text) FROM anon, authenticated, service_role, PUBLIC;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_board_set_mission_operation(text,text,text,text,text) TO service_role;

COMMIT;
