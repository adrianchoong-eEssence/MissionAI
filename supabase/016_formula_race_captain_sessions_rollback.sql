-- Guarded rollback: preserves captain access and session history when any row exists.
do $$ declare row_count bigint;
begin
 if to_regclass('public.formula_race_team_access') is not null then
  execute 'select count(*) from public.formula_race_team_access' into row_count;
  if row_count>0 then raise exception 'Rollback blocked: formula_race_team_access contains % rows. Export and preserve them first.',row_count;end if;
 end if;
end $$;
drop function if exists public.exos_formula_race_team_status(text);
drop function if exists public.exos_formula_race_restore_captain(text,text);
drop function if exists public.exos_formula_race_captain_login(text,text,text,text);
drop function if exists public.exos_set_formula_race_team_pin(text,text,text,text);
drop table if exists public.formula_race_team_access;
