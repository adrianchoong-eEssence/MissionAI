-- Atomic, device-scoped participant joins. Safe to apply without resetting events.

alter table public.runtime_participants
    add column if not exists idempotency_key text;

create unique index if not exists runtime_participants_event_idempotency_key
    on public.runtime_participants(event_id, idempotency_key)
    where idempotency_key is not null;

create index if not exists runtime_participants_event_normalized_joined_idx
    on public.runtime_participants(event_id, normalized_name, joined_at);

drop function if exists public.exos_join_event(text, text, text);

create or replace function public.exos_join_event(
    p_join_code text,
    p_participant_name text,
    p_device_id text
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
    v_device_id text;
    v_idempotency_key text;
    v_team_name text;
    v_rejoined boolean := false;
begin
    if nullif(trim(p_participant_name), '') is null then
        raise exception 'Participant full name is required';
    end if;
    if nullif(trim(p_device_id), '') is null then
        raise exception 'Participant device identifier is required';
    end if;

    v_normalized_name := lower(
        regexp_replace(trim(p_participant_name), '\s+', ' ', 'g')
    );
    v_device_id := lower(trim(p_device_id));

    select * into v_event
      from public.runtime_events
     where join_code = upper(trim(p_join_code))
       and active = true
     for update;

    if not found then
        raise exception 'Invalid or inactive join code';
    end if;

    v_idempotency_key := md5(
        v_event.event_id || '|' || v_normalized_name || '|' || v_device_id
    );

    select * into v_participant
      from public.runtime_participants
     where event_id = v_event.event_id
       and idempotency_key = v_idempotency_key
     limit 1;

    if not found then
        -- Bind one pre-migration registration to this device instead of duplicating it.
        select * into v_participant
          from public.runtime_participants
         where event_id = v_event.event_id
           and normalized_name = v_normalized_name
           and idempotency_key is null
         order by joined_at, participant_id
         for update skip locked
         limit 1;

        if found then
            v_rejoined := true;
            update public.runtime_participants
               set idempotency_key = v_idempotency_key
             where participant_id = v_participant.participant_id
            returning * into v_participant;
        end if;
    else
        v_rejoined := true;
    end if;

    if not found then
        -- Preserve the EVT-0004 least-populated-country mechanic atomically.
        select team.team_name into v_team_name
          from public.runtime_teams team
          left join public.runtime_participants participant
            on participant.event_id = team.event_id
           and participant.team_name = team.team_name
         where team.event_id = v_event.event_id
         group by team.team_name, team.position
         order by count(participant.participant_id), team.position
         limit 1;

        if v_team_name is null then
            raise exception 'No teams are published for this event';
        end if;

        insert into public.runtime_participants (
            event_id, normalized_name, display_name, team_name,
            status, idempotency_key
        ) values (
            v_event.event_id,
            v_normalized_name,
            regexp_replace(trim(p_participant_name), '\s+', ' ', 'g'),
            v_team_name,
            'COUNTRY:' || regexp_replace(v_team_name, '^\S+\s*', ''),
            v_idempotency_key
        )
        on conflict (event_id, idempotency_key)
            where idempotency_key is not null
        do update set idempotency_key = excluded.idempotency_key
        returning * into v_participant;
    end if;

    return jsonb_build_object(
        'ParticipantID', v_participant.participant_id::text,
        'EventID', v_event.event_id,
        'EventName', v_event.event_name,
        'Name', v_participant.display_name,
        'Team', v_participant.team_name,
        'Points', v_participant.points,
        'Status', v_participant.status,
        'SessionToken', v_participant.session_token::text,
        'Rejoined', v_rejoined
    );
end;
$$;

create or replace function public.exos_restore_join(
    p_join_code text,
    p_participant_name text,
    p_device_id text
)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
    select jsonb_build_object(
        'ParticipantID', participant.participant_id::text,
        'EventID', event.event_id,
        'EventName', event.event_name,
        'Name', participant.display_name,
        'Team', participant.team_name,
        'Points', participant.points,
        'Status', participant.status,
        'SessionToken', participant.session_token::text,
        'Rejoined', true
    )
      from public.runtime_events event
      join public.runtime_participants participant
        on participant.event_id = event.event_id
     where event.join_code = upper(trim(p_join_code))
       and participant.idempotency_key = md5(
           event.event_id || '|' ||
           lower(regexp_replace(trim(p_participant_name), '\s+', ' ', 'g')) ||
           '|' || lower(trim(p_device_id))
       )
     limit 1;
$$;

revoke all on function public.exos_join_event(text, text, text) from public;
revoke all on function public.exos_restore_join(text, text, text) from public;
grant execute on function public.exos_join_event(text, text, text) to anon, authenticated;
grant execute on function public.exos_restore_join(text, text, text) to anon, authenticated;
