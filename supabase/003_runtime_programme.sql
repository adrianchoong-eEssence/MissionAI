alter table public.runtime_events
    add column if not exists current_stage_no integer not null default 0,
    add column if not exists stage_state text not null default '',
    add column if not exists stage_name text not null default '',
    add column if not exists current_mission_id text not null default '',
    add column if not exists display_mode text not null default 'Hybrid',
    add column if not exists stage_payload jsonb not null default '{}'::jsonb,
    add column if not exists state_version bigint not null default 0,
    add column if not exists state_updated_at timestamptz not null default now();

create table if not exists public.runtime_missions (
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    mission_id text not null,
    mission_payload jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    primary key (event_id, mission_id)
);

create index if not exists runtime_missions_event_idx
    on public.runtime_missions(event_id);

alter table public.runtime_missions enable row level security;

create or replace function public.exos_publish_programme(
    p_event_id text,
    p_missions jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_mission_count integer;
begin
    if not exists (
        select 1
          from public.runtime_events
         where event_id = trim(p_event_id)
    ) then
        raise exception 'Runtime event % was not found', trim(p_event_id);
    end if;

    delete from public.runtime_missions
     where event_id = trim(p_event_id);

    insert into public.runtime_missions (
        event_id,
        mission_id,
        mission_payload,
        updated_at
    )
    select trim(p_event_id),
           trim(mission.mission_id),
           coalesce(mission.mission_payload, '{}'::jsonb),
           now()
      from jsonb_to_recordset(coalesce(p_missions, '[]'::jsonb))
           as mission(mission_id text, mission_payload jsonb)
     where nullif(trim(mission.mission_id), '') is not null;

    get diagnostics v_mission_count = row_count;

    return jsonb_build_object(
        'EventID', trim(p_event_id),
        'MissionsPublished', v_mission_count
    );
end;
$$;

create or replace function public.exos_set_event_stage(
    p_event_id text,
    p_stage_payload jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_event public.runtime_events%rowtype;
begin
    update public.runtime_events
       set current_stage_no = coalesce(
               nullif(p_stage_payload ->> 'StageNo', '')::integer,
               0
           ),
           stage_state = coalesce(p_stage_payload ->> 'StageType', ''),
           stage_name = coalesce(p_stage_payload ->> 'StageName', ''),
           current_mission_id = coalesce(p_stage_payload ->> 'MissionID', ''),
           display_mode = coalesce(p_stage_payload ->> 'DisplayMode', 'Hybrid'),
           stage_payload = coalesce(p_stage_payload, '{}'::jsonb),
           state_version = state_version + 1,
           state_updated_at = now(),
           updated_at = now()
     where event_id = trim(p_event_id)
    returning * into v_event;

    if not found then
        raise exception 'Runtime event % was not found', trim(p_event_id);
    end if;

    return jsonb_build_object(
        'EventID', v_event.event_id,
        'StageNo', v_event.current_stage_no,
        'StageType', v_event.stage_state,
        'StageName', v_event.stage_name,
        'MissionID', v_event.current_mission_id,
        'DisplayMode', v_event.display_mode,
        'StateVersion', v_event.state_version,
        'UpdatedAt', v_event.state_updated_at
    );
end;
$$;

create or replace function public.exos_participant_current_mission(
    p_session_token text
)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
    select jsonb_build_object(
        'EventID', event.event_id,
        'StageNo', event.current_stage_no,
        'StageType', event.stage_state,
        'StageName', event.stage_name,
        'MissionID', event.current_mission_id,
        'DisplayMode', event.display_mode,
        'StateVersion', event.state_version,
        'UpdatedAt', event.state_updated_at,
        'Stage', event.stage_payload,
        'Mission', mission.mission_payload
    )
      from public.runtime_participants participant
      join public.runtime_events event
        on event.event_id = participant.event_id
      left join public.runtime_missions mission
        on mission.event_id = event.event_id
       and mission.mission_id = event.current_mission_id
     where participant.session_token::text = trim(p_session_token)
       and event.active = true
     limit 1;
$$;

revoke all on table public.runtime_missions from anon, authenticated;

revoke all on function public.exos_publish_programme(text, jsonb) from public;
revoke all on function public.exos_set_event_stage(text, jsonb) from public;
revoke all on function public.exos_participant_current_mission(text) from public;

grant execute on function public.exos_publish_programme(text, jsonb)
    to service_role;
grant execute on function public.exos_set_event_stage(text, jsonb)
    to service_role;
grant execute on function public.exos_participant_current_mission(text)
    to anon, authenticated, service_role;
