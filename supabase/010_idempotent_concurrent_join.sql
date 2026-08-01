-- Atomic normalized-name participant joins. Safe to apply without resetting events.

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
    v_team_id text;
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

    -- Durable event + normalized-name identity is the source of truth.  This
    -- lookup must happen before idempotency/device matching and allocation.
    -- Existing historical duplicates are left untouched; the earliest record
    -- is restored deterministically.
    select * into v_participant
      from public.runtime_participants
     where event_id = v_event.event_id
       and normalized_name = v_normalized_name
     order by joined_at, participant_id
     for update
     limit 1;

    if found then
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

    select team_id into v_team_id
      from public.runtime_teams
     where event_id = v_event.event_id
       and team_name = v_participant.team_name
     order by position
     limit 1;

    return jsonb_build_object(
        'ParticipantID', v_participant.participant_id::text,
        'EventID', v_event.event_id,
        'EventName', v_event.event_name,
        'Name', v_participant.display_name,
        'Team', v_participant.team_name,
        'TeamID', coalesce(v_team_id, ''),
        'Country', case
            when v_participant.status like 'COUNTRY:%'
            then split_part(split_part(v_participant.status, 'COUNTRY:', 2), '|', 1)
            else regexp_replace(v_participant.team_name, '^\S+\s*', '')
        end,
        'Flag', split_part(v_participant.team_name, ' ', 1),
        'Points', v_participant.points,
        'Status', v_participant.status,
        'IsLeader', position('|LEADER' in v_participant.status) > 0,
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
        'TeamID', coalesce(team.team_id, ''),
        'Country', case
            when participant.status like 'COUNTRY:%'
            then split_part(split_part(participant.status, 'COUNTRY:', 2), '|', 1)
            else regexp_replace(participant.team_name, '^\S+\s*', '')
        end,
        'Flag', split_part(participant.team_name, ' ', 1),
        'Points', participant.points,
        'Status', participant.status,
        'IsLeader', position('|LEADER' in participant.status) > 0,
        'SessionToken', participant.session_token::text,
        'Rejoined', true
    )
      from public.runtime_events event
      join public.runtime_participants participant
        on participant.event_id = event.event_id
      left join public.runtime_teams team
        on team.event_id = participant.event_id
       and team.team_name = participant.team_name
     where event.join_code = upper(trim(p_join_code))
       and participant.normalized_name = lower(
           regexp_replace(trim(p_participant_name), '\s+', ' ', 'g')
       )
     order by participant.joined_at, participant.participant_id, team.position
     limit 1;
$$;

create or replace function public.exos_restore_participant(
    p_session_token text
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
        'TeamID', coalesce(team.team_id, ''),
        'Country', case
            when participant.status like 'COUNTRY:%'
            then split_part(split_part(participant.status, 'COUNTRY:', 2), '|', 1)
            else regexp_replace(participant.team_name, '^\S+\s*', '')
        end,
        'Flag', split_part(participant.team_name, ' ', 1),
        'Points', participant.points,
        'Status', participant.status,
        'IsLeader', position('|LEADER' in participant.status) > 0,
        'SessionToken', participant.session_token::text,
        'Rejoined', true
    )
      from public.runtime_participants participant
      join public.runtime_events event using (event_id)
      left join public.runtime_teams team
        on team.event_id = participant.event_id
       and team.team_name = participant.team_name
     where participant.session_token::text = trim(p_session_token)
     order by team.position
     limit 1;
$$;

revoke all on function public.exos_join_event(text, text, text) from public;
revoke all on function public.exos_restore_join(text, text, text) from public;
revoke all on function public.exos_restore_participant(text) from public;
grant execute on function public.exos_join_event(text, text, text) to anon, authenticated;
grant execute on function public.exos_restore_join(text, text, text) to anon, authenticated;
grant execute on function public.exos_restore_participant(text) to anon, authenticated;
