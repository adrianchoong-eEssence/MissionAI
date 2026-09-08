-- Disposable P0-C live operations certification.
--
-- Run only after 044 is installed on the authorised dedicated project.  This
-- creates one exact fixture, verifies the canonical operations, and removes
-- only that fixture.  It never writes to MAXIS-20260907-MISSION-AI.
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = 'CERT-P0C-20260908') THEN
        RAISE EXCEPTION 'CERT-P0C residue exists; refusing to touch an ambiguous fixture';
    END IF;
END;
$$;

CREATE TEMP TABLE cert_p0c_maxis_sentinel ON COMMIT DROP AS
SELECT
    (SELECT count(*) FROM public.participants_v2 WHERE event_id = 'MAXIS-20260907-MISSION-AI')::integer AS participants,
    (SELECT count(*) FROM public.submissions_v2 WHERE event_id = 'MAXIS-20260907-MISSION-AI')::integer AS submissions,
    (SELECT count(*) FROM public.score_transactions_v2 WHERE event_id = 'MAXIS-20260907-MISSION-AI')::integer AS scores,
    (SELECT coalesce(md5(to_jsonb(e)::text), 'MISSING') FROM public.events_v2 e
      WHERE event_id = 'MAXIS-20260907-MISSION-AI') AS event_digest;

CREATE TEMP TABLE cert_p0c_people(
    label text PRIMARY KEY,
    participant_id uuid NOT NULL,
    participant_session_id uuid,
    session_token uuid
) ON COMMIT DROP;

INSERT INTO public.events_v2(
    event_id, event_name, join_code, event_type, programme_type, lifecycle_status, event_payload, published_at
) VALUES (
    'CERT-P0C-20260908', 'CERT P0-C Live Operations', 'CERTP0C8', 'STANDARD', 'STANDARD', 'DRAFT', '{}'::jsonb, now()
);
INSERT INTO public.teams_v2(team_id, event_id, team_name, country, team_flag, team_capacity)
VALUES ('CERT-P0C-20260908-A', 'CERT-P0C-20260908', 'CERT P0-C A', 'A', '🅰️', 2);

WITH inserted AS (
    INSERT INTO public.participants_v2(
        event_id, team_id, normalized_name, display_name, country, flag, is_team_formation_captain, is_leader
    ) VALUES
        ('CERT-P0C-20260908', 'CERT-P0C-20260908-A', 'cert p0c captain a', 'CERT P0-C Captain A', 'A', '🅰️', true, true),
        ('CERT-P0C-20260908', 'CERT-P0C-20260908-A', 'cert p0c captain b', 'CERT P0-C Captain B', 'A', '🅰️', false, false)
    RETURNING participant_id, display_name
)
INSERT INTO cert_p0c_people(label, participant_id)
SELECT CASE display_name
    WHEN 'CERT P0-C Captain A' THEN 'CAPTAIN_A'
    ELSE 'CAPTAIN_B'
END, participant_id
FROM inserted;

INSERT INTO public.participant_sessions_v2(event_id, participant_id, device_id, idempotency_key)
SELECT 'CERT-P0C-20260908', participant_id,
       CASE label WHEN 'CAPTAIN_A' THEN 'CERT-P0C-A-DEVICE' ELSE 'CERT-P0C-B-DEVICE' END,
       'CERT-P0C-PARTICIPANT-' || label
  FROM cert_p0c_people;
UPDATE cert_p0c_people c
   SET participant_session_id = s.participant_session_id,
       session_token = s.session_token
  FROM public.participant_sessions_v2 s
 WHERE s.event_id = 'CERT-P0C-20260908' AND s.participant_id = c.participant_id;

INSERT INTO public.team_access_credentials_v2(event_id, team_id, credential_hash, credential_purpose, created_by)
VALUES ('CERT-P0C-20260908', 'CERT-P0C-20260908-A', repeat('c', 64), 'TEAM_FORMATION_CAPTAIN', 'CERT-P0C');
INSERT INTO public.team_access_sessions_v2(
    event_id, team_access_credential_id, team_id, device_id, team_formation_captain_participant_id, created_by
)
SELECT c.event_id, c.team_access_credential_id, c.team_id, 'CERT-P0C-A-DEVICE',
       (SELECT participant_id FROM cert_p0c_people WHERE label = 'CAPTAIN_A'), 'CERT-P0C'
  FROM public.team_access_credentials_v2 c
 WHERE c.event_id = 'CERT-P0C-20260908';

INSERT INTO public.programmes_v2(programme_id, event_id, programme_name, programme_type, module_count, published_at)
VALUES ('CERT-P0C-20260908-PROGRAMME', 'CERT-P0C-20260908', 'CERT P0-C Programme', 'STANDARD', 1, now());
INSERT INTO public.modules_v2(module_id, programme_id, module_name, activity_sequence)
VALUES ('CERT-P0C-20260908-MODULE', 'CERT-P0C-20260908-PROGRAMME', 'CERT P0-C Module', 1);
INSERT INTO public.activities_v2(activity_id, module_id, programme_id, activity_name, activity_order, activity_payload)
VALUES (
    'CERT-P0C-20260908-MISSION', 'CERT-P0C-20260908-MODULE', 'CERT-P0C-20260908-PROGRAMME',
    'CERT Captain Authority', 1,
    '{"race_station":{"Enabled":true,"DisplayName":"CERT Captain Authority","ReviewRequired":true,"Evidence":{"Text":{"Required":false}},"Scoring":{"Mode":"TEAM_FULL","Maximum":100}}}'::jsonb
);

SELECT public.exos_v2_configure_attendance('CERT-P0C-20260908', 'CERT-P0C-FACILITATOR');
SELECT public.exos_v2_set_participant_attendance(
    'CERT-P0C-20260908', (SELECT participant_id FROM cert_p0c_people WHERE label = 'CAPTAIN_A'),
    'PRESENT', 'CERT-P0C-FACILITATOR', 'fixture Captain A present'
);
SELECT public.exos_v2_set_participant_attendance(
    'CERT-P0C-20260908', (SELECT participant_id FROM cert_p0c_people WHERE label = 'CAPTAIN_B'),
    'ABSENT', 'CERT-P0C-FACILITATOR', 'fixture Captain B initially absent'
);
UPDATE public.events_v2
   SET event_payload = event_payload || '{
       "TeamFormation":{"SchemaVersion":1,"Mode":"PREASSIGNED","Phase":"ACTIVE"},
       "RaceConfiguration":{"SchemaVersion":1,"EngineKind":"THEME_PARK_RACE","StrategyMode":"OPEN_MISSION_BOARD","RuntimePhase":"ACTIVE","MissionBoard":{"MaximumConcurrentSelections":1,"MissionOperations":{"CERT-P0C-20260908-MISSION":{"OperationalStatus":"AVAILABLE","SecretState":"RELEASED"}}}}
   }'::jsonb,
       updated_at = now()
 WHERE event_id = 'CERT-P0C-20260908';
INSERT INTO public.activity_runtime_v2(
    event_id, team_id, participant_id, activity_id, session_id, state_payload, activity_started_at
) SELECT 'CERT-P0C-20260908', 'CERT-P0C-20260908-A', participant_id,
         'CERT-P0C-20260908-MISSION', participant_session_id,
         jsonb_build_object('StrategyMode', 'OPEN_MISSION_BOARD', 'MissionState', 'SELECTED'), now()
    FROM cert_p0c_people WHERE label = 'CAPTAIN_A';

-- Canonical adjustment ledger: exact retry is stable, a conflicting reuse
-- cannot mutate it, and an explicit counter-adjustment keeps history intact.
SELECT public.exos_v2_theme_park_race_adjust_team_score(
    'CERT-P0C-20260908', 'CERT-P0C-20260908-A', 50, 'AI usage', 'CERT-P0C-FACILITATOR', 'CERT-P0C-BONUS-1'
);
SELECT public.exos_v2_theme_park_race_adjust_team_score(
    'CERT-P0C-20260908', 'CERT-P0C-20260908-A', 50, 'AI usage', 'CERT-P0C-FACILITATOR', 'CERT-P0C-BONUS-1'
);
DO $$
BEGIN
    BEGIN
        PERFORM public.exos_v2_theme_park_race_adjust_team_score(
            'CERT-P0C-20260908', 'CERT-P0C-20260908-A', 150, 'conflicting change', 'CERT-P0C-FACILITATOR', 'CERT-P0C-BONUS-1'
        );
        RAISE EXCEPTION 'conflicting adjustment retry mutated canonical score';
    EXCEPTION WHEN OTHERS THEN
        IF position('conflicts' IN lower(SQLERRM)) = 0 THEN RAISE; END IF;
    END;
END;
$$;
SELECT public.exos_v2_theme_park_race_adjust_team_score(
    'CERT-P0C-20260908', 'CERT-P0C-20260908-A', -20, 'Rule penalty', 'CERT-P0C-FACILITATOR', 'CERT-P0C-PENALTY-1'
);
DO $$
DECLARE v_status jsonb;
BEGIN
    SELECT public.exos_v2_theme_park_race_operator_status('CERT-P0C-20260908') INTO v_status;
    IF (SELECT count(*) FROM public.score_transactions_v2
         WHERE event_id = 'CERT-P0C-20260908'
           AND source_reference ->> 'Operation' = 'TEAM_SCORE_ADJUSTMENT') <> 2
       OR (SELECT sum(score_delta) FROM public.score_transactions_v2
           WHERE event_id = 'CERT-P0C-20260908'
             AND source_reference ->> 'Operation' = 'TEAM_SCORE_ADJUSTMENT') <> 30
       OR jsonb_array_length(v_status -> 'RecentScoreAdjustments') <> 2 THEN
        RAISE EXCEPTION 'canonical immutable adjustment ledger or operator projection is invalid';
    END IF;
END;
$$;

-- Clear from ACTIVE revokes A's Captain bit and active team session, reopens
-- Captain selection, and leaves no residual Captain authority.
SELECT public.exos_v2_clear_team_formation_captain(
    'CERT-P0C-20260908', 'CERT-P0C-20260908-A', 'CERT-P0C-FACILITATOR', 'Captain device replacement'
);
DO $$
DECLARE v_token text := (SELECT session_token::text FROM cert_p0c_people WHERE label = 'CAPTAIN_A');
BEGIN
    BEGIN
        PERFORM public.exos_v2_theme_park_race_board_submit(
            v_token, 'CERT-P0C-20260908-MISSION', '{}'::jsonb
        );
        RAISE EXCEPTION 'cleared Captain retained submission authority';
    EXCEPTION WHEN OTHERS THEN
        IF position('captain' IN lower(SQLERRM)) = 0 THEN RAISE; END IF;
    END;
    IF EXISTS (SELECT 1 FROM public.participants_v2
                WHERE event_id = 'CERT-P0C-20260908' AND team_id = 'CERT-P0C-20260908-A'
                  AND is_team_formation_captain)
       OR EXISTS (SELECT 1 FROM public.team_access_sessions_v2
                  WHERE event_id = 'CERT-P0C-20260908' AND team_id = 'CERT-P0C-20260908-A'
                    AND team_formation_captain_participant_id IS NOT NULL AND is_active)
       OR (SELECT event_payload #>> '{TeamFormation,Phase}' FROM public.events_v2
           WHERE event_id = 'CERT-P0C-20260908') <> 'CAPTAIN_SELECTION' THEN
        RAISE EXCEPTION 'Captain clear did not revoke authority and reopen selection';
    END IF;
END;
$$;

-- B cannot claim while ABSENT.  A canonical attendance correction makes B
-- eligible, then the frozen Captain-claim RPC produces exactly one Captain.
DO $$
DECLARE v_token uuid := (SELECT session_token FROM cert_p0c_people WHERE label = 'CAPTAIN_B');
BEGIN
    BEGIN
        PERFORM public.exos_v2_claim_team_formation_captain(v_token, 'CERT-P0C-B-DEVICE');
        RAISE EXCEPTION 'ABSENT participant claimed Captain authority';
    EXCEPTION WHEN OTHERS THEN
        IF position('present' IN lower(SQLERRM)) = 0 THEN RAISE; END IF;
    END;
END;
$$;
SELECT public.exos_v2_set_participant_attendance(
    'CERT-P0C-20260908', (SELECT participant_id FROM cert_p0c_people WHERE label = 'CAPTAIN_B'),
    'PRESENT', 'CERT-P0C-FACILITATOR', 'replacement Captain present'
);
SELECT public.exos_v2_claim_team_formation_captain(
    (SELECT session_token FROM cert_p0c_people WHERE label = 'CAPTAIN_B'), 'CERT-P0C-B-DEVICE'
);
DO $$
BEGIN
    IF (SELECT count(*) FROM public.participants_v2
         WHERE event_id = 'CERT-P0C-20260908' AND team_id = 'CERT-P0C-20260908-A'
           AND is_team_formation_captain) <> 1
       OR (SELECT participant_id FROM public.participants_v2
           WHERE event_id = 'CERT-P0C-20260908' AND team_id = 'CERT-P0C-20260908-A'
             AND is_team_formation_captain) <> (SELECT participant_id FROM cert_p0c_people WHERE label = 'CAPTAIN_B')
       OR (SELECT count(*) FROM public.team_access_sessions_v2
           WHERE event_id = 'CERT-P0C-20260908' AND team_id = 'CERT-P0C-20260908-A'
             AND is_active AND team_formation_captain_participant_id IS NOT NULL) <> 1 THEN
        RAISE EXCEPTION 'replacement Captain claim created invalid authority';
    END IF;
END;
$$;
SELECT public.exos_v2_activate_team_formation('CERT-P0C-20260908', 'CERT-P0C-FACILITATOR');

-- Exact cleanup only.  No broad table-clear operation is used.
SELECT set_config('exos.attendance_mutation', 'v1', true);
SELECT set_config('exos.team_formation_write', 'CERT-P0C-20260908', true);
DELETE FROM public.score_transactions_v2 WHERE event_id = 'CERT-P0C-20260908';
DELETE FROM public.reviews_v2 WHERE event_id = 'CERT-P0C-20260908';
DELETE FROM public.submissions_v2 WHERE event_id = 'CERT-P0C-20260908';
DELETE FROM public.activity_runtime_v2 WHERE event_id = 'CERT-P0C-20260908';
DELETE FROM public.participant_attendance_v2 WHERE event_id = 'CERT-P0C-20260908';
DELETE FROM public.team_access_sessions_v2 WHERE event_id = 'CERT-P0C-20260908';
DELETE FROM public.team_access_credentials_v2 WHERE event_id = 'CERT-P0C-20260908';
DELETE FROM public.participant_sessions_v2 WHERE event_id = 'CERT-P0C-20260908';
DELETE FROM public.participants_v2 WHERE event_id = 'CERT-P0C-20260908';
DELETE FROM public.activities_v2 WHERE programme_id = 'CERT-P0C-20260908-PROGRAMME';
DELETE FROM public.modules_v2 WHERE programme_id = 'CERT-P0C-20260908-PROGRAMME';
DELETE FROM public.programmes_v2 WHERE programme_id = 'CERT-P0C-20260908-PROGRAMME';
DELETE FROM public.teams_v2 WHERE event_id = 'CERT-P0C-20260908';
DELETE FROM public.audit_log_v2 WHERE event_id = 'CERT-P0C-20260908';
DELETE FROM public.events_v2 WHERE event_id = 'CERT-P0C-20260908';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = 'CERT-P0C-20260908')
       OR EXISTS (SELECT 1 FROM public.audit_log_v2 WHERE event_id = 'CERT-P0C-20260908')
       OR EXISTS (SELECT 1 FROM public.score_transactions_v2 WHERE event_id = 'CERT-P0C-20260908') THEN
        RAISE EXCEPTION 'CERT-P0C cleanup residue remains';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM cert_p0c_maxis_sentinel s
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
