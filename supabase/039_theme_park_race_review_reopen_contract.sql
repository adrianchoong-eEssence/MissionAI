-- Theme Park Race OPEN_MISSION_BOARD atomic facilitator review/reopen contract.
-- Additive only; depends on installed 020/025, 036, 037, 037a, and 038.
-- It creates no tables and leaves non-Theme-Park and CONFIGURED_TEAM_ROUTE
-- review behaviour unchanged.
BEGIN;

CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_board_review(
    p_submission_id uuid,
    p_expected_submitted_at timestamptz,
    p_decision public.exos_v2_review_decision,
    p_score numeric,
    p_actor text,
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
    v_runtime public.activity_runtime_v2%rowtype;
    v_configuration jsonb;
    v_decision text := upper(trim(p_decision::text));
    v_score numeric := coalesce(p_score, 0);
    v_key text;
    v_source jsonb;
BEGIN
    IF p_submission_id IS NULL OR p_expected_submitted_at IS NULL OR nullif(trim(p_actor), '') IS NULL THEN
        RAISE EXCEPTION 'Submission ID, submitted-at revision, and facilitator identity are required';
    END IF;
    IF v_decision NOT IN ('APPROVE', 'REJECT') OR v_score < 0 THEN
        RAISE EXCEPTION 'Theme Park Race board review decision or score is invalid';
    END IF;
    SELECT * INTO v_submission FROM public.submissions_v2 WHERE submission_id = p_submission_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Submission not found'; END IF;
    SELECT * INTO v_event FROM public.events_v2 WHERE event_id = v_submission.event_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Theme Park Race event is unavailable'; END IF;
    v_configuration := coalesce(v_event.event_payload->'RaceConfiguration', '{}'::jsonb);
    IF upper(coalesce(v_configuration->>'EngineKind', '')) <> 'THEME_PARK_RACE'
       OR upper(coalesce(v_configuration->>'StrategyMode', '')) <> 'OPEN_MISSION_BOARD' THEN
        RAISE EXCEPTION 'Submission is not an OPEN_MISSION_BOARD submission';
    END IF;
    IF v_submission.submitted_at IS DISTINCT FROM p_expected_submitted_at THEN
        RAISE EXCEPTION 'Submission revision is stale';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(v_event.event_id || '|OPEN_MISSION_BOARD|' || v_submission.team_id, 61));
    SELECT * INTO v_runtime FROM public.activity_runtime_v2
     WHERE runtime_id = v_submission.runtime_id AND event_id = v_submission.event_id
       AND team_id = v_submission.team_id AND activity_id = v_submission.activity_id FOR UPDATE;
    IF NOT FOUND OR coalesce(v_runtime.state_payload->>'StrategyMode', '') <> 'OPEN_MISSION_BOARD' THEN
        RAISE EXCEPTION 'Submission has no canonical OPEN_MISSION_BOARD runtime';
    END IF;
    IF v_submission.submission_status = 'APPROVED' AND v_decision = 'APPROVE' THEN
        RETURN jsonb_build_object('SubmissionID', v_submission.submission_id::text, 'Status', 'APPROVED', 'Score', v_submission.score, 'Idempotent', true);
    END IF;
    IF v_submission.submission_status = 'REJECTED' AND v_decision = 'REJECT' THEN
        RETURN jsonb_build_object('SubmissionID', v_submission.submission_id::text, 'Status', 'REJECTED', 'Score', 0, 'Idempotent', true);
    END IF;
    IF v_submission.submission_status <> 'SUBMITTED'
       OR coalesce(v_runtime.state_payload->>'MissionState', '') <> 'SUBMITTED' THEN
        RAISE EXCEPTION 'Only the current submitted board revision may be reviewed';
    END IF;
    -- Ledger identity is server-derived from the immutable reviewed revision.
    -- Caller request keys are audit metadata only and can never collide across
    -- submissions or rewrite a competitive transaction.
    v_key := 'theme-park-race-board-review-039|' || v_submission.submission_id::text || '|' || v_submission.submitted_at::text;
    v_source := jsonb_build_object('Contract', 'THEME_PARK_RACE_BOARD_REVIEW_039', 'ActivityID', v_submission.activity_id,
        'SubmissionID', v_submission.submission_id::text, 'RevisionSubmittedAt', v_submission.submitted_at,
        'RequestIdempotencyKey', nullif(trim(p_idempotency_key), ''));
    INSERT INTO public.reviews_v2(event_id, submission_id, reviewer, decision, score_points, rationale, reviewed_at)
    VALUES(v_submission.event_id, v_submission.submission_id, trim(p_actor), v_decision::public.exos_v2_review_decision, v_score, coalesce(p_reason, ''), now())
    ON CONFLICT(submission_id, reviewer) DO UPDATE SET decision = excluded.decision, score_points = excluded.score_points,
        rationale = excluded.rationale, reviewed_at = now();
    IF v_decision = 'REJECT' THEN
        UPDATE public.submissions_v2 SET submission_status = 'REJECTED', score = 0, reviewed_at = now(), reviewed_by = trim(p_actor), updated_at = now()
         WHERE submission_id = v_submission.submission_id RETURNING * INTO v_submission;
        UPDATE public.activity_runtime_v2 SET state_payload = v_runtime.state_payload || jsonb_build_object('MissionState', 'REJECTED', 'ReviewedAt', now(), 'ReviewedBy', trim(p_actor)),
            is_completed = false, completion_ratio = 0, activity_ended_at = null, updated_at = now() WHERE runtime_id = v_runtime.runtime_id;
        INSERT INTO public.score_transactions_v2(event_id, team_id, submission_id, scoring_mode, score_delta, reason, idempotency_key, source_reference, created_by)
        VALUES(v_submission.event_id, v_submission.team_id, v_submission.submission_id, 'TEAM_COMPETITIVE', 0, 'Theme Park Race board submission rejected', v_key,
               v_source || jsonb_build_object('Decision', 'REJECT'), trim(p_actor))
        ON CONFLICT(event_id, idempotency_key) DO NOTHING;
    ELSE
        UPDATE public.submissions_v2 SET submission_status = 'APPROVED', score = v_score, reviewed_at = now(), reviewed_by = trim(p_actor), updated_at = now()
         WHERE submission_id = v_submission.submission_id RETURNING * INTO v_submission;
        UPDATE public.activity_runtime_v2 SET state_payload = v_runtime.state_payload || jsonb_build_object('MissionState', 'APPROVED', 'ReviewedAt', now(), 'ReviewedBy', trim(p_actor)),
            is_completed = true, completion_ratio = 100, updated_at = now() WHERE runtime_id = v_runtime.runtime_id;
        INSERT INTO public.score_transactions_v2(event_id, team_id, submission_id, scoring_mode, score_delta, reason, idempotency_key, source_reference, created_by)
        VALUES(v_submission.event_id, v_submission.team_id, v_submission.submission_id, 'TEAM_COMPETITIVE', v_score, 'Theme Park Race board submission approved', v_key,
               v_source || jsonb_build_object('Decision', 'APPROVE'), trim(p_actor))
        ON CONFLICT(event_id, idempotency_key) DO NOTHING;
    END IF;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES(v_submission.event_id, trim(p_actor), 'THEME_PARK_RACE_BOARD_REVIEWED', 'submissions_v2', v_submission.submission_id::text,
           jsonb_build_object('Decision', v_decision, 'Score', v_submission.score, 'ActivityID', v_submission.activity_id, 'SubmittedAt', v_submission.submitted_at));
    RETURN jsonb_build_object('SubmissionID', v_submission.submission_id::text, 'EventID', v_submission.event_id, 'TeamID', v_submission.team_id,
        'ActivityID', v_submission.activity_id, 'Status', v_submission.submission_status::text, 'Score', v_submission.score, 'Idempotent', false);
END;
$$;

REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_board_review(uuid,timestamptz,public.exos_v2_review_decision,numeric,text,text,text) FROM anon, authenticated, service_role, PUBLIC;
GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_board_review(uuid,timestamptz,public.exos_v2_review_decision,numeric,text,text,text) TO service_role;
COMMIT;
