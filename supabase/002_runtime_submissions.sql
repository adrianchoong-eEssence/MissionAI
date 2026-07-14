create table if not exists public.runtime_submissions (
    submission_id text primary key,
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    mission_id text not null,
    submission_key text not null,
    team_name text not null default '',
    participant_name text not null default '',
    image_url text not null default '',
    drive_file_id text not null default '',
    submission_type text not null default '',
    metric1 text not null default '',
    metric2 text not null default '',
    metric3 text not null default '',
    score text not null default '',
    status text not null default 'PENDING',
    judged text not null default 'No',
    remarks text not null default '',
    submitted_at text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (event_id, mission_id, submission_key)
);

create index if not exists runtime_submissions_event_idx
    on public.runtime_submissions(event_id);

create index if not exists runtime_submissions_mission_idx
    on public.runtime_submissions(event_id, mission_id);

alter table public.runtime_submissions enable row level security;

create or replace function public.exos_save_submission(
    p_submission_id text,
    p_event_id text,
    p_mission_id text,
    p_team_name text,
    p_participant_name text,
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
    v_submission_key text;
    v_submission public.runtime_submissions%rowtype;
begin
    if nullif(trim(p_event_id), '') is null then
        raise exception 'Event ID is required';
    end if;

    if nullif(trim(p_mission_id), '') is null then
        raise exception 'Mission ID is required';
    end if;

    if upper(trim(coalesce(p_submission_type, ''))) = 'NASI' then
        v_submission_key := 'PARTICIPANT:' || lower(
            regexp_replace(trim(coalesce(p_participant_name, '')), '\s+', ' ', 'g')
        );
    else
        v_submission_key := 'TEAM:' || lower(
            regexp_replace(trim(coalesce(p_team_name, '')), '\s+', ' ', 'g')
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
        trim(coalesce(p_team_name, '')),
        trim(coalesce(p_participant_name, '')),
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

create or replace function public.exos_get_submission(
    p_event_id text,
    p_mission_id text,
    p_scope_type text,
    p_scope_value text
)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
    select to_jsonb(submission)
      from public.runtime_submissions submission
     where event_id = trim(p_event_id)
       and mission_id = trim(p_mission_id)
       and submission_key = (
           case
               when upper(trim(p_scope_type)) = 'PARTICIPANT'
                   then 'PARTICIPANT:' || lower(
                       regexp_replace(trim(p_scope_value), '\s+', ' ', 'g')
                   )
               else 'TEAM:' || lower(
                   regexp_replace(trim(p_scope_value), '\s+', ' ', 'g')
               )
           end
       )
     limit 1;
$$;

create or replace function public.exos_update_submission(
    p_submission_id text,
    p_score text default '',
    p_status text default 'APPROVED',
    p_judged text default 'Yes',
    p_remarks text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_submission public.runtime_submissions%rowtype;
begin
    update public.runtime_submissions
       set score = coalesce(p_score, ''),
           status = upper(trim(coalesce(p_status, 'APPROVED'))),
           judged = coalesce(p_judged, 'Yes'),
           remarks = coalesce(p_remarks, ''),
           updated_at = now()
     where submission_id = trim(p_submission_id)
    returning * into v_submission;

    if not found then
        return jsonb_build_object('Updated', false);
    end if;

    return jsonb_build_object(
        'Updated', true,
        'Submission', to_jsonb(v_submission)
    );
end;
$$;

revoke all on table public.runtime_submissions from anon, authenticated;

revoke all on function public.exos_save_submission(
    text, text, text, text, text, text, text, text,
    text, text, text, text, text, text, text, text
) from public;
revoke all on function public.exos_get_submission(text, text, text, text)
    from public;
revoke all on function public.exos_update_submission(text, text, text, text, text)
    from public;

grant execute on function public.exos_save_submission(
    text, text, text, text, text, text, text, text,
    text, text, text, text, text, text, text, text
) to anon, authenticated, service_role;
grant execute on function public.exos_get_submission(text, text, text, text)
    to anon, authenticated, service_role;
grant execute on function public.exos_update_submission(text, text, text, text, text)
    to service_role;
