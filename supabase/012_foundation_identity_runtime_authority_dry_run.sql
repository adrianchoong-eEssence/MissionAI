-- READ ONLY Sprint 011A preflight. This file performs SELECT statements only.

with duplicate_names as (
    select event_id,public.exos_normalize_participant_name(display_name) normalized_name,
           count(*) records,array_agg(participant_id order by joined_at) participant_ids
      from public.runtime_participants where merged_into_participant_id is null
     group by event_id,public.exos_normalize_participant_name(display_name) having count(*)>1
), incomplete_identity as (
    select participant_id,event_id,display_name,team_id,country,flag,status
      from public.runtime_participants where merged_into_participant_id is null
       and (nullif(team_id,'') is null or nullif(country,'') is null or nullif(flag,'') is null)
), leader_conflicts as (
    select event_id,team_id,count(*) leaders,array_agg(participant_id) participant_ids
      from public.runtime_participants where merged_into_participant_id is null and status like '%|LEADER%'
     group by event_id,team_id having count(*)>1
), duplicate_credit_sources as (
    select event_id,team_name,source_type,source_id,count(*) transactions,
           array_agg(transaction_id order by created_at) transaction_ids
      from public.runtime_credit_transactions
     where transaction_type='EARN' and source_id<>''
     group by event_id,team_name,source_type,source_id having count(*)>1
)
select jsonb_pretty(jsonb_build_object(
    'DuplicateIdentityCandidates',coalesce((select jsonb_agg(to_jsonb(d)) from duplicate_names d),'[]'),
    'IncompleteDurableIdentity',coalesce((select jsonb_agg(to_jsonb(i)) from incomplete_identity i),'[]'),
    'LeaderConflicts',coalesce((select jsonb_agg(to_jsonb(l)) from leader_conflicts l),'[]'),
    'DuplicateCreditSources',coalesce((select jsonb_agg(to_jsonb(c)) from duplicate_credit_sources c),'[]'),
    'SafeToApply',not exists(select 1 from duplicate_credit_sources),
    'ProductionRecordsChanged',false
));
