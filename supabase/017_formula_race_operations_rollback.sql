-- Guarded rollback: never deletes build, judging, race or scoring history.
do $$ declare table_name text;row_count bigint;
begin
 foreach table_name in array array['formula_race_build_status','formula_race_judging','formula_race_results','formula_race_event_config'] loop
  if to_regclass('public.'||table_name) is not null then
   execute format('select count(*) from public.%I',table_name) into row_count;
   if row_count>0 then raise exception 'Rollback blocked: % contains % rows. Export and preserve them first.',table_name,row_count;end if;
  end if;
 end loop;
end $$;
drop function if exists public.exos_save_formula_race_result(text,text,integer,integer,numeric,boolean,text,text);
drop function if exists public.exos_save_formula_race_judging(text,text,jsonb,text,text);
drop function if exists public.exos_set_formula_race_build_status(text,text,text,jsonb,text,text);
drop function if exists public.exos_formula_race_state(text);
drop table if exists public.formula_race_results;
drop table if exists public.formula_race_judging;
drop table if exists public.formula_race_build_status;
drop table if exists public.formula_race_event_config;
