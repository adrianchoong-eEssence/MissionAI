-- Disposable P0-B scoring certification.
--
-- Run only after 043 is installed on the authorised dedicated project.  It
-- creates one exact CERT-P0B-* fixture, verifies canonical scoring, then
-- removes only that fixture.  It never writes to MAXIS-20260907-MISSION-AI.
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = 'CERT-P0B-20260908')
       OR EXISTS (SELECT 1 FROM public.theme_park_race_scoring_snapshots_v2 WHERE event_id = 'CERT-P0B-20260908') THEN
        RAISE EXCEPTION 'CERT-P0B residue exists; refusing to touch an ambiguous fixture';
    END IF;
END;
$$;

CREATE TEMP TABLE cert_p0b_maxis_sentinel ON COMMIT DROP AS
SELECT
    (SELECT count(*) FROM public.participants_v2 WHERE event_id = 'MAXIS-20260907-MISSION-AI')::integer AS participants,
    (SELECT count(*) FROM public.submissions_v2 WHERE event_id = 'MAXIS-20260907-MISSION-AI')::integer AS submissions,
    (SELECT count(*) FROM public.score_transactions_v2 WHERE event_id = 'MAXIS-20260907-MISSION-AI')::integer AS scores,
    (SELECT coalesce(md5(to_jsonb(e)::text), 'MISSING') FROM public.events_v2 e
      WHERE event_id = 'MAXIS-20260907-MISSION-AI') AS event_digest;

CREATE TEMP TABLE cert_p0b_people(
    label text PRIMARY KEY,
    participant_id uuid NOT NULL,
    team_id text NOT NULL,
    participant_session_id uuid,
    session_token uuid
) ON COMMIT DROP;

CREATE TEMP TABLE cert_p0b_submissions(
    kind text PRIMARY KEY,
    submission_id uuid,
    submitted_at timestamptz
) ON COMMIT DROP;
INSERT INTO cert_p0b_submissions(kind) VALUES ('PPR'), ('RUBRIC');

-- Populate identities before enabling Team Formation config.  The fixture is
-- still fully canonical when scoring begins; no historical Team Formation
-- records or live event rows are modified.
INSERT INTO public.events_v2(
    event_id, event_name, join_code, event_type, programme_type, lifecycle_status, event_payload, published_at
) VALUES (
    'CERT-P0B-20260908', 'CERT P0-B Scoring', 'CERTP0B8', 'STANDARD', 'STANDARD', 'DRAFT', '{}'::jsonb, now()
);
INSERT INTO public.teams_v2(team_id, event_id, team_name, country, team_flag, team_capacity) VALUES
    ('CERT-P0B-20260908-A', 'CERT-P0B-20260908', 'CERT P0-B A', 'A', '🅰️', 3),
    ('CERT-P0B-20260908-B', 'CERT-P0B-20260908', 'CERT P0-B B', 'B', '🅱️', 1);

WITH inserted AS (
    INSERT INTO public.participants_v2(
        event_id, team_id, normalized_name, display_name, country, flag, is_team_formation_captain
    )
    SELECT 'CERT-P0B-20260908', team_id, normalized_name, display_name, country, flag, captain
      FROM (VALUES
        ('CAPTAIN_A', 'CERT-P0B-20260908-A', 'cert p0b captain a', 'CERT P0-B Captain A', 'A', '🅰️', true),
        ('A2',        'CERT-P0B-20260908-A', 'cert p0b a2',        'CERT P0-B A2',        'A', '🅰️', false),
        ('A3',        'CERT-P0B-20260908-A', 'cert p0b a3',        'CERT P0-B A3',        'A', '🅰️', false),
        ('OTHER_B',   'CERT-P0B-20260908-B', 'cert p0b other b',   'CERT P0-B Other B',   'B', '🅱️', false)
      ) AS source(label, team_id, normalized_name, display_name, country, flag, captain)
    RETURNING participant_id, team_id, display_name
)
INSERT INTO cert_p0b_people(label, participant_id, team_id)
SELECT CASE display_name
    WHEN 'CERT P0-B Captain A' THEN 'CAPTAIN_A'
    WHEN 'CERT P0-B A2' THEN 'A2'
    WHEN 'CERT P0-B A3' THEN 'A3'
    ELSE 'OTHER_B'
END, participant_id, team_id
FROM inserted;

INSERT INTO public.participant_sessions_v2(event_id, participant_id, device_id, idempotency_key)
SELECT 'CERT-P0B-20260908', participant_id,
       CASE label WHEN 'CAPTAIN_A' THEN 'CERT-P0B-CAPTAIN-A-DEVICE' ELSE 'CERT-P0B-' || label END,
       'CERT-P0B-PARTICIPANT-' || label
  FROM cert_p0b_people;
UPDATE cert_p0b_people c
   SET participant_session_id = s.participant_session_id,
       session_token = s.session_token
  FROM public.participant_sessions_v2 s
 WHERE s.event_id = 'CERT-P0B-20260908' AND s.participant_id = c.participant_id;

INSERT INTO public.team_access_credentials_v2(event_id, team_id, credential_hash, created_by) VALUES
    ('CERT-P0B-20260908', 'CERT-P0B-20260908-A', repeat('a', 64), 'CERT-P0B'),
    ('CERT-P0B-20260908', 'CERT-P0B-20260908-B', repeat('b', 64), 'CERT-P0B');
INSERT INTO public.team_access_sessions_v2(
    event_id, team_access_credential_id, team_id, device_id, created_by, team_formation_captain_participant_id
)
SELECT c.event_id, c.team_access_credential_id, c.team_id, 'CERT-P0B-CAPTAIN-A-DEVICE', 'CERT-P0B',
       (SELECT participant_id FROM cert_p0b_people WHERE label = 'CAPTAIN_A')
  FROM public.team_access_credentials_v2 c
 WHERE c.event_id = 'CERT-P0B-20260908' AND c.team_id = 'CERT-P0B-20260908-A';

INSERT INTO public.programmes_v2(programme_id, event_id, programme_name, programme_type, module_count, published_at)
VALUES ('CERT-P0B-20260908-PROGRAMME', 'CERT-P0B-20260908', 'CERT P0-B Programme', 'STANDARD', 1, now());
INSERT INTO public.modules_v2(module_id, programme_id, module_name, activity_sequence)
VALUES ('CERT-P0B-20260908-MODULE', 'CERT-P0B-20260908-PROGRAMME', 'CERT P0-B Module', 1);
INSERT INTO public.activities_v2(
    activity_id, module_id, programme_id, activity_name, activity_order, activity_payload
) VALUES
    ('CERT-P0B-20260908-PPR', 'CERT-P0B-20260908-MODULE', 'CERT-P0B-20260908-PROGRAMME', 'CERT Participation', 1,
     '{"race_station":{"Enabled":true,"DisplayName":"CERT Participation","ReviewRequired":true,"Scoring":{"Mode":"PARTICIPATION_PRORATED","Maximum":150,"Rounding":"HALF_UP"}}}'::jsonb),
    ('CERT-P0B-20260908-RUBRIC', 'CERT-P0B-20260908-MODULE', 'CERT-P0B-20260908-PROGRAMME', 'CERT Rubric', 2,
     '{"race_station":{"Enabled":true,"DisplayName":"CERT Rubric","ReviewRequired":true,"Scoring":{"Mode":"FACILITATOR_RUBRIC","Maximum":150,"Rounding":"HALF_UP","Rubric":{"Criteria":[{"ID":"quality","Label":"Quality","Weight":2},{"ID":"teamwork","Label":"Teamwork","Weight":1}]}}}}'::jsonb);

SELECT public.exos_v2_configure_attendance('CERT-P0B-20260908', 'CERT-P0B-FACILITATOR');
SELECT public.exos_v2_set_participant_attendance('CERT-P0B-20260908', participant_id, 'PRESENT', 'CERT-P0B-FACILITATOR', 'present')
  FROM cert_p0b_people WHERE label IN ('CAPTAIN_A', 'A2', 'A3');
SELECT public.exos_v2_set_participant_attendance('CERT-P0B-20260908', participant_id, 'ABSENT', 'CERT-P0B-FACILITATOR', 'other team absent')
  FROM cert_p0b_people WHERE label = 'OTHER_B';

UPDATE public.events_v2
   SET event_payload = event_payload || '{
       "TeamFormation":{"SchemaVersion":1,"Mode":"PREASSIGNED","Phase":"ACTIVE"},
       "RaceConfiguration":{"SchemaVersion":1,"EngineKind":"THEME_PARK_RACE","StrategyMode":"OPEN_MISSION_BOARD","RuntimePhase":"ACTIVE","MissionBoard":{"MaximumConcurrentSelections":1,"MissionOperations":{"CERT-P0B-20260908-PPR":{"OperationalStatus":"AVAILABLE","SecretState":"RELEASED"},"CERT-P0B-20260908-RUBRIC":{"OperationalStatus":"AVAILABLE","SecretState":"RELEASED"}}}}
   }'::jsonb,
       updated_at = now()
 WHERE event_id = 'CERT-P0B-20260908';

INSERT INTO public.activity_runtime_v2(
    event_id, team_id, participant_id, activity_id, session_id, state_payload, activity_started_at
)
SELECT 'CERT-P0B-20260908', c.team_id, c.participant_id, activity_id, c.participant_session_id,
       jsonb_build_object('StrategyMode', 'OPEN_MISSION_BOARD', 'MissionState', 'SELECTED'), now()
  FROM cert_p0b_people c
 CROSS JOIN (VALUES ('CERT-P0B-20260908-PPR'), ('CERT-P0B-20260908-RUBRIC')) activities(activity_id)
 WHERE c.label = 'CAPTAIN_A';

DO $$
DECLARE
    v_preview jsonb;
    v_token text := (SELECT session_token::text FROM cert_p0b_people WHERE label = 'CAPTAIN_A');
    v_a2 text := (SELECT participant_id::text FROM cert_p0b_people WHERE label = 'A2');
    v_other text := (SELECT participant_id::text FROM cert_p0b_people WHERE label = 'OTHER_B');
BEGIN
    SELECT public.exos_v2_theme_park_race_participation_preview(v_token, 'CERT-P0B-20260908-PPR') INTO v_preview;
    IF (v_preview ->> 'PresentTeamSize')::integer <> 3
       OR jsonb_array_length(v_preview -> 'PresentParticipants') <> 3 THEN
        RAISE EXCEPTION 'canonical Captain PRESENT roster is invalid: %', v_preview;
    END IF;

    BEGIN
        PERFORM public.exos_v2_theme_park_race_submit_participation(v_token, 'CERT-P0B-20260908-PPR', '{}'::jsonb,
            jsonb_build_array(v_other));
        RAISE EXCEPTION 'cross-team completion selection was accepted';
    EXCEPTION WHEN OTHERS THEN
        IF position('canonical team' IN SQLERRM) = 0 THEN RAISE; END IF;
    END;
    BEGIN
        PERFORM public.exos_v2_theme_park_race_submit_participation(v_token, 'CERT-P0B-20260908-PPR', '{}'::jsonb,
            jsonb_build_array(v_a2, v_a2));
        RAISE EXCEPTION 'duplicate completion selection was accepted';
    EXCEPTION WHEN OTHERS THEN
        IF position('unique' IN SQLERRM) = 0 THEN RAISE; END IF;
    END;
END;
$$;

-- A same-team ABSENT participant is distinct from a cross-team participant
-- and is also rejected; restore PRESENT before the 2/3 snapshot assertion.
SELECT public.exos_v2_set_participant_attendance(
    'CERT-P0B-20260908', (SELECT participant_id FROM cert_p0b_people WHERE label = 'A3'),
    'ABSENT', 'CERT-P0B-FACILITATOR', 'negative absent-member validation'
);
DO $$
DECLARE v_token text := (SELECT session_token::text FROM cert_p0b_people WHERE label = 'CAPTAIN_A');
BEGIN
    BEGIN
        PERFORM public.exos_v2_theme_park_race_submit_participation(v_token, 'CERT-P0B-20260908-PPR', '{}'::jsonb,
            jsonb_build_array((SELECT participant_id::text FROM cert_p0b_people WHERE label = 'A3')));
        RAISE EXCEPTION 'ABSENT completion selection was accepted';
    EXCEPTION WHEN OTHERS THEN
        IF position('canonical team' IN SQLERRM) = 0 THEN RAISE; END IF;
    END;
END;
$$;
SELECT public.exos_v2_set_participant_attendance(
    'CERT-P0B-20260908', (SELECT participant_id FROM cert_p0b_people WHERE label = 'A3'),
    'PRESENT', 'CERT-P0B-FACILITATOR', 'restore after negative validation'
);

-- A zero PRESENT denominator is never converted into a score. Restore all
-- attendance before the valid 2/3 submission below.
SELECT public.exos_v2_set_participant_attendance('CERT-P0B-20260908', participant_id, 'ABSENT', 'CERT-P0B-FACILITATOR', 'zero-denominator validation')
  FROM cert_p0b_people WHERE label IN ('CAPTAIN_A', 'A2', 'A3');
DO $$
DECLARE v_token text := (SELECT session_token::text FROM cert_p0b_people WHERE label = 'CAPTAIN_A');
BEGIN
    BEGIN
        PERFORM public.exos_v2_theme_park_race_submit_participation(v_token, 'CERT-P0B-20260908-PPR', '{}'::jsonb, '[]'::jsonb);
        RAISE EXCEPTION 'zero PRESENT denominator was accepted';
    EXCEPTION WHEN OTHERS THEN
        IF position('at least one present' IN lower(SQLERRM)) = 0 THEN RAISE; END IF;
    END;
END;
$$;
SELECT public.exos_v2_set_participant_attendance('CERT-P0B-20260908', participant_id, 'PRESENT', 'CERT-P0B-FACILITATOR', 'restore after zero-denominator validation')
  FROM cert_p0b_people WHERE label IN ('CAPTAIN_A', 'A2', 'A3');

UPDATE cert_p0b_submissions
   SET submission_id = (public.exos_v2_theme_park_race_submit_participation(
       (SELECT session_token::text FROM cert_p0b_people WHERE label = 'CAPTAIN_A'),
       'CERT-P0B-20260908-PPR', jsonb_build_object('Remarks', 'CERT P0-B'),
       jsonb_build_array(
           (SELECT participant_id::text FROM cert_p0b_people WHERE label = 'CAPTAIN_A'),
           (SELECT participant_id::text FROM cert_p0b_people WHERE label = 'A2')
       )
   ) ->> 'SubmissionID')::uuid
 WHERE kind = 'PPR';
UPDATE cert_p0b_submissions c
   SET submitted_at = s.submitted_at
  FROM public.submissions_v2 s WHERE s.submission_id = c.submission_id;

DO $$
DECLARE v_snapshot public.theme_park_race_scoring_snapshots_v2%rowtype;
BEGIN
    SELECT * INTO v_snapshot FROM public.theme_park_race_scoring_snapshots_v2
     WHERE submission_id = (SELECT submission_id FROM cert_p0b_submissions WHERE kind = 'PPR');
    IF NOT FOUND OR v_snapshot.scoring_mode <> 'PARTICIPATION_PRORATED'
       OR v_snapshot.present_team_size <> 3 OR v_snapshot.participants_completing <> 2
       OR v_snapshot.eligible_score <> 100
       OR jsonb_array_length(v_snapshot.completing_participant_ids) <> 2 THEN
        RAISE EXCEPTION 'immutable participation snapshot is invalid: %', to_jsonb(v_snapshot);
    END IF;
END;
$$;

-- Attendance changes after submission cannot alter this submitted revision.
SELECT public.exos_v2_set_participant_attendance(
    'CERT-P0B-20260908', (SELECT participant_id FROM cert_p0b_people WHERE label = 'A3'),
    'ABSENT', 'CERT-P0B-FACILITATOR', 'after submitted snapshot'
);

DO $$
BEGIN
    -- A manual 039 score must be blocked for participation just as it is for
    -- rubric scoring; only the P0-B wrapper may carry the single-use permit.
    BEGIN
        PERFORM public.exos_v2_theme_park_race_board_review(
            (SELECT submission_id FROM cert_p0b_submissions WHERE kind = 'PPR'),
            (SELECT submitted_at FROM cert_p0b_submissions WHERE kind = 'PPR'),
            'APPROVE'::public.exos_v2_review_decision, 150, 'CERT-P0B-FACILITATOR', 'bypass', 'CERT-P0B-PPR-BYPASS'
        );
        RAISE EXCEPTION 'direct manual participation score was accepted';
    EXCEPTION WHEN OTHERS THEN
        IF position('canonical facilitator review RPC' IN SQLERRM) = 0 THEN RAISE; END IF;
    END;
END;
$$;

SELECT public.exos_v2_theme_park_race_review_scored_submission(
    submission_id, submitted_at, 'APPROVE'::public.exos_v2_review_decision, '{}'::jsonb,
    'CERT-P0B-FACILITATOR', 'approved from snapshot', 'CERT-P0B-PPR-APPROVE'
) FROM cert_p0b_submissions WHERE kind = 'PPR';
-- Exact repeat is idempotent: it cannot append another competitive score.
SELECT public.exos_v2_theme_park_race_review_scored_submission(
    submission_id, submitted_at, 'APPROVE'::public.exos_v2_review_decision, '{}'::jsonb,
    'CERT-P0B-FACILITATOR', 'approved from snapshot', 'CERT-P0B-PPR-APPROVE-RETRY'
) FROM cert_p0b_submissions WHERE kind = 'PPR';

DO $$
DECLARE v_before integer; v_after integer;
BEGIN
    SELECT count(*) INTO v_before FROM public.score_transactions_v2
     WHERE submission_id = (SELECT submission_id FROM cert_p0b_submissions WHERE kind = 'PPR') AND score_delta > 0;
    BEGIN
        PERFORM public.exos_v2_theme_park_race_review_scored_submission(
            (SELECT submission_id FROM cert_p0b_submissions WHERE kind = 'PPR'),
            (SELECT submitted_at - interval '1 microsecond' FROM cert_p0b_submissions WHERE kind = 'PPR'),
            'APPROVE'::public.exos_v2_review_decision, '{}'::jsonb,
            'CERT-P0B-FACILITATOR', 'stale', 'CERT-P0B-PPR-STALE'
        );
        RAISE EXCEPTION 'stale participation review was accepted';
    EXCEPTION WHEN OTHERS THEN
        IF position('stale' IN lower(SQLERRM)) = 0 THEN RAISE; END IF;
    END;
    SELECT count(*) INTO v_after FROM public.score_transactions_v2
     WHERE submission_id = (SELECT submission_id FROM cert_p0b_submissions WHERE kind = 'PPR') AND score_delta > 0;
    IF v_before <> 1 OR v_after <> 1
       OR (SELECT score FROM public.submissions_v2 WHERE submission_id = (SELECT submission_id FROM cert_p0b_submissions WHERE kind = 'PPR')) <> 100 THEN
        RAISE EXCEPTION 'participation approval is not immutable/idempotent';
    END IF;
END;
$$;

UPDATE cert_p0b_submissions
   SET submission_id = (public.exos_v2_theme_park_race_board_submit(
       (SELECT session_token::text FROM cert_p0b_people WHERE label = 'CAPTAIN_A'),
       'CERT-P0B-20260908-RUBRIC', jsonb_build_object('Remarks', 'CERT rubric')
   ) ->> 'SubmissionID')::uuid
 WHERE kind = 'RUBRIC';
UPDATE cert_p0b_submissions c SET submitted_at = s.submitted_at
  FROM public.submissions_v2 s WHERE s.submission_id = c.submission_id;

DO $$
BEGIN
    -- The older 039 manual-score path must not bypass rubric calculation.
    BEGIN
        PERFORM public.exos_v2_theme_park_race_board_review(
            (SELECT submission_id FROM cert_p0b_submissions WHERE kind = 'RUBRIC'),
            (SELECT submitted_at FROM cert_p0b_submissions WHERE kind = 'RUBRIC'),
            'APPROVE'::public.exos_v2_review_decision, 150, 'CERT-P0B-FACILITATOR', 'bypass', 'CERT-P0B-BYPASS'
        );
        RAISE EXCEPTION 'direct manual rubric score was accepted';
    EXCEPTION WHEN OTHERS THEN
        IF position('canonical facilitator review RPC' IN SQLERRM) = 0 THEN RAISE; END IF;
    END;
END;
$$;

SELECT public.exos_v2_theme_park_race_review_scored_submission(
    submission_id, submitted_at, 'APPROVE'::public.exos_v2_review_decision,
    '{"quality":80,"teamwork":100}'::jsonb,
    'CERT-P0B-FACILITATOR', 'weighted rubric', 'CERT-P0B-RUBRIC-APPROVE'
) FROM cert_p0b_submissions WHERE kind = 'RUBRIC';
SELECT public.exos_v2_theme_park_race_review_scored_submission(
    submission_id, submitted_at, 'APPROVE'::public.exos_v2_review_decision,
    '{"quality":80,"teamwork":100}'::jsonb,
    'CERT-P0B-FACILITATOR', 'weighted rubric', 'CERT-P0B-RUBRIC-RETRY'
) FROM cert_p0b_submissions WHERE kind = 'RUBRIC';

DO $$
BEGIN
    IF (SELECT score FROM public.submissions_v2 WHERE submission_id = (SELECT submission_id FROM cert_p0b_submissions WHERE kind = 'RUBRIC')) <> 130
       OR (SELECT count(*) FROM public.score_transactions_v2 WHERE submission_id = (SELECT submission_id FROM cert_p0b_submissions WHERE kind = 'RUBRIC') AND score_delta > 0) <> 1
       OR (SELECT count(*) FROM public.theme_park_race_scoring_snapshots_v2 WHERE submission_id = (SELECT submission_id FROM cert_p0b_submissions WHERE kind = 'RUBRIC') AND scoring_mode = 'FACILITATOR_RUBRIC') <> 1 THEN
        RAISE EXCEPTION 'rubric score, snapshot, or idempotency is invalid';
    END IF;
END;
$$;

-- Exact cleanup only.  The two guarded data stores are opened only for this
-- transaction and this fixture key; no broad DELETE/TRUNCATE is used.
SELECT set_config('exos.attendance_mutation', 'v1', true);
SELECT set_config('exos.team_formation_write', 'CERT-P0B-20260908', true);
DO $$
DECLARE v_submission_id uuid;
BEGIN
    -- The production guard intentionally consumes every permit.  Delete each
    -- exact fixture snapshot with its own single-use cleanup permit.
    FOR v_submission_id IN
        SELECT submission_id FROM public.theme_park_race_scoring_snapshots_v2
         WHERE event_id = 'CERT-P0B-20260908'
    LOOP
        PERFORM set_config('exos.tpr_scoring_snapshot_write', 'v1', true);
        DELETE FROM public.theme_park_race_scoring_snapshots_v2
         WHERE event_id = 'CERT-P0B-20260908' AND submission_id = v_submission_id;
    END LOOP;
END;
$$;
DELETE FROM public.score_transactions_v2 WHERE event_id = 'CERT-P0B-20260908';
DELETE FROM public.reviews_v2 WHERE event_id = 'CERT-P0B-20260908';
DELETE FROM public.submissions_v2 WHERE event_id = 'CERT-P0B-20260908';
DELETE FROM public.activity_runtime_v2 WHERE event_id = 'CERT-P0B-20260908';
DELETE FROM public.participant_attendance_v2 WHERE event_id = 'CERT-P0B-20260908';
DELETE FROM public.team_access_sessions_v2 WHERE event_id = 'CERT-P0B-20260908';
DELETE FROM public.team_access_credentials_v2 WHERE event_id = 'CERT-P0B-20260908';
DELETE FROM public.participant_sessions_v2 WHERE event_id = 'CERT-P0B-20260908';
DELETE FROM public.participants_v2 WHERE event_id = 'CERT-P0B-20260908';
DELETE FROM public.activities_v2 WHERE programme_id = 'CERT-P0B-20260908-PROGRAMME';
DELETE FROM public.modules_v2 WHERE programme_id = 'CERT-P0B-20260908-PROGRAMME';
DELETE FROM public.programmes_v2 WHERE programme_id = 'CERT-P0B-20260908-PROGRAMME';
DELETE FROM public.teams_v2 WHERE event_id = 'CERT-P0B-20260908';
DELETE FROM public.audit_log_v2 WHERE event_id = 'CERT-P0B-20260908';
DELETE FROM public.events_v2 WHERE event_id = 'CERT-P0B-20260908';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = 'CERT-P0B-20260908')
       OR EXISTS (SELECT 1 FROM public.theme_park_race_scoring_snapshots_v2 WHERE event_id = 'CERT-P0B-20260908')
       OR EXISTS (SELECT 1 FROM public.audit_log_v2 WHERE event_id = 'CERT-P0B-20260908') THEN
        RAISE EXCEPTION 'CERT-P0B cleanup residue remains';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM cert_p0b_maxis_sentinel s
        WHERE s.participants = (SELECT count(*) FROM public.participants_v2 WHERE event_id = 'MAXIS-20260907-MISSION-AI')
          AND s.submissions = (SELECT count(*) FROM public.submissions_v2 WHERE event_id = 'MAXIS-20260907-MISSION-AI')
          AND s.scores = (SELECT count(*) FROM public.score_transactions_v2 WHERE event_id = 'MAXIS-20260907-MISSION-AI')
          AND s.event_digest = (SELECT coalesce(md5(to_jsonb(e)::text), 'MISSING') FROM public.events_v2 e WHERE event_id = 'MAXIS-20260907-MISSION-AI')
    ) THEN
        RAISE EXCEPTION 'historical Maxis sentinel changed';
    END IF;
END;
$$;

COMMIT;
