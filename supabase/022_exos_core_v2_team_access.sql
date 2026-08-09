BEGIN;

create table if not exists public.team_access_credentials_v2 (
    team_access_credential_id uuid primary key default extensions.gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete cascade,
    credential_hash text not null,
    credential_purpose text not null default 'TEAM_PIN',
    is_active boolean not null default true,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (event_id, team_id, credential_purpose)
);

create unique index if not exists team_access_credentials_v2_event_team_active_idx
    on public.team_access_credentials_v2 (event_id, team_id)
    where is_active = true;

create table if not exists public.team_access_sessions_v2 (
    team_access_session_id uuid primary key default extensions.gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_access_credential_id uuid not null references public.team_access_credentials_v2(team_access_credential_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete cascade,
    device_id text not null,
    session_token uuid not null unique default extensions.gen_random_uuid(),
    is_active boolean not null default true,
    recovery_required boolean not null default false,
    takeover_by_session_id uuid references public.team_access_sessions_v2(team_access_session_id),
    created_by text,
    last_seen_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (event_id, team_id, device_id)
);

create index if not exists team_access_sessions_v2_event_team_idx
    on public.team_access_sessions_v2 (event_id, team_id);

alter table public.team_access_credentials_v2 enable row level security;
alter table public.team_access_sessions_v2 enable row level security;

do $$
declare
    t text;
    existing text[] := array['team_access_credentials_v2','team_access_sessions_v2'];
begin
    foreach t in array existing loop
        if not exists (
            select 1
              from pg_policies p
             where p.schemaname = 'public'
               and p.tablename = t
               and p.policyname = (t || '_sr_all_policy')
        ) then
            execute format(
                'create policy %I on public.%I for all to service_role using (true) with check (true);',
                t || '_sr_all_policy', t
            );
        end if;
    end loop;
end $$;

create or replace function public.exos_v2_set_team_access_pin(
    p_event_id text,
    p_team_id text,
    p_pin text,
    p_actor text default 'system'
)
returns jsonb
language plpgsql security definer
set search_path = public as
$$
declare
    v_event public.events_v2%rowtype;
    v_team public.teams_v2%rowtype;
    v_credential_id uuid;
    v_pin_hash text;
begin
    if nullif(trim(p_event_id),'') is null then
        raise exception 'EventID is required';
    end if;
    if nullif(trim(p_team_id),'') is null then
        raise exception 'TeamID is required';
    end if;
    if nullif(trim(p_pin),'') is null then
        raise exception 'PIN is required';
    end if;

    select * into v_event
      from public.events_v2
     where event_id = trim(p_event_id)
     limit 1;
    if not found then
        raise exception 'Event not found';
    end if;

    select * into v_team
      from public.teams_v2
     where team_id = trim(p_team_id)
       and event_id = v_event.event_id
     limit 1;
    if not found then
        raise exception 'Team does not belong to event';
    end if;

    v_pin_hash := extensions.crypt(trim(p_pin), extensions.gen_salt('bf'));

    insert into public.team_access_credentials_v2 (
        event_id,
        team_id,
        credential_hash,
        credential_purpose,
        created_by
    ) values (
        v_event.event_id,
        v_team.team_id,
        v_pin_hash,
        'TEAM_PIN',
        coalesce(trim(p_actor), 'system')
    )
    on conflict (event_id, team_id, credential_purpose)
    do update
       set credential_hash = excluded.credential_hash,
           created_by = excluded.created_by,
           is_active = true,
           updated_at = now();

    select team_access_credential_id into v_credential_id
      from public.team_access_credentials_v2
     where event_id = v_event.event_id and team_id = v_team.team_id and credential_purpose='TEAM_PIN'
     limit 1;

    insert into public.audit_log_v2 (event_id, actor, action, entity_type, entity_id, before_state, after_state)
    values (
        v_event.event_id,
        coalesce(trim(p_actor), 'system'),
        'TEAM_ACCESS_PIN_SET',
        'team_access_credentials_v2',
        v_team.team_id,
        '{}'::jsonb,
        jsonb_build_object('team_id', v_team.team_id, 'event_id', v_event.event_id)
    );

    return jsonb_build_object(
        'Configured', true,
        'EventID', v_event.event_id,
        'TeamID', v_team.team_id,
        'CredentialId', v_credential_id
    );
end;
$$;

create or replace function public.exos_v2_team_access_login(
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
    v_cred public.team_access_credentials_v2%rowtype;
    v_active public.team_access_sessions_v2%rowtype;
    v_session public.team_access_sessions_v2%rowtype;
begin
    if nullif(trim(p_join_code),'') is null then
        raise exception 'Join code is required';
    end if;
    if nullif(trim(p_team_id),'') is null then
        raise exception 'TeamID is required';
    end if;
    if nullif(trim(p_pin),'') is null then
        raise exception 'PIN is required';
    end if;
    if nullif(trim(p_device_id),'') is null then
        raise exception 'Device ID is required';
    end if;

    select * into v_event
      from public.events_v2
     where join_code = upper(trim(p_join_code))
       and published_at is not null
     limit 1;
    if not found then
        raise exception 'Invalid or unpublished join code';
    end if;

    select * into v_cred
      from public.team_access_credentials_v2
     where event_id = v_event.event_id
       and team_id = trim(p_team_id)
       and is_active = true
     limit 1;
    if not found then
        raise exception 'Team access is not configured';
    end if;

    if extensions.crypt(trim(p_pin), v_cred.credential_hash) <> v_cred.credential_hash then
        raise exception 'Invalid PIN';
    end if;

    select * into v_active
      from public.team_access_sessions_v2
     where event_id = v_event.event_id
       and team_id = v_cred.team_id
       and is_active = true
     order by updated_at desc
     limit 1;

    if v_active.team_access_session_id is not null and lower(trim(v_active.device_id)) <> lower(trim(p_device_id)) then
        return jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', false,
            'EventID', v_event.event_id,
            'TeamID', v_cred.team_id,
            'SessionToken', null,
            'Message', 'Team access is active on a different device. Recovery flow required.'
        );
    end if;

    insert into public.team_access_sessions_v2 (
        event_id,
        team_id,
        team_access_credential_id,
        device_id,
        created_by
    ) values (
        v_event.event_id,
        v_cred.team_id,
        v_cred.team_access_credential_id,
        trim(p_device_id),
        'anonymous'
    )
    on conflict (event_id, team_id, device_id)
    do update
      set updated_at = now(),
          last_seen_at = now(),
          is_active = true,
          team_access_credential_id = excluded.team_access_credential_id,
          recovery_required = false
    returning * into v_session;

    if v_session.team_access_session_id is null then
        select * into v_session
          from public.team_access_sessions_v2
         where event_id = v_event.event_id
           and team_id = v_cred.team_id
           and device_id = trim(p_device_id)
         limit 1;
    end if;

    update public.team_access_sessions_v2
       set is_active = false,
           recovery_required = true
     where team_access_session_id = v_active.team_access_session_id
       and v_active.team_access_session_id is not null
       and v_active.team_access_session_id <> v_session.team_access_session_id;

    update public.team_access_sessions_v2
       set last_seen_at = now(),
           updated_at = now()
     where team_access_session_id = v_session.team_access_session_id;

    return jsonb_build_object(
        'RecoveryRequired', false,
        'Ambiguous', false,
        'EventID', v_event.event_id,
        'TeamID', v_cred.team_id,
        'SessionToken', v_session.session_token::text
    );
end;
$$;

create or replace function public.exos_v2_restore_team_access(
    p_session_token text,
    p_device_id text
)
returns jsonb
language plpgsql security definer
set search_path = public as
$$
declare
    v_session public.team_access_sessions_v2%rowtype;
begin
    if nullif(trim(p_session_token),'') is null then
        raise exception 'SessionToken is required';
    end if;
    if nullif(trim(p_device_id),'') is null then
        raise exception 'Device ID is required';
    end if;

    select * into v_session
      from public.team_access_sessions_v2
     where session_token = p_session_token::uuid
       and event_id = any(array(select event_id from public.events_v2))
       and is_active = true
     limit 1;
    if not found then
        return jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', false,
            'Message', 'No active session found'
        );
    end if;

    if lower(trim(v_session.device_id)) <> lower(trim(p_device_id)) then
        return jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', false,
            'Message', 'Device mismatch for active session'
        );
    end if;

    update public.team_access_sessions_v2
       set last_seen_at = now(),
           updated_at = now()
     where team_access_session_id = v_session.team_access_session_id;

    return jsonb_build_object(
        'RecoveryRequired', false,
        'Ambiguous', false,
        'EventID', v_session.event_id,
        'TeamID', v_session.team_id
    );
end;
$$;

revoke all on table public.team_access_credentials_v2 from anon, authenticated;
revoke all on table public.team_access_sessions_v2 from anon, authenticated;
revoke all on function public.exos_v2_set_team_access_pin(text,text,text,text) from public;
revoke all on function public.exos_v2_team_access_login(text,text,text,text) from public;
revoke all on function public.exos_v2_restore_team_access(text,text) from public;

grant execute on function public.exos_v2_set_team_access_pin(text,text,text,text) to service_role;
grant execute on function public.exos_v2_team_access_login(text,text,text,text) to anon, authenticated;
grant execute on function public.exos_v2_restore_team_access(text,text) to anon, authenticated;

grant select, insert, update, delete on table public.team_access_credentials_v2 to service_role;
grant select, insert, update, delete on table public.team_access_sessions_v2 to service_role;

grant select on table public.team_access_credentials_v2 to anon, authenticated;
grant select on table public.team_access_sessions_v2 to anon, authenticated;

COMMIT;
