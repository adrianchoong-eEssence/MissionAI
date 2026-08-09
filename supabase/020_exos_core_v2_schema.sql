-- EXOS Core v2: canonical runtime foundation schema.
-- Intent: introduce v2 runtime entities without modifying existing v1 structures.
do $$
declare
    legacy_table_names text[] := array[
        'runtime_events', 'runtime_participants', 'runtime_submissions', 'runtime_teams',
        'runtime_missions', 'runtime_teams_v2', 'runtime_participants_v2',
        'runtime_submissions_v2', 'formula_race_team_access', 'formula_race_team_checkpoints',
        'runtime_mission_submissions', 'runtime_mission_evidence', 'runtime_mission_status',
        'formula_race_results', 'formula_race_checkpoint_runtime'
    ];
begin
    if exists(
        select 1
          from information_schema.tables t
         where t.table_schema = 'public'
           and t.table_name = any(legacy_table_names)
    ) then
        raise exception 'Legacy EXOS runtime tables detected. Do not run 020 on a project containing legacy runtime objects.';
    end if;

    if exists(
        select 1
          from information_schema.routines r
         where r.routine_schema = 'public'
           and r.routine_name in ('exos_join_event','exos_publish_event','join_player_by_code')
    ) then
        raise exception 'Legacy EXOS RPCs detected in this project. Use the clean-room migration only on an empty schema.';
    end if;
end $$;

create extension if not exists pgcrypto;

create extension if not exists pg_trgm;

create type if not exists public.exos_v2_activity_type as enum (
    'STANDARD',
    'MISSION',
    'CHECKPOINT',
    'REFLECTION',
    'LOCATION',
    'MARKETPLACE',
    'BUILD',
    'JUDGING',
    'RACE',
    'AI',
    'CUSTOM'
);

create type if not exists public.exos_v2_scoring_mode as enum (
    'TEAM_COMPETITIVE',
    'ENTERPRISE',
    'NON_SCORING'
);

create type if not exists public.exos_v2_submission_status as enum (
    'PENDING',
    'SUBMITTED',
    'APPROVED',
    'REJECTED',
    'WITHDRAWN'
);

create type if not exists public.exos_v2_review_decision as enum (
    'APPROVE',
    'REJECT',
    'PENDING'
);

create type if not exists public.exos_v2_build_status as enum (
    'NOT_STARTED',
    'IN_PROGRESS',
    'BLOCKED',
    'COMPLETED'
);

create table if not exists public.events_v2 (
    event_id text primary key,
    event_name text not null,
    join_code text unique not null,
    event_type text not null default 'STANDARD',
    programme_type text not null default 'AGILE',
    scoring_mode public.exos_v2_scoring_mode not null default 'TEAM_COMPETITIVE',
    lifecycle_status text not null default 'DRAFT',
    event_payload jsonb not null default '{}'::jsonb,
    published_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.programmes_v2 (
    programme_id text primary key,
    event_id text not null references public.events_v2(event_id) on delete cascade,
    programme_name text not null,
    programme_type text not null default 'STANDARD',
    programme_schema_version integer not null default 1,
    module_count integer not null default 0,
    is_active boolean not null default true,
    published_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (event_id, programme_name)
);

create table if not exists public.modules_v2 (
    module_id text primary key,
    programme_id text not null references public.programmes_v2(programme_id) on delete cascade,
    module_name text not null,
    activity_sequence integer not null default 0,
    module_payload jsonb not null default '{}'::jsonb,
    scoring_mode public.exos_v2_scoring_mode not null default 'TEAM_COMPETITIVE',
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (programme_id, module_id)
);

create table if not exists public.activities_v2 (
    activity_id text primary key,
    module_id text not null references public.modules_v2(module_id) on delete cascade,
    programme_id text not null references public.programmes_v2(programme_id) on delete cascade,
    activity_type public.exos_v2_activity_type not null default 'STANDARD',
    scoring_mode public.exos_v2_scoring_mode not null default 'TEAM_COMPETITIVE',
    activity_name text not null,
    activity_order integer not null default 0,
    duration_seconds integer not null default 0,
    activity_payload jsonb not null default '{}'::jsonb,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (module_id, activity_order),
    unique (programme_id, activity_id)
);

create table if not exists public.teams_v2 (
    team_id text primary key,
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_name text not null,
    country text not null,
    team_flag text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    unique (event_id, team_name),
    unique (event_id, team_id)
);

create index if not exists teams_v2_event_idx on public.teams_v2(event_id);

create table if not exists public.participants_v2 (
    participant_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete restrict,
    normalized_name text not null,
    display_name text not null,
    participant_payload jsonb not null default '{}'::jsonb,
    country text not null,
    flag text not null,
    participant_status text not null default 'REGISTERED',
    is_leader boolean not null default false,
    team_leader_at timestamptz,
    intelligence_credits integer not null default 0,
    merged_into_participant_id uuid references public.participants_v2(participant_id) on delete set null,
    is_archived boolean not null default false,
    created_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    unique (event_id, participant_id)
);

create table if not exists public.participant_sessions_v2 (
    participant_session_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    participant_id uuid not null references public.participants_v2(participant_id) on delete cascade,
    device_id text not null,
    session_token uuid not null unique default gen_random_uuid(),
    idempotency_key text not null,
    joined_from_client text,
    last_seen_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    is_active boolean not null default true,
    unique (event_id, participant_id, idempotency_key),
    unique (event_id, idempotency_key)
);

create index if not exists participant_sessions_v2_event_idx on public.participant_sessions_v2(event_id);

create table if not exists public.activity_runtime_v2 (
    runtime_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete restrict,
    participant_id uuid not null references public.participants_v2(participant_id) on delete cascade,
    activity_id text not null references public.activities_v2(activity_id) on delete cascade,
    session_id uuid references public.participant_sessions_v2(participant_session_id) on delete set null,
    state_payload jsonb not null default '{}'::jsonb,
    activity_started_at timestamptz,
    activity_ended_at timestamptz,
    checkpoint_count integer not null default 0,
    completion_ratio numeric(6,2) not null default 0,
    is_completed boolean not null default false,
    updated_at timestamptz not null default now(),
    unique (event_id, participant_id, activity_id)
);

create table if not exists public.submissions_v2 (
    submission_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete restrict,
    participant_id uuid not null references public.participants_v2(participant_id) on delete cascade,
    activity_id text not null references public.activities_v2(activity_id) on delete cascade,
    runtime_id uuid references public.activity_runtime_v2(runtime_id) on delete set null,
    submission_key text not null,
    submission_status public.exos_v2_submission_status not null default 'PENDING',
    submission_payload jsonb not null default '{}'::jsonb,
    submitted_at timestamptz not null default now(),
    reviewed_at timestamptz,
    reviewed_by text,
    score numeric(12,2),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (event_id, submission_key),
    unique (submission_id, event_id, activity_id)
);

create index if not exists submissions_v2_event_idx on public.submissions_v2(event_id);
create index if not exists submissions_v2_team_idx on public.submissions_v2(team_id);

create table if not exists public.submission_evidence_v2 (
    evidence_id uuid primary key default gen_random_uuid(),
    submission_id uuid not null references public.submissions_v2(submission_id) on delete cascade,
    evidence_type text not null,
    evidence_uri text,
    evidence_payload jsonb not null default '{}'::jsonb,
    captured_by text,
    captured_at timestamptz not null default now()
);

create table if not exists public.reviews_v2 (
    review_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    submission_id uuid not null references public.submissions_v2(submission_id) on delete cascade,
    reviewer text not null,
    decision public.exos_v2_review_decision not null default 'PENDING',
    score_points numeric(12,2) default 0,
    rationale text,
    reviewed_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    unique (submission_id, reviewer)
);

create table if not exists public.score_transactions_v2 (
    score_transaction_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete restrict,
    submission_id uuid references public.submissions_v2(submission_id) on delete set null,
    scoring_mode public.exos_v2_scoring_mode not null default 'TEAM_COMPETITIVE',
    score_delta numeric(12,2) not null,
    reason text not null,
    idempotency_key text not null,
    source_reference jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    created_by text,
    unique (event_id, idempotency_key),
    check (
        (scoring_mode = 'TEAM_COMPETITIVE' and score_delta >= -1000 and score_delta <= 1000)
        or scoring_mode <> 'TEAM_COMPETITIVE'
    )
);

create index if not exists score_transactions_v2_event_team_idx on public.score_transactions_v2(event_id, team_id);

create table if not exists public.credit_transactions_v2 (
    credit_transaction_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete restrict,
    participant_id uuid references public.participants_v2(participant_id) on delete set null,
    transaction_type text not null,
    amount integer not null,
    idempotency_key text not null,
    reason text not null,
    created_at timestamptz not null default now(),
    created_by text,
    unique (event_id, idempotency_key),
    check (amount <> 0)
);

create index if not exists credit_transactions_v2_event_team_idx on public.credit_transactions_v2(event_id, team_id);

create table if not exists public.marketplace_items_v2 (
    item_id text primary key,
    event_id text not null references public.events_v2(event_id) on delete cascade,
    item_name text not null,
    item_type text not null,
    unit_cost_credits integer not null default 0,
    stock_limit integer,
    is_active boolean not null default true,
    item_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (event_id, item_name)
);

create table if not exists public.marketplace_transactions_v2 (
    marketplace_transaction_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete restrict,
    item_id text not null references public.marketplace_items_v2(item_id) on delete restrict,
    credit_transaction_id uuid references public.credit_transactions_v2(credit_transaction_id) on delete set null,
    quantity integer not null default 1,
    amount_paid integer not null default 0,
    status text not null default 'PENDING',
    idempotency_key text not null,
    purchased_at timestamptz not null default now(),
    unique (event_id, idempotency_key),
    check (quantity > 0 and amount_paid >= 0)
);

create table if not exists public.build_status_v2 (
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete restrict,
    activity_id text not null references public.activities_v2(activity_id) on delete cascade,
    build_status public.exos_v2_build_status not null default 'NOT_STARTED',
    progress_pct numeric(5,2) not null default 0,
    build_payload jsonb not null default '{}'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    last_updated timestamptz not null default now(),
    unique (event_id, team_id, activity_id)
);

create table if not exists public.judging_scores_v2 (
    judging_score_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete restrict,
    activity_id text not null references public.activities_v2(activity_id) on delete cascade,
    judge_name text not null,
    score_dimension text not null,
    score_value numeric(12,2) not null,
    decision text not null default 'PENDING',
    rationale text,
    recorded_at timestamptz not null default now(),
    unique (event_id, team_id, activity_id, judge_name, score_dimension)
);

create table if not exists public.race_results_v2 (
    race_result_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete restrict,
    activity_id text not null references public.activities_v2(activity_id) on delete cascade,
    checkpoint text,
    ranking_position integer,
    result_payload jsonb not null default '{}'::jsonb,
    locked boolean not null default false,
    recorded_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (event_id, team_id, activity_id, checkpoint)
);

create table if not exists public.projector_state_v2 (
    event_id text not null references public.events_v2(event_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete restrict,
    projection_stage text not null,
    state_payload jsonb not null default '{}'::jsonb,
    visible_to_event bool not null default false,
    updated_at timestamptz not null default now(),
    unique (event_id, team_id)
);

create table if not exists public.location_checkpoints_v2 (
    checkpoint_id text primary key,
    event_id text not null references public.events_v2(event_id) on delete cascade,
    activity_id text not null references public.activities_v2(activity_id) on delete cascade,
    team_id text not null references public.teams_v2(team_id) on delete restrict,
    checkpoint_name text not null,
    expected_latitude double precision not null,
    expected_longitude double precision not null,
    allowed_radius_m numeric not null default 100,
    sequence_number integer not null default 0,
    checkpoint_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (event_id, activity_id, sequence_number)
);

create table if not exists public.location_evidence_v2 (
    location_evidence_id uuid primary key default gen_random_uuid(),
    checkpoint_id text not null references public.location_checkpoints_v2(checkpoint_id) on delete cascade,
    submission_id uuid references public.submissions_v2(submission_id) on delete set null,
    participant_session_id uuid references public.participant_sessions_v2(participant_session_id) on delete set null,
    latitude double precision not null,
    longitude double precision not null,
    accuracy double precision,
    captured_at timestamptz not null default now(),
    verification_status text not null default 'PENDING',
    verification_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.ai_jobs_v2 (
    ai_job_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.events_v2(event_id) on delete cascade,
    job_type text not null,
    target_entity text not null,
    target_id text not null,
    status text not null default 'QUEUED',
    job_payload jsonb not null default '{}'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    created_by text,
    created_at timestamptz not null default now(),
    unique (event_id, job_type, target_entity, target_id)
);

create table if not exists public.ai_results_v2 (
    ai_result_id uuid primary key default gen_random_uuid(),
    ai_job_id uuid not null references public.ai_jobs_v2(ai_job_id) on delete cascade,
    event_id text not null references public.events_v2(event_id) on delete cascade,
    result_payload jsonb not null default '{}'::jsonb,
    confidence numeric(5,4),
    is_approved boolean not null default false,
    reviewed_by text,
    reviewed_at timestamptz,
    created_at timestamptz not null default now(),
    unique (ai_job_id)
);

create table if not exists public.audit_log_v2 (
    audit_id bigserial primary key,
    event_id text,
    actor text not null,
    action text not null,
    entity_type text not null,
    entity_id text not null,
    before_state jsonb not null default '{}'::jsonb,
    after_state jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

alter table public.events_v2 enable row level security;
alter table public.programmes_v2 enable row level security;
alter table public.modules_v2 enable row level security;
alter table public.activities_v2 enable row level security;
alter table public.teams_v2 enable row level security;
alter table public.participants_v2 enable row level security;
alter table public.participant_sessions_v2 enable row level security;
alter table public.activity_runtime_v2 enable row level security;
alter table public.submissions_v2 enable row level security;
alter table public.submission_evidence_v2 enable row level security;
alter table public.reviews_v2 enable row level security;
alter table public.score_transactions_v2 enable row level security;
alter table public.credit_transactions_v2 enable row level security;
alter table public.marketplace_items_v2 enable row level security;
alter table public.marketplace_transactions_v2 enable row level security;
alter table public.build_status_v2 enable row level security;
alter table public.judging_scores_v2 enable row level security;
alter table public.race_results_v2 enable row level security;
alter table public.projector_state_v2 enable row level security;
alter table public.location_checkpoints_v2 enable row level security;
alter table public.location_evidence_v2 enable row level security;
alter table public.ai_jobs_v2 enable row level security;
alter table public.ai_results_v2 enable row level security;
alter table public.audit_log_v2 enable row level security;

do $$
declare
    table_names text[] := array[
        'events_v2','programmes_v2','modules_v2','activities_v2','teams_v2',
        'participants_v2','participant_sessions_v2','activity_runtime_v2','submissions_v2',
        'submission_evidence_v2','reviews_v2','score_transactions_v2','credit_transactions_v2',
        'marketplace_items_v2','marketplace_transactions_v2','build_status_v2','judging_scores_v2',
        'race_results_v2','projector_state_v2','location_checkpoints_v2','location_evidence_v2',
        'ai_jobs_v2','ai_results_v2','audit_log_v2'
    ];
    t text;
begin
    foreach t in array table_names loop
        execute format(
            'create policy if not exists %I on public.%I for all to service_role using (true) with check (true);',
            t || '_sr_all_policy', t
        );
    end loop;
end $$;

create or replace function public.exos_v2_normalize_participant_name(p_name text)
returns text language sql immutable as $$
    select lower(trim(regexp_replace(p_name, '\s+', ' ', 'g')));
$$;

create or replace function public.exos_v2_next_team_id(p_event_id text)
returns text language sql stable as $$
    select t.team_id
      from public.teams_v2 t
     left join public.participants_v2 p on p.event_id=t.event_id and p.team_id=t.team_id and p.merged_into_participant_id is null
     where t.event_id=trim(p_event_id)
     group by t.team_id, t.event_id
    order by count(p.participant_id), t.team_id
    limit 1;
$$;

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
        'Team', t.team_name,
        'Country', p.country,
        'Flag', p.flag,
        'Name', p.display_name,
        'SessionToken', s.session_token::text
    )
      from public.participants_v2 p
      join public.events_v2 e on e.event_id = p.event_id
      join public.teams_v2 t on t.team_id = p.team_id
      left join public.participant_sessions_v2 s on s.participant_id = p.participant_id
         and s.event_id = p.event_id
         and s.is_active
      where p.event_id = trim(p_event_id)
        and p.participant_id = p_participant_id
      limit 1;
$$;

create or replace function public.exos_v2_publish_event(
    p_event_id text,
    p_join_code text,
    p_event_name text,
    p_teams jsonb,
    p_scoring_mode public.exos_v2_scoring_mode default 'TEAM_COMPETITIVE',
    p_event_type text default 'STANDARD'
)
returns jsonb
language plpgsql security definer
set search_path = public, extensions as $$
begin
    if nullif(trim(p_event_id),'') is null then
        raise exception 'Event ID is required';
    end if;
    if nullif(trim(p_join_code),'') is null then
        raise exception 'Join code is required';
    end if;
    if nullif(trim(p_event_name),'') is null then
        raise exception 'Event name is required';
    end if;
    if (select count(*) from jsonb_array_elements(coalesce(p_teams,'[]'::jsonb))) < 1 then
        raise exception 'At least one team payload is required';
    end if;

    insert into public.events_v2 (event_id,event_name,join_code,scoring_mode,event_type,programme_type,published_at,updated_at)
    values (trim(p_event_id), trim(p_event_name), upper(trim(p_join_code)), p_scoring_mode, trim(p_event_type), 'STANDARD', now(), now())
    on conflict (event_id) do update
      set event_name=excluded.event_name,
          join_code=excluded.join_code,
          scoring_mode=excluded.scoring_mode,
          event_type=excluded.event_type,
          updated_at=now(),
          published_at=case when events_v2.published_at is null then now() else events_v2.published_at end;

    delete from public.teams_v2 where event_id=trim(p_event_id);
    insert into public.teams_v2 (team_id,event_id,team_name,country,team_flag)
    select coalesce(nullif(trim(team->>'team_id'),''), 'TEAM-' || lpad((row_number() over())::text, 2, '0')),
           trim(p_event_id),
           trim(team->>'team_name'),
           trim(team->>'country'),
           coalesce(trim(team->>'team_flag'), 'FLAG')
      from jsonb_array_elements(p_teams) as team
     where nullif(trim(team->>'team_name'),'') is not null;

    return jsonb_build_object(
        'EventID', trim(p_event_id),
        'JoinCode', upper(trim(p_join_code)),
        'EventName', trim(p_event_name),
        'TeamsPublished', (select count(*) from public.teams_v2 where event_id=trim(p_event_id))
    );
end;
$$;

create or replace function public.exos_v2_join_event_v2(
    p_join_code text,
    p_participant_name text,
    p_device_id text,
    p_requested_team_id text default ''
)
returns jsonb
language plpgsql security definer
set search_path = public, extensions as $$
declare
    v_event public.events_v2%rowtype;
    v_normalized text;
    v_idempotency_key text;
    v_team_id text;
    v_existing_id uuid;
    v_count integer;
    v_participant public.participants_v2%rowtype;
    v_session public.participant_sessions_v2%rowtype;
    v_event_lock bigint;
    v_identity_lock bigint;
    v_next_participant_id uuid := gen_random_uuid();
begin
    if nullif(trim(p_participant_name),'') is null then raise exception 'Participant full name is required'; end if;
    if nullif(trim(p_device_id),'') is null then raise exception 'Device identifier is required'; end if;

    select * into v_event from public.events_v2
     where join_code=upper(trim(p_join_code)) and published_at is not null
     for update;
    if not found then raise exception 'Invalid or unpublished join code'; end if;

    v_normalized := public.exos_v2_normalize_participant_name(p_participant_name);
    v_idempotency_key := encode(digest(v_event.event_id||'|'||v_normalized||'|'||lower(trim(p_device_id)), 'sha256'), 'hex');
    v_event_lock := hashtextextended(v_event.event_id, 11);
    v_identity_lock := hashtextextended(v_event.event_id || '|' || v_normalized, 17);
    perform pg_advisory_xact_lock(v_event_lock);
    perform pg_advisory_xact_lock(v_identity_lock);

    select participant_id into v_existing_id
      from public.participant_sessions_v2 s
      where s.event_id=v_event.event_id and s.idempotency_key=v_idempotency_key and s.is_active
      order by s.created_at desc limit 1;

    if v_existing_id is not null then
        select * into v_participant from public.participants_v2 where participant_id=v_existing_id;
        if v_participant.participant_id is null or v_participant.merged_into_participant_id is not null then
            return jsonb_build_object(
                'RecoveryRequired', true,
                'Ambiguous', false,
                'EventID', v_event.event_id,
                'Name', trim(p_participant_name),
                'Message', 'Identity is merged. Recovery required with facilitator.'
            );
        end if;
        select * into v_session from public.participant_sessions_v2
          where participant_id=v_existing_id and event_id=v_event.event_id and idempotency_key=v_idempotency_key
          order by created_at desc limit 1;
        if v_session.participant_session_id is not null then
            update public.participant_sessions_v2
               set last_seen_at = now(), is_active = true
             where participant_session_id = v_session.participant_session_id;
            update public.participants_v2
               set last_seen_at = now()
             where participant_id = v_existing_id;
            return public.exos_v2_identity_payload(v_event.event_id, v_existing_id);
        end if;
    end if;

    select count(*) into v_count
      from public.participants_v2 p
     where p.event_id=v_event.event_id and p.normalized_name=v_normalized and p.merged_into_participant_id is null;

    if v_count >= 1 then
        return jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', v_count > 1,
            'EventID', v_event.event_id,
            'Name', trim(p_participant_name),
            'Message', 'Same name exists for different device/session. Reconnect with original device or recover with facilitator.'
        );
    end if;

    if nullif(trim(p_requested_team_id),'') is not null then
        select team_id into v_team_id from public.teams_v2
          where event_id=v_event.event_id and team_id=trim(p_requested_team_id);
        if v_team_id is null then raise exception 'Requested team is not valid for this event'; end if;
    else
        v_team_id := public.exos_v2_next_team_id(v_event.event_id);
    end if;

    if v_team_id is null then raise exception 'No teams are published for this event'; end if;

    insert into public.participants_v2 (
        participant_id,event_id,team_id,normalized_name,display_name,country,flag,participant_payload
    )
    values (
        v_next_participant_id,v_event.event_id,v_team_id,v_normalized,trim(p_participant_name),
        (select country from public.teams_v2 where team_id=v_team_id),
        (select team_flag from public.teams_v2 where team_id=v_team_id),
        '{}'::jsonb
    )
    returning * into v_participant;

    insert into public.participant_sessions_v2 (
        event_id,participant_id,device_id,idempotency_key
    ) values (
        v_event.event_id,v_participant.participant_id,trim(p_device_id),v_idempotency_key
    ) on conflict (event_id, idempotency_key) do update
      set device_id = excluded.device_id,
          last_seen_at = now(),
          is_active = true
    ) returning * into v_session;

    if v_session.participant_id is distinct from v_participant.participant_id then
        delete from public.participants_v2 where participant_id = v_next_participant_id;
        select * into v_participant from public.participants_v2 where participant_id = v_session.participant_id;
        select * into v_session from public.participant_sessions_v2
          where participant_session_id = v_session.participant_session_id;
        update public.participant_sessions_v2
           set last_seen_at = now(), is_active = true
         where participant_session_id = v_session.participant_session_id;
        update public.participants_v2
           set last_seen_at = now()
         where participant_id = v_session.participant_id;
        return public.exos_v2_identity_payload(v_event.event_id, v_session.participant_id);
    end if;

    insert into public.audit_log_v2 (event_id,actor,action,entity_type,entity_id,before_state,after_state)
    values (v_event.event_id, 'system', 'PARTICIPANT_REGISTERED', 'participants_v2', v_participant.participant_id::text, '{}'::jsonb, to_jsonb(v_participant));

    return public.exos_v2_identity_payload(v_event.event_id, v_participant.participant_id);
end;
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
begin
    v_normalized := public.exos_v2_normalize_participant_name(p_participant_name);
    select * into v_event from public.events_v2 where join_code=upper(trim(p_join_code)) limit 1;
    if not found then return null; end if;

    select count(*) into v_count
      from public.participants_v2
     where event_id=v_event.event_id and normalized_name=v_normalized and merged_into_participant_id is null;
    if v_count > 1 then
        return jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', true,
            'EventID', v_event.event_id,
            'Name', trim(p_participant_name),
            'Message', 'Multiple participants share this identity. Ask facilitator to choose the correct record.'
        );
    end if;
    if v_count = 0 then return null; end if;

    select * into v_participant from public.participants_v2
      where event_id=v_event.event_id and normalized_name=v_normalized and merged_into_participant_id is null
      order by created_at limit 1;

    select * into v_session from public.participant_sessions_v2
      where event_id=v_event.event_id and participant_id=v_participant.participant_id and is_active
      order by created_at desc limit 1;
    if v_session.participant_session_id is null then
        return jsonb_build_object(
            'RecoveryRequired', true,
            'Ambiguous', false,
            'EventID', v_event.event_id,
            'Name', trim(p_participant_name),
            'Message', 'No active session found. Recovery required with facilitator'
        );
    end if;

    if nullif(trim(p_device_id),'') is not null then
        if v_session.device_id is not null and lower(trim(v_session.device_id)) <> lower(trim(p_device_id)) then
            return jsonb_build_object(
                'RecoveryRequired', true,
                'Ambiguous', false,
                'EventID', v_event.event_id,
                'Name', trim(p_participant_name),
                'Message', 'Different device/session than recorded. Recovery path required.'
            );
        end if;
    end if;

    return jsonb_build_object(
        'RecoveryRequired', false,
        'Ambiguous', false,
        'EventID', v_event.event_id,
        'ParticipantID', v_participant.participant_id,
        'TeamID', v_participant.team_id,
        'Team', (select team_name from public.teams_v2 where team_id=v_participant.team_id),
        'Country', v_participant.country,
        'Flag', v_participant.flag,
        'Name', v_participant.display_name,
        'SessionToken', v_session.session_token
    );
end;
$$;

create or replace function public.exos_v2_admin_recover_identity(
    p_event_id text,
    p_participant_id uuid,
    p_target_team_id text,
    p_actor text,
    p_reason text
)
returns jsonb
language plpgsql security definer
set search_path = public as $$
declare
    v_participant public.participants_v2%rowtype;
    v_team public.teams_v2%rowtype;
    v_before jsonb;
begin
    if nullif(trim(p_event_id), '') is null then
        raise exception 'EventID is required';
    end if;
    if nullif(trim(p_target_team_id), '') is null then
        raise exception 'Target team is required';
    end if;

    select * into v_participant from public.participants_v2
      where participant_id = p_participant_id and event_id = trim(p_event_id) for update;
    if not found then
        raise exception 'Participant not found for event';
    end if;

    select * into v_team from public.teams_v2
      where team_id = trim(p_target_team_id) and event_id = trim(p_event_id);
    if not found then
        raise exception 'Target team is not valid for this event';
    end if;

    v_before := jsonb_build_object(
        'EventID', v_participant.event_id,
        'ParticipantID', v_participant.participant_id,
        'TeamID', v_participant.team_id
    );

    update public.participants_v2
       set team_id = v_team.team_id,
           merged_into_participant_id = null
     where participant_id = v_participant.participant_id;

    update public.participant_sessions_v2
       set is_active = true, last_seen_at = now()
     where participant_id = v_participant.participant_id
       and event_id = trim(p_event_id);

    insert into public.audit_log_v2 (event_id, actor, action, entity_type, entity_id, before_state, after_state)
    values (
        trim(p_event_id),
        coalesce(trim(p_actor), 'system'),
        'ADMIN_RECOVER_PARTICIPANT',
        'participants_v2',
        p_participant_id::text,
        v_before,
        jsonb_build_object('event_id', trim(p_event_id), 'team_id', v_team.team_id)
    );

    return jsonb_build_object(
        'RecoveryRequired', false,
        'EventID', trim(p_event_id),
        'ParticipantID', p_participant_id,
        'TeamID', v_team.team_id,
        'Reason', coalesce(trim(p_reason), 'manual_recovery')
    );
end;
$$;

create or replace function public.exos_v2_admin_merge_participants(
    p_event_id text,
    p_target_participant_id uuid,
    p_merged_participant_id uuid,
    p_actor text,
    p_reason text
)
returns jsonb
language plpgsql security definer
set search_path = public as $$
declare
    v_target public.participants_v2%rowtype;
    v_merged public.participants_v2%rowtype;
    v_before jsonb;
begin
    if p_target_participant_id = p_merged_participant_id then
        raise exception 'Cannot merge a participant into itself';
    end if;

    select * into v_target from public.participants_v2
      where event_id = trim(p_event_id) and participant_id = p_target_participant_id
      for update;
    select * into v_merged from public.participants_v2
      where event_id = trim(p_event_id) and participant_id = p_merged_participant_id
      for update;
    if v_target.participant_id is null or v_merged.participant_id is null then
        raise exception 'Both participants must belong to the same event';
    end if;

    v_before := jsonb_build_object(
        'target', to_jsonb(v_target),
        'merged', to_jsonb(v_merged)
    );

    update public.submissions_v2
       set participant_id = v_target.participant_id
     where event_id = trim(p_event_id)
       and participant_id = v_merged.participant_id;

    update public.activity_runtime_v2
       set participant_id = v_target.participant_id
     where event_id = trim(p_event_id)
       and participant_id = v_merged.participant_id;

    update public.participants_v2
       set merged_into_participant_id = v_target.participant_id,
           is_archived = true
     where participant_id = v_merged.participant_id;

    update public.participant_sessions_v2
       set participant_id = v_target.participant_id
     where participant_id = v_merged.participant_id
       and event_id = trim(p_event_id);

    insert into public.audit_log_v2 (event_id, actor, action, entity_type, entity_id, before_state, after_state)
    values (
        trim(p_event_id),
        coalesce(trim(p_actor), 'system'),
        'ADMIN_MERGE_PARTICIPANTS',
        'participants_v2',
        p_target_participant_id::text,
        v_before,
        jsonb_build_object(
            'target_participant_id', p_target_participant_id,
            'merged_participant_id', p_merged_participant_id,
            'reason', coalesce(trim(p_reason), 'manual_merge')
        )
    );

    return jsonb_build_object(
        'RecoveryRequired', false,
        'EventID', trim(p_event_id),
        'TargetParticipantID', p_target_participant_id,
        'MergedParticipantID', p_merged_participant_id,
        'Reason', coalesce(trim(p_reason), 'manual_merge')
    );
end;
$$;

create or replace function public.exos_v2_ledger_score(
    p_event_id text,
    p_team_id text,
    p_submission_id uuid,
    p_amount numeric,
    p_reason text,
    p_scoring_mode public.exos_v2_scoring_mode default 'TEAM_COMPETITIVE',
    p_idempotency_key text default ''
)
returns uuid
language plpgsql security definer
set search_path=public as $$
declare
    v_tx_id uuid;
    v_key text;
begin
    if p_scoring_mode <> 'TEAM_COMPETITIVE' then
        raise exception 'Only TEAM_COMPETITIVE scores contribute to leaderboard';
    end if;
    v_key := nullif(trim(p_idempotency_key),'');
    if v_key is null then
        v_key := encode(digest(trim(p_event_id)||'|'||trim(p_team_id)||'|'||coalesce(p_submission_id::text,'')||'|'||coalesce(trim(p_reason), ''),'sha256'),'hex');
    end if;
    insert into public.score_transactions_v2 (
        event_id,team_id,submission_id,scoring_mode,score_delta,reason,idempotency_key
    ) values (
        trim(p_event_id),trim(p_team_id),p_submission_id,p_scoring_mode,p_amount,p_reason,v_key
    ) on conflict(event_id,idempotency_key) do update
      set score_delta = EXCLUDED.score_delta,
          reason = EXCLUDED.reason,
          created_at = now()
      returning score_transaction_id into v_tx_id;
    return v_tx_id;
end;
$$;

create or replace function public.exos_v2_ledger_credit(
    p_event_id text,p_team_id text,p_participant_id uuid,p_transaction_type text,p_amount integer,p_reason text,p_idempotency_key text
)
returns uuid
language plpgsql security definer
set search_path=public as $$
declare
    v_credit_id uuid;
begin
    insert into public.credit_transactions_v2 (
        event_id,team_id,participant_id,transaction_type,amount,idempotency_key,reason
    ) values (
        trim(p_event_id),trim(p_team_id),p_participant_id,trim(p_transaction_type),p_amount,trim(p_idempotency_key),trim(p_reason)
    ) on conflict(event_id,idempotency_key) do update
      set amount = EXCLUDED.amount,
          reason = EXCLUDED.reason,
          created_at = now()
      returning credit_transaction_id into v_credit_id;
    return v_credit_id;
end;
$$;

revoke all on table public.events_v2 from anon, authenticated;
revoke all on table public.programmes_v2 from anon, authenticated;
revoke all on table public.modules_v2 from anon, authenticated;
revoke all on table public.activities_v2 from anon, authenticated;
revoke all on table public.teams_v2 from anon, authenticated;
revoke all on table public.participants_v2 from anon, authenticated;
revoke all on table public.participant_sessions_v2 from anon, authenticated;
revoke all on table public.activity_runtime_v2 from anon, authenticated;
revoke all on table public.submissions_v2 from anon, authenticated;
revoke all on table public.submission_evidence_v2 from anon, authenticated;
revoke all on table public.reviews_v2 from anon, authenticated;
revoke all on table public.score_transactions_v2 from anon, authenticated;
revoke all on table public.credit_transactions_v2 from anon, authenticated;
revoke all on table public.marketplace_items_v2 from anon, authenticated;
revoke all on table public.marketplace_transactions_v2 from anon, authenticated;
revoke all on table public.build_status_v2 from anon, authenticated;
revoke all on table public.judging_scores_v2 from anon, authenticated;
revoke all on table public.race_results_v2 from anon, authenticated;
revoke all on table public.projector_state_v2 from anon, authenticated;
revoke all on table public.location_checkpoints_v2 from anon, authenticated;
revoke all on table public.location_evidence_v2 from anon, authenticated;
revoke all on table public.ai_jobs_v2 from anon, authenticated;
revoke all on table public.ai_results_v2 from anon, authenticated;
revoke all on table public.audit_log_v2 from anon, authenticated;

revoke all on function public.exos_v2_normalize_participant_name(text) from public;
revoke all on function public.exos_v2_next_team_id(text) from public;
revoke all on function public.exos_v2_identity_payload(text,uuid) from public;
revoke all on function public.exos_v2_publish_event(text,text,text,jsonb,public.exos_v2_scoring_mode,text) from public;
revoke all on function public.exos_v2_join_event_v2(text,text,text,text) from public;
revoke all on function public.exos_v2_restore_join(text,text,text) from public;
revoke all on function public.exos_v2_admin_recover_identity(text,uuid,text,text,text) from public;
revoke all on function public.exos_v2_admin_merge_participants(text,uuid,uuid,text,text) from public;
revoke all on function public.exos_v2_ledger_score(text,text,uuid,numeric,text,public.exos_v2_scoring_mode,text) from public;
revoke all on function public.exos_v2_ledger_credit(text,text,uuid,text,integer,text,text) from public;

grant execute on function public.exos_v2_join_event_v2(text,text,text,text) to anon, authenticated;
grant execute on function public.exos_v2_restore_join(text,text,text) to anon, authenticated;
grant execute on function public.exos_v2_admin_recover_identity(text,uuid,text,text,text) to service_role;
grant execute on function public.exos_v2_admin_merge_participants(text,uuid,uuid,text,text) to service_role;
grant execute on function public.exos_v2_publish_event(text,text,text,jsonb,public.exos_v2_scoring_mode,text) to service_role;
grant execute on function public.exos_v2_ledger_score(text,text,uuid,numeric,text,public.exos_v2_scoring_mode,text) to service_role;
grant execute on function public.exos_v2_ledger_credit(text,text,uuid,text,integer,text,text) to service_role;
