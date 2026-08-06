-- Fixed-team, PIN-authenticated captain sessions. Plaintext PINs are never stored.
create table if not exists public.formula_race_team_access (
 event_id text not null, team_id text not null, pin_hash text not null,
 active_device_id text, active_session_token uuid, connected_at timestamptz,
 last_seen_at timestamptz, updated_at timestamptz not null default now(), updated_by text not null,
 primary key(event_id,team_id),
 foreign key(event_id,team_id) references public.runtime_teams(event_id,team_id) on delete cascade
);
alter table public.formula_race_team_access enable row level security;
revoke all on table public.formula_race_team_access from anon,authenticated;

create or replace function public.exos_set_formula_race_team_pin(p_event_id text,p_team_id text,p_pin text,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$
begin
 if length(trim(p_pin))<4 then raise exception 'Team PIN must contain at least four characters'; end if;
 if nullif(trim(p_actor),'') is null then raise exception 'Facilitator identity is required'; end if;
 if not exists(select 1 from public.runtime_teams where event_id=trim(p_event_id) and team_id=trim(p_team_id))
 then raise exception 'Team does not exist in this event'; end if;
 insert into public.formula_race_team_access(event_id,team_id,pin_hash,updated_by)
 values(trim(p_event_id),trim(p_team_id),crypt(trim(p_pin),gen_salt('bf')),trim(p_actor))
 on conflict(event_id,team_id) do update set pin_hash=excluded.pin_hash,
 active_device_id=null,active_session_token=null,connected_at=null,last_seen_at=null,
 updated_at=now(),updated_by=excluded.updated_by;
 return jsonb_build_object('Configured',true,'EventID',trim(p_event_id),'TeamID',trim(p_team_id));
end $$;

create or replace function public.exos_formula_race_captain_login(p_join_code text,p_team_id text,p_pin text,p_device_id text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare e public.runtime_events%rowtype;t public.runtime_teams%rowtype;a public.formula_race_team_access%rowtype;token uuid;
begin
 if nullif(trim(p_device_id),'') is null then raise exception 'Device identifier is required'; end if;
 select * into e from public.runtime_events where join_code=upper(trim(p_join_code)) and active=true for update;
 if not found then raise exception 'Invalid or inactive event code'; end if;
 select * into t from public.runtime_teams where event_id=e.event_id and team_id=trim(p_team_id) for update;
 if not found then raise exception 'Selected team is not available for this event'; end if;
 select * into a from public.formula_race_team_access where event_id=e.event_id and team_id=t.team_id for update;
 if not found or crypt(trim(p_pin),a.pin_hash)<>a.pin_hash then raise exception 'Incorrect team PIN'; end if;
 if nullif(a.active_device_id,'') is not null and a.active_device_id<>trim(p_device_id)
 then raise exception 'This team already has an active captain device. Ask a facilitator to reset it.'; end if;
 token:=coalesce(a.active_session_token,gen_random_uuid());
 update public.formula_race_team_access set active_device_id=trim(p_device_id),active_session_token=token,
 connected_at=coalesce(connected_at,now()),last_seen_at=now() where event_id=e.event_id and team_id=t.team_id;
 return jsonb_build_object('EventID',e.event_id,'EventName',e.event_name,'TeamID',t.team_id,
 'TeamName',t.team_name,'SessionToken',token::text,'Connected',true);
end $$;

create or replace function public.exos_formula_race_restore_captain(p_session_token text,p_device_id text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare a public.formula_race_team_access%rowtype;e public.runtime_events%rowtype;t public.runtime_teams%rowtype;
begin
 select * into a from public.formula_race_team_access where active_session_token::text=trim(p_session_token)
 and active_device_id=trim(p_device_id) for update;if not found then return null;end if;
 select * into e from public.runtime_events where event_id=a.event_id;
 select * into t from public.runtime_teams where event_id=a.event_id and team_id=a.team_id;
 update public.formula_race_team_access set last_seen_at=now() where event_id=a.event_id and team_id=a.team_id;
 return jsonb_build_object('EventID',e.event_id,'EventName',e.event_name,'TeamID',t.team_id,
 'TeamName',t.team_name,'SessionToken',a.active_session_token::text,'Connected',true);
end $$;

create or replace function public.exos_formula_race_team_status(p_event_id text)
returns table(team_id text,connected boolean,connected_at timestamptz,last_seen_at timestamptz)
language sql stable security definer set search_path=public as $$
 select t.team_id,(a.active_session_token is not null),a.connected_at,a.last_seen_at
 from public.runtime_teams t left join public.formula_race_team_access a
 on a.event_id=t.event_id and a.team_id=t.team_id where t.event_id=trim(p_event_id)
 order by t.position,t.team_id;
$$;

revoke all on function public.exos_set_formula_race_team_pin(text,text,text,text) from public;
revoke all on function public.exos_formula_race_captain_login(text,text,text,text) from public;
revoke all on function public.exos_formula_race_restore_captain(text,text) from public;
revoke all on function public.exos_formula_race_team_status(text) from public;
grant execute on function public.exos_set_formula_race_team_pin(text,text,text,text) to service_role;
grant execute on function public.exos_formula_race_captain_login(text,text,text,text) to anon,authenticated;
grant execute on function public.exos_formula_race_restore_captain(text,text) to anon,authenticated;
grant execute on function public.exos_formula_race_team_status(text) to service_role;
