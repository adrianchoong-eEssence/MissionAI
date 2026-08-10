-- Staging Core v2 Captain recovery. No tables or existing RPC semantics change.
create or replace function public.exos_v2_recover_team_access(
    p_join_code text,
    p_team_id text,
    p_pin text,
    p_device_id text
)
returns jsonb
language plpgsql security definer
set search_path = public as
$$
declare
    v_event public.events_v2%rowtype;
    v_credential public.team_access_credentials_v2%rowtype;
    v_previous public.team_access_sessions_v2%rowtype;
    v_session public.team_access_sessions_v2%rowtype;
begin
    if nullif(trim(p_join_code), '') is null
       or nullif(trim(p_team_id), '') is null
       or nullif(trim(p_pin), '') is null
       or nullif(trim(p_device_id), '') is null then
        raise exception 'Join code, team, PIN, and device are required';
    end if;

    select * into v_event
      from public.events_v2
     where join_code = upper(trim(p_join_code))
       and published_at is not null
     limit 1;
    if not found then
        raise exception 'Invalid or unpublished join code';
    end if;

    select * into v_credential
      from public.team_access_credentials_v2
     where event_id = v_event.event_id
       and team_id = trim(p_team_id)
       and credential_purpose = 'TEAM_PIN'
       and is_active = true
     limit 1;
    if not found or extensions.crypt(trim(p_pin), v_credential.credential_hash) <> v_credential.credential_hash then
        raise exception 'Invalid PIN';
    end if;

    select * into v_previous
      from public.team_access_sessions_v2
     where event_id = v_event.event_id
       and team_id = v_credential.team_id
       and is_active = true
       and lower(device_id) <> lower(trim(p_device_id))
     order by updated_at desc
     limit 1
     for update;

    update public.team_access_sessions_v2
       set is_active = false,
           recovery_required = true,
           updated_at = now()
     where team_access_session_id = v_previous.team_access_session_id;

    insert into public.team_access_sessions_v2 (
        event_id, team_id, team_access_credential_id, device_id, takeover_by_session_id, created_by
    ) values (
        v_event.event_id, v_credential.team_id, v_credential.team_access_credential_id,
        trim(p_device_id), v_previous.team_access_session_id, 'captain_recovery'
    )
    on conflict (event_id, team_id, device_id)
    do update set
        is_active = true,
        recovery_required = false,
        team_access_credential_id = excluded.team_access_credential_id,
        takeover_by_session_id = excluded.takeover_by_session_id,
        last_seen_at = now(),
        updated_at = now()
    returning * into v_session;

    insert into public.audit_log_v2 (
        event_id, actor, action, entity_type, entity_id, before_state, after_state
    ) values (
        v_event.event_id,
        'captain_recovery',
        'TEAM_ACCESS_RECOVERED',
        'team_access_sessions_v2',
        v_session.team_access_session_id::text,
        jsonb_build_object('previous_session_id', v_previous.team_access_session_id),
        jsonb_build_object('team_id', v_credential.team_id, 'session_id', v_session.team_access_session_id)
    );

    return jsonb_build_object(
        'RecoveryRequired', false,
        'Ambiguous', false,
        'EventID', v_event.event_id,
        'TeamID', v_credential.team_id,
        'SessionToken', v_session.session_token::text
    );
end;
$$;

revoke all on function public.exos_v2_recover_team_access(text, text, text, text) from public;
grant execute on function public.exos_v2_recover_team_access(text, text, text, text) to anon, authenticated;
