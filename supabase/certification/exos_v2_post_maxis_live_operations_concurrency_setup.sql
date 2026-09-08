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

CREATE TEMP TABLE cert_p0c_conc_people(label text PRIMARY KEY, participant_id uuid NOT NULL, session_token uuid) ON COMMIT DROP;
INSERT INTO public.events_v2(event_id,event_name,join_code,event_type,programme_type,lifecycle_status,event_payload,published_at)
VALUES ('CERT-P0C-CONC-20260908','CERT P0-C Concurrency','CERTP0CC8','STANDARD','STANDARD','DRAFT','{}'::jsonb,now());
INSERT INTO public.teams_v2(team_id,event_id,team_name,country,team_flag,team_capacity)
VALUES ('CERT-P0C-CONC-20260908-A','CERT-P0C-CONC-20260908','CERT P0-C Concurrent A','A','🅰️',2);
WITH inserted AS (
    INSERT INTO public.participants_v2(event_id,team_id,normalized_name,display_name,is_team_formation_captain,is_leader)
    VALUES
      ('CERT-P0C-CONC-20260908','CERT-P0C-CONC-20260908-A','cert p0c conc a','CERT P0-C Concurrent A',true,true),
      ('CERT-P0C-CONC-20260908','CERT-P0C-CONC-20260908-A','cert p0c conc b','CERT P0-C Concurrent B',false,false)
    RETURNING participant_id, display_name
)
INSERT INTO cert_p0c_conc_people(label,participant_id)
SELECT CASE display_name WHEN 'CERT P0-C Concurrent A' THEN 'A' ELSE 'B' END, participant_id FROM inserted;
INSERT INTO public.participant_sessions_v2(event_id,participant_id,device_id,idempotency_key)
SELECT 'CERT-P0C-CONC-20260908',participant_id,'CERT-P0C-CONC-' || label || '-DEVICE','CERT-P0C-CONC-PARTICIPANT-' || label
FROM cert_p0c_conc_people;
UPDATE cert_p0c_conc_people c SET session_token=s.session_token
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
  "RaceConfiguration":{"SchemaVersion":1,"EngineKind":"THEME_PARK_RACE","StrategyMode":"OPEN_MISSION_BOARD","RuntimePhase":"ACTIVE","MissionBoard":{"MaximumConcurrentSelections":1,"MissionOperations":{}}}
}'::jsonb WHERE event_id='CERT-P0C-CONC-20260908';

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
SELECT
    (SELECT session_token::text FROM cert_p0c_conc_people WHERE label='B') AS captain_b_session_token,
    (SELECT participant_id::text FROM cert_p0c_conc_people WHERE label='A') AS captain_a_participant_id,
    (SELECT participant_id::text FROM cert_p0c_conc_people WHERE label='B') AS captain_b_participant_id;

COMMIT;
