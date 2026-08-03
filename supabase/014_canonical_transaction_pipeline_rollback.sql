begin;
do $$ begin
  if exists(select 1 from public.canonical_submissions limit 1)
     or exists(select 1 from public.review_decisions limit 1)
     or exists(select 1 from public.award_transactions limit 1)
     or exists(select 1 from public.judge_scores limit 1) then
    raise exception 'Rollback blocked: canonical transaction history exists and must be preserved.';
  end if;
end $$;
drop view if exists public.leaderboard_projection;
drop view if exists public.team_balance_projection;
drop table if exists public.scoring_locks;
drop table if exists public.judge_scores;
drop table if exists public.judging_configurations;
drop table if exists public.award_transactions;
drop table if exists public.review_decisions;
drop table if exists public.canonical_submissions;
commit;
