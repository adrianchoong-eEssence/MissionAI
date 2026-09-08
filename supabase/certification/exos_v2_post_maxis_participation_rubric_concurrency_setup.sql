-- P0-B separate-connection concurrency fixture setup.
-- Execute this setup, the documented concurrent RPC calls, then the paired
-- verify/cleanup script.  All rows use this exact event only.
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = 'CERT-P0B-CONC-20260908')
       OR EXISTS (SELECT 1 FROM public.theme_park_race_scoring_snapshots_v2 WHERE event_id = 'CERT-P0B-CONC-20260908') THEN
        RAISE EXCEPTION 'CERT-P0B concurrency residue exists; refusing ambiguous setup';
    END IF;
END;
$$;

CREATE TEMP TABLE cert_p0b_conc_people(
    label text PRIMARY KEY, participant_id uuid NOT NULL, team_id text NOT NULL,
    participant_session_id uuid, session_token uuid
) ON COMMIT DROP;

INSERT INTO public.events_v2(event_id, event_name, join_code, event_type, programme_type, lifecycle_status, event_payload, published_at)
VALUES ('CERT-P0B-CONC-20260908', 'CERT P0-B Concurrency', 'CERTP0BC8', 'STANDARD', 'STANDARD', 'DRAFT', '{}'::jsonb, now());
INSERT INTO public.teams_v2(team_id, event_id, team_name, country, team_flag, team_capacity)
VALUES ('CERT-P0B-CONC-20260908-A', 'CERT-P0B-CONC-20260908', 'CERT P0-B Concurrent A', 'A', '🅰️', 3);

WITH inserted AS (
    INSERT INTO public.participants_v2(event_id, team_id, normalized_name, display_name, country, flag, is_team_formation_captain)
    SELECT 'CERT-P0B-CONC-20260908', 'CERT-P0B-CONC-20260908-A', normalized_name, display_name, 'A', '🅰️', captain
      FROM (VALUES
        ('CAPTAIN', 'cert p0b conc captain', 'CERT P0-B Concurrent Captain', true),
        ('A2', 'cert p0b conc a2', 'CERT P0-B Concurrent A2', false),
        ('A3', 'cert p0b conc a3', 'CERT P0-B Concurrent A3', false)
      ) AS source(label, normalized_name, display_name, captain)
    RETURNING participant_id, display_name
)
INSERT INTO cert_p0b_conc_people(label, participant_id, team_id)
SELECT CASE display_name WHEN 'CERT P0-B Concurrent Captain' THEN 'CAPTAIN'
                         WHEN 'CERT P0-B Concurrent A2' THEN 'A2' ELSE 'A3' END,
       participant_id, 'CERT-P0B-CONC-20260908-A'
FROM inserted;

INSERT INTO public.participant_sessions_v2(event_id, participant_id, device_id, idempotency_key)
SELECT 'CERT-P0B-CONC-20260908', participant_id,
       CASE label WHEN 'CAPTAIN' THEN 'CERT-P0B-CONC-CAPTAIN-DEVICE' ELSE 'CERT-P0B-CONC-' || label END,
       'CERT-P0B-CONC-PARTICIPANT-' || label
FROM cert_p0b_conc_people;
UPDATE cert_p0b_conc_people c SET participant_session_id = s.participant_session_id, session_token = s.session_token
  FROM public.participant_sessions_v2 s WHERE s.event_id = 'CERT-P0B-CONC-20260908' AND s.participant_id = c.participant_id;

INSERT INTO public.team_access_credentials_v2(event_id, team_id, credential_hash, created_by)
VALUES ('CERT-P0B-CONC-20260908', 'CERT-P0B-CONC-20260908-A', repeat('c', 64), 'CERT-P0B');
INSERT INTO public.team_access_sessions_v2(event_id, team_access_credential_id, team_id, device_id, created_by, team_formation_captain_participant_id)
SELECT c.event_id, c.team_access_credential_id, c.team_id, 'CERT-P0B-CONC-CAPTAIN-DEVICE', 'CERT-P0B',
       (SELECT participant_id FROM cert_p0b_conc_people WHERE label = 'CAPTAIN')
FROM public.team_access_credentials_v2 c WHERE c.event_id = 'CERT-P0B-CONC-20260908';

INSERT INTO public.programmes_v2(programme_id, event_id, programme_name, programme_type, module_count, published_at)
VALUES ('CERT-P0B-CONC-20260908-PROGRAMME', 'CERT-P0B-CONC-20260908', 'CERT P0-B Concurrency Programme', 'STANDARD', 1, now());
INSERT INTO public.modules_v2(module_id, programme_id, module_name, activity_sequence)
VALUES ('CERT-P0B-CONC-20260908-MODULE', 'CERT-P0B-CONC-20260908-PROGRAMME', 'CERT P0-B Concurrency Module', 1);
INSERT INTO public.activities_v2(activity_id, module_id, programme_id, activity_name, activity_order, activity_payload)
VALUES ('CERT-P0B-CONC-20260908-PPR', 'CERT-P0B-CONC-20260908-MODULE', 'CERT-P0B-CONC-20260908-PROGRAMME', 'CERT P0-B Concurrent Participation', 1,
        '{"race_station":{"Enabled":true,"ReviewRequired":true,"Scoring":{"Mode":"PARTICIPATION_PRORATED","Maximum":101,"Rounding":"HALF_UP"}}}'::jsonb);

SELECT public.exos_v2_configure_attendance('CERT-P0B-CONC-20260908', 'CERT-P0B-FACILITATOR');
SELECT public.exos_v2_set_participant_attendance('CERT-P0B-CONC-20260908', participant_id, 'PRESENT', 'CERT-P0B-FACILITATOR', 'present')
  FROM cert_p0b_conc_people;
UPDATE public.events_v2 SET event_payload = event_payload || '{
  "TeamFormation":{"SchemaVersion":1,"Mode":"PREASSIGNED","Phase":"ACTIVE"},
  "RaceConfiguration":{"SchemaVersion":1,"EngineKind":"THEME_PARK_RACE","StrategyMode":"OPEN_MISSION_BOARD","RuntimePhase":"ACTIVE","MissionBoard":{"MaximumConcurrentSelections":1,"MissionOperations":{"CERT-P0B-CONC-20260908-PPR":{"OperationalStatus":"AVAILABLE","SecretState":"RELEASED"}}}}
}'::jsonb WHERE event_id = 'CERT-P0B-CONC-20260908';
INSERT INTO public.activity_runtime_v2(event_id, team_id, participant_id, activity_id, session_id, state_payload, activity_started_at)
SELECT 'CERT-P0B-CONC-20260908', team_id, participant_id, 'CERT-P0B-CONC-20260908-PPR', participant_session_id,
       jsonb_build_object('StrategyMode', 'OPEN_MISSION_BOARD', 'MissionState', 'SELECTED'), now()
FROM cert_p0b_conc_people WHERE label = 'CAPTAIN';

-- Fixture-only coordination values. Do not report these opaque temporary IDs.
SELECT
    (SELECT session_token::text FROM cert_p0b_conc_people WHERE label = 'CAPTAIN') AS captain_session_token,
    (SELECT participant_id::text FROM cert_p0b_conc_people WHERE label = 'CAPTAIN') AS captain_id,
    (SELECT participant_id::text FROM cert_p0b_conc_people WHERE label = 'A2') AS a2_id,
    (SELECT participant_id::text FROM cert_p0b_conc_people WHERE label = 'A3') AS a3_id;

COMMIT;
