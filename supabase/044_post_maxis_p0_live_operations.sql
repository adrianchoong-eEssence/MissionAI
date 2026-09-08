-- Post-Maxis P0-C live operations hardening.
--
-- Additive only.  This contract does not reinterpret a historical score,
-- submission, Captain assignment, Team Formation configuration or Formula
-- R.A.C.E. event.  The new operations apply only when a service facilitator
-- explicitly invokes them for a THEME_PARK_RACE event.
BEGIN;

-- An attendance-enabled Team Formation event may promote only an explicitly
-- PRESENT participant to Captain.  Events that have not opted into 042 retain
-- their exact 036 claim and transfer behaviour.  This trigger is deliberately
-- narrow: it neither changes identity/team membership nor writes attendance.
CREATE OR REPLACE FUNCTION public.exos_v2_team_formation_captain_attendance_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF NEW.is_team_formation_captain
       AND NOT coalesce(OLD.is_team_formation_captain, false)
       AND coalesce((
            SELECT e.event_payload #>> '{Attendance,SchemaVersion}'
              FROM public.events_v2 e
             WHERE e.event_id = NEW.event_id
       ), '') = '1'
       AND NOT EXISTS (
            SELECT 1
              FROM public.participant_attendance_v2 a
             WHERE a.event_id = NEW.event_id
               AND a.participant_id = NEW.participant_id
               AND a.attendance_state = 'PRESENT'
       ) THEN
        RAISE EXCEPTION 'Only a canonical PRESENT participant may claim or receive Team Formation Captain authority';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS exos_v2_team_formation_captain_attendance_guard_trg
    ON public.participants_v2;
CREATE TRIGGER exos_v2_team_formation_captain_attendance_guard_trg
BEFORE UPDATE OF is_team_formation_captain ON public.participants_v2
FOR EACH ROW
EXECUTE FUNCTION public.exos_v2_team_formation_captain_attendance_guard();

-- Create an immutable competitive adjustment.  The caller's idempotency key
-- is namespaced server-side by event/team/operation and is never allowed to
-- rewrite an existing score transaction.  A correction is a second, explicit
-- counter-adjustment; no ledger row is updated or deleted.
CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_adjust_team_score(
    p_event_id text,
    p_team_id text,
    p_amount numeric,
    p_reason text,
    p_actor text,
    p_idempotency_key text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_team public.teams_v2%rowtype;
    v_key text;
    v_source jsonb;
    v_existing public.score_transactions_v2%rowtype;
    v_transaction_id uuid;
    v_idempotent boolean := false;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL
       OR nullif(trim(p_team_id), '') IS NULL
       OR coalesce(p_amount, 0) = 0
       OR abs(p_amount) > 1000
       OR nullif(trim(p_reason), '') IS NULL
       OR nullif(trim(p_actor), '') IS NULL
       OR nullif(trim(p_idempotency_key), '') IS NULL THEN
        RAISE EXCEPTION 'Event, team, non-zero adjustment within 1000 points, reason, facilitator identity, and idempotency key are required';
    END IF;

    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id)
     FOR UPDATE;
    IF NOT FOUND
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,EngineKind}', '')) <> 'THEME_PARK_RACE' THEN
        RAISE EXCEPTION 'Event is not configured for Theme Park Race';
    END IF;
    SELECT * INTO v_team
      FROM public.teams_v2
     WHERE event_id = v_event.event_id
       AND team_id = trim(p_team_id)
       AND is_active
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Team is not active for this event';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|THEME_PARK_RACE_SCORE_ADJUSTMENT|' || v_team.team_id, 89)
    );
    v_key := encode(extensions.digest(
        v_event.event_id || '|THEME_PARK_RACE_SCORE_ADJUSTMENT|'
        || v_team.team_id || '|' || trim(p_idempotency_key), 'sha256'
    ), 'hex');
    v_source := jsonb_build_object(
        'Contract', 'THEME_PARK_RACE_LIVE_OPERATIONS_044',
        'Operation', 'TEAM_SCORE_ADJUSTMENT',
        'RequestIdempotencyKey', trim(p_idempotency_key),
        'Actor', trim(p_actor)
    );

    INSERT INTO public.score_transactions_v2(
        event_id, team_id, submission_id, scoring_mode, score_delta, reason,
        idempotency_key, source_reference, created_by
    ) VALUES (
        v_event.event_id, v_team.team_id, NULL, 'TEAM_COMPETITIVE', p_amount,
        trim(p_reason), v_key, v_source, trim(p_actor)
    ) ON CONFLICT (event_id, idempotency_key) DO NOTHING
    RETURNING score_transaction_id INTO v_transaction_id;

    IF v_transaction_id IS NULL THEN
        SELECT * INTO v_existing
          FROM public.score_transactions_v2
         WHERE event_id = v_event.event_id
           AND idempotency_key = v_key
         FOR UPDATE;
        IF NOT FOUND
           OR v_existing.team_id <> v_team.team_id
           OR v_existing.submission_id IS NOT NULL
           OR v_existing.scoring_mode <> 'TEAM_COMPETITIVE'
           OR v_existing.score_delta IS DISTINCT FROM p_amount
           OR v_existing.reason IS DISTINCT FROM trim(p_reason)
           OR v_existing.created_by IS DISTINCT FROM trim(p_actor)
           OR (v_existing.source_reference ->> 'Contract') IS DISTINCT FROM 'THEME_PARK_RACE_LIVE_OPERATIONS_044'
           OR (v_existing.source_reference ->> 'Operation') IS DISTINCT FROM 'TEAM_SCORE_ADJUSTMENT'
           OR (v_existing.source_reference ->> 'RequestIdempotencyKey') IS DISTINCT FROM trim(p_idempotency_key) THEN
            RAISE EXCEPTION 'Adjustment idempotency key conflicts with an immutable canonical score adjustment';
        END IF;
        v_transaction_id := v_existing.score_transaction_id;
        v_idempotent := true;
    ELSE
        INSERT INTO public.audit_log_v2(
            event_id, actor, action, entity_type, entity_id, after_state
        ) VALUES (
            v_event.event_id, trim(p_actor), 'THEME_PARK_RACE_TEAM_SCORE_ADJUSTED',
            'score_transactions_v2', v_transaction_id::text,
            jsonb_build_object(
                'team_id', v_team.team_id,
                'score_delta', p_amount,
                'reason', trim(p_reason),
                'idempotency_key', trim(p_idempotency_key)
            )
        );
    END IF;

    RETURN jsonb_build_object(
        'EventID', v_event.event_id,
        'TeamID', v_team.team_id,
        'ScoreTransactionID', v_transaction_id::text,
        'ScoreDelta', p_amount,
        'Idempotent', v_idempotent
    );
END;
$$;

-- Read-only service projection of the immutable adjustment ledger.  It is
-- intentionally not a participant-facing table/API surface.
CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_score_adjustments(
    p_event_id text,
    p_limit integer DEFAULT 20
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_rows jsonb;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID is required';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = trim(p_event_id);
    IF NOT FOUND
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,EngineKind}', '')) <> 'THEME_PARK_RACE' THEN
        RAISE EXCEPTION 'Event is not configured for Theme Park Race';
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'ScoreTransactionID', adjustment_row.score_transaction_id::text,
        'TeamID', adjustment_row.team_id,
        'ScoreDelta', adjustment_row.score_delta,
        'Reason', adjustment_row.reason,
        'Actor', adjustment_row.created_by,
        'CreatedAt', adjustment_row.created_at,
        'RequestIdempotencyKey', adjustment_row.source_reference ->> 'RequestIdempotencyKey'
    ) ORDER BY adjustment_row.created_at DESC, adjustment_row.score_transaction_id DESC), '[]'::jsonb)
      INTO v_rows
      FROM (
          SELECT s.*
            FROM public.score_transactions_v2 s
           WHERE s.event_id = v_event.event_id
             AND s.source_reference ->> 'Contract' = 'THEME_PARK_RACE_LIVE_OPERATIONS_044'
             AND s.source_reference ->> 'Operation' = 'TEAM_SCORE_ADJUSTMENT'
           ORDER BY s.created_at DESC, s.score_transaction_id DESC
           LIMIT greatest(least(coalesce(p_limit, 20), 100), 1)
      ) AS adjustment_row;
    RETURN jsonb_build_object('EventID', v_event.event_id, 'Adjustments', v_rows);
END;
$$;

-- Clear the effective Captain and every active Captain session for one team.
-- If the event was ACTIVE, reopening Team Formation Captain selection is an
-- explicit, audited lifecycle consequence.  The facilitator must reactivate
-- the teams after a replacement Captain claims; gameplay is never silently
-- resumed by this operation.
CREATE OR REPLACE FUNCTION public.exos_v2_clear_team_formation_captain(
    p_event_id text,
    p_team_id text,
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
    v_team public.teams_v2%rowtype;
    v_configuration jsonb;
    v_before jsonb;
    v_cleared_count integer := 0;
    v_revoked_sessions integer := 0;
    v_reopened boolean := false;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL
       OR nullif(trim(p_team_id), '') IS NULL
       OR nullif(trim(p_actor), '') IS NULL
       OR nullif(trim(p_reason), '') IS NULL THEN
        RAISE EXCEPTION 'Event, team, facilitator identity, and clear reason are required';
    END IF;
    SELECT * INTO v_event
      FROM public.events_v2
     WHERE event_id = trim(p_event_id)
     FOR UPDATE;
    IF NOT FOUND
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,EngineKind}', '')) <> 'THEME_PARK_RACE' THEN
        RAISE EXCEPTION 'Event is not configured for Theme Park Race';
    END IF;
    v_configuration := coalesce(v_event.event_payload -> 'TeamFormation', '{}'::jsonb);
    IF coalesce(v_configuration ->> 'SchemaVersion', '') <> '1'
       OR upper(coalesce(v_configuration ->> 'Phase', '')) NOT IN ('CAPTAIN_SELECTION', 'ACTIVE') THEN
        RAISE EXCEPTION 'Captain clear is available only during Captain selection or active Team Formation';
    END IF;
    SELECT * INTO v_team
      FROM public.teams_v2
     WHERE event_id = v_event.event_id
       AND team_id = trim(p_team_id)
       AND is_active
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Team is not active for this event';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|TEAM_FORMATION_CAPTAIN|' || v_team.team_id, 47)
    );
    PERFORM set_config('exos.team_formation_write', v_event.event_id, true);
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'ParticipantID', p.participant_id::text,
        'IsCaptain', p.is_team_formation_captain,
        'IsLeader', p.is_leader
    ) ORDER BY p.participant_id), '[]'::jsonb)
      INTO v_before
      FROM public.participants_v2 p
     WHERE p.event_id = v_event.event_id
       AND p.team_id = v_team.team_id
       AND p.is_team_formation_captain
       AND p.merged_into_participant_id IS NULL
       AND NOT p.is_archived;

    UPDATE public.participants_v2
       SET is_team_formation_captain = false,
           is_leader = false,
           team_leader_at = NULL,
           last_seen_at = now()
     WHERE event_id = v_event.event_id
       AND team_id = v_team.team_id
       AND is_team_formation_captain
       AND merged_into_participant_id IS NULL
       AND NOT is_archived;
    GET DIAGNOSTICS v_cleared_count = ROW_COUNT;

    UPDATE public.team_access_sessions_v2
       SET is_active = false,
           recovery_required = true,
           updated_at = now()
     WHERE event_id = v_event.event_id
       AND team_id = v_team.team_id
       AND team_formation_captain_participant_id IS NOT NULL
       AND is_active;
    GET DIAGNOSTICS v_revoked_sessions = ROW_COUNT;

    IF upper(coalesce(v_configuration ->> 'Phase', '')) = 'ACTIVE' THEN
        v_configuration := v_configuration || jsonb_build_object(
            'Phase', 'CAPTAIN_SELECTION',
            'CaptainSelectionOpenedAt', now(),
            'CaptainSelectionOpenedBy', trim(p_actor),
            'CaptainSelectionReopenedReason', trim(p_reason)
        );
        UPDATE public.events_v2
           SET event_payload = jsonb_set(event_payload, '{TeamFormation}', v_configuration, true),
               updated_at = now()
         WHERE event_id = v_event.event_id;
        v_reopened := true;
    END IF;

    IF v_cleared_count > 0 OR v_revoked_sessions > 0 OR v_reopened THEN
        INSERT INTO public.audit_log_v2(
            event_id, actor, action, entity_type, entity_id, before_state, after_state
        ) VALUES (
            v_event.event_id, trim(p_actor), 'TEAM_FORMATION_CAPTAIN_CLEARED',
            'teams_v2', v_team.team_id, v_before,
            jsonb_build_object(
                'team_id', v_team.team_id,
                'reason', trim(p_reason),
                'captains_cleared', v_cleared_count,
                'captain_sessions_revoked', v_revoked_sessions,
                'captain_selection_reopened', v_reopened
            )
        );
    END IF;
    RETURN jsonb_build_object(
        'EventID', v_event.event_id,
        'TeamID', v_team.team_id,
        'Cleared', v_cleared_count > 0 OR v_revoked_sessions > 0,
        'Idempotent', v_cleared_count = 0 AND v_revoked_sessions = 0,
        'CaptainCount', 0,
        'CaptainSessionsRevoked', v_revoked_sessions,
        'CaptainSelectionReopened', v_reopened,
        'TeamFormationPhase', CASE WHEN v_reopened THEN 'CAPTAIN_SELECTION' ELSE v_configuration ->> 'Phase' END
    );
END;
$$;

-- A single read-only source for Mission Control and an API/Kai operator.
-- Every mutating operation named in this projection remains one of the same
-- service-only canonical RPCs; this function adds no second authority path.
CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_operator_status(
    p_event_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.events_v2%rowtype;
    v_teams jsonb;
    v_pending integer;
    v_adjustments jsonb;
BEGIN
    IF nullif(trim(p_event_id), '') IS NULL THEN
        RAISE EXCEPTION 'Event ID is required';
    END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = trim(p_event_id);
    IF NOT FOUND
       OR upper(coalesce(v_event.event_payload #>> '{RaceConfiguration,EngineKind}', '')) <> 'THEME_PARK_RACE' THEN
        RAISE EXCEPTION 'Event is not configured for Theme Park Race';
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'TeamID', t.team_id,
        'CaptainParticipantID', captain.participant_id::text,
        'CaptainName', captain.display_name,
        'CaptainSessionActive', coalesce(captain_session.is_active, false),
        'PresentTeamSize', present_counts.present_count
    ) ORDER BY t.team_id), '[]'::jsonb)
      INTO v_teams
      FROM public.teams_v2 t
      LEFT JOIN LATERAL (
          SELECT p.participant_id, p.display_name
            FROM public.participants_v2 p
           WHERE p.event_id = t.event_id AND p.team_id = t.team_id
             AND p.is_team_formation_captain AND NOT p.is_archived
             AND p.merged_into_participant_id IS NULL
           LIMIT 1
      ) captain ON true
      LEFT JOIN LATERAL (
          SELECT s.is_active
            FROM public.team_access_sessions_v2 s
           WHERE s.event_id = t.event_id AND s.team_id = t.team_id
             AND s.team_formation_captain_participant_id = captain.participant_id
           ORDER BY s.updated_at DESC, s.created_at DESC LIMIT 1
      ) captain_session ON true
      LEFT JOIN LATERAL (
          SELECT count(*)::integer AS present_count
            FROM public.participants_v2 p
            JOIN public.participant_attendance_v2 a
              ON a.event_id = p.event_id AND a.participant_id = p.participant_id
           WHERE p.event_id = t.event_id AND p.team_id = t.team_id
             AND a.attendance_state = 'PRESENT' AND NOT p.is_archived
             AND p.merged_into_participant_id IS NULL
      ) present_counts ON true
     WHERE t.event_id = v_event.event_id AND t.is_active;
    SELECT count(*) INTO v_pending
      FROM public.submissions_v2 s
     WHERE s.event_id = v_event.event_id AND s.submission_status = 'SUBMITTED';
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'ScoreTransactionID', adjustment_row.score_transaction_id::text,
        'TeamID', adjustment_row.team_id, 'ScoreDelta', adjustment_row.score_delta,
        'Reason', adjustment_row.reason, 'Actor', adjustment_row.created_by, 'CreatedAt', adjustment_row.created_at
    ) ORDER BY adjustment_row.created_at DESC, adjustment_row.score_transaction_id DESC), '[]'::jsonb)
      INTO v_adjustments
      FROM (
          SELECT s.* FROM public.score_transactions_v2 s
           WHERE s.event_id = v_event.event_id
             AND s.source_reference ->> 'Contract' = 'THEME_PARK_RACE_LIVE_OPERATIONS_044'
             AND s.source_reference ->> 'Operation' = 'TEAM_SCORE_ADJUSTMENT'
           ORDER BY s.created_at DESC, s.score_transaction_id DESC LIMIT 20
      ) adjustment_row;
    RETURN jsonb_build_object(
        'EventID', v_event.event_id,
        'TeamFormationPhase', coalesce(v_event.event_payload #>> '{TeamFormation,Phase}', ''),
        'RuntimePhase', coalesce(v_event.event_payload #>> '{RaceConfiguration,RuntimePhase}', 'READY'),
        'PendingReviewCount', coalesce(v_pending, 0),
        'Teams', v_teams,
        'RecentScoreAdjustments', v_adjustments,
        'Operations', jsonb_build_array(
            'ATTENDANCE', 'CAPTAIN_STATUS', 'OPEN_CAPTAIN_SELECTION', 'CLEAR_CAPTAIN',
            'TRANSFER_CAPTAIN', 'ACTIVATE_TEAMS', 'RUNTIME_ACTIVE', 'HOLD', 'RESUME',
            'MISSION_OPERATION', 'TEAM_SCORE_ADJUSTMENT', 'PENDING_REVIEW_SUMMARY'
        )
    );
END;
$$;

-- CREATE OR REPLACE retains ACLs.  Pin each intended role matrix explicitly:
-- service-only RPCs only; trigger helpers are not executable APIs.
REVOKE ALL ON FUNCTION public.exos_v2_team_formation_captain_attendance_guard()
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_adjust_team_score(text,text,numeric,text,text,text)
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_score_adjustments(text,integer)
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_clear_team_formation_captain(text,text,text,text)
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_operator_status(text)
    FROM PUBLIC, anon, authenticated, service_role;

GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_adjust_team_score(text,text,numeric,text,text,text)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_score_adjustments(text,integer)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_clear_team_formation_captain(text,text,text,text)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_operator_status(text)
    TO service_role;

COMMIT;
