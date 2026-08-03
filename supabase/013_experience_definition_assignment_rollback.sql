begin;

-- Refuse rollback while assignments exist: definition history must never be orphaned.
do $$
begin
  if exists (select 1 from public.event_experience_assignments limit 1) then
    raise exception 'Rollback blocked: back up and remove approved assignments first.';
  end if;
  if exists (
    select 1 from public.runtime_submissions
    where experience_assignment_id is not null
       or experience_definition_id is not null
    limit 1
  ) then
    raise exception 'Rollback blocked: historical submissions reference Experience versions.';
  end if;
end $$;

drop trigger if exists exos_stamp_submission_experience_version
  on public.runtime_submissions;
drop function if exists public.exos_stamp_submission_experience_version();
drop table if exists public.event_experience_assignments;
drop table if exists public.experience_definitions;
alter table public.runtime_submissions
  drop column if exists experience_assignment_id,
  drop column if exists experience_definition_id,
  drop column if exists experience_definition_version,
  drop column if exists experience_assignment_version;

commit;
