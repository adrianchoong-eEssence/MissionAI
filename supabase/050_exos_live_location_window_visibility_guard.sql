-- Corrective guard for Live Location V1 operator visibility.
-- Retained historical points must never present as current outside the bounded
-- tracking window. This replaces only the newly introduced read RPC.
BEGIN;

CREATE OR REPLACE FUNCTION public.exos_v2_live_location_operator_map(p_event_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_config public.event_location_configurations_v2%rowtype;
BEGIN
    SELECT * INTO v_config FROM public.event_location_configurations_v2 WHERE event_id = trim(p_event_id);
    IF NOT FOUND THEN RAISE EXCEPTION 'Live location is not configured for this event'; END IF;
    RETURN jsonb_build_object('EventID', v_config.event_id, 'Enabled', v_config.enabled,
        'CadenceSeconds', v_config.cadence_seconds, 'StaleAfterSeconds', v_config.stale_after_seconds,
        'SeparationThresholdMeters', v_config.separation_threshold_meters,
        'Participants', coalesce((
            WITH last_locations AS (
                SELECT DISTINCT ON (u.participant_id) u.* FROM public.participant_location_updates_v2 u
                 WHERE u.event_id = v_config.event_id ORDER BY u.participant_id, u.received_at DESC
            ) SELECT jsonb_agg(jsonb_build_object(
                'ParticipantID', p.participant_id::text, 'ParticipantName', p.display_name, 'TeamID', p.team_id,
                'Latitude', l.latitude, 'Longitude', l.longitude, 'AccuracyMeters', l.accuracy_meters,
                'LastUpdate', l.received_at, 'Status', CASE
                    WHEN NOT v_config.enabled OR now() < v_config.tracking_starts_at OR now() >= v_config.tracking_ends_at THEN 'UNAVAILABLE'
                    WHEN coalesce(c.consent_state, '') <> 'ENABLED' OR l.location_update_id IS NULL THEN 'UNAVAILABLE'
                    WHEN l.received_at >= now() - make_interval(secs => v_config.stale_after_seconds) THEN 'CURRENT'
                    ELSE 'STALE'
                END
            ) ORDER BY p.team_id, p.display_name)
              FROM public.participants_v2 p
              LEFT JOIN public.participant_location_consents_v2 c ON c.event_id = p.event_id AND c.participant_id = p.participant_id
              LEFT JOIN last_locations l ON l.participant_id = p.participant_id
             WHERE p.event_id = v_config.event_id AND NOT p.is_archived AND p.merged_into_participant_id IS NULL
        ), '[]'::jsonb));
END; $$;

REVOKE ALL ON FUNCTION public.exos_v2_live_location_operator_map(text)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.exos_v2_live_location_operator_map(text) TO service_role;

COMMIT;
