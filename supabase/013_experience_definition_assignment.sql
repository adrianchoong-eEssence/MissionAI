begin;

create table if not exists public.experience_definitions (
    experience_definition_id text not null,
    version integer not null check (version > 0),
    name text not null,
    internal_description text not null default '',
    participant_title text not null,
    participant_narrative text not null default '',
    participant_task text not null default '',
    experience_type text not null default 'Standard',
    difficulty text not null default 'Unspecified',
    default_intelligence_credits integer not null default 0,
    default_evidence_type text not null default 'NONE',
    default_evidence_instructions text not null default '',
    default_character_id text,
    default_ai_response text not null default '',
    default_hint text not null default '',
    reference_asset_ids jsonb not null default '[]'::jsonb,
    tags jsonb not null default '[]'::jsonb,
    learning_themes jsonb not null default '[]'::jsonb,
    venue_tags jsonb not null default '[]'::jsonb,
    status text not null default 'DRAFT' check (status in ('DRAFT','PUBLISHED','ARCHIVED')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (experience_definition_id, version)
);

create table if not exists public.event_experience_assignments (
    experience_assignment_id text primary key,
    event_id text not null references public.runtime_events(event_id) on delete restrict,
    programme_id text not null,
    module_id text not null,
    activity_id text not null,
    experience_definition_id text not null,
    definition_version integer not null,
    assignment_order integer not null check (assignment_order > 0),
    active boolean not null default true,
    participant_title_override text,
    narrative_override text,
    task_override text,
    credits_override integer,
    evidence_type_override text,
    evidence_instructions_override text,
    character_id_override text,
    asset_ids_override jsonb,
    hint_override text,
    ai_response_override text,
    availability_rule text not null default 'ALWAYS',
    start_rule text not null default 'FACILITATOR',
    end_rule text not null default 'FACILITATOR',
    unlock_rule text not null default 'NONE',
    runtime_eligible boolean not null default true,
    assignment_version integer not null default 1 check (assignment_version > 0),
    submission_rule text not null default 'LEADER_ONLY'
      check (submission_rule in ('LEADER_ONLY','ANY_MEMBER','MULTIPLE')),
    allows_multiple_submissions boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (experience_definition_id, definition_version)
      references public.experience_definitions(experience_definition_id, version)
      on delete restrict,
    unique (event_id, activity_id, assignment_order),
    unique (event_id, experience_assignment_id, assignment_version)
);

create index if not exists experience_definition_search_idx
  on public.experience_definitions(status, experience_type, difficulty, name);
create index if not exists event_experience_assignment_lookup_idx
  on public.event_experience_assignments(event_id, activity_id, active, assignment_order);

alter table public.runtime_submissions
  add column if not exists experience_assignment_id text,
  add column if not exists experience_definition_id text,
  add column if not exists experience_definition_version integer,
  add column if not exists experience_assignment_version integer;

create or replace function public.exos_stamp_submission_experience_version()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_assignment public.event_experience_assignments%rowtype;
  v_assignment_id text;
begin
  select stage_payload->>'ExperienceAssignmentID'
    into v_assignment_id
    from public.runtime_events
   where event_id = new.event_id;
  if nullif(v_assignment_id, '') is null then
    return new;
  end if;
  select * into v_assignment
    from public.event_experience_assignments
   where experience_assignment_id = v_assignment_id
     and event_id = new.event_id;
  if not found or not v_assignment.active or not v_assignment.runtime_eligible then
    raise exception 'Active canonical Experience Assignment is unavailable';
  end if;
  new.experience_assignment_id := v_assignment.experience_assignment_id;
  new.experience_definition_id := v_assignment.experience_definition_id;
  new.experience_definition_version := v_assignment.definition_version;
  new.experience_assignment_version := v_assignment.assignment_version;
  return new;
end;
$$;

drop trigger if exists exos_stamp_submission_experience_version
  on public.runtime_submissions;
create trigger exos_stamp_submission_experience_version
before insert on public.runtime_submissions
for each row execute function public.exos_stamp_submission_experience_version();

alter table public.experience_definitions enable row level security;
alter table public.event_experience_assignments enable row level security;
revoke all on public.experience_definitions from anon, authenticated;
revoke all on public.event_experience_assignments from anon, authenticated;

commit;
