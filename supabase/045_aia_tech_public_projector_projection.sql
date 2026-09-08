-- AIA Tech's additive, fixed-event read-only projector projection.
-- PREPARED ONLY: owner approval and the normal migration process are required
-- before installation.  It accepts no EventID and cannot disclose another event.
BEGIN;

CREATE OR REPLACE FUNCTION public.exos_v2_aia_tech_projector_projection()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_projection jsonb;
BEGIN
  WITH eligible_event AS (
    SELECT e.event_id,e.event_name,CASE upper(coalesce(e.event_payload #>> '{RaceConfiguration,RuntimePhase}','READY'))
      WHEN 'ACTIVE' THEN 'LIVE' WHEN 'HELD' THEN 'HOLD' WHEN 'CLOSED' THEN 'ENDED' ELSE 'READY' END state
    FROM public.events_v2 e WHERE e.event_id='AIA-TECH-20261023-UAT'
      AND upper(coalesce(e.event_payload #>> '{RaceConfiguration,EngineKind}',''))='THEME_PARK_RACE'
      AND upper(coalesce(e.event_payload #>> '{RaceConfiguration,StrategyMode}',''))='OPEN_MISSION_BOARD'
  ), missions AS (
    SELECT a.activity_id FROM eligible_event e JOIN public.programmes_v2 p ON p.event_id=e.event_id AND p.is_active
    JOIN public.activities_v2 a ON a.programme_id=p.programme_id WHERE a.is_active AND a.activity_payload ? 'race_station'
  ), scores AS (
    SELECT t.team_id,coalesce(t.team_name,'Team') team_name,coalesce(sum(s.score_delta) FILTER (WHERE s.scoring_mode='TEAM_COMPETITIVE'),0)::numeric score
    FROM eligible_event e JOIN public.teams_v2 t ON t.event_id=e.event_id AND t.is_active
    LEFT JOIN public.score_transactions_v2 s ON s.event_id=t.event_id AND s.team_id=t.team_id GROUP BY t.team_id,t.team_name
  ), completed AS (
    SELECT r.team_id,count(DISTINCT r.activity_id)::int completed FROM public.activity_runtime_v2 r JOIN missions m ON m.activity_id=r.activity_id
    JOIN eligible_event e ON e.event_id=r.event_id WHERE r.is_completed AND upper(coalesce(r.state_payload->>'MissionState',''))='APPROVED' GROUP BY r.team_id
  ), ranked AS (
    SELECT s.*,coalesce(c.completed,0) completed,exists(select 1 from scores where score<>0) has_score,
      row_number() over(order by s.score desc,s.team_id)::int rank FROM scores s LEFT JOIN completed c ON c.team_id=s.team_id
  ) SELECT jsonb_build_object('Event',jsonb_build_object('DisplayName',e.event_name,'State',e.state,'HasAwardedScore',coalesce((select bool_or(has_score) from ranked),false)),
    'Teams',coalesce((select jsonb_agg(jsonb_build_object('Country',team_name,'Flag','','Rank',case when has_score then rank else null end,'Score',score,'Completed',completed,'Total',(select count(*) from missions)) order by rank) from ranked),'[]'::jsonb)) INTO v_projection FROM eligible_event e;
  IF v_projection IS NULL THEN RAISE EXCEPTION 'Public projector is unavailable'; END IF;
  RETURN v_projection;
END; $$;

REVOKE ALL ON FUNCTION public.exos_v2_aia_tech_projector_projection() FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_aia_tech_projector_projection() TO anon, authenticated;
COMMIT;
