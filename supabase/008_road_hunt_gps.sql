create schema if not exists extensions;
create extension if not exists postgis with schema extensions;

alter table public.runtime_events
    add column if not exists road_hunt_enabled boolean not null default false,
    add column if not exists location_interval_seconds integer not null default 20;

create table if not exists public.runtime_route_stops (
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    stop_id text not null,
    position integer not null default 0,
    stop_name text not null,
    latitude double precision not null check (latitude between -90 and 90),
    longitude double precision not null check (longitude between -180 and 180),
    radius_meters integer not null default 150 check (radius_meters between 20 and 5000),
    mission_ids jsonb not null default '[]'::jsonb,
    instructions text not null default '',
    active boolean not null default true,
    location extensions.geography(Point, 4326) generated always as (
        extensions.st_setsrid(
            extensions.st_makepoint(longitude, latitude),
            4326
        )::extensions.geography
    ) stored,
    updated_at timestamptz not null default now(),
    primary key (event_id, stop_id)
);

create index if not exists runtime_route_stops_event_idx
    on public.runtime_route_stops(event_id, position);
create index if not exists runtime_route_stops_location_idx
    on public.runtime_route_stops using gist(location);

create table if not exists public.runtime_team_trackers (
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    team_name text not null,
    participant_id uuid not null references public.runtime_participants(participant_id) on delete cascade,
    claimed_at timestamptz not null default now(),
    last_seen_at timestamptz,
    primary key (event_id, team_name)
);

create table if not exists public.runtime_team_locations (
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    team_name text not null,
    participant_id uuid not null references public.runtime_participants(participant_id) on delete cascade,
    latitude double precision not null check (latitude between -90 and 90),
    longitude double precision not null check (longitude between -180 and 180),
    accuracy_meters double precision,
    heading_degrees double precision,
    speed_mps double precision,
    captured_at timestamptz not null,
    updated_at timestamptz not null default now(),
    location extensions.geography(Point, 4326) generated always as (
        extensions.st_setsrid(
            extensions.st_makepoint(longitude, latitude),
            4326
        )::extensions.geography
    ) stored,
    primary key (event_id, team_name)
);

create index if not exists runtime_team_locations_location_idx
    on public.runtime_team_locations using gist(location);

create table if not exists public.runtime_location_history (
    location_id bigint generated always as identity primary key,
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    team_name text not null,
    participant_id uuid not null references public.runtime_participants(participant_id) on delete cascade,
    latitude double precision not null check (latitude between -90 and 90),
    longitude double precision not null check (longitude between -180 and 180),
    accuracy_meters double precision,
    heading_degrees double precision,
    speed_mps double precision,
    captured_at timestamptz not null,
    received_at timestamptz not null default now(),
    location extensions.geography(Point, 4326) generated always as (
        extensions.st_setsrid(
            extensions.st_makepoint(longitude, latitude),
            4326
        )::extensions.geography
    ) stored
);

create index if not exists runtime_location_history_event_team_idx
    on public.runtime_location_history(event_id, team_name, captured_at desc);
create index if not exists runtime_location_history_location_idx
    on public.runtime_location_history using gist(location);

create table if not exists public.runtime_geofence_arrivals (
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    team_name text not null,
    stop_id text not null,
    participant_id uuid references public.runtime_participants(participant_id) on delete set null,
    distance_meters double precision not null default 0,
    arrival_source text not null default 'GPS' check (arrival_source in ('GPS', 'MANUAL')),
    arrived_at timestamptz not null default now(),
    primary key (event_id, team_name, stop_id),
    foreign key (event_id, stop_id)
        references public.runtime_route_stops(event_id, stop_id)
        on delete cascade
);

create index if not exists runtime_geofence_arrivals_event_idx
    on public.runtime_geofence_arrivals(event_id, arrived_at);

alter table public.runtime_route_stops enable row level security;
alter table public.runtime_team_trackers enable row level security;
alter table public.runtime_team_locations enable row level security;
alter table public.runtime_location_history enable row level security;
alter table public.runtime_geofence_arrivals enable row level security;

create or replace function public.exos_configure_road_hunt(
    p_event_id text,
    p_enabled boolean default true,
    p_location_interval_seconds integer default 20,
    p_reset boolean default false
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
    update public.runtime_events
       set road_hunt_enabled = coalesce(p_enabled, true),
           location_interval_seconds = greatest(
               10,
               least(coalesce(p_location_interval_seconds, 20), 120)
           ),
           updated_at = now()
     where event_id = trim(p_event_id);

    if not found then
        raise exception 'Runtime event % was not found', trim(p_event_id);
    end if;

    if p_reset then
        delete from public.runtime_geofence_arrivals
         where event_id = trim(p_event_id);
        delete from public.runtime_location_history
         where event_id = trim(p_event_id);
        delete from public.runtime_team_locations
         where event_id = trim(p_event_id);
        delete from public.runtime_team_trackers
         where event_id = trim(p_event_id);
    end if;

    return jsonb_build_object(
        'EventID', trim(p_event_id),
        'Enabled', coalesce(p_enabled, true),
        'LocationIntervalSeconds', greatest(
            10,
            least(coalesce(p_location_interval_seconds, 20), 120)
        ),
        'Reset', coalesce(p_reset, false)
    );
end;
$$;

create or replace function public.exos_publish_route(
    p_event_id text,
    p_stops jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
    v_stop_count integer;
begin
    if not exists (
        select 1
          from public.runtime_events
         where event_id = trim(p_event_id)
    ) then
        raise exception 'Runtime event % was not found', trim(p_event_id);
    end if;

    delete from public.runtime_route_stops
     where event_id = trim(p_event_id);

    insert into public.runtime_route_stops (
        event_id,
        stop_id,
        position,
        stop_name,
        latitude,
        longitude,
        radius_meters,
        mission_ids,
        instructions,
        active,
        updated_at
    )
    select trim(p_event_id),
           upper(trim(stop.stop_id)),
           coalesce(stop.position, 0),
           trim(stop.stop_name),
           stop.latitude,
           stop.longitude,
           greatest(20, least(coalesce(stop.radius_meters, 150), 5000)),
           coalesce(stop.mission_ids, '[]'::jsonb),
           coalesce(stop.instructions, ''),
           coalesce(stop.active, true),
           now()
      from jsonb_to_recordset(coalesce(p_stops, '[]'::jsonb)) as stop(
          stop_id text,
          position integer,
          stop_name text,
          latitude double precision,
          longitude double precision,
          radius_meters integer,
          mission_ids jsonb,
          instructions text,
          active boolean
      )
     where nullif(trim(stop.stop_id), '') is not null
       and nullif(trim(stop.stop_name), '') is not null
       and stop.latitude between -90 and 90
       and stop.longitude between -180 and 180;

    get diagnostics v_stop_count = row_count;

    return jsonb_build_object(
        'EventID', trim(p_event_id),
        'StopsPublished', v_stop_count
    );
end;
$$;

create or replace function public.exos_road_hunt_state(
    p_session_token text
)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, extensions
as $$
declare
    v_participant public.runtime_participants%rowtype;
    v_event public.runtime_events%rowtype;
    v_tracker public.runtime_team_trackers%rowtype;
    v_stops jsonb;
    v_arrivals jsonb;
begin
    select participant.*
      into v_participant
      from public.runtime_participants participant
     where participant.session_token::text = trim(p_session_token)
     limit 1;

    if not found then
        raise exception 'Invalid participant session';
    end if;

    select *
      into v_event
      from public.runtime_events
     where event_id = v_participant.event_id
       and active = true;

    if not found then
        raise exception 'Runtime event is not active';
    end if;

    select *
      into v_tracker
      from public.runtime_team_trackers
     where event_id = v_participant.event_id
       and team_name = v_participant.team_name;

    select coalesce(jsonb_agg(
        jsonb_build_object(
            'StopID', stop.stop_id,
            'Position', stop.position,
            'StopName', stop.stop_name,
            'Latitude', stop.latitude,
            'Longitude', stop.longitude,
            'RadiusMeters', stop.radius_meters,
            'MissionIDs', stop.mission_ids,
            'Instructions', stop.instructions,
            'Active', stop.active
        ) order by stop.position, stop.stop_id
    ), '[]'::jsonb)
      into v_stops
      from public.runtime_route_stops stop
     where stop.event_id = v_participant.event_id
       and stop.active = true;

    select coalesce(jsonb_agg(
        jsonb_build_object(
            'StopID', arrival.stop_id,
            'DistanceMeters', round(arrival.distance_meters::numeric, 1),
            'Source', arrival.arrival_source,
            'ArrivedAt', arrival.arrived_at
        ) order by arrival.arrived_at
    ), '[]'::jsonb)
      into v_arrivals
      from public.runtime_geofence_arrivals arrival
     where arrival.event_id = v_participant.event_id
       and arrival.team_name = v_participant.team_name;

    return jsonb_build_object(
        'EventID', v_participant.event_id,
        'TeamName', v_participant.team_name,
        'ParticipantID', v_participant.participant_id::text,
        'Enabled', v_event.road_hunt_enabled,
        'LocationIntervalSeconds', v_event.location_interval_seconds,
        'HasNavigator', v_tracker.participant_id is not null,
        'IsNavigator', v_tracker.participant_id = v_participant.participant_id,
        'NavigatorParticipantID', coalesce(v_tracker.participant_id::text, ''),
        'NavigatorLastSeenAt', v_tracker.last_seen_at,
        'Stops', v_stops,
        'Arrivals', v_arrivals
    );
end;
$$;

create or replace function public.exos_claim_team_tracker(
    p_session_token text
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
    v_participant public.runtime_participants%rowtype;
    v_event public.runtime_events%rowtype;
    v_tracker public.runtime_team_trackers%rowtype;
begin
    select participant.*
      into v_participant
      from public.runtime_participants participant
     where participant.session_token::text = trim(p_session_token)
     limit 1;

    if not found then
        raise exception 'Invalid participant session';
    end if;

    select *
      into v_event
      from public.runtime_events
     where event_id = v_participant.event_id
       and active = true;

    if not found or not v_event.road_hunt_enabled then
        raise exception 'Road Hunt tracking is not enabled for this event';
    end if;

    insert into public.runtime_team_trackers (
        event_id,
        team_name,
        participant_id,
        claimed_at
    ) values (
        v_participant.event_id,
        v_participant.team_name,
        v_participant.participant_id,
        now()
    )
    on conflict (event_id, team_name) do nothing;

    select *
      into v_tracker
      from public.runtime_team_trackers
     where event_id = v_participant.event_id
       and team_name = v_participant.team_name;

    return jsonb_build_object(
        'EventID', v_participant.event_id,
        'TeamName', v_participant.team_name,
        'Claimed', v_tracker.participant_id = v_participant.participant_id,
        'IsNavigator', v_tracker.participant_id = v_participant.participant_id,
        'NavigatorParticipantID', v_tracker.participant_id::text,
        'ClaimedAt', v_tracker.claimed_at
    );
end;
$$;

create or replace function public.exos_submit_team_location(
    p_session_token text,
    p_latitude double precision,
    p_longitude double precision,
    p_accuracy_meters double precision default null,
    p_heading_degrees double precision default null,
    p_speed_mps double precision default null,
    p_captured_at timestamptz default now()
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
    v_participant public.runtime_participants%rowtype;
    v_event public.runtime_events%rowtype;
    v_tracker public.runtime_team_trackers%rowtype;
    v_point extensions.geography(Point, 4326);
    v_arrivals jsonb;
begin
    if p_latitude is null or p_latitude < -90 or p_latitude > 90 then
        raise exception 'Latitude is invalid';
    end if;
    if p_longitude is null or p_longitude < -180 or p_longitude > 180 then
        raise exception 'Longitude is invalid';
    end if;

    select participant.*
      into v_participant
      from public.runtime_participants participant
     where participant.session_token::text = trim(p_session_token)
     limit 1;

    if not found then
        raise exception 'Invalid participant session';
    end if;

    select *
      into v_event
      from public.runtime_events
     where event_id = v_participant.event_id
       and active = true;

    if not found or not v_event.road_hunt_enabled then
        raise exception 'Road Hunt tracking is not enabled for this event';
    end if;

    select *
      into v_tracker
      from public.runtime_team_trackers
     where event_id = v_participant.event_id
       and team_name = v_participant.team_name
     for update;

    if not found or v_tracker.participant_id <> v_participant.participant_id then
        raise exception 'This participant is not the nominated team navigator';
    end if;

    v_point := extensions.st_setsrid(
        extensions.st_makepoint(p_longitude, p_latitude),
        4326
    )::extensions.geography;

    insert into public.runtime_team_locations (
        event_id,
        team_name,
        participant_id,
        latitude,
        longitude,
        accuracy_meters,
        heading_degrees,
        speed_mps,
        captured_at,
        updated_at
    ) values (
        v_participant.event_id,
        v_participant.team_name,
        v_participant.participant_id,
        p_latitude,
        p_longitude,
        case when p_accuracy_meters is null then null else greatest(p_accuracy_meters, 0) end,
        p_heading_degrees,
        p_speed_mps,
        coalesce(p_captured_at, now()),
        now()
    )
    on conflict (event_id, team_name) do update
       set participant_id = excluded.participant_id,
           latitude = excluded.latitude,
           longitude = excluded.longitude,
           accuracy_meters = excluded.accuracy_meters,
           heading_degrees = excluded.heading_degrees,
           speed_mps = excluded.speed_mps,
           captured_at = excluded.captured_at,
           updated_at = now();

    insert into public.runtime_location_history (
        event_id,
        team_name,
        participant_id,
        latitude,
        longitude,
        accuracy_meters,
        heading_degrees,
        speed_mps,
        captured_at
    ) values (
        v_participant.event_id,
        v_participant.team_name,
        v_participant.participant_id,
        p_latitude,
        p_longitude,
        case when p_accuracy_meters is null then null else greatest(p_accuracy_meters, 0) end,
        p_heading_degrees,
        p_speed_mps,
        coalesce(p_captured_at, now())
    );

    update public.runtime_team_trackers
       set last_seen_at = now()
     where event_id = v_participant.event_id
       and team_name = v_participant.team_name;

    insert into public.runtime_geofence_arrivals (
        event_id,
        team_name,
        stop_id,
        participant_id,
        distance_meters,
        arrival_source,
        arrived_at
    )
    select stop.event_id,
           v_participant.team_name,
           stop.stop_id,
           v_participant.participant_id,
           extensions.st_distance(stop.location, v_point),
           'GPS',
           now()
      from public.runtime_route_stops stop
     where stop.event_id = v_participant.event_id
       and stop.active = true
       and extensions.st_dwithin(
           stop.location,
           v_point,
           stop.radius_meters + least(greatest(coalesce(p_accuracy_meters, 0), 0), 100)
       )
    on conflict (event_id, team_name, stop_id) do nothing;

    select coalesce(jsonb_agg(
        jsonb_build_object(
            'StopID', arrival.stop_id,
            'DistanceMeters', round(arrival.distance_meters::numeric, 1),
            'Source', arrival.arrival_source,
            'ArrivedAt', arrival.arrived_at
        ) order by arrival.arrived_at
    ), '[]'::jsonb)
      into v_arrivals
      from public.runtime_geofence_arrivals arrival
     where arrival.event_id = v_participant.event_id
       and arrival.team_name = v_participant.team_name;

    return jsonb_build_object(
        'EventID', v_participant.event_id,
        'TeamName', v_participant.team_name,
        'Accepted', true,
        'Latitude', p_latitude,
        'Longitude', p_longitude,
        'AccuracyMeters', p_accuracy_meters,
        'CapturedAt', coalesce(p_captured_at, now()),
        'Arrivals', v_arrivals
    );
end;
$$;

create or replace function public.exos_road_hunt_status(
    p_event_id text
)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, extensions
as $$
declare
    v_event public.runtime_events%rowtype;
    v_stops jsonb;
    v_teams jsonb;
    v_arrivals jsonb;
begin
    select *
      into v_event
      from public.runtime_events
     where event_id = trim(p_event_id);

    if not found then
        raise exception 'Runtime event % was not found', trim(p_event_id);
    end if;

    select coalesce(jsonb_agg(
        jsonb_build_object(
            'StopID', stop.stop_id,
            'Position', stop.position,
            'StopName', stop.stop_name,
            'Latitude', stop.latitude,
            'Longitude', stop.longitude,
            'RadiusMeters', stop.radius_meters,
            'MissionIDs', stop.mission_ids,
            'Instructions', stop.instructions,
            'Active', stop.active
        ) order by stop.position, stop.stop_id
    ), '[]'::jsonb)
      into v_stops
      from public.runtime_route_stops stop
     where stop.event_id = v_event.event_id;

    select coalesce(jsonb_agg(
        jsonb_build_object(
            'TeamName', team.team_name,
            'Position', team.position,
            'HasNavigator', tracker.participant_id is not null,
            'NavigatorParticipantID', coalesce(tracker.participant_id::text, ''),
            'ClaimedAt', tracker.claimed_at,
            'LastSeenAt', tracker.last_seen_at,
            'Latitude', location.latitude,
            'Longitude', location.longitude,
            'AccuracyMeters', location.accuracy_meters,
            'HeadingDegrees', location.heading_degrees,
            'SpeedMps', location.speed_mps,
            'CapturedAt', location.captured_at
        ) order by team.position
    ), '[]'::jsonb)
      into v_teams
      from public.runtime_teams team
      left join public.runtime_team_trackers tracker
        on tracker.event_id = team.event_id
       and tracker.team_name = team.team_name
      left join public.runtime_team_locations location
        on location.event_id = team.event_id
       and location.team_name = team.team_name
     where team.event_id = v_event.event_id;

    select coalesce(jsonb_agg(
        jsonb_build_object(
            'TeamName', arrival.team_name,
            'StopID', arrival.stop_id,
            'DistanceMeters', round(arrival.distance_meters::numeric, 1),
            'Source', arrival.arrival_source,
            'ArrivedAt', arrival.arrived_at
        ) order by arrival.arrived_at
    ), '[]'::jsonb)
      into v_arrivals
      from public.runtime_geofence_arrivals arrival
     where arrival.event_id = v_event.event_id;

    return jsonb_build_object(
        'EventID', v_event.event_id,
        'Enabled', v_event.road_hunt_enabled,
        'LocationIntervalSeconds', v_event.location_interval_seconds,
        'Stops', v_stops,
        'Teams', v_teams,
        'Arrivals', v_arrivals
    );
end;
$$;

create or replace function public.exos_release_team_tracker(
    p_event_id text,
    p_team_name text
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
    v_deleted integer;
begin
    delete from public.runtime_team_trackers
     where event_id = trim(p_event_id)
       and team_name = trim(p_team_name);
    get diagnostics v_deleted = row_count;

    return jsonb_build_object(
        'EventID', trim(p_event_id),
        'TeamName', trim(p_team_name),
        'Released', v_deleted > 0
    );
end;
$$;

create or replace function public.exos_record_manual_arrival(
    p_event_id text,
    p_team_name text,
    p_stop_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
    if not exists (
        select 1
          from public.runtime_teams
         where event_id = trim(p_event_id)
           and team_name = trim(p_team_name)
    ) then
        raise exception 'Team was not found for this event';
    end if;

    if not exists (
        select 1
          from public.runtime_route_stops
         where event_id = trim(p_event_id)
           and stop_id = upper(trim(p_stop_id))
    ) then
        raise exception 'Route stop was not found for this event';
    end if;

    insert into public.runtime_geofence_arrivals (
        event_id,
        team_name,
        stop_id,
        participant_id,
        distance_meters,
        arrival_source,
        arrived_at
    ) values (
        trim(p_event_id),
        trim(p_team_name),
        upper(trim(p_stop_id)),
        null,
        0,
        'MANUAL',
        now()
    )
    on conflict (event_id, team_name, stop_id) do update
       set arrival_source = 'MANUAL',
           arrived_at = now();

    return jsonb_build_object(
        'EventID', trim(p_event_id),
        'TeamName', trim(p_team_name),
        'StopID', upper(trim(p_stop_id)),
        'Recorded', true
    );
end;
$$;

revoke all on table public.runtime_route_stops from anon, authenticated;
revoke all on table public.runtime_team_trackers from anon, authenticated;
revoke all on table public.runtime_team_locations from anon, authenticated;
revoke all on table public.runtime_location_history from anon, authenticated;
revoke all on table public.runtime_geofence_arrivals from anon, authenticated;

revoke all on function public.exos_configure_road_hunt(text, boolean, integer, boolean) from public;
revoke all on function public.exos_publish_route(text, jsonb) from public;
revoke all on function public.exos_road_hunt_state(text) from public;
revoke all on function public.exos_claim_team_tracker(text) from public;
revoke all on function public.exos_submit_team_location(text, double precision, double precision, double precision, double precision, double precision, timestamptz) from public;
revoke all on function public.exos_road_hunt_status(text) from public;
revoke all on function public.exos_release_team_tracker(text, text) from public;
revoke all on function public.exos_record_manual_arrival(text, text, text) from public;

grant execute on function public.exos_configure_road_hunt(text, boolean, integer, boolean)
    to service_role;
grant execute on function public.exos_publish_route(text, jsonb)
    to service_role;
grant execute on function public.exos_road_hunt_status(text)
    to service_role;
grant execute on function public.exos_release_team_tracker(text, text)
    to service_role;
grant execute on function public.exos_record_manual_arrival(text, text, text)
    to service_role;

grant execute on function public.exos_road_hunt_state(text)
    to anon, authenticated, service_role;
grant execute on function public.exos_claim_team_tracker(text)
    to anon, authenticated, service_role;
grant execute on function public.exos_submit_team_location(text, double precision, double precision, double precision, double precision, double precision, timestamptz)
    to anon, authenticated, service_role;
