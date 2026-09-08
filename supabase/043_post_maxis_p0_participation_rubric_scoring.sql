-- Post-Maxis P0-B Theme Park Race scoring.
--
-- This is an additive, explicitly configured contract. It does not replace
-- 037-040 definitions. Existing Theme Park events retain 039 review semantics
-- unless an activity race_station explicitly selects one of the new modes.
BEGIN;

CREATE TABLE IF NOT EXISTS public.theme_park_race_scoring_snapshots_v2 (
    event_id text NOT NULL REFERENCES public.events_v2(event_id) ON DELETE RESTRICT,
    team_id text NOT NULL REFERENCES public.teams_v2(team_id) ON DELETE RESTRICT,
    submission_id uuid NOT NULL REFERENCES public.submissions_v2(submission_id) ON DELETE CASCADE,
    submitted_at timestamptz NOT NULL,
    scoring_mode text NOT NULL
        CHECK (scoring_mode IN ('PARTICIPATION_PRORATED', 'FACILITATOR_RUBRIC')),
    mission_maximum numeric(12,2) NOT NULL CHECK (mission_maximum >= 0),
    present_participant_ids jsonb NOT NULL CHECK (jsonb_typeof(present_participant_ids) = 'array'),
    completing_participant_ids jsonb NOT NULL CHECK (jsonb_typeof(completing_participant_ids) = 'array'),
    present_team_size integer,
    participants_completing integer NOT NULL CHECK (participants_completing >= 0),
    eligible_score numeric(12,2) NOT NULL CHECK (eligible_score >= 0),
    rubric_criteria jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(rubric_criteria) = 'array'),
    rubric_scores jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(rubric_scores) = 'object'),
    captured_by text NOT NULL CHECK (nullif(trim(captured_by), '') IS NOT NULL),
    captured_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (submission_id, submitted_at),
    CHECK (
        (scoring_mode = 'PARTICIPATION_PRORATED'
         AND present_team_size IS NOT NULL
         AND present_team_size > 0
         AND participants_completing <= present_team_size
         AND jsonb_array_length(present_participant_ids) = present_team_size
         AND jsonb_array_length(completing_participant_ids) = participants_completing)
        OR scoring_mode = 'FACILITATOR_RUBRIC'
    )
);

CREATE INDEX IF NOT EXISTS theme_park_race_scoring_snapshots_v2_event_submission_idx
    ON public.theme_park_race_scoring_snapshots_v2(event_id, submission_id, submitted_at);

ALTER TABLE public.theme_park_race_scoring_snapshots_v2 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.theme_park_race_scoring_snapshots_v2
    FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_scoring_snapshot_write_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF current_setting('exos.tpr_scoring_snapshot_write', true) IS DISTINCT FROM 'v1' THEN
        RAISE EXCEPTION 'Theme Park Race scoring snapshots are created only by canonical scoring RPCs';
    END IF;
    -- A permit is deliberately single-use.  A later direct DML statement in
    -- the same database transaction cannot inherit a canonical RPC permit.
    PERFORM set_config('exos.tpr_scoring_snapshot_write', '', true);
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_theme_park_race_scoring_snapshot_write_guard_trg
    ON public.theme_park_race_scoring_snapshots_v2;
CREATE TRIGGER exos_v2_theme_park_race_scoring_snapshot_write_guard_trg
BEFORE INSERT OR UPDATE OR DELETE ON public.theme_park_race_scoring_snapshots_v2
FOR EACH ROW EXECUTE FUNCTION public.exos_v2_theme_park_race_scoring_snapshot_write_guard();

-- New scoring modes have their own Captain submission path. A browser that
-- calls the older board RPC directly cannot avoid the canonical present-roster
-- validation or immutable snapshot below.
CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_scored_submission_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_station jsonb;
    v_mode text;
BEGIN
    IF NEW.submission_status <> 'SUBMITTED' THEN
        RETURN NEW;
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = NEW.event_id;
    IF NOT FOUND
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,EngineKind}', '')) <> 'THEME_PARK_RACE'
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,StrategyMode}', '')) <> 'OPEN_MISSION_BOARD' THEN
        RETURN NEW;
    END IF;
    SELECT a.activity_payload -> 'race_station' INTO v_station
      FROM public.activities_v2 a
      JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
     WHERE p.event_id = NEW.event_id AND a.activity_id = NEW.activity_id AND a.is_active;
    v_mode := upper(coalesce(v_station #>> '{Scoring,Mode}', 'TEAM_FULL'));
    IF v_mode = 'PARTICIPATION_PRORATED' THEN
        IF current_setting('exos.tpr_participation_submission', true) IS DISTINCT FROM 'v1' THEN
            RAISE EXCEPTION 'Participation-prorated submissions require the canonical Captain participant-selection RPC';
        END IF;
        -- Consume the one canonical-submit permit so it cannot authorize a
        -- second direct board-submit in this same transaction.
        PERFORM set_config('exos.tpr_participation_submission', '', true);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_theme_park_race_scored_submission_guard_trg
    ON public.submissions_v2;
CREATE TRIGGER exos_v2_theme_park_race_scored_submission_guard_trg
BEFORE INSERT OR UPDATE OF submission_status, submission_payload ON public.submissions_v2
FOR EACH ROW EXECUTE FUNCTION public.exos_v2_theme_park_race_scored_submission_guard();

-- New scoring modes likewise cannot be finalised through the older manual
-- 039 score argument. The service-only wrapper calculates or validates every
-- score before delegating to the proven atomic 039 review contract.
CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_scored_review_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_station jsonb;
    v_mode text;
BEGIN
    IF NEW.submission_status NOT IN ('APPROVED', 'REJECTED') THEN
        RETURN NEW;
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = NEW.event_id;
    IF NOT FOUND
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,EngineKind}', '')) <> 'THEME_PARK_RACE'
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,StrategyMode}', '')) <> 'OPEN_MISSION_BOARD' THEN
        RETURN NEW;
    END IF;
    SELECT a.activity_payload -> 'race_station' INTO v_station
      FROM public.activities_v2 a
      JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
     WHERE p.event_id = NEW.event_id AND a.activity_id = NEW.activity_id AND a.is_active;
    v_mode := upper(coalesce(v_station #>> '{Scoring,Mode}', 'TEAM_FULL'));
    IF v_mode IN ('PARTICIPATION_PRORATED', 'FACILITATOR_RUBRIC') THEN
        IF current_setting('exos.tpr_scored_review', true) IS DISTINCT FROM 'v1' THEN
            RAISE EXCEPTION 'Configured participation or rubric scoring requires the canonical facilitator review RPC';
        END IF;
        -- Consume the permit inside the trigger.  This closes same-transaction
        -- direct-board-review bypasses while preserving the wrapper call.
        PERFORM set_config('exos.tpr_scored_review', '', true);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_theme_park_race_scored_review_guard_trg
    ON public.submissions_v2;
CREATE TRIGGER exos_v2_theme_park_race_scored_review_guard_trg
BEFORE UPDATE OF submission_status, score ON public.submissions_v2
FOR EACH ROW EXECUTE FUNCTION public.exos_v2_theme_park_race_scored_review_guard();

CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_participation_preview(
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
    v_present jsonb;
    v_present_count integer;
    v_maximum numeric;
BEGIN
    SELECT * INTO v_session FROM public.participant_sessions_v2
     WHERE session_token::text = trim(p_session_token) AND is_active;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT * INTO v_participant FROM public.participants_v2
     WHERE participant_id = v_session.participant_id AND event_id = v_session.event_id
       AND is_team_formation_captain AND NOT is_archived AND merged_into_participant_id IS NULL;
    IF NOT FOUND OR NOT EXISTS (
        SELECT 1 FROM public.team_access_sessions_v2 s
         WHERE s.event_id = v_session.event_id AND s.team_id = v_participant.team_id
           AND s.team_formation_captain_participant_id = v_participant.participant_id
           AND s.device_id = v_session.device_id AND s.is_active
    ) THEN
        RAISE EXCEPTION 'Only the effective Captain with an active Captain session may select participation';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = v_session.event_id;
    IF NOT FOUND
       OR coalesce(v_event.event_payload #>> '{Attendance,SchemaVersion}', '') <> '1'
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,EngineKind}', '')) <> 'THEME_PARK_RACE'
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,StrategyMode}', '')) <> 'OPEN_MISSION_BOARD' THEN
        RAISE EXCEPTION 'Participation scoring is not configured for this event';
    END IF;
    SELECT a.activity_payload -> 'race_station' INTO v_station
      FROM public.activities_v2 a
      JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
     WHERE p.event_id = v_event.event_id AND a.activity_id = trim(p_activity_id) AND a.is_active;
    v_maximum := nullif(v_station #>> '{Scoring,Maximum}', '')::numeric;
    IF v_station IS NULL
       OR upper(coalesce(v_station #>> '{Scoring,Mode}', 'TEAM_FULL')) <> 'PARTICIPATION_PRORATED'
       OR v_maximum IS NULL OR v_maximum < 0 THEN
        RAISE EXCEPTION 'Mission is not configured for participation-prorated scoring';
    END IF;
    SELECT
        coalesce(jsonb_agg(jsonb_build_object(
            'ParticipantID', p.participant_id::text,
            'DisplayName', p.display_name
        ) ORDER BY p.created_at, p.participant_id), '[]'::jsonb),
        count(*)::integer
      INTO v_present, v_present_count
      FROM public.participants_v2 p
      JOIN public.participant_attendance_v2 a
        ON a.event_id = p.event_id AND a.participant_id = p.participant_id
     WHERE p.event_id = v_event.event_id AND p.team_id = v_participant.team_id
       AND a.attendance_state = 'PRESENT'
       AND NOT p.is_archived AND p.merged_into_participant_id IS NULL;
    IF coalesce(v_present_count, 0) = 0 THEN
        RAISE EXCEPTION 'No PRESENT participants are available for this team';
    END IF;
    RETURN jsonb_build_object(
        'EventID', v_event.event_id,
        'TeamID', v_participant.team_id,
        'ActivityID', trim(p_activity_id),
        'MissionMaximum', v_maximum,
        'PresentTeamSize', v_present_count,
        'PresentParticipants', v_present,
        'Rounding', 'HALF_UP'
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_submit_participation(
    p_session_token text,
    p_activity_id text,
    p_submission_payload jsonb DEFAULT '{}'::jsonb,
    p_completing_participant_ids jsonb DEFAULT '[]'::jsonb
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
    v_present jsonb;
    v_selected jsonb;
    v_present_count integer;
    v_selected_count integer;
    v_valid_selected_count integer;
    v_maximum numeric;
    v_eligible numeric;
    v_payload jsonb;
    v_result jsonb;
BEGIN
    IF jsonb_typeof(coalesce(p_completing_participant_ids, 'null'::jsonb)) <> 'array' THEN
        RAISE EXCEPTION 'Participation submission requires canonical completing participant IDs';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(p_completing_participant_ids) value
         WHERE value !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    ) THEN
        RAISE EXCEPTION 'Participation participant IDs must be UUIDs';
    END IF;
    SELECT * INTO v_session FROM public.participant_sessions_v2
     WHERE session_token::text = trim(p_session_token) AND is_active FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Participant session is invalid'; END IF;
    SELECT * INTO v_participant FROM public.participants_v2
     WHERE participant_id = v_session.participant_id AND event_id = v_session.event_id
       AND is_team_formation_captain AND NOT is_archived AND merged_into_participant_id IS NULL;
    IF NOT FOUND OR NOT EXISTS (
        SELECT 1 FROM public.team_access_sessions_v2 s
         WHERE s.event_id = v_session.event_id AND s.team_id = v_participant.team_id
           AND s.team_formation_captain_participant_id = v_participant.participant_id
           AND s.device_id = v_session.device_id AND s.is_active
    ) THEN
        RAISE EXCEPTION 'Only the effective Captain with an active Captain session may submit participation';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = v_session.event_id FOR UPDATE;
    IF coalesce(v_event.event_payload #>> '{Attendance,SchemaVersion}', '') <> '1'
       OR coalesce(v_event.event_payload #>> '{TeamFormation,Phase}', '') <> 'ACTIVE'
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,EngineKind}', '')) <> 'THEME_PARK_RACE'
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,StrategyMode}', '')) <> 'OPEN_MISSION_BOARD'
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,RuntimePhase}', 'READY')) <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Participation scoring is not active for this event';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(v_event.event_id || '|OPEN_MISSION_BOARD|' || v_participant.team_id, 61));
    SELECT a.* INTO v_activity
      FROM public.activities_v2 a
      JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
     WHERE p.event_id = v_event.event_id AND a.activity_id = trim(p_activity_id)
       AND a.is_active AND a.activity_payload ? 'race_station';
    IF NOT FOUND THEN RAISE EXCEPTION 'Mission is unavailable'; END IF;
    v_station := v_activity.activity_payload -> 'race_station';
    v_maximum := nullif(v_station #>> '{Scoring,Maximum}', '')::numeric;
    IF upper(coalesce(v_station #>> '{Scoring,Mode}', 'TEAM_FULL')) <> 'PARTICIPATION_PRORATED'
       OR v_maximum IS NULL OR v_maximum < 0 THEN
        RAISE EXCEPTION 'Mission is not configured for participation-prorated scoring';
    END IF;
    -- Locks team membership before reading attendance. A concurrent attendance
    -- correction serialises before or after this snapshot, never halfway through it.
    PERFORM 1 FROM public.participants_v2 p
     WHERE p.event_id = v_event.event_id AND p.team_id = v_participant.team_id
       AND NOT p.is_archived AND p.merged_into_participant_id IS NULL
     ORDER BY p.participant_id FOR UPDATE;
    SELECT * INTO v_runtime FROM public.activity_runtime_v2
     WHERE event_id = v_event.event_id AND team_id = v_participant.team_id
       AND activity_id = v_activity.activity_id
     ORDER BY updated_at DESC LIMIT 1 FOR UPDATE;
    IF NOT FOUND OR coalesce(v_runtime.state_payload ->> 'MissionState', '') NOT IN ('SELECTED', 'REJECTED', 'SUBMITTED') THEN
        RAISE EXCEPTION 'Mission must be selected before participation submission';
    END IF;
    SELECT
        coalesce(jsonb_agg(p.participant_id::text ORDER BY p.participant_id), '[]'::jsonb),
        count(*)::integer
      INTO v_present, v_present_count
      FROM public.participants_v2 p
      JOIN public.participant_attendance_v2 a
        ON a.event_id = p.event_id AND a.participant_id = p.participant_id
     WHERE p.event_id = v_event.event_id AND p.team_id = v_participant.team_id
       AND a.attendance_state = 'PRESENT'
       AND NOT p.is_archived AND p.merged_into_participant_id IS NULL;
    IF coalesce(v_present_count, 0) = 0 THEN
        RAISE EXCEPTION 'Participation scoring requires at least one PRESENT team member';
    END IF;
    SELECT coalesce(jsonb_agg(value::uuid::text ORDER BY value::uuid), '[]'::jsonb), count(*)::integer,
           count(DISTINCT value::uuid)::integer
      INTO v_selected, v_selected_count, v_valid_selected_count
      FROM jsonb_array_elements_text(p_completing_participant_ids) value;
    IF v_selected_count <> v_valid_selected_count THEN
        RAISE EXCEPTION 'Completing participant IDs must be unique';
    END IF;
    SELECT count(*)::integer INTO v_valid_selected_count
      FROM jsonb_array_elements_text(v_selected) selected(participant_id)
      JOIN public.participants_v2 p ON p.participant_id::text = selected.participant_id
      JOIN public.participant_attendance_v2 a ON a.event_id = p.event_id AND a.participant_id = p.participant_id
     WHERE p.event_id = v_event.event_id AND p.team_id = v_participant.team_id
       AND a.attendance_state = 'PRESENT'
       AND NOT p.is_archived AND p.merged_into_participant_id IS NULL;
    IF v_valid_selected_count <> v_selected_count OR v_selected_count > v_present_count THEN
        RAISE EXCEPTION 'Completing participants must be unique PRESENT members of the Captain''s canonical team';
    END IF;
    -- PostgreSQL numeric round() is deterministic half-away-from-zero; all
    -- values here are non-negative, so it is the documented HALF_UP rule.
    v_eligible := least(v_maximum, round(v_maximum * v_selected_count::numeric / v_present_count::numeric, 0));
    v_payload := coalesce(p_submission_payload, '{}'::jsonb) || jsonb_build_object(
        'Participation', jsonb_build_object(
            'SchemaVersion', 1,
            'ScoringMode', 'PARTICIPATION_PRORATED',
            'PresentParticipantIDs', v_present,
            'PresentTeamSize', v_present_count,
            'CompletingParticipantIDs', v_selected,
            'ParticipantsCompleting', v_selected_count,
            'MissionMaximum', v_maximum,
            'EligibleScore', v_eligible,
            'Rounding', 'HALF_UP'
        )
    );
    IF coalesce(v_runtime.state_payload ->> 'MissionState', '') = 'SUBMITTED' THEN
        SELECT * INTO v_submission FROM public.submissions_v2
         WHERE event_id = v_event.event_id AND team_id = v_participant.team_id
           AND activity_id = v_activity.activity_id
         FOR UPDATE;
        IF FOUND AND coalesce(v_submission.submission_payload #> '{Participation,CompletingParticipantIDs}', '[]'::jsonb) = v_selected THEN
            RETURN jsonb_build_object(
                'SubmissionID', v_submission.submission_id::text,
                'EventID', v_submission.event_id,
                'TeamID', v_submission.team_id,
                'ActivityID', v_submission.activity_id,
                'Status', v_submission.submission_status::text,
                'EligibleScore', v_eligible,
                'Idempotent', true
            );
        END IF;
        RAISE EXCEPTION 'Mission is already submitted with a different canonical participation selection';
    END IF;
    PERFORM set_config('exos.tpr_participation_submission', 'v1', true);
    v_result := public.exos_v2_theme_park_race_board_submit(
        p_session_token, trim(p_activity_id), v_payload
    );
    SELECT * INTO v_submission FROM public.submissions_v2
     WHERE submission_id = (v_result ->> 'SubmissionID')::uuid
     FOR UPDATE;
    PERFORM set_config('exos.tpr_scoring_snapshot_write', 'v1', true);
    INSERT INTO public.theme_park_race_scoring_snapshots_v2(
        event_id, team_id, submission_id, submitted_at, scoring_mode, mission_maximum,
        present_participant_ids, completing_participant_ids, present_team_size,
        participants_completing, eligible_score, captured_by
    ) VALUES (
        v_submission.event_id, v_submission.team_id, v_submission.submission_id,
        v_submission.submitted_at, 'PARTICIPATION_PRORATED', v_maximum,
        v_present, v_selected, v_present_count, v_selected_count, v_eligible,
        v_participant.participant_id::text
    ) ON CONFLICT (submission_id, submitted_at) DO NOTHING;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (
        v_submission.event_id, v_participant.participant_id::text,
        'THEME_PARK_RACE_PARTICIPATION_SUBMITTED', 'submissions_v2',
        v_submission.submission_id::text,
        jsonb_build_object('ActivityID', v_submission.activity_id, 'PresentTeamSize', v_present_count,
            'ParticipantsCompleting', v_selected_count, 'EligibleScore', v_eligible, 'Rounding', 'HALF_UP')
    );
    RETURN v_result || jsonb_build_object('EligibleScore', v_eligible, 'PresentTeamSize', v_present_count, 'Idempotent', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_review_scored_submission(
    p_submission_id uuid,
    p_expected_submitted_at timestamptz,
    p_decision public.exos_v2_review_decision,
    p_rubric_scores jsonb DEFAULT '{}'::jsonb,
    p_actor text DEFAULT '',
    p_reason text DEFAULT '',
    p_idempotency_key text DEFAULT ''
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_submission public.submissions_v2%rowtype;
    v_event public.events_v2%rowtype;
    v_station jsonb;
    v_mode text;
    v_maximum numeric;
    v_snapshot public.theme_park_race_scoring_snapshots_v2%rowtype;
    v_decision text := upper(trim(p_decision::text));
    v_criteria jsonb;
    v_criterion jsonb;
    v_seen_ids text[] := ARRAY[]::text[];
    v_criterion_id text;
    v_weight numeric;
    v_value numeric;
    v_weighted numeric := 0;
    v_total_weight numeric := 0;
    v_score numeric := 0;
    v_result jsonb;
BEGIN
    IF p_submission_id IS NULL OR p_expected_submitted_at IS NULL
       OR nullif(trim(p_actor), '') IS NULL
       OR v_decision NOT IN ('APPROVE', 'REJECT') THEN
        RAISE EXCEPTION 'Submission, current revision, valid decision, and facilitator identity are required';
    END IF;
    SELECT * INTO v_submission FROM public.submissions_v2 WHERE submission_id = p_submission_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Submission not found'; END IF;
    IF v_submission.submitted_at IS DISTINCT FROM p_expected_submitted_at THEN
        RAISE EXCEPTION 'Submission revision is stale';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = v_submission.event_id FOR UPDATE;
    IF NOT FOUND
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,EngineKind}', '')) <> 'THEME_PARK_RACE'
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,StrategyMode}', '')) <> 'OPEN_MISSION_BOARD' THEN
        RAISE EXCEPTION 'Submission is not an OPEN_MISSION_BOARD Theme Park Race submission';
    END IF;
    SELECT a.activity_payload -> 'race_station' INTO v_station
      FROM public.activities_v2 a
      JOIN public.programmes_v2 p ON p.programme_id = a.programme_id
     WHERE p.event_id = v_event.event_id AND a.activity_id = v_submission.activity_id AND a.is_active;
    v_mode := upper(coalesce(v_station #>> '{Scoring,Mode}', 'TEAM_FULL'));
    v_maximum := nullif(v_station #>> '{Scoring,Maximum}', '')::numeric;
    IF v_mode NOT IN ('PARTICIPATION_PRORATED', 'FACILITATOR_RUBRIC')
       OR v_maximum IS NULL OR v_maximum < 0 THEN
        RAISE EXCEPTION 'Mission is not configured for canonical participation or rubric scoring';
    END IF;
    IF v_submission.submission_status = 'APPROVED' AND v_decision = 'APPROVE' THEN
        SELECT * INTO v_snapshot FROM public.theme_park_race_scoring_snapshots_v2
         WHERE submission_id = v_submission.submission_id AND submitted_at = v_submission.submitted_at;
        RETURN jsonb_build_object('SubmissionID', v_submission.submission_id::text, 'Status', 'APPROVED',
            'Score', v_submission.score, 'EligibleScore', coalesce(v_snapshot.eligible_score, v_submission.score), 'Idempotent', true);
    END IF;
    IF v_submission.submission_status = 'REJECTED' AND v_decision = 'REJECT' THEN
        RETURN jsonb_build_object('SubmissionID', v_submission.submission_id::text, 'Status', 'REJECTED',
            'Score', 0, 'Idempotent', true);
    END IF;
    IF v_submission.submission_status <> 'SUBMITTED' THEN
        RAISE EXCEPTION 'Only the current submitted revision may be reviewed';
    END IF;
    IF v_mode = 'PARTICIPATION_PRORATED' THEN
        SELECT * INTO v_snapshot FROM public.theme_park_race_scoring_snapshots_v2
         WHERE submission_id = v_submission.submission_id AND submitted_at = v_submission.submitted_at
         FOR UPDATE;
        IF NOT FOUND OR v_snapshot.scoring_mode <> 'PARTICIPATION_PRORATED' THEN
            RAISE EXCEPTION 'Participation scoring snapshot is missing for this submitted revision';
        END IF;
        IF v_snapshot.eligible_score > v_snapshot.mission_maximum
           OR v_snapshot.participants_completing > v_snapshot.present_team_size THEN
            RAISE EXCEPTION 'Participation scoring snapshot is invalid';
        END IF;
        v_score := CASE WHEN v_decision = 'APPROVE' THEN v_snapshot.eligible_score ELSE 0 END;
    ELSE
        v_criteria := coalesce(v_station #> '{Scoring,Rubric,Criteria}', '[]'::jsonb);
        IF jsonb_typeof(v_criteria) <> 'array' OR jsonb_array_length(v_criteria) = 0 THEN
            RAISE EXCEPTION 'Facilitator rubric criteria are not configured';
        END IF;
        IF v_decision = 'APPROVE' AND jsonb_typeof(coalesce(p_rubric_scores, 'null'::jsonb)) <> 'object' THEN
            RAISE EXCEPTION 'Facilitator rubric scores are required';
        END IF;
        IF v_decision = 'APPROVE' THEN
            FOR v_criterion IN SELECT value FROM jsonb_array_elements(v_criteria) LOOP
                v_criterion_id := nullif(trim(v_criterion ->> 'ID'), '');
                IF v_criterion_id IS NULL OR v_criterion_id = ANY(v_seen_ids) THEN
                    RAISE EXCEPTION 'Facilitator rubric criteria are invalid';
                END IF;
                v_seen_ids := array_append(v_seen_ids, v_criterion_id);
                IF nullif(trim(v_criterion ->> 'Weight'), '') IS NOT NULL
                   AND (v_criterion ->> 'Weight') !~ '^[0-9]+(\.[0-9]+)?$' THEN
                    RAISE EXCEPTION 'Facilitator rubric weight is invalid';
                END IF;
                v_weight := coalesce(nullif(trim(v_criterion ->> 'Weight'), '')::numeric, 1);
                IF v_weight <= 0 OR nullif(trim(p_rubric_scores ->> v_criterion_id), '') IS NULL
                   OR (p_rubric_scores ->> v_criterion_id) !~ '^[0-9]+(\.[0-9]+)?$' THEN
                    RAISE EXCEPTION 'Each configured rubric criterion requires a numeric 0-to-100 score';
                END IF;
                v_value := (p_rubric_scores ->> v_criterion_id)::numeric;
                IF v_value < 0 OR v_value > 100 THEN
                    RAISE EXCEPTION 'Facilitator rubric scores must be between 0 and 100';
                END IF;
                v_weighted := v_weighted + v_weight * v_value;
                v_total_weight := v_total_weight + v_weight;
            END LOOP;
            IF v_total_weight <= 0 OR (SELECT count(*) FROM jsonb_object_keys(p_rubric_scores)) <> cardinality(v_seen_ids) THEN
                RAISE EXCEPTION 'Facilitator rubric scores do not match the configured criteria';
            END IF;
            v_score := least(v_maximum, round(v_maximum * v_weighted / v_total_weight / 100, 0));
        END IF;
        PERFORM set_config('exos.tpr_scoring_snapshot_write', 'v1', true);
        INSERT INTO public.theme_park_race_scoring_snapshots_v2(
            event_id, team_id, submission_id, submitted_at, scoring_mode, mission_maximum,
            present_participant_ids, completing_participant_ids, present_team_size,
            participants_completing, eligible_score, rubric_criteria, rubric_scores, captured_by
        ) VALUES (
            v_submission.event_id, v_submission.team_id, v_submission.submission_id,
            v_submission.submitted_at, 'FACILITATOR_RUBRIC', v_maximum,
            '[]'::jsonb, '[]'::jsonb, null, 0, v_score, v_criteria,
            CASE WHEN v_decision = 'APPROVE' THEN p_rubric_scores ELSE '{}'::jsonb END,
            trim(p_actor)
        ) ON CONFLICT (submission_id, submitted_at) DO NOTHING
        RETURNING * INTO v_snapshot;
        IF NOT FOUND THEN
            SELECT * INTO v_snapshot FROM public.theme_park_race_scoring_snapshots_v2
             WHERE submission_id = v_submission.submission_id AND submitted_at = v_submission.submitted_at;
        END IF;
    END IF;
    PERFORM set_config('exos.tpr_scored_review', 'v1', true);
    v_result := public.exos_v2_theme_park_race_board_review(
        p_submission_id, p_expected_submitted_at, p_decision,
        v_score, trim(p_actor), coalesce(p_reason, ''), coalesce(p_idempotency_key, '')
    );
    IF NOT coalesce((v_result ->> 'Idempotent')::boolean, false) THEN
        INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
        VALUES (
            v_submission.event_id, trim(p_actor), 'THEME_PARK_RACE_SCORED_REVIEWED',
            'submissions_v2', v_submission.submission_id::text,
            jsonb_build_object('ScoringMode', v_mode, 'Decision', v_decision,
                'Score', v_score, 'EligibleScore', coalesce(v_snapshot.eligible_score, v_score),
                'SubmittedAt', v_submission.submitted_at)
        );
    END IF;
    RETURN v_result || jsonb_build_object(
        'ScoringMode', v_mode,
        'EligibleScore', coalesce(v_snapshot.eligible_score, v_score)
    );
END;
$$;

REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_scoring_snapshot_write_guard()
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_scored_submission_guard()
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_scored_review_guard()
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_participation_preview(text, text)
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_submit_participation(text, text, jsonb, jsonb)
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_review_scored_submission(uuid, timestamptz, public.exos_v2_review_decision, jsonb, text, text, text)
    FROM PUBLIC, anon, authenticated, service_role;

GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_participation_preview(text, text)
    TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_submit_participation(text, text, jsonb, jsonb)
    TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_review_scored_submission(uuid, timestamptz, public.exos_v2_review_decision, jsonb, text, text, text)
    TO service_role;

COMMIT;
