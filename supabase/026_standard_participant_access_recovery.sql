-- Standard Core v2 participant access recovery.
-- Adds no tables or columns and never changes participant/team assignment.

begin;

create or replace function public.exos_v2_identity_payload(
    p_event_id text,
    p_participant_id uuid
)
returns jsonb
language sql stable
as $$
    select jsonb_build_object(
        'RecoveryRequired', false,
        'Ambiguous', false,
        'EventID', p.event_id,
        'EventName', e.event_name,
        'ParticipantID', p.participant_id::text,
        'TeamID', p.team_id,
        'Team', coalesce(nullif(identity.item->>'TeamIdentity', ''), t.team_name),
        'TeamName', t.team_name,
        'TeamIdentity', coalesce(nullif(identity.item->>'TeamIdentity', ''), t.team_name),
        'ThemeType', coalesce(
            nullif(e.event_payload #>> '{TeamIdentityConfig,ThemeType}', ''),
            nullif(e.event_payload->>'ThemeType', ''),
            'CUSTOM'
        ),
        'ThemeName', coalesce(
            nullif(e.event_payload #>> '{TeamIdentityConfig,ThemeName}', ''),
            nullif(e.event_payload->>'TeamTheme', ''),
            'Team'
        ),
        'Country', coalesce(nullif(identity.item->>'Country', ''), p.country, ''),
        'Flag', coalesce(
            nullif(identity.item->>'Emoji', ''),
            nullif(identity.item->>'Icon', ''),
            nullif(p.flag, ''),
            nullif(t.team_flag, ''),
            ''
        ),
        'Icon', coalesce(identity.item->>'Icon', ''),
        'Emoji', coalesce(identity.item->>'Emoji', ''),
        'Image', coalesce(identity.item->>'Image', ''),
        'Name', p.display_name,
        'SessionToken', active_session.session_token::text
    )
      from public.participants_v2 p
      join public.events_v2 e on e.event_id = p.event_id
      join public.teams_v2 t on t.team_id = p.team_id and t.event_id = p.event_id
      left join lateral (
          select item
            from jsonb_array_elements(
                coalesce(e.event_payload #> '{TeamIdentityConfig,Identities}', '[]'::jsonb)
            ) item
           where item->>'TeamID' = p.team_id
           limit 1
      ) identity on true
      left join lateral (
          select s.session_token
            from public.participant_sessions_v2 s
           where s.participant_id = p.participant_id
             and s.event_id = p.event_id
             and s.is_active
           order by s.last_seen_at desc, s.created_at desc
           limit 1
      ) active_session on true
     where p.event_id = trim(p_event_id)
       and p.participant_id = p_participant_id
     limit 1;
$$;

create or replace function public.exos_v2_restore_join(
    p_join_code text,
    p_participant_name text,
    p_device_id text
)
returns jsonb
language plpgsql stable security definer
set search_path = public as $$
declare
    v_event public.events_v2%rowtype;
    v_normalized text;
    v_session public.participant_sessions_v2%rowtype;
    v_count integer;
    v_participant public.participants_v2%rowtype;
    v_identity jsonb;
begin
    v_normalized := public.exos_v2_normalize_participant_name(p_participant_name);
    select * into v_event from public.events_v2
     where join_code = upper(trim(p_join_code)) limit 1;
    if not found then return null; end if;

    select count(*) into v_count
      from public.participants_v2
     where event_id = v_event.event_id
       and normalized_name = v_normalized
       and merged_into_participant_id is null
       and not is_archived;
    if v_count > 1 then
        return jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', true,
            'EventID', v_event.event_id,
            'Name', trim(p_participant_name),
            'Message', 'Multiple participants share this identity. Re-identification is required.'
        );
    end if;
    if v_count = 0 then return null; end if;

    select * into v_participant from public.participants_v2
     where event_id = v_event.event_id
       and normalized_name = v_normalized
       and merged_into_participant_id is null
       and not is_archived
     order by created_at limit 1;
    v_identity := public.exos_v2_identity_payload(
        v_event.event_id, v_participant.participant_id
    );

    select * into v_session from public.participant_sessions_v2
     where event_id = v_event.event_id
       and participant_id = v_participant.participant_id
       and is_active
     order by last_seen_at desc, created_at desc limit 1;
    if v_session.participant_session_id is null then
        return (v_identity - 'SessionToken') || jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', false,
            'Message', 'Existing participant found. Recover expedition access on this device.'
        );
    end if;

    if nullif(trim(p_device_id), '') is not null
       and lower(trim(v_session.device_id)) <> lower(trim(p_device_id)) then
        return (v_identity - 'SessionToken') || jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', false,
            'Message', 'Existing participant found on another device. Recover expedition access to continue.'
        );
    end if;

    return v_identity;
end;
$$;

create or replace function public.exos_v2_recover_participant_access(
    p_join_code text,
    p_participant_name text,
    p_device_id text
)
returns jsonb
language plpgsql security definer
set search_path = public as $$
declare
    v_event public.events_v2%rowtype;
    v_normalized text;
    v_count integer;
    v_participant public.participants_v2%rowtype;
    v_idempotency_key text;
    v_session public.participant_sessions_v2%rowtype;
begin
    if nullif(trim(p_device_id), '') is null then
        raise exception 'Device identifier is required';
    end if;
    v_normalized := public.exos_v2_normalize_participant_name(p_participant_name);
    select * into v_event from public.events_v2
     where join_code = upper(trim(p_join_code)) and published_at is not null
     limit 1;
    if not found then raise exception 'Invalid or unpublished join code'; end if;

    perform pg_advisory_xact_lock(
        hashtextextended(v_event.event_id || '|' || v_normalized, 17)
    );
    select count(*) into v_count from public.participants_v2
     where event_id = v_event.event_id
       and normalized_name = v_normalized
       and merged_into_participant_id is null
       and not is_archived;
    if v_count <> 1 then
        raise exception 'Participant recovery is not uniquely resolvable';
    end if;

    select * into v_participant from public.participants_v2
     where event_id = v_event.event_id
       and normalized_name = v_normalized
       and merged_into_participant_id is null
       and not is_archived
     order by created_at limit 1
     for update;

    v_idempotency_key := encode(
        extensions.digest(
            v_event.event_id || '|' || v_normalized || '|' || lower(trim(p_device_id)),
            'sha256'
        ),
        'hex'
    );
    update public.participant_sessions_v2
       set is_active = false, last_seen_at = now()
     where event_id = v_event.event_id
       and participant_id = v_participant.participant_id
       and idempotency_key <> v_idempotency_key;

    insert into public.participant_sessions_v2 (
        event_id, participant_id, device_id, idempotency_key, joined_from_client
    ) values (
        v_event.event_id, v_participant.participant_id, trim(p_device_id),
        v_idempotency_key, 'participant_recovery'
    ) on conflict (event_id, idempotency_key) do update
      set participant_id = excluded.participant_id,
          device_id = excluded.device_id,
          joined_from_client = excluded.joined_from_client,
          last_seen_at = now(),
          is_active = true
    returning * into v_session;

    update public.participants_v2 set last_seen_at = now()
     where participant_id = v_participant.participant_id;
    insert into public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, before_state, after_state
    ) values (
        v_event.event_id, 'participant_recovery', 'PARTICIPANT_ACCESS_RECOVERED',
        'participants_v2', v_participant.participant_id::text,
        jsonb_build_object('participant_id', v_participant.participant_id),
        jsonb_build_object('participant_id', v_participant.participant_id,
                           'team_id', v_participant.team_id,
                           'session_id', v_session.participant_session_id)
    );
    return public.exos_v2_identity_payload(
        v_event.event_id, v_participant.participant_id
    );
end;
$$;

revoke all on function public.exos_v2_identity_payload(text, uuid) from public;
revoke all on function public.exos_v2_restore_join(text, text, text) from public;
revoke all on function public.exos_v2_recover_participant_access(text, text, text) from public;
grant execute on function public.exos_v2_restore_join(text, text, text) to anon, authenticated;
grant execute on function public.exos_v2_recover_participant_access(text, text, text) to anon, authenticated;

commit;
