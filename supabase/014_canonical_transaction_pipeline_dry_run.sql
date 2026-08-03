-- SELECT-only Gate 6 preflight; performs no writes.
select
  (select count(*) from public.runtime_submissions) runtime_submissions,
  (select count(*) from public.runtime_credit_transactions) legacy_credit_transactions,
  (select count(*) from public.runtime_submissions where submission_id is null or event_id is null) invalid_submissions,
  (select count(*) from (
     select event_id, mission_id, submission_key, count(*)
     from public.runtime_submissions group by 1,2,3 having count(*) > 1
   ) duplicates) duplicate_logical_submissions,
  (select count(*) from (
     select event_id, source_type, source_id, team_name, count(*)
     from public.runtime_credit_transactions group by 1,2,3,4 having count(*) > 1
   ) duplicates) duplicate_legacy_awards,
  false production_records_changed;

select event_id, team_name,
  sum(case when transaction_type='EARN' then amount else 0 end) legacy_earned,
  sum(case when transaction_type='SPEND' then amount else 0 end) legacy_spent,
  sum(amount) legacy_net
from public.runtime_credit_transactions
group by event_id, team_name order by event_id, team_name;
