-- Maxis live public projector projection.
--
-- This additive, read-only endpoint is intentionally limited to the human
-- event identifier below.  It neither accepts an EventID parameter nor reads
-- any other event, so publishing this projector cannot make unrelated EXOS
-- events discoverable.  It returns only the projection fields required by a
-- hall display; it has no participant, submission, evidence, session or
-- facilitator columns in its result contract.
BEGIN;

CREATE OR REPLACE FUNCTION public.exos_v2_maxis_live_projector_projection()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_projection jsonb;
BEGIN
    WITH eligible_event AS (
        SELECT
            e.event_id,
            e.event_name,
            CASE upper(coalesce(e.event_payload #>> '{RaceConfiguration,RuntimePhase}', 'READY'))
                WHEN 'ACTIVE' THEN 'LIVE'
                WHEN 'HELD' THEN 'HOLD'
                WHEN 'CLOSED' THEN 'ENDED'
                ELSE 'READY'
            END AS display_state
        FROM public.events_v2 AS e
        WHERE e.event_id = 'MAXIS-20260907-MISSION-AI'
          AND upper(coalesce(e.event_payload #>> '{RaceConfiguration,EngineKind}', '')) = 'THEME_PARK_RACE'
          AND upper(coalesce(e.event_payload #>> '{RaceConfiguration,StrategyMode}', '')) = 'OPEN_MISSION_BOARD'
    ), mission_board AS (
        SELECT a.activity_id
        FROM eligible_event AS e
        JOIN public.programmes_v2 AS p ON p.event_id = e.event_id AND p.is_active
        JOIN public.activities_v2 AS a ON a.programme_id = p.programme_id
        WHERE a.is_active
          AND a.activity_payload ? 'race_station'
          AND coalesce((a.activity_payload #>> '{race_station,Enabled}')::boolean, true)
    ), mission_total AS (
        SELECT count(*)::integer AS total FROM mission_board
    ), team_scores AS (
        SELECT
            t.team_id,
            coalesce(t.country, t.team_name, '') AS country,
            coalesce(t.team_flag, '') AS flag,
            coalesce(sum(s.score_delta) FILTER (WHERE s.scoring_mode = 'TEAM_COMPETITIVE'), 0)::numeric AS score
        FROM eligible_event AS e
        JOIN public.teams_v2 AS t ON t.event_id = e.event_id AND t.is_active
        LEFT JOIN public.score_transactions_v2 AS s
          ON s.event_id = t.event_id AND s.team_id = t.team_id
        GROUP BY t.team_id, t.country, t.team_name, t.team_flag
    ), team_completed AS (
        SELECT r.team_id, count(DISTINCT r.activity_id)::integer AS completed
        FROM public.activity_runtime_v2 AS r
        JOIN mission_board AS m ON m.activity_id = r.activity_id
        JOIN eligible_event AS e ON e.event_id = r.event_id
        WHERE r.is_completed
          AND upper(coalesce(r.state_payload ->> 'MissionState', '')) = 'APPROVED'
        GROUP BY r.team_id
    ), ranked AS (
        SELECT
            s.country,
            s.flag,
            s.score,
            coalesce(c.completed, 0) AS completed,
            EXISTS (SELECT 1 FROM team_scores WHERE score <> 0) AS has_awarded_score,
            row_number() OVER (ORDER BY s.score DESC, s.team_id ASC)::integer AS canonical_rank
        FROM team_scores AS s
        LEFT JOIN team_completed AS c ON c.team_id = s.team_id
    )
    SELECT jsonb_build_object(
        'Event', jsonb_build_object(
            'DisplayName', e.event_name,
            'State', e.display_state,
            'HasAwardedScore', coalesce((SELECT bool_or(r.has_awarded_score) FROM ranked AS r), false)
        ),
        'Teams', coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'Country', r.country,
                    'Flag', r.flag,
                    'Rank', CASE WHEN r.has_awarded_score THEN r.canonical_rank ELSE NULL END,
                    'Score', r.score,
                    'Completed', r.completed,
                    'Total', mt.total
                )
                ORDER BY CASE WHEN r.has_awarded_score THEN r.canonical_rank ELSE NULL END NULLS LAST, r.country
            ) FILTER (WHERE r.country IS NOT NULL),
            '[]'::jsonb
        )
    )
    INTO v_projection
    FROM eligible_event AS e
    CROSS JOIN mission_total AS mt
    LEFT JOIN ranked AS r ON true
    GROUP BY e.event_name, e.display_state, mt.total;

    IF v_projection IS NULL THEN
        RAISE EXCEPTION 'Public projector is unavailable';
    END IF;

    RETURN v_projection;
END;
$$;

-- This is the only public projection endpoint.  It is read-only and has no
-- caller-controlled event selector.  No application role receives direct
-- table access from this migration.
REVOKE ALL ON FUNCTION public.exos_v2_maxis_live_projector_projection()
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.exos_v2_maxis_live_projector_projection()
    TO anon, authenticated;

COMMIT;
