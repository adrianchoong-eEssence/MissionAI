-- P0-C separate-connection concurrency fixture setup.
-- Execute this setup, the documented concurrent canonical RPC calls, then the
-- paired verify/cleanup script.  Every row belongs only to CERT-P0C-CONC-*.
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id = 'CERT-P0C-CONC-20260908') THEN
        RAISE EXCEPTION 'CERT-P0C concurrency residue exists; refusing ambiguous setup';
    END IF;
END;
$$;

CREATE TEMP TABLE cert_p0c_conc_people(
    label text PRIMARY KEY,
    participant_id uuid NOT NULL,
    participant_session_id uuid,
    session_token uuid
) ON COMMIT DROP;
INSERT INTO public.events_v2(event_id,event_name,join_code,event_type,programme_type,lifecycle_status,event_payload,published_at)
VALUES ('CERT-P0C-CONC-20260908','CERT P0-C Concurrency','CERTP0CC8','STANDARD','STANDARD','DRAFT','{}'::jsonb,now());
INSERT INTO public.teams_v2(team_id,event_id,team_name,country,team_flag,team_capacity)
VALUES ('CERT-P0C-CONC-20260908-A','CERT-P0C-CONC-20260908','CERT P0-C Concurrent A','A','🅰️',2);
WITH inserted AS (
    INSERT INTO public.participants_v2(event_id,team_id,normalized_name,display_name,country,flag,is_team_formation_captain,is_leader)
    VALUES
      ('CERT-P0C-CONC-20260908','CERT-P0C-CONC-20260908-A','cert p0c conc a','CERT P0-C Concurrent A','A','🅰️',true,true),
      ('CERT-P0C-CONC-20260908','CERT-P0C-CONC-20260908-A','cert p0c conc b','CERT P0-C Concurrent B','A','🅰️',false,false)
    RETURNING participant_id, display_name
)
INSERT INTO cert_p0c_conc_people(label,participant_id)
SELECT CASE display_name WHEN 'CERT P0-C Concurrent A' THEN 'A' ELSE 'B' END, participant_id FROM inserted;
INSERT INTO public.participant_sessions_v2(event_id,participant_id,device_id,idempotency_key)
SELECT 'CERT-P0C-CONC-20260908',participant_id,'CERT-P0C-CONC-' || label || '-DEVICE','CERT-P0C-CONC-PARTICIPANT-' || label
FROM cert_p0c_conc_people;
UPDATE cert_p0c_conc_people c
   SET participant_session_id=s.participant_session_id,
       session_token=s.session_token
FROM public.participant_sessions_v2 s WHERE s.event_id='CERT-P0C-CONC-20260908' AND s.participant_id=c.participant_id;
INSERT INTO public.team_access_credentials_v2(event_id,team_id,credential_hash,credential_purpose,created_by)
VALUES ('CERT-P0C-CONC-20260908','CERT-P0C-CONC-20260908-A',repeat('d',64),'TEAM_FORMATION_CAPTAIN','CERT-P0C');
INSERT INTO public.team_access_sessions_v2(event_id,team_access_credential_id,team_id,device_id,team_formation_captain_participant_id,created_by)
SELECT event_id,team_access_credential_id,team_id,'CERT-P0C-CONC-A-DEVICE',
       (SELECT participant_id FROM cert_p0c_conc_people WHERE label='A'),'CERT-P0C'
FROM public.team_access_credentials_v2 WHERE event_id='CERT-P0C-CONC-20260908';
SELECT public.exos_v2_configure_attendance('CERT-P0C-CONC-20260908','CERT-P0C-FACILITATOR');
SELECT public.exos_v2_set_participant_attendance('CERT-P0C-CONC-20260908',participant_id,'PRESENT','CERT-P0C-FACILITATOR','concurrency fixture')
FROM cert_p0c_conc_people;
UPDATE public.events_v2 SET event_payload=event_payload || '{
  "TeamFormation":{"SchemaVersion":1,"Mode":"PREASSIGNED","Phase":"ACTIVE"},
  "RaceConfiguration":{"SchemaVersion":1,"EngineKind":"THEME_PARK_RACE","StrategyMode":"OPEN_MISSION_BOARD","RuntimePhase":"ACTIVE","MissionBoard":{"MaximumConcurrentSelections":1,"MissionOperations":{"CERT-P0C-CONC-20260908-MISSION":{"OperationalStatus":"AVAILABLE","SecretState":"RELEASED"}}}}
}'::jsonb WHERE event_id='CERT-P0C-CONC-20260908';
INSERT INTO public.programmes_v2(programme_id,event_id,programme_name,programme_type,module_count,published_at)
VALUES ('CERT-P0C-CONC-20260908-PROGRAMME','CERT-P0C-CONC-20260908','CERT P0-C Concurrent Programme','STANDARD',1,now());
INSERT INTO public.modules_v2(module_id,programme_id,module_name,activity_sequence)
VALUES ('CERT-P0C-CONC-20260908-MODULE','CERT-P0C-CONC-20260908-PROGRAMME','CERT P0-C Concurrent Module',1);
INSERT INTO public.activities_v2(activity_id,module_id,programme_id,activity_name,activity_order,activity_payload)
VALUES (
    'CERT-P0C-CONC-20260908-MISSION','CERT-P0C-CONC-20260908-MODULE',
    'CERT-P0C-CONC-20260908-PROGRAMME','CERT P0-C Concurrent Mission',1,
    '{"race_station":{"Enabled":true,"ReviewRequired":true,"Evidence":{"Text":{"Required":false}}}}'::jsonb
);
INSERT INTO public.activity_runtime_v2(
    event_id,team_id,participant_id,activity_id,session_id,state_payload,activity_started_at
)
SELECT 'CERT-P0C-CONC-20260908','CERT-P0C-CONC-20260908-A',participant_id,
       'CERT-P0C-CONC-20260908-MISSION',participant_session_id,
       jsonb_build_object('StrategyMode','OPEN_MISSION_BOARD','MissionState','SELECTED'),now()
  FROM cert_p0c_conc_people WHERE label='A';

-- Run each pair in separate database connections before verification:
--   1A/1B exact duplicate adjustment:
--       select public.exos_v2_theme_park_race_adjust_team_score('CERT-P0C-CONC-20260908','CERT-P0C-CONC-20260908-A',25,'same request','CERT-P0C-FACILITATOR','CERT-P0C-CONC-DUP');
--   2A/2B different adjustment requests:
--       ... 50,'first distinct',...,'CERT-P0C-CONC-DISTINCT-A'
--       ... -20,'second distinct',...,'CERT-P0C-CONC-DISTINCT-B'
--   3A/3B clear/claim race:
--       select public.exos_v2_clear_team_formation_captain('CERT-P0C-CONC-20260908','CERT-P0C-CONC-20260908-A','CERT-P0C-FACILITATOR','concurrent clear');
--       select public.exos_v2_claim_team_formation_captain('<B session token below>','CERT-P0C-CONC-B-DEVICE');
-- If claim wins before clear, repeat B's normal claim once after both calls;
-- the unique Captain index plus the shared advisory lock must still yield one.
--   4A/4B clear/submission race:
--       select public.exos_v2_clear_team_formation_captain('CERT-P0C-CONC-20260908','CERT-P0C-CONC-20260908-A','CERT-P0C-FACILITATOR','concurrent clear before submit');
--       select public.exos_v2_theme_park_race_board_submit('<A session token below>','CERT-P0C-CONC-20260908-MISSION','{}'::jsonb);
-- The serial outcome may contain one submission only when it committed before
-- the clear; an immediate post-clear retry with A's token must be rejected.
SELECT
    (SELECT session_token::text FROM cert_p0c_conc_people WHERE label='A') AS captain_a_session_token,
    (SELECT session_token::text FROM cert_p0c_conc_people WHERE label='B') AS captain_b_session_token,
    (SELECT participant_id::text FROM cert_p0c_conc_people WHERE label='A') AS captain_a_participant_id,
    (SELECT participant_id::text FROM cert_p0c_conc_people WHERE label='B') AS captain_b_participant_id;

COMMIT;
