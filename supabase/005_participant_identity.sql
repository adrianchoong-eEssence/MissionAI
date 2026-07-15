alter table public.runtime_participants
    drop constraint if exists runtime_participants_event_id_normalized_name_key;

create index if not exists runtime_participants_event_name_idx
    on public.runtime_participants(event_id, normalized_name);

alter table public.runtime_submissions
    add column if not exists participant_id uuid
        references public.runtime_participants(participant_id)
        on delete set null;

create index if not exists runtime_submissions_participant_idx
    on public.runtime_submissions(participant_id);

create or replace function public.exos_join_event(
    p_join_code text,
    p_participant_name text
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
    v_team_name text;
    v_team_count integer;
begin
    if nullif(trim(p_participant_name), '') is null then
        raise exception 'Participant full name is required';
    end if;

    v_normalized_name := lower(
        regexp_replace(trim(p_participant_name), '\s+', ' ', 'g')
    );

    select *
      into v_event
      from public.runtime_events
     where join_code = upper(trim(p_join_code))
       and active = true
     for update;

    if not found then
        raise exception 'Invalid or inactive join code';
    end if;

    select count(*)
      into v_team_count
      from public.runtime_teams
     where event_id = v_event.event_id;

    if v_team_count < 1 then
        raise exception 'No teams are published for this event';
    end if;

    select team_name
      into v_team_name
      from public.runtime_teams
     where event_id = v_event.event_id
       and position = mod(v_event.next_team_index, v_team_count);

    if v_team_name is null then
        raise exception 'Team allocation is incomplete for this event';
    end if;

    insert into public.runtime_participants (
        event_id,
        normalized_name,
        display_name,
        team_name
    ) values (
        v_event.event_id,
        v_normalized_name,
        trim(p_participant_name),
        v_team_name
    )
    returning * into v_participant;

    update public.runtime_events
       set next_team_index = mod(
               v_event.next_team_index + 1,
               v_team_count
           ),
           updated_at = now()
     where event_id = v_event.event_id;

    return jsonb_build_object(
        'ParticipantID', v_participant.participant_id::text,
        'EventID', v_event.event_id,
        'EventName', v_event.event_name,
        'Name', v_participant.display_name,
        'Team', v_participant.team_name,
        'Points', v_participant.points,
        'Status', v_participant.status,
        'SessionToken', v_participant.session_token::text,
        'Rejoined', false
    );
end;
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
        'Points', participant.points,
        'Status', participant.status,
        'SessionToken', participant.session_token::text
    )
      from public.runtime_participants participant
      join public.runtime_events event using (event_id)
     where participant.session_token::text = trim(p_session_token)
     limit 1;
$$;

create or replace function public.exos_save_submission_v2(
    p_submission_id text,
    p_event_id text,
    p_mission_id text,
    p_team_name text,
    p_participant_name text,
    p_session_token text,
    p_image_url text default '',
    p_drive_file_id text default '',
    p_submission_type text default '',
    p_metric1 text default '',
    p_metric2 text default '',
    p_metric3 text default '',
    p_score text default '',
    p_status text default 'PENDING',
    p_judged text default 'No',
    p_remarks text default '',
    p_submitted_at text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_participant public.runtime_participants%rowtype;
    v_submission_key text;
    v_submission public.runtime_submissions%rowtype;
begin
    select *
      into v_participant
      from public.runtime_participants
     where event_id = trim(p_event_id)
       and session_token::text = trim(p_session_token)
     limit 1;

    if not found then
        raise exception 'Invalid participant session';
    end if;

    if nullif(trim(p_mission_id), '') is null then
        raise exception 'Mission ID is required';
    end if;

    if upper(trim(coalesce(p_submission_type, ''))) = 'NASI' then
        v_submission_key := 'PARTICIPANT:' ||
            v_participant.participant_id::text;
    else
        v_submission_key := 'TEAM:' || lower(
            regexp_replace(v_participant.team_name, '\s+', ' ', 'g')
        );
    end if;

    select *
      into v_submission
      from public.runtime_submissions
     where submission_id = trim(p_submission_id)
        or (
            event_id = trim(p_event_id)
            and mission_id = trim(p_mission_id)
            and submission_key = v_submission_key
        )
     order by created_at
     limit 1;

    if found then
        return to_jsonb(v_submission);
    end if;

    insert into public.runtime_submissions (
        submission_id,
        event_id,
        mission_id,
        submission_key,
        participant_id,
        team_name,
        participant_name,
        image_url,
        drive_file_id,
        submission_type,
        metric1,
        metric2,
        metric3,
        score,
        status,
        judged,
        remarks,
        submitted_at
    ) values (
        trim(p_submission_id),
        trim(p_event_id),
        trim(p_mission_id),
        v_submission_key,
        v_participant.participant_id,
        v_participant.team_name,
        v_participant.display_name,
        coalesce(p_image_url, ''),
        coalesce(p_drive_file_id, ''),
        upper(trim(coalesce(p_submission_type, ''))),
        coalesce(p_metric1, ''),
        coalesce(p_metric2, ''),
        coalesce(p_metric3, ''),
        coalesce(p_score, ''),
        upper(trim(coalesce(p_status, 'PENDING'))),
        coalesce(p_judged, 'No'),
        coalesce(p_remarks, ''),
        coalesce(p_submitted_at, '')
    )
    returning * into v_submission;

    return to_jsonb(v_submission);
end;
$$;

create or replace function public.exos_get_submission_v2(
    p_event_id text,
    p_mission_id text,
    p_scope_type text,
    p_scope_value text,
    p_session_token text default ''
)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
    v_participant_id uuid;
    v_submission_key text;
    v_submission public.runtime_submissions%rowtype;
begin
    if upper(trim(p_scope_type)) = 'PARTICIPANT' then
        select participant_id
          into v_participant_id
          from public.runtime_participants
         where event_id = trim(p_event_id)
           and session_token::text = trim(p_session_token)
         limit 1;

        if not found then
            return null;
        end if;
        v_submission_key := 'PARTICIPANT:' || v_participant_id::text;
    else
        v_submission_key := 'TEAM:' || lower(
            regexp_replace(trim(p_scope_value), '\s+', ' ', 'g')
        );
    end if;

    select *
      into v_submission
      from public.runtime_submissions
     where event_id = trim(p_event_id)
       and mission_id = trim(p_mission_id)
       and submission_key = v_submission_key
     limit 1;

    if not found then
        return null;
    end if;
    return to_jsonb(v_submission);
end;
$$;

revoke all on function public.exos_save_submission_v2(
    text, text, text, text, text, text, text, text, text,
    text, text, text, text, text, text, text, text
) from public;
revoke all on function public.exos_get_submission_v2(
    text, text, text, text, text
) from public;

grant execute on function public.exos_save_submission_v2(
    text, text, text, text, text, text, text, text, text,
    text, text, text, text, text, text, text, text
) to anon, authenticated, service_role;
grant execute on function public.exos_get_submission_v2(
    text, text, text, text, text
) to anon, authenticated, service_role;
