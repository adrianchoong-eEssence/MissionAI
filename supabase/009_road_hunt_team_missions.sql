-- Team-specific mission unlocking for GPS Road Hunts.
-- Install after 008_road_hunt_gps.sql.

create or replace function public.exos_enforce_road_hunt_mission_unlock()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    v_road_hunt_enabled boolean := false;
begin
    if new.participant_id is null then
        return new;
    end if;

    select event.road_hunt_enabled
      into v_road_hunt_enabled
      from public.runtime_events event
     where event.event_id = new.event_id;

    if coalesce(v_road_hunt_enabled, false)
       and not exists (
           select 1
             from public.runtime_geofence_arrivals arrival
             join public.runtime_route_stops stop
               on stop.event_id = arrival.event_id
              and stop.stop_id = arrival.stop_id
             cross join lateral jsonb_array_elements_text(
                 coalesce(stop.mission_ids, '[]'::jsonb)
             ) as mission_id(value)
            where arrival.event_id = new.event_id
              and arrival.team_name = new.team_name
              and trim(mission_id.value) = trim(new.mission_id)
       ) then
        raise exception 'Mission % is not unlocked for team %',
            new.mission_id,
            new.team_name;
    end if;

    return new;
end;
$$;

drop trigger if exists runtime_submission_road_hunt_unlock
    on public.runtime_submissions;

create trigger runtime_submission_road_hunt_unlock
before insert on public.runtime_submissions
for each row
execute function public.exos_enforce_road_hunt_mission_unlock();


create or replace function public.exos_road_hunt_missions(
    p_session_token text
)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
    v_participant public.runtime_participants%rowtype;
    v_event public.runtime_events%rowtype;
    v_available_missions jsonb := '[]'::jsonb;
    v_next_stop jsonb := '{}'::jsonb;
    v_total_missions integer := 0;
    v_unlocked_missions integer := 0;
    v_submitted_missions integer := 0;
begin
    select participant.*
      into v_participant
      from public.runtime_participants participant
     where participant.session_token::text = trim(p_session_token)
     limit 1;

    if not found then
        raise exception 'Invalid participant session';
    end if;

    select event.*
      into v_event
      from public.runtime_events event
     where event.event_id = v_participant.event_id
       and event.active = true;

    if not found then
        raise exception 'Runtime event is not active';
    end if;

    select count(distinct mission_id.value)
      into v_total_missions
      from public.runtime_route_stops stop
      cross join lateral jsonb_array_elements_text(
          coalesce(stop.mission_ids, '[]'::jsonb)
      ) as mission_id(value)
     where stop.event_id = v_participant.event_id
       and stop.active = true;

    with unlocked as (
        select distinct on (trim(mission_id.value))
               stop.stop_id,
               stop.stop_name,
               stop.position as stop_position,
               trim(mission_id.value) as mission_id,
               mission_id.ordinality as mission_position,
               mission.mission_payload,
               submission.submission_id,
               submission.status as submission_status,
               submission.judged,
               submission.score
          from public.runtime_geofence_arrivals arrival
          join public.runtime_route_stops stop
            on stop.event_id = arrival.event_id
           and stop.stop_id = arrival.stop_id
           and stop.active = true
          cross join lateral jsonb_array_elements_text(
              coalesce(stop.mission_ids, '[]'::jsonb)
          ) with ordinality mission_id(value, ordinality)
          join public.runtime_missions mission
            on mission.event_id = stop.event_id
           and mission.mission_id = trim(mission_id.value)
          left join public.runtime_submissions submission
            on submission.event_id = stop.event_id
           and submission.team_name = v_participant.team_name
           and submission.mission_id = trim(mission_id.value)
         where arrival.event_id = v_participant.event_id
           and arrival.team_name = v_participant.team_name
         order by trim(mission_id.value), stop.position, mission_id.ordinality
    ), ordered as (
        select *
          from unlocked
         order by stop_position, mission_position, mission_id
    )
    select coalesce(jsonb_agg(
               jsonb_build_object(
                   'StopID', ordered.stop_id,
                   'StopName', ordered.stop_name,
                   'StopPosition', ordered.stop_position,
                   'MissionPosition', ordered.mission_position,
                   'MissionID', ordered.mission_id,
                   'Mission', ordered.mission_payload,
                   'Submitted', ordered.submission_id is not null,
                   'SubmissionID', coalesce(ordered.submission_id, ''),
                   'SubmissionStatus', coalesce(ordered.submission_status, ''),
                   'Judged', coalesce(ordered.judged, ''),
                   'Score', coalesce(ordered.score, '')
               )
               order by ordered.stop_position,
                        ordered.mission_position,
                        ordered.mission_id
           ), '[]'::jsonb),
           count(*),
           count(*) filter (where ordered.submission_id is not null)
      into v_available_missions,
           v_unlocked_missions,
           v_submitted_missions
      from ordered;

    select coalesce(jsonb_build_object(
               'StopID', stop.stop_id,
               'Position', stop.position,
               'StopName', stop.stop_name,
               'Latitude', stop.latitude,
               'Longitude', stop.longitude,
               'RadiusMeters', stop.radius_meters,
               'Instructions', stop.instructions,
               'MissionIDs', stop.mission_ids
           ), '{}'::jsonb)
      into v_next_stop
      from public.runtime_route_stops stop
     where stop.event_id = v_participant.event_id
       and stop.active = true
       and not exists (
           select 1
             from public.runtime_geofence_arrivals arrival
            where arrival.event_id = stop.event_id
              and arrival.team_name = v_participant.team_name
              and arrival.stop_id = stop.stop_id
       )
     order by stop.position, stop.stop_id
     limit 1;

    return jsonb_build_object(
        'EventID', v_participant.event_id,
        'TeamName', v_participant.team_name,
        'Enabled', v_event.road_hunt_enabled,
        'TotalMissions', coalesce(v_total_missions, 0),
        'UnlockedMissions', coalesce(v_unlocked_missions, 0),
        'SubmittedMissions', coalesce(v_submitted_missions, 0),
        'NextStop', coalesce(v_next_stop, '{}'::jsonb),
        'AvailableMissions', coalesce(v_available_missions, '[]'::jsonb)
    );
end;
$$;

revoke all on function public.exos_enforce_road_hunt_mission_unlock()
    from public;
revoke all on function public.exos_road_hunt_missions(text)
    from public;

-- Participant submissions must use the session-bound V2 RPC. Keep the legacy
-- importer available only to trusted server-side administration.
revoke execute on function public.exos_save_submission(
    text, text, text, text, text, text, text, text,
    text, text, text, text, text, text, text, text
) from anon, authenticated;
grant execute on function public.exos_save_submission(
    text, text, text, text, text, text, text, text,
    text, text, text, text, text, text, text, text
) to service_role;

grant execute on function public.exos_road_hunt_missions(text)
    to anon, authenticated, service_role;

notify pgrst, 'reload schema';
