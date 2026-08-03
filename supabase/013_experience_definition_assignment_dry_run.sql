-- SELECT-only Gate 5 production preflight. This file performs no writes.
with legacy as (
  select event_id, mission_id, mission_payload
  from public.runtime_missions
), candidates as (
  select
    event_id,
    mission_id,
    coalesce(mission_payload->>'TemplateID', '') as proposed_definition_id,
    coalesce(mission_payload->>'Title', '') as title,
    coalesce(mission_payload->>'Version', '1') as proposed_version
  from legacy
)
select
  count(*) as legacy_runtime_experiences,
  count(*) filter (where proposed_definition_id <> '') as reusable_definition_candidates,
  count(*) filter (where proposed_definition_id = '') as manual_definition_reviews,
  count(*) filter (where title = '') as invalid_missing_titles,
  false as production_records_changed
from candidates;

select event_id, mission_id, proposed_definition_id, proposed_version, title
from (
  select
    event_id,
    mission_id,
    coalesce(mission_payload->>'TemplateID', '') as proposed_definition_id,
    coalesce(mission_payload->>'Version', '1') as proposed_version,
    coalesce(mission_payload->>'Title', '') as title
  from public.runtime_missions
) audit
order by event_id, mission_id;
