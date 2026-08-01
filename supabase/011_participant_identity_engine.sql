-- Sprint 010: durable, backend-authoritative participant identity engine.
-- Safe migration: audits existing rows; never auto-merges or deletes them.

create or replace function public.exos_normalize_participant_name(p_name text)
returns text
language sql
immutable
strict
as $$
    select trim(regexp_replace(
        regexp_replace(lower(trim(p_name)), '[[:punct:]]+', ' ', 'g'),
        '\s+', ' ', 'g'
    ));
$$;

alter table public.runtime_participants
    add column if not exists first_name text,
    add column if not exists last_name text,
    add column if not exists team_id text,
    add column if not exists country text,
    add column if not exists flag text,
    add column if not exists last_seen_at timestamptz,
    add column if not exists merged_into_participant_id uuid
        references public.runtime_participants(participant_id) on delete restrict;

update public.runtime_participants participant
   set team_id = team.team_id
  from public.runtime_teams team
 where participant.event_id = team.event_id
   and participant.team_name = team.team_name
   and nullif(participant.team_id, '') is null;

update public.runtime_participants
   set country = split_part(split_part(status, 'COUNTRY:', 2), '|', 1)
 where nullif(country, '') is null and status like 'COUNTRY:%';

create index if not exists runtime_participants_durable_identity_idx
    on public.runtime_participants(event_id, exos_normalize_participant_name(display_name))
    where merged_into_participant_id is null;

create table if not exists public.runtime_identity_audit_log (
    audit_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    action text not null,
    actor text not null,
    canonical_participant_id uuid references public.runtime_participants(participant_id),
    affected_participant_id uuid references public.runtime_participants(participant_id),
    before_state jsonb not null default '{}'::jsonb,
    after_state jsonb not null default '{}'::jsonb,
    reason text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.runtime_submission_overrides (
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    team_id text not null default '*',
    allow_any_member boolean not null default false,
    updated_by text not null,
    updated_at timestamptz not null default now(),
    primary key (event_id, team_id)
);

alter table public.runtime_identity_audit_log enable row level security;
alter table public.runtime_submission_overrides enable row level security;
revoke all on table public.runtime_identity_audit_log from anon, authenticated;
revoke all on table public.runtime_submission_overrides from anon, authenticated;

create or replace function public.exos_identity_payload(
    p_participant public.runtime_participants,
    p_event public.runtime_events
)
returns jsonb
language sql
stable
as $$
    select jsonb_build_object(
        'ParticipantID', p_participant.participant_id::text,
        'EventID', p_event.event_id,
        'EventName', p_event.event_name,
        'Name', p_participant.display_name,
        'Team', p_participant.team_name,
        'TeamID', coalesce(p_participant.team_id, team.team_id, ''),
        'Country', coalesce(nullif(p_participant.country, ''),
            split_part(split_part(p_participant.status, 'COUNTRY:', 2), '|', 1)),
        'Flag', coalesce(nullif(p_participant.flag, ''), split_part(p_participant.team_name, ' ', 1)),
        'Points', p_participant.points,
        'Status', p_participant.status,
        'IsLeader', position('|LEADER' in p_participant.status) > 0,
        'SubmissionRights', case when position('|LEADER' in p_participant.status) > 0
            then 'LEADER' else 'MEMBER' end,
        'SessionToken', p_participant.session_token::text
    )
      from (select 1) seed
      left join public.runtime_teams team
        on team.event_id = p_participant.event_id
       and team.team_name = p_participant.team_name
     limit 1;
$$;

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
    v_normalized text;
    v_matches integer;
    v_team public.runtime_teams%rowtype;
    v_idempotency_key text;
begin
    if nullif(trim(p_participant_name), '') is null then
        raise exception 'Participant full name is required';
    end if;
    v_normalized := public.exos_normalize_participant_name(p_participant_name);

    select * into v_event from public.runtime_events
     where join_code = upper(trim(p_join_code)) and active = true for update;
    if not found then raise exception 'Invalid or inactive join code'; end if;

    -- Identity lookup is deliberately before every allocation operation.
    select count(*) into v_matches from public.runtime_participants
     where event_id = v_event.event_id
       and public.exos_normalize_participant_name(display_name) = v_normalized
       and merged_into_participant_id is null;

    if v_matches > 1 then
        return jsonb_build_object(
            'RecoveryRequired', true, 'Ambiguous', true,
            'EventID', v_event.event_id, 'Name', trim(p_participant_name),
            'Message', 'More than one expedition record matches. Ask a facilitator to choose the correct record.'
        );
    elsif v_matches = 1 then
        select * into v_participant from public.runtime_participants
         where event_id = v_event.event_id
           and public.exos_normalize_participant_name(display_name) = v_normalized
           and merged_into_participant_id is null
         order by joined_at, participant_id limit 1 for update;
        update public.runtime_participants set last_seen_at = now()
         where participant_id = v_participant.participant_id;
        return public.exos_identity_payload(v_participant, v_event)
            || jsonb_build_object('Rejoined', true, 'RecoveryRequired', true);
    end if;

    v_idempotency_key := encode(digest(
        v_event.event_id || '|' || v_normalized || '|' || lower(trim(p_device_id)), 'sha256'
    ), 'hex');

    select team.* into v_team from public.runtime_teams team
      left join public.runtime_participants participant
        on participant.event_id = team.event_id and participant.team_id = team.team_id
       and participant.merged_into_participant_id is null
     where team.event_id = v_event.event_id
     group by team.event_id, team.position, team.team_id, team.team_name
     order by count(participant.participant_id), team.position
     limit 1;
    if not found then raise exception 'No teams are published for this event'; end if;

    insert into public.runtime_participants (
        event_id, normalized_name, display_name, team_name, team_id,
        country, flag, status, idempotency_key, last_seen_at
    ) values (
        v_event.event_id, v_normalized,
        regexp_replace(trim(p_participant_name), '\s+', ' ', 'g'),
        v_team.team_name, v_team.team_id,
        regexp_replace(v_team.team_name, '^\S+\s*', ''),
        split_part(v_team.team_name, ' ', 1),
        'COUNTRY:' || regexp_replace(v_team.team_name, '^\S+\s*', ''),
        v_idempotency_key, now()
    )
    on conflict (event_id, idempotency_key) where idempotency_key is not null
    do update set last_seen_at = now()
    returning * into v_participant;

    return public.exos_identity_payload(v_participant, v_event)
        || jsonb_build_object('Rejoined', false, 'RecoveryRequired', false);
end;
$$;

create or replace function public.exos_admin_set_submission_override(
    p_event_id text, p_team_id text, p_enabled boolean, p_actor text
)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_before jsonb; v_team text := coalesce(nullif(trim(p_team_id), ''), '*');
begin
    select to_jsonb(row) into v_before from public.runtime_submission_overrides row
     where event_id = trim(p_event_id) and team_id = v_team;
    insert into public.runtime_submission_overrides(event_id, team_id, allow_any_member, updated_by)
    values(trim(p_event_id), v_team, p_enabled, trim(p_actor))
    on conflict(event_id, team_id) do update set allow_any_member=excluded.allow_any_member,
        updated_by=excluded.updated_by, updated_at=now();
    insert into public.runtime_identity_audit_log(event_id, action, actor, before_state, after_state)
    values(trim(p_event_id), 'SET_SUBMISSION_OVERRIDE', trim(p_actor), coalesce(v_before,'{}'),
        jsonb_build_object('TeamID',v_team,'Enabled',p_enabled));
    return jsonb_build_object('EventID',trim(p_event_id),'TeamID',v_team,'Enabled',p_enabled);
end; $$;

create or replace function public.exos_admin_transfer_leader(
    p_event_id text, p_team_id text, p_participant_id uuid, p_actor text
)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_target public.runtime_participants%rowtype; v_before jsonb;
begin
    select * into v_target from public.runtime_participants
     where participant_id=p_participant_id and event_id=trim(p_event_id)
       and team_id=trim(p_team_id) and merged_into_participant_id is null for update;
    if not found then raise exception 'Participant is not an active member of this team'; end if;
    select jsonb_agg(to_jsonb(p)) into v_before from public.runtime_participants p
     where event_id=trim(p_event_id) and team_id=trim(p_team_id);
    update public.runtime_participants set status=replace(status,'|LEADER','')
     where event_id=trim(p_event_id) and team_id=trim(p_team_id);
    update public.runtime_participants set status=replace(status,'|LEADER','') || '|LEADER'
     where participant_id=p_participant_id;
    insert into public.runtime_identity_audit_log(event_id,action,actor,canonical_participant_id,before_state,after_state)
    values(trim(p_event_id),'TRANSFER_LEADER',trim(p_actor),p_participant_id,coalesce(v_before,'[]'),
        jsonb_build_object('TeamID',trim(p_team_id),'LeaderParticipantID',p_participant_id));
    return jsonb_build_object('Transferred',true,'ParticipantID',p_participant_id,'TeamID',trim(p_team_id));
end; $$;

create or replace function public.exos_admin_move_participant(
    p_participant_id uuid, p_team_id text, p_actor text, p_reason text
)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_participant public.runtime_participants%rowtype; v_team public.runtime_teams%rowtype;
begin
    select * into v_participant from public.runtime_participants where participant_id=p_participant_id for update;
    if not found then raise exception 'Participant not found'; end if;
    select * into v_team from public.runtime_teams where event_id=v_participant.event_id and team_id=trim(p_team_id);
    if not found then raise exception 'Team not found'; end if;
    update public.runtime_participants set team_id=v_team.team_id, team_name=v_team.team_name,
        country=regexp_replace(v_team.team_name,'^\S+\s*',''), flag=split_part(v_team.team_name,' ',1),
        status='COUNTRY:'||regexp_replace(v_team.team_name,'^\S+\s*','')
     where participant_id=p_participant_id;
    insert into public.runtime_identity_audit_log(event_id,action,actor,canonical_participant_id,before_state,after_state,reason)
    values(v_participant.event_id,'MOVE_PARTICIPANT',trim(p_actor),p_participant_id,to_jsonb(v_participant),
        jsonb_build_object('TeamID',v_team.team_id,'Team',v_team.team_name),trim(p_reason));
    return jsonb_build_object('Moved',true,'ParticipantID',p_participant_id,'TeamID',v_team.team_id);
end; $$;

create or replace function public.exos_identity_migration_audit(p_event_id text)
returns jsonb language sql stable security definer set search_path=public as $$
with participants as (
  select p.*, public.exos_normalize_participant_name(p.display_name) canonical_name
  from public.runtime_participants p where p.event_id=trim(p_event_id)
), duplicates as (
  select canonical_name, count(*) count, jsonb_agg(participant_id order by joined_at) participant_ids
  from participants where merged_into_participant_id is null group by canonical_name having count(*) > 1
), team_mutations as (
  select p.participant_id, p.team_name, p.team_id from participants p
  left join public.runtime_teams t on t.event_id=p.event_id and t.team_id=p.team_id
  where t.team_id is null or t.team_name<>p.team_name
), leaders as (
  select team_id, count(*) count from participants where status like '%|LEADER%' group by team_id having count(*)>1
), orphaned as (
  select s.submission_id from public.runtime_submissions s left join participants p on p.participant_id=s.participant_id
  where s.event_id=trim(p_event_id) and s.participant_id is not null and p.participant_id is null
)
select jsonb_build_object(
 'EventID',trim(p_event_id),
 'DuplicateCandidates',coalesce((select jsonb_agg(to_jsonb(d)) from duplicates d),'[]'),
 'TeamMutationCandidates',coalesce((select jsonb_agg(to_jsonb(t)) from team_mutations t),'[]'),
 'LeaderInconsistencies',coalesce((select jsonb_agg(to_jsonb(l)) from leaders l),'[]'),
 'OrphanedSubmissions',coalesce((select jsonb_agg(to_jsonb(o)) from orphaned o),'[]'),
 'AutomaticChangesApplied',false
); $$;

create or replace function public.exos_admin_duplicate_decision(
    p_event_id text, p_canonical_participant_id uuid, p_duplicate_participant_id uuid,
    p_decision text, p_actor text, p_reason text
)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_canonical public.runtime_participants%rowtype; v_duplicate public.runtime_participants%rowtype;
begin
    if upper(trim(p_decision)) not in ('CONFIRM_SAME','MERGE','KEEP_SEPARATE') then
        raise exception 'Invalid duplicate decision';
    end if;
    select * into v_canonical from public.runtime_participants
     where participant_id=p_canonical_participant_id and event_id=trim(p_event_id) for update;
    select * into v_duplicate from public.runtime_participants
     where participant_id=p_duplicate_participant_id and event_id=trim(p_event_id) for update;
    if not found or v_canonical.participant_id is null or v_canonical.participant_id=v_duplicate.participant_id then
        raise exception 'Two valid distinct participant records are required';
    end if;

    if upper(trim(p_decision))='MERGE' then
        -- Preserve linked submissions and the highest valid participant points.
        update public.runtime_submissions set participant_id=v_canonical.participant_id
         where participant_id=v_duplicate.participant_id;
        update public.runtime_participants
           set points=greatest(v_canonical.points,v_duplicate.points),
               status=case when v_canonical.status like '%|LEADER%' or v_duplicate.status like '%|LEADER%'
                    then replace(v_canonical.status,'|LEADER','')||'|LEADER' else v_canonical.status end
         where participant_id=v_canonical.participant_id;
        update public.runtime_participants set merged_into_participant_id=v_canonical.participant_id
         where participant_id=v_duplicate.participant_id;
    end if;

    insert into public.runtime_identity_audit_log(
        event_id,action,actor,canonical_participant_id,affected_participant_id,
        before_state,after_state,reason
    ) values (
        trim(p_event_id),'DUPLICATE_'||upper(trim(p_decision)),trim(p_actor),
        v_canonical.participant_id,v_duplicate.participant_id,
        jsonb_build_object('Canonical',to_jsonb(v_canonical),'Duplicate',to_jsonb(v_duplicate)),
        jsonb_build_object('Merged',upper(trim(p_decision))='MERGE'),trim(p_reason)
    );
    return jsonb_build_object('Decision',upper(trim(p_decision)),
        'CanonicalParticipantID',v_canonical.participant_id,
        'DuplicateParticipantID',v_duplicate.participant_id);
end; $$;

create or replace function public.exos_can_participant_submit(p_session_token text)
returns jsonb language sql stable security definer set search_path=public as $$
select jsonb_build_object(
  'Allowed', position('|LEADER' in p.status)>0
    or coalesce(event_override.allow_any_member,false)
    or coalesce(team_override.allow_any_member,false),
  'Reason', case
    when position('|LEADER' in p.status)>0 then 'LEADER'
    when coalesce(event_override.allow_any_member,false) then 'EVENT_OVERRIDE'
    when coalesce(team_override.allow_any_member,false) then 'TEAM_OVERRIDE'
    else 'LEADER_ONLY' end,
  'ParticipantID',p.participant_id,'TeamID',p.team_id
)
from public.runtime_participants p
left join public.runtime_submission_overrides event_override
  on event_override.event_id=p.event_id and event_override.team_id='*'
left join public.runtime_submission_overrides team_override
  on team_override.event_id=p.event_id and team_override.team_id=p.team_id
where p.session_token::text=trim(p_session_token) and p.merged_into_participant_id is null
limit 1; $$;

revoke all on function public.exos_admin_set_submission_override(text,text,boolean,text) from public;
revoke all on function public.exos_admin_transfer_leader(text,text,uuid,text) from public;
revoke all on function public.exos_admin_move_participant(uuid,text,text,text) from public;
revoke all on function public.exos_identity_migration_audit(text) from public;
revoke all on function public.exos_admin_duplicate_decision(text,uuid,uuid,text,text,text) from public;
grant execute on function public.exos_join_event(text,text,text) to anon, authenticated;
grant execute on function public.exos_can_participant_submit(text) to anon, authenticated;
grant execute on function public.exos_admin_set_submission_override(text,text,boolean,text) to service_role;
grant execute on function public.exos_admin_transfer_leader(text,text,uuid,text) to service_role;
grant execute on function public.exos_admin_move_participant(uuid,text,text,text) to service_role;
grant execute on function public.exos_identity_migration_audit(text) to service_role;
grant execute on function public.exos_admin_duplicate_decision(text,uuid,uuid,text,text,text) to service_role;
