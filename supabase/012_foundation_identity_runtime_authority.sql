-- Sprint 011A: P0 Gates 1 and 2.
-- Non-destructive. Requires migration 011. Does not rewrite participant rows.

alter table public.runtime_events
    add column if not exists runtime_control_state jsonb not null default '{}'::jsonb;

create unique index if not exists runtime_credit_earn_once
    on public.runtime_credit_transactions(event_id, team_name, source_type, source_id)
    where transaction_type = 'EARN' and source_id <> '';

create or replace function public.exos_guard_participant_identity()
returns trigger language plpgsql set search_path=public as $$
declare v_override boolean := coalesce(current_setting('exos.identity_override', true), '') = 'on';
begin
    if new.participant_id <> old.participant_id or new.event_id <> old.event_id then
        raise exception 'ParticipantID and EventID are immutable';
    end if;
    if not v_override and (
        new.display_name is distinct from old.display_name
        or new.normalized_name is distinct from old.normalized_name
        or new.team_id is distinct from old.team_id
        or new.team_name is distinct from old.team_name
        or new.country is distinct from old.country
        or new.flag is distinct from old.flag
        or (new.status like '%|LEADER%') is distinct from (old.status like '%|LEADER%')
        or new.merged_into_participant_id is distinct from old.merged_into_participant_id
    ) then
        raise exception 'Durable participant identity requires an audited override';
    end if;
    return new;
end; $$;

drop trigger if exists runtime_participant_identity_guard on public.runtime_participants;
create trigger runtime_participant_identity_guard
before update on public.runtime_participants
for each row execute function public.exos_guard_participant_identity();

create or replace function public.exos_join_event_v2(
    p_join_code text,
    p_participant_name text,
    p_device_id text,
    p_requested_team_id text default ''
)
returns jsonb language plpgsql security definer set search_path=public as $$
declare
    v_event public.runtime_events%rowtype;
    v_participant public.runtime_participants%rowtype;
    v_normalized text;
    v_matches integer;
    v_team public.runtime_teams%rowtype;
    v_idempotency_key text;
begin
    if nullif(trim(p_participant_name),'') is null then raise exception 'Participant full name is required'; end if;
    if nullif(trim(p_device_id),'') is null then raise exception 'Participant device identifier is required'; end if;
    v_normalized := public.exos_normalize_participant_name(p_participant_name);

    select * into v_event from public.runtime_events
     where join_code=upper(trim(p_join_code)) and active=true for update;
    if not found then raise exception 'Invalid or inactive join code'; end if;

    select count(*) into v_matches from public.runtime_participants
     where event_id=v_event.event_id
       and public.exos_normalize_participant_name(display_name)=v_normalized
       and merged_into_participant_id is null;

    if v_matches > 1 then
        return jsonb_build_object(
            'RecoveryRequired',true,'Ambiguous',true,'EventID',v_event.event_id,
            'Name',trim(p_participant_name),
            'Message','More than one expedition record matches. Ask a facilitator to choose the correct record.'
        );
    elsif v_matches = 1 then
        select * into v_participant from public.runtime_participants
         where event_id=v_event.event_id
           and public.exos_normalize_participant_name(display_name)=v_normalized
           and merged_into_participant_id is null
         order by joined_at,participant_id limit 1 for update;
        update public.runtime_participants set last_seen_at=now()
         where participant_id=v_participant.participant_id;
        return public.exos_identity_payload(v_participant,v_event)
            || jsonb_build_object('Rejoined',true,'RecoveryRequired',true);
    end if;

    v_idempotency_key := encode(digest(
        v_event.event_id||'|'||v_normalized||'|'||lower(trim(p_device_id)), 'sha256'
    ),'hex');

    if nullif(trim(p_requested_team_id),'') is not null then
        select * into v_team from public.runtime_teams
         where event_id=v_event.event_id and team_id=trim(p_requested_team_id)
         order by position limit 1;
        if not found then raise exception 'Requested team is not published for this event'; end if;
    else
        select team.* into v_team from public.runtime_teams team
        left join public.runtime_participants participant
          on participant.event_id=team.event_id and participant.team_id=team.team_id
         and participant.merged_into_participant_id is null
        where team.event_id=v_event.event_id
        group by team.event_id,team.position,team.team_id,team.team_name
        order by count(participant.participant_id),team.position limit 1;
        if not found then raise exception 'No teams are published for this event'; end if;
    end if;

    insert into public.runtime_participants(
        event_id,normalized_name,display_name,team_name,team_id,country,flag,
        status,idempotency_key,last_seen_at
    ) values (
        v_event.event_id,v_normalized,regexp_replace(trim(p_participant_name),'\s+',' ','g'),
        v_team.team_name,v_team.team_id,regexp_replace(v_team.team_name,'^\S+\s*',''),
        split_part(v_team.team_name,' ',1),
        'COUNTRY:'||regexp_replace(v_team.team_name,'^\S+\s*',''),v_idempotency_key,now()
    ) on conflict(event_id,idempotency_key) where idempotency_key is not null
      do update set last_seen_at=now()
    returning * into v_participant;

    return public.exos_identity_payload(v_participant,v_event)
        || jsonb_build_object('Rejoined',false,'RecoveryRequired',false);
end; $$;

create or replace function public.exos_claim_team_leader(p_session_token text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_participant public.runtime_participants%rowtype; v_leader public.runtime_participants%rowtype;
begin
    select * into v_participant from public.runtime_participants
     where session_token::text=trim(p_session_token) and merged_into_participant_id is null for update;
    if not found then raise exception 'Participant session was not found'; end if;
    select * into v_leader from public.runtime_participants
     where event_id=v_participant.event_id and team_id=v_participant.team_id
       and status like '%|LEADER%' and merged_into_participant_id is null
     order by joined_at limit 1 for update;
    if found then return jsonb_build_object('Claimed',false,'LeaderName',v_leader.display_name); end if;
    perform set_config('exos.identity_override','on',true);
    update public.runtime_participants set status=replace(status,'|LEADER','')||'|LEADER'
     where participant_id=v_participant.participant_id;
    insert into public.runtime_identity_audit_log(event_id,action,actor,canonical_participant_id,after_state)
    values(v_participant.event_id,'CLAIM_LEADER',v_participant.display_name,v_participant.participant_id,
        jsonb_build_object('TeamID',v_participant.team_id,'LeaderParticipantID',v_participant.participant_id));
    return jsonb_build_object('Claimed',true,'LeaderName',v_participant.display_name);
end; $$;

create or replace function public.exos_restore_join(
    p_join_code text,p_participant_name text,p_device_id text
)
returns jsonb language plpgsql stable security definer set search_path=public as $$
declare v_event public.runtime_events%rowtype; v_participant public.runtime_participants%rowtype;
        v_normalized text; v_matches integer;
begin
    v_normalized:=public.exos_normalize_participant_name(p_participant_name);
    select * into v_event from public.runtime_events
     where join_code=upper(trim(p_join_code)) and active=true limit 1;
    if not found then return null; end if;
    select count(*) into v_matches from public.runtime_participants
     where event_id=v_event.event_id
       and public.exos_normalize_participant_name(display_name)=v_normalized
       and merged_into_participant_id is null;
    if v_matches>1 then
        return jsonb_build_object('RecoveryRequired',true,'Ambiguous',true,
            'EventID',v_event.event_id,'Name',trim(p_participant_name),
            'Message','More than one expedition record matches. Ask a facilitator to choose the correct record.');
    elsif v_matches=0 then return null; end if;
    select * into v_participant from public.runtime_participants
     where event_id=v_event.event_id
       and public.exos_normalize_participant_name(display_name)=v_normalized
       and merged_into_participant_id is null
     order by joined_at,participant_id limit 1;
    return public.exos_identity_payload(v_participant,v_event)
        || jsonb_build_object('Rejoined',true,'RecoveryRequired',true);
end; $$;

create or replace function public.exos_admin_transfer_leader(
    p_event_id text,p_team_id text,p_participant_id uuid,p_actor text
)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_target public.runtime_participants%rowtype; v_before jsonb;
begin
    select * into v_target from public.runtime_participants
     where participant_id=p_participant_id and event_id=trim(p_event_id)
       and team_id=trim(p_team_id) and merged_into_participant_id is null for update;
    if not found then raise exception 'Participant is not an active member of this team'; end if;
    select jsonb_agg(to_jsonb(p)) into v_before from public.runtime_participants p
     where event_id=trim(p_event_id) and team_id=trim(p_team_id);
    perform set_config('exos.identity_override','on',true);
    update public.runtime_participants set status=replace(status,'|LEADER','')
     where event_id=trim(p_event_id) and team_id=trim(p_team_id);
    update public.runtime_participants set status=replace(status,'|LEADER','')||'|LEADER'
     where participant_id=p_participant_id;
    insert into public.runtime_identity_audit_log(event_id,action,actor,canonical_participant_id,before_state,after_state)
    values(trim(p_event_id),'TRANSFER_LEADER',trim(p_actor),p_participant_id,coalesce(v_before,'[]'),
        jsonb_build_object('TeamID',trim(p_team_id),'LeaderParticipantID',p_participant_id));
    return jsonb_build_object('Transferred',true,'ParticipantID',p_participant_id,'TeamID',trim(p_team_id));
end; $$;

create or replace function public.exos_admin_move_participant(
    p_participant_id uuid,p_team_id text,p_actor text,p_reason text
)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_participant public.runtime_participants%rowtype; v_team public.runtime_teams%rowtype;
begin
    select * into v_participant from public.runtime_participants where participant_id=p_participant_id for update;
    if not found then raise exception 'Participant not found'; end if;
    select * into v_team from public.runtime_teams where event_id=v_participant.event_id and team_id=trim(p_team_id);
    if not found then raise exception 'Team not found'; end if;
    perform set_config('exos.identity_override','on',true);
    update public.runtime_participants set team_id=v_team.team_id,team_name=v_team.team_name,
        country=regexp_replace(v_team.team_name,'^\S+\s*',''),flag=split_part(v_team.team_name,' ',1),
        status='COUNTRY:'||regexp_replace(v_team.team_name,'^\S+\s*','')
     where participant_id=p_participant_id;
    insert into public.runtime_identity_audit_log(event_id,action,actor,canonical_participant_id,before_state,after_state,reason)
    values(v_participant.event_id,'MOVE_PARTICIPANT',trim(p_actor),p_participant_id,to_jsonb(v_participant),
        jsonb_build_object('TeamID',v_team.team_id,'Team',v_team.team_name),trim(p_reason));
    return jsonb_build_object('Moved',true,'ParticipantID',p_participant_id,'TeamID',v_team.team_id);
end; $$;

create or replace function public.exos_admin_duplicate_decision(
    p_event_id text,p_canonical_participant_id uuid,p_duplicate_participant_id uuid,
    p_decision text,p_actor text,p_reason text
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
        perform set_config('exos.identity_override','on',true);
        update public.runtime_submissions set participant_id=v_canonical.participant_id
         where participant_id=v_duplicate.participant_id;
        update public.runtime_participants set points=greatest(v_canonical.points,v_duplicate.points),
            status=case when v_canonical.status like '%|LEADER%' or v_duplicate.status like '%|LEADER%'
                then replace(v_canonical.status,'|LEADER','')||'|LEADER' else v_canonical.status end
         where participant_id=v_canonical.participant_id;
        update public.runtime_participants set merged_into_participant_id=v_canonical.participant_id
         where participant_id=v_duplicate.participant_id;
    end if;
    insert into public.runtime_identity_audit_log(
        event_id,action,actor,canonical_participant_id,affected_participant_id,before_state,after_state,reason
    ) values(trim(p_event_id),'DUPLICATE_'||upper(trim(p_decision)),trim(p_actor),
        v_canonical.participant_id,v_duplicate.participant_id,
        jsonb_build_object('Canonical',to_jsonb(v_canonical),'Duplicate',to_jsonb(v_duplicate)),
        jsonb_build_object('Merged',upper(trim(p_decision))='MERGE'),trim(p_reason));
    return jsonb_build_object('Decision',upper(trim(p_decision)),
        'CanonicalParticipantID',v_canonical.participant_id,'DuplicateParticipantID',v_duplicate.participant_id);
end; $$;

create or replace function public.exos_runtime_control_state(p_event_id text)
returns jsonb language sql stable security definer set search_path=public as $$
    select coalesce(runtime_control_state,'{}'::jsonb) from public.runtime_events
     where event_id=trim(p_event_id) limit 1;
$$;

create or replace function public.exos_set_runtime_control_state(
    p_event_id text,p_key text,p_value jsonb
)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_state jsonb;
begin
    if trim(p_key) not in ('StageTimers','ProjectorBroadcast','CurrentStageStatus','RegistrationOpen') then
        raise exception 'Unsupported runtime control key';
    end if;
    update public.runtime_events
       set runtime_control_state=jsonb_set(coalesce(runtime_control_state,'{}'::jsonb),
            array[trim(p_key)],coalesce(p_value,'null'::jsonb),true),updated_at=now()
     where event_id=trim(p_event_id) returning runtime_control_state into v_state;
    if not found then raise exception 'Runtime event not found'; end if;
    return v_state;
end; $$;

revoke all on function public.exos_join_event_v2(text,text,text,text) from public;
revoke all on function public.exos_claim_team_leader(text) from public;
revoke all on function public.exos_restore_join(text,text,text) from public;
revoke all on function public.exos_runtime_control_state(text) from public;
revoke all on function public.exos_set_runtime_control_state(text,text,jsonb) from public;
grant execute on function public.exos_join_event_v2(text,text,text,text) to anon,authenticated;
grant execute on function public.exos_claim_team_leader(text) to anon,authenticated;
grant execute on function public.exos_restore_join(text,text,text) to anon,authenticated;
grant execute on function public.exos_runtime_control_state(text) to service_role;
grant execute on function public.exos_set_runtime_control_state(text,text,jsonb) to service_role;
