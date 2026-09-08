-- P0-B corrective companion to installed 043.
--
-- 043's permits were transaction-local but not single-use.  This additive
-- correction consumes each permit in the guard trigger that authorises the
-- canonical RPC write, so no later direct board write in that same transaction
-- can inherit it.  It changes no tables, historical events, submissions,
-- scores, identities, or activity configuration.
BEGIN;

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
    PERFORM set_config('exos.tpr_scoring_snapshot_write', '', true);
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

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
        PERFORM set_config('exos.tpr_participation_submission', '', true);
    END IF;
    RETURN NEW;
END;
$$;

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
        PERFORM set_config('exos.tpr_scored_review', '', true);
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_scoring_snapshot_write_guard()
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_scored_submission_guard()
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_scored_review_guard()
    FROM PUBLIC, anon, authenticated, service_role;

COMMIT;
