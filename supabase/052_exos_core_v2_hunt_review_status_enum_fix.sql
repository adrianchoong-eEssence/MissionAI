-- Correct the enum expression in the additive Hunt review RPC installed by 051.
-- 051 remains immutable and exactly matches the installed migration history.
BEGIN;

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
       OR jsonb_typeof(coalesce(p_rubric_scores, '{}'::jsonb)) <> 'object' THEN RAISE EXCEPTION 'Hunt review is invalid'; END IF;
    SELECT * INTO v_submission FROM public.submissions_v2 WHERE submission_id = p_submission_id FOR UPDATE;
    IF NOT FOUND OR v_submission.submission_status <> 'SUBMITTED' OR v_submission.submitted_at <> p_expected_submitted_at THEN RAISE EXCEPTION 'Hunt submission is no longer the current review revision'; END IF;
    SELECT * INTO v_mission FROM public.event_hunt_missions_v2 WHERE event_id = v_submission.event_id AND activity_id = v_submission.activity_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Submission is not a Hunt mission'; END IF;
    SELECT * INTO v_snapshot FROM public.hunt_scoring_snapshots_v2 WHERE submission_id = v_submission.submission_id AND submitted_at = v_submission.submitted_at FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Hunt scoring snapshot is unavailable'; END IF;
    IF v_decision = 'APPROVE' THEN
        IF v_snapshot.scoring_mode = 'TEAM_FULL' THEN v_score := v_snapshot.mission_maximum;
        ELSIF v_snapshot.scoring_mode = 'PARTICIPATION_PRORATED' THEN v_score := v_snapshot.eligible_score;
        ELSE
            FOR v_criterion IN SELECT value FROM jsonb_array_elements(v_snapshot.rubric) LOOP
                v_criterion_id := trim(coalesce(v_criterion ->> 'ID', '')); v_criterion_max := nullif(v_criterion ->> 'Maximum', '')::numeric;
                IF v_criterion_id = '' OR v_criterion_max IS NULL OR v_criterion_max < 0 OR coalesce(p_rubric_scores ->> v_criterion_id, '') !~ '^([0-9]+)(\\.[0-9]+)?$' THEN RAISE EXCEPTION 'Facilitator rubric scores must cover every configured criterion'; END IF;
                v_value := (p_rubric_scores ->> v_criterion_id)::numeric;
                IF v_value < 0 OR v_value > v_criterion_max THEN RAISE EXCEPTION 'Rubric score is outside its configured maximum'; END IF;
                v_score := v_score + v_value;
            END LOOP;
            IF v_score > v_snapshot.mission_maximum THEN RAISE EXCEPTION 'Rubric total exceeds Hunt mission maximum'; END IF;
        END IF;
    END IF;
    UPDATE public.submissions_v2 SET submission_status = CASE WHEN v_decision = 'APPROVE' THEN 'APPROVED'::public.exos_v2_submission_status ELSE 'REJECTED'::public.exos_v2_submission_status END,
        score = CASE WHEN v_decision = 'APPROVE' THEN v_score ELSE 0 END, reviewed_at = now(), reviewed_by = trim(p_actor), updated_at = now()
    WHERE submission_id = v_submission.submission_id;
    INSERT INTO public.reviews_v2(event_id, submission_id, reviewer, decision, score_points, rationale, reviewed_at)
    VALUES (v_submission.event_id, v_submission.submission_id, trim(p_actor), CASE WHEN v_decision = 'APPROVE' THEN 'APPROVE'::public.exos_v2_review_decision ELSE 'REJECT'::public.exos_v2_review_decision END,
        CASE WHEN v_decision = 'APPROVE' THEN v_score ELSE 0 END, coalesce(p_reason, ''), now())
    ON CONFLICT (submission_id, reviewer) DO UPDATE SET decision = excluded.decision, score_points = excluded.score_points, rationale = excluded.rationale, reviewed_at = now();
    IF v_decision = 'APPROVE' THEN
        v_key := coalesce(nullif(trim(p_idempotency_key), ''), 'hunt-review|' || v_submission.submission_id::text || '|' || v_submission.submitted_at::text);
        INSERT INTO public.score_transactions_v2(event_id, team_id, submission_id, scoring_mode, score_delta, reason, idempotency_key, source_reference, created_by)
        VALUES (v_submission.event_id, v_submission.team_id, v_submission.submission_id, 'TEAM_COMPETITIVE', v_score, 'Approved Hunt mission', v_key, jsonb_build_object('HuntMissionID', v_mission.mission_id, 'ScoringMode', v_snapshot.scoring_mode), trim(p_actor))
        ON CONFLICT (event_id, idempotency_key) DO UPDATE SET score_delta = excluded.score_delta, reason = excluded.reason, source_reference = excluded.source_reference, created_by = excluded.created_by;
    END IF;
    UPDATE public.hunt_scoring_snapshots_v2 SET rubric_scores = p_rubric_scores WHERE submission_id = v_submission.submission_id AND submitted_at = v_submission.submitted_at;
    UPDATE public.hunt_team_mission_runtime_v2 SET mission_state = CASE WHEN v_decision = 'APPROVE' THEN 'COMPLETED' ELSE 'RETURNED' END, updated_by = trim(p_actor), updated_at = now() WHERE event_id = v_submission.event_id AND team_id = v_submission.team_id AND mission_id = v_mission.mission_id;
    INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
    VALUES (v_submission.event_id, trim(p_actor), 'HUNT_MISSION_REVIEWED', 'submissions_v2', v_submission.submission_id::text, jsonb_build_object('MissionID', v_mission.mission_id, 'Decision', v_decision, 'Score', v_score));
    RETURN jsonb_build_object('SubmissionID', v_submission.submission_id::text, 'MissionID', v_mission.mission_id, 'Status', CASE WHEN v_decision = 'APPROVE' THEN 'COMPLETED' ELSE 'RETURNED' END, 'Score', v_score);
END; $$;

REVOKE ALL ON FUNCTION public.exos_v2_hunt_review_submission(uuid,timestamptz,text,jsonb,text,text,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.exos_v2_hunt_review_submission(uuid,timestamptz,text,jsonb,text,text,text) TO service_role;
COMMIT;
