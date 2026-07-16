create table if not exists public.runtime_ai_messages (
    message_id uuid primary key default gen_random_uuid(),
    event_id text not null
        references public.runtime_events(event_id) on delete cascade,
    participant_id uuid
        references public.runtime_participants(participant_id) on delete set null,
    team_name text not null,
    mission_id text not null,
    facilitator_name text not null default '',
    role text not null check (role in ('user', 'assistant')),
    message text not null check (
        char_length(trim(message)) between 1 and 4000
    ),
    hint_level integer not null default 0 check (hint_level between 0 and 3),
    created_at timestamptz not null default now()
);

create index if not exists runtime_ai_messages_lookup_idx
    on public.runtime_ai_messages(
        event_id,
        team_name,
        mission_id,
        created_at
    );

create table if not exists public.runtime_ai_hint_state (
    event_id text not null
        references public.runtime_events(event_id) on delete cascade,
    team_name text not null,
    mission_id text not null,
    hint_level integer not null default 0 check (hint_level between 0 and 3),
    updated_at timestamptz not null default now(),
    primary key (event_id, team_name, mission_id)
);

alter table public.runtime_ai_messages enable row level security;
alter table public.runtime_ai_hint_state enable row level security;

create or replace function public.exos_ai_conversation(
    p_session_token text,
    p_mission_id text default ''
)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
    v_participant public.runtime_participants%rowtype;
    v_mission_id text;
    v_hint_level integer := 0;
    v_messages jsonb := '[]'::jsonb;
begin
    select *
      into v_participant
      from public.runtime_participants
     where session_token::text = trim(p_session_token)
     limit 1;

    if not found then
        raise exception 'Invalid participant session';
    end if;

    v_mission_id := trim(coalesce(p_mission_id, ''));
    if v_mission_id = '' then
        select current_mission_id
          into v_mission_id
          from public.runtime_events
         where event_id = v_participant.event_id;
    end if;

    if nullif(v_mission_id, '') is null then
        raise exception 'No live mission is available';
    end if;

    select hint_level
      into v_hint_level
      from public.runtime_ai_hint_state
     where event_id = v_participant.event_id
       and team_name = v_participant.team_name
       and mission_id = v_mission_id;

    v_hint_level := coalesce(v_hint_level, 0);

    select coalesce(
               jsonb_agg(
                   recent.message_payload
                   order by recent.created_at, recent.message_id
               ),
               '[]'::jsonb
           )
      into v_messages
      from (
          select message.created_at,
                 message.message_id,
                 jsonb_build_object(
                     'MessageID', message.message_id::text,
                     'Role', initcap(message.role),
                     'Message', message.message,
                     'FacilitatorName', message.facilitator_name,
                     'HintLevel', message.hint_level,
                     'CreatedAt', message.created_at
                 ) as message_payload
            from public.runtime_ai_messages message
           where message.event_id = v_participant.event_id
             and message.team_name = v_participant.team_name
             and message.mission_id = v_mission_id
           order by message.created_at desc, message.message_id desc
           limit 100
      ) recent;

    return jsonb_build_object(
        'EventID', v_participant.event_id,
        'TeamName', v_participant.team_name,
        'MissionID', v_mission_id,
        'HintLevel', v_hint_level,
        'Messages', v_messages
    );
end;
$$;

create or replace function public.exos_ai_add_message(
    p_session_token text,
    p_mission_id text,
    p_facilitator_name text,
    p_role text,
    p_message text,
    p_hint_level integer default 0
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_participant public.runtime_participants%rowtype;
    v_message public.runtime_ai_messages%rowtype;
    v_role text;
begin
    select *
      into v_participant
      from public.runtime_participants
     where session_token::text = trim(p_session_token)
     limit 1;

    if not found then
        raise exception 'Invalid participant session';
    end if;

    if nullif(trim(p_mission_id), '') is null then
        raise exception 'Mission ID is required';
    end if;

    if not exists (
        select 1
          from public.runtime_missions
         where event_id = v_participant.event_id
           and mission_id = trim(p_mission_id)
    ) then
        raise exception 'Mission % was not found for this event', trim(p_mission_id);
    end if;

    v_role := lower(trim(coalesce(p_role, '')));
    if v_role not in ('user', 'assistant') then
        raise exception 'AI message role must be user or assistant';
    end if;

    if nullif(trim(p_message), '') is null then
        raise exception 'AI message cannot be empty';
    end if;

    insert into public.runtime_ai_messages (
        event_id,
        participant_id,
        team_name,
        mission_id,
        facilitator_name,
        role,
        message,
        hint_level
    ) values (
        v_participant.event_id,
        v_participant.participant_id,
        v_participant.team_name,
        trim(p_mission_id),
        left(trim(coalesce(p_facilitator_name, '')), 120),
        v_role,
        left(trim(p_message), 4000),
        greatest(0, least(coalesce(p_hint_level, 0), 3))
    )
    returning * into v_message;

    return jsonb_build_object(
        'MessageID', v_message.message_id::text,
        'EventID', v_message.event_id,
        'TeamName', v_message.team_name,
        'MissionID', v_message.mission_id,
        'Role', initcap(v_message.role),
        'Message', v_message.message,
        'FacilitatorName', v_message.facilitator_name,
        'HintLevel', v_message.hint_level,
        'CreatedAt', v_message.created_at
    );
end;
$$;

create or replace function public.exos_ai_advance_hint(
    p_session_token text,
    p_mission_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_participant public.runtime_participants%rowtype;
    v_mission_payload jsonb;
    v_hint_level integer := 0;
    v_hint_text text := '';
    v_label text := '';
    v_enabled boolean := true;
begin
    select *
      into v_participant
      from public.runtime_participants
     where session_token::text = trim(p_session_token)
     limit 1;

    if not found then
        raise exception 'Invalid participant session';
    end if;

    if nullif(trim(p_mission_id), '') is null then
        raise exception 'Mission ID is required';
    end if;

    select mission_payload
      into v_mission_payload
      from public.runtime_missions
     where event_id = v_participant.event_id
       and mission_id = trim(p_mission_id);

    if not found then
        raise exception 'Mission % was not found for this event', trim(p_mission_id);
    end if;

    v_enabled := upper(trim(coalesce(
        v_mission_payload ->> 'AIHelpEnabled',
        'YES'
    ))) not in ('NO', 'FALSE', '0', 'OFF');

    if not v_enabled then
        select coalesce(hint_level, 0)
          into v_hint_level
          from public.runtime_ai_hint_state
         where event_id = v_participant.event_id
           and team_name = v_participant.team_name
           and mission_id = trim(p_mission_id);

        return jsonb_build_object(
            'Enabled', false,
            'Level', coalesce(v_hint_level, 0),
            'Label', 'AI help disabled',
            'HintText', '',
            'Remaining', 0
        );
    end if;

    insert into public.runtime_ai_hint_state (
        event_id,
        team_name,
        mission_id,
        hint_level,
        updated_at
    ) values (
        v_participant.event_id,
        v_participant.team_name,
        trim(p_mission_id),
        1,
        now()
    )
    on conflict (event_id, team_name, mission_id) do update
       set hint_level = least(
               public.runtime_ai_hint_state.hint_level + 1,
               3
           ),
           updated_at = now()
    returning hint_level into v_hint_level;

    if v_hint_level = 1 then
        v_label := 'Nudge';
        v_hint_text := coalesce(
            nullif(trim(v_mission_payload ->> 'Hint1'), ''),
            'Review the mission objective and identify the first fact your team can verify.'
        );
    elsif v_hint_level = 2 then
        v_label := 'Stronger Hint';
        v_hint_text := coalesce(
            nullif(trim(v_mission_payload ->> 'Hint2'), ''),
            'Break the challenge into smaller steps, test each assumption, then compare the evidence.'
        );
    else
        v_label := 'Method Hint';
        v_hint_text := coalesce(
            nullif(trim(v_mission_payload ->> 'Hint3'), ''),
            'Define the goal, list the constraints, test the most likely option, and validate before submitting.'
        );
    end if;

    return jsonb_build_object(
        'Enabled', true,
        'Level', v_hint_level,
        'Label', v_label,
        'HintText', v_hint_text,
        'Remaining', greatest(3 - v_hint_level, 0)
    );
end;
$$;

create or replace function public.exos_reset_ai_event(p_event_id text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_messages integer := 0;
    v_hints integer := 0;
begin
    delete from public.runtime_ai_messages
     where event_id = trim(p_event_id);
    get diagnostics v_messages = row_count;

    delete from public.runtime_ai_hint_state
     where event_id = trim(p_event_id);
    get diagnostics v_hints = row_count;

    return jsonb_build_object(
        'EventID', trim(p_event_id),
        'MessagesDeleted', v_messages,
        'HintStatesDeleted', v_hints
    );
end;
$$;

revoke all on table public.runtime_ai_messages from anon, authenticated;
revoke all on table public.runtime_ai_hint_state from anon, authenticated;

revoke all on function public.exos_ai_conversation(text, text) from public;
revoke all on function public.exos_ai_add_message(
    text, text, text, text, text, integer
) from public;
revoke all on function public.exos_ai_advance_hint(text, text) from public;
revoke all on function public.exos_reset_ai_event(text) from public;

grant execute on function public.exos_ai_conversation(text, text)
    to anon, authenticated, service_role;
grant execute on function public.exos_ai_add_message(
    text, text, text, text, text, integer
) to service_role;
grant execute on function public.exos_ai_advance_hint(text, text)
    to service_role;
grant execute on function public.exos_reset_ai_event(text)
    to service_role;
