-- Post-Maxis P0-A canonical attendance.
--
-- This is deliberately additive and event-opt-in. An event acquires the
-- attendance contract only when a service facilitator invokes
-- exos_v2_configure_attendance. No existing event, score, identity or team
-- assignment is interpreted differently merely because this migration exists.
BEGIN;

CREATE TABLE IF NOT EXISTS public.participant_attendance_v2 (
    event_id text NOT NULL
        REFERENCES public.events_v2(event_id) ON DELETE RESTRICT,
    participant_id uuid NOT NULL
        REFERENCES public.participants_v2(participant_id) ON DELETE RESTRICT,
    attendance_state text NOT NULL
        CHECK (attendance_state IN ('PREASSIGNED', 'PRESENT', 'ABSENT')),
    changed_by text NOT NULL
        CHECK (nullif(trim(changed_by), '') IS NOT NULL),
    changed_at timestamptz NOT NULL DEFAULT now(),
    reason text NOT NULL DEFAULT '',
    PRIMARY KEY (event_id, participant_id)
);

CREATE INDEX IF NOT EXISTS participant_attendance_v2_event_state_idx
    ON public.participant_attendance_v2(event_id, attendance_state);

ALTER TABLE public.participant_attendance_v2 ENABLE ROW LEVEL SECURITY;

-- The table is never an application mutation surface. Its three functions
-- below are the sole canonical path, under service_role authority.
REVOKE ALL ON TABLE public.participant_attendance_v2
    FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.exos_v2_participant_attendance_write_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF current_setting('exos.attendance_mutation', true) IS DISTINCT FROM 'v1' THEN
        RAISE EXCEPTION 'participant_attendance_v2 is mutated only through the canonical attendance RPC';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_participant_attendance_write_guard
    ON public.participant_attendance_v2;
CREATE TRIGGER exos_v2_participant_attendance_write_guard
BEFORE INSERT OR UPDATE OR DELETE ON public.participant_attendance_v2
FOR EACH ROW
EXECUTE FUNCTION public.exos_v2_participant_attendance_write_guard();

CREATE OR REPLACE FUNCTION public.exos_v2_configure_attendance(
    p_event_id text,
    p_actor text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL
       OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Event and facilitator identity are required';
    END IF;

    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id)
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event not found';
    END IF;

    UPDATE public.events_v2
       SET event_payload = jsonb_set(
               event_payload,
               '{Attendance}',
               jsonb_build_object(
                   'SchemaVersion', 1,
                   'ConfiguredBy', trim(p_actor),
                   'ConfiguredAt', now()
               ),
               true
           ),
           updated_at = now()
     WHERE event_id = v_event.event_id;

    INSERT INTO public.audit_log_v2(
        event_id, actor, action, entity_type, entity_id, after_state
    ) VALUES (
        v_event.event_id, trim(p_actor), 'ATTENDANCE_CONFIGURED',
        'events_v2', v_event.event_id, jsonb_build_object('SchemaVersion', 1)
    );

    RETURN jsonb_build_object('EventID', v_event.event_id, 'Enabled', true);
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_set_participant_attendance(
    p_event_id text,
    p_participant_id uuid,
    p_attendance_state text,
    p_actor text,
    p_reason text DEFAULT ''
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_participant public.participants_v2%rowtype;
    v_before jsonb;
    v_state text := upper(trim(p_attendance_state));
    v_reason text := coalesce(trim(p_reason), '');
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL
       OR p_participant_id IS NULL
       OR nullif(trim(p_actor), '') IS NULL
       OR v_state NOT IN ('PREASSIGNED', 'PRESENT', 'ABSENT') THEN
        RAISE EXCEPTION 'Event, participant, attendance state, and facilitator identity are required';
    END IF;

    -- Attendance is opt-in, so existing historical events retain their exact
    -- pre-042 behaviour until a facilitator explicitly configures this state.
    IF coalesce((
        SELECT event_payload #>> '{Attendance,SchemaVersion}'
          FROM public.events_v2
         WHERE event_id = trim(p_event_id)
    ), '') <> '1' THEN
        RAISE EXCEPTION 'Attendance is not configured for this event';
    END IF;

    SELECT * INTO v_participant
      FROM public.participants_v2
     WHERE event_id = trim(p_event_id)
       AND participant_id = p_participant_id
       AND NOT is_archived
       AND merged_into_participant_id IS NULL
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Participant is unavailable for this event';
    END IF;

    -- One canonical write order per participant. The participant row lock and
    -- this transaction-scoped key serialize competing facilitator updates;
    -- every committed correction is therefore auditable in serial order.
    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            v_participant.event_id || '|ATTENDANCE|' || v_participant.participant_id::text,
            73
        )
    );

    SELECT jsonb_build_object(
        'AttendanceState', attendance_state,
        'ChangedBy', changed_by,
        'ChangedAt', changed_at,
        'Reason', reason
    ) INTO v_before
      FROM public.participant_attendance_v2
     WHERE event_id = v_participant.event_id
       AND participant_id = v_participant.participant_id
     FOR UPDATE;

    PERFORM set_config('exos.attendance_mutation', 'v1', true);
    INSERT INTO public.participant_attendance_v2(
        event_id, participant_id, attendance_state, changed_by, changed_at, reason
    ) VALUES (
        v_participant.event_id, v_participant.participant_id, v_state,
        trim(p_actor), now(), v_reason
    ) ON CONFLICT (event_id, participant_id) DO UPDATE
        SET attendance_state = EXCLUDED.attendance_state,
            changed_by = EXCLUDED.changed_by,
            changed_at = EXCLUDED.changed_at,
            reason = EXCLUDED.reason;

    INSERT INTO public.audit_log_v2(
        event_id, actor, action, entity_type, entity_id, before_state, after_state
    ) VALUES (
        v_participant.event_id, trim(p_actor), 'PARTICIPANT_ATTENDANCE_CHANGED',
        'participants_v2', v_participant.participant_id::text,
        coalesce(v_before, '{}'::jsonb),
        jsonb_build_object('AttendanceState', v_state, 'Reason', v_reason)
    );

    RETURN jsonb_build_object(
        'EventID', v_participant.event_id,
        'ParticipantID', v_participant.participant_id::text,
        'AttendanceState', v_state
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_attendance_summary(p_event_id text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_teams jsonb;
    v_registered integer;
    v_present integer;
    v_absent integer;
    v_preassigned integer;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID is required';
    END IF;

    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id);
    IF NOT FOUND
       OR coalesce(v_event.event_payload #>> '{Attendance,SchemaVersion}', '') <> '1' THEN
        RAISE EXCEPTION 'Attendance is not configured for this event';
    END IF;

    SELECT
        count(p.participant_id)::integer,
        count(p.participant_id) FILTER (WHERE a.attendance_state = 'PRESENT')::integer,
        count(p.participant_id) FILTER (WHERE a.attendance_state = 'ABSENT')::integer,
        count(p.participant_id) FILTER (
            WHERE coalesce(a.attendance_state, 'PREASSIGNED') = 'PREASSIGNED'
        )::integer
      INTO v_registered, v_present, v_absent, v_preassigned
      FROM public.participants_v2 p
      LEFT JOIN public.participant_attendance_v2 a
        ON a.event_id = p.event_id
       AND a.participant_id = p.participant_id
     WHERE p.event_id = v_event.event_id
       AND NOT p.is_archived
       AND p.merged_into_participant_id IS NULL;

    -- Start at teams_v2, not participants_v2, so a zero-present team remains
    -- visible and has a canonical PresentTeamSize of zero.
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'TeamID', team_id,
        'Registered', registered,
        'Present', present,
        'Absent', absent,
        'Preassigned', preassigned,
        'PresentTeamSize', present
    ) ORDER BY team_id), '[]'::jsonb)
      INTO v_teams
      FROM (
          SELECT
              t.team_id,
              count(p.participant_id)::integer AS registered,
              count(p.participant_id) FILTER (WHERE a.attendance_state = 'PRESENT')::integer AS present,
              count(p.participant_id) FILTER (WHERE a.attendance_state = 'ABSENT')::integer AS absent,
              count(p.participant_id) FILTER (
                  WHERE coalesce(a.attendance_state, 'PREASSIGNED') = 'PREASSIGNED'
              )::integer AS preassigned
            FROM public.teams_v2 t
            LEFT JOIN public.participants_v2 p
              ON p.event_id = t.event_id
             AND p.team_id = t.team_id
             AND NOT p.is_archived
             AND p.merged_into_participant_id IS NULL
            LEFT JOIN public.participant_attendance_v2 a
              ON a.event_id = p.event_id
             AND a.participant_id = p.participant_id
           WHERE t.event_id = v_event.event_id
           GROUP BY t.team_id
      ) AS team_counts;

    RETURN jsonb_build_object(
        'EventID', v_event.event_id,
        'Registered', coalesce(v_registered, 0),
        'Present', coalesce(v_present, 0),
        'Absent', coalesce(v_absent, 0),
        'Preassigned', coalesce(v_preassigned, 0),
        'Teams', v_teams
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_attendance_roster(p_event_id text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_participants jsonb;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID is required';
    END IF;

    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id);
    IF NOT FOUND
       OR coalesce(v_event.event_payload #>> '{Attendance,SchemaVersion}', '') <> '1' THEN
        RAISE EXCEPTION 'Attendance is not configured for this event';
    END IF;

    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'ParticipantID', p.participant_id::text,
        'TeamID', p.team_id,
        'DisplayName', p.display_name,
        'AttendanceState', coalesce(a.attendance_state, 'PREASSIGNED'),
        'ChangedBy', a.changed_by,
        'ChangedAt', a.changed_at,
        'Reason', a.reason
    ) ORDER BY p.team_id, p.created_at, p.participant_id), '[]'::jsonb)
      INTO v_participants
      FROM public.participants_v2 p
      LEFT JOIN public.participant_attendance_v2 a
        ON a.event_id = p.event_id
       AND a.participant_id = p.participant_id
     WHERE p.event_id = v_event.event_id
       AND NOT p.is_archived
       AND p.merged_into_participant_id IS NULL;

    RETURN jsonb_build_object('EventID', v_event.event_id, 'Participants', v_participants);
END;
$$;

-- Every function is service-role-only. CREATE OR REPLACE retains old ACLs,
-- therefore revoke every unintended role before the explicit grant.
REVOKE ALL ON FUNCTION public.exos_v2_participant_attendance_write_guard()
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_configure_attendance(text, text)
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_set_participant_attendance(text, uuid, text, text, text)
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_attendance_summary(text)
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_attendance_roster(text)
    FROM PUBLIC, anon, authenticated, service_role;

GRANT EXECUTE ON FUNCTION public.exos_v2_configure_attendance(text, text)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_set_participant_attendance(text, uuid, text, text, text)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_attendance_summary(text)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_attendance_roster(text)
    TO service_role;

COMMIT;
