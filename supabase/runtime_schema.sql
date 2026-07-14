create extension if not exists pgcrypto;

create table if not exists public.runtime_events (
    event_id text primary key,
    join_code text not null unique,
    event_name text not null,
    active boolean not null default true,
    next_team_index integer not null default 0,
    published_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.runtime_teams (
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    position integer not null,
    team_id text not null,
    team_name text not null,
    primary key (event_id, position),
    unique (event_id, team_id)
);

create table if not exists public.runtime_participants (
    participant_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    normalized_name text not null,
    display_name text not null,
    team_name text not null,
    points numeric not null default 0,
    status text not null default 'Waiting',
    session_token uuid not null default gen_random_uuid() unique,
    joined_at timestamptz not null default now(),
    unique (event_id, normalized_name)
);

create index if not exists runtime_participants_event_idx
    on public.runtime_participants(event_id);

alter table public.runtime_events enable row level security;
alter table public.runtime_teams enable row level security;
alter table public.runtime_participants enable row level security;

create or replace function public.exos_publish_event(
    p_event_id text,
    p_join_code text,
    p_event_name text,
    p_teams jsonb,
    p_reset_registration boolean default false
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_team_count integer;
begin
    if nullif(trim(p_event_id), '') is null then
        raise exception 'Event ID is required';
    end if;

    if nullif(trim(p_join_code), '') is null then
        raise exception 'Join code is required';
    end if;

    select count(*)
      into v_team_count
      from jsonb_to_recordset(coalesce(p_teams, '[]'::jsonb))
           as team(team_id text, team_name text, position integer)
     where nullif(trim(team.team_name), '') is not null;

    if v_team_count < 1 then
        raise exception 'At least one team is required';
    end if;

    insert into public.runtime_events (
        event_id,
        join_code,
        event_name,
        active,
        next_team_index,
        published_at,
        updated_at
    ) values (
        trim(p_event_id),
        upper(trim(p_join_code)),
        trim(p_event_name),
        true,
        0,
        now(),
        now()
    )
    on conflict (event_id) do update
       set join_code = excluded.join_code,
           event_name = excluded.event_name,
           active = true,
           next_team_index = case
               when p_reset_registration then 0
               else public.runtime_events.next_team_index
           end,
           updated_at = now();

    delete from public.runtime_teams
     where event_id = trim(p_event_id);

    insert into public.runtime_teams (event_id, position, team_id, team_name)
    select trim(p_event_id),
           team.position,
           coalesce(nullif(trim(team.team_id), ''), 'TEAM-' || lpad((team.position + 1)::text, 2, '0')),
           trim(team.team_name)
      from jsonb_to_recordset(p_teams)
           as team(team_id text, team_name text, position integer)
     where nullif(trim(team.team_name), '') is not null
     order by team.position;

    if p_reset_registration then
        delete from public.runtime_participants
         where event_id = trim(p_event_id);
    end if;

    return jsonb_build_object(
        'EventID', trim(p_event_id),
        'JoinCode', upper(trim(p_join_code)),
        'EventName', trim(p_event_name),
        'TeamsPublished', v_team_count,
        'RegistrationReset', p_reset_registration
    );
end;
$$;

create or replace function public.exos_event_by_join_code(p_join_code text)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
    select jsonb_build_object(
        'EventID', event_id,
        'EventName', event_name,
        'JoinCode', join_code
    )
      from public.runtime_events
     where join_code = upper(trim(p_join_code))
       and active = true
     limit 1;
$$;

create or replace function public.exos_join_event(
    p_join_code text,
    p_participant_name text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_event public.runtime_events%rowtype;
    v_participant public.runtime_participants%rowtype;
    v_normalized_name text;
    v_team_name text;
    v_team_count integer;
begin
    if nullif(trim(p_participant_name), '') is null then
        raise exception 'Participant name is required';
    end if;

    v_normalized_name := lower(regexp_replace(trim(p_participant_name), '\s+', ' ', 'g'));

    select *
      into v_event
      from public.runtime_events
     where join_code = upper(trim(p_join_code))
       and active = true
     for update;

    if not found then
        raise exception 'Invalid or inactive join code';
    end if;

    select *
      into v_participant
      from public.runtime_participants
     where event_id = v_event.event_id
       and normalized_name = v_normalized_name;

    if found then
        return jsonb_build_object(
            'EventID', v_event.event_id,
            'EventName', v_event.event_name,
            'Name', v_participant.display_name,
            'Team', v_participant.team_name,
            'Points', v_participant.points,
            'Status', v_participant.status,
            'SessionToken', v_participant.session_token::text,
            'Rejoined', true
        );
    end if;

    select count(*)
      into v_team_count
      from public.runtime_teams
     where event_id = v_event.event_id;

    if v_team_count < 1 then
        raise exception 'No teams are published for this event';
    end if;

    select team_name
      into v_team_name
      from public.runtime_teams
     where event_id = v_event.event_id
       and position = mod(v_event.next_team_index, v_team_count);

    if v_team_name is null then
        raise exception 'Team allocation is incomplete for this event';
    end if;

    insert into public.runtime_participants (
        event_id,
        normalized_name,
        display_name,
        team_name
    ) values (
        v_event.event_id,
        v_normalized_name,
        trim(p_participant_name),
        v_team_name
    )
    returning * into v_participant;

    update public.runtime_events
       set next_team_index = mod(v_event.next_team_index + 1, v_team_count),
           updated_at = now()
     where event_id = v_event.event_id;

    return jsonb_build_object(
        'EventID', v_event.event_id,
        'EventName', v_event.event_name,
        'Name', v_participant.display_name,
        'Team', v_participant.team_name,
        'Points', v_participant.points,
        'Status', v_participant.status,
        'SessionToken', v_participant.session_token::text,
        'Rejoined', false
    );
end;
$$;

create or replace function public.exos_restore_participant(p_session_token text)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
    select jsonb_build_object(
        'EventID', event.event_id,
        'EventName', event.event_name,
        'Name', participant.display_name,
        'Team', participant.team_name,
        'Points', participant.points,
        'Status', participant.status,
        'SessionToken', participant.session_token::text
    )
      from public.runtime_participants participant
      join public.runtime_events event using (event_id)
     where participant.session_token::text = trim(p_session_token)
     limit 1;
$$;

create or replace function public.exos_reset_event_registration(p_event_id text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_deleted integer;
begin
    delete from public.runtime_participants
     where event_id = trim(p_event_id);
    get diagnostics v_deleted = row_count;

    update public.runtime_events
       set next_team_index = 0,
           updated_at = now()
     where event_id = trim(p_event_id);

    return jsonb_build_object(
        'EventID', trim(p_event_id),
        'ParticipantsDeleted', v_deleted,
        'NextTeamIndex', 0
    );
end;
$$;

revoke all on table public.runtime_events from anon, authenticated;
revoke all on table public.runtime_teams from anon, authenticated;
revoke all on table public.runtime_participants from anon, authenticated;

revoke all on function public.exos_publish_event(text, text, text, jsonb, boolean) from public;
revoke all on function public.exos_join_event(text, text) from public;
revoke all on function public.exos_event_by_join_code(text) from public;
revoke all on function public.exos_restore_participant(text) from public;
revoke all on function public.exos_reset_event_registration(text) from public;

grant execute on function public.exos_join_event(text, text)
    to anon, authenticated, service_role;
grant execute on function public.exos_event_by_join_code(text)
    to anon, authenticated, service_role;
grant execute on function public.exos_restore_participant(text)
    to anon, authenticated, service_role;
grant execute on function public.exos_publish_event(text, text, text, jsonb, boolean)
    to service_role;
grant execute on function public.exos_reset_event_registration(text)
    to service_role;
