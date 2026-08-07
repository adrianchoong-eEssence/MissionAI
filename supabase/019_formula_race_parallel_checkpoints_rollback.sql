begin;
do $$ begin
 if exists(select 1 from canonical_submissions where participant_id is null) then
  raise exception 'Rollback blocked: captain checkpoint submissions must be exported or removed first';
 end if;
end $$;
drop function if exists public.exos_formula_race_review_checkpoint(text,text,text,text,text,text);
drop function if exists public.exos_formula_race_submit_checkpoint(text,text,text,text,text,text);
drop function if exists public.exos_formula_race_save_checkpoints(text,text,jsonb,text);
drop function if exists public.exos_formula_race_set_checkpoint_runtime(text,text,text,text);
drop function if exists public.exos_formula_race_checkpoint_state(text);
drop table if exists public.formula_race_checkpoint_runtime;
drop table if exists public.formula_race_checkpoints;
drop index if exists public.canonical_submission_race_progress_idx;
alter table public.canonical_submissions alter column participant_id set not null;
commit;
