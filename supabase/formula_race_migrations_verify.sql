-- Read-only post-deployment verification for Formula R.A.C.E. migrations 015-017.
do $$ declare missing text[]:=array[]::text[];item text;definition text;
begin
 foreach item in array array['formula_race_team_access','formula_race_build_status','formula_race_judging','formula_race_results','formula_race_event_config'] loop
  if to_regclass('public.'||item) is null then missing:=array_append(missing,item);end if;
 end loop;
 if cardinality(missing)>0 then raise exception 'Missing Formula R.A.C.E. tables: %',array_to_string(missing,', ');end if;

 -- RLS must be enabled and anon/authenticated must have no direct table privileges.
 if exists(select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relname=any(array['formula_race_team_access','formula_race_build_status','formula_race_judging','formula_race_results','formula_race_event_config']) and not c.relrowsecurity)
 then raise exception 'RLS is not enabled on every Formula R.A.C.E. table';end if;
 if exists(select 1 from information_schema.role_table_grants where table_schema='public'
  and table_name=any(array['formula_race_team_access','formula_race_build_status','formula_race_judging','formula_race_results','formula_race_event_config'])
  and grantee in('anon','authenticated')) then raise exception 'Direct anon/authenticated table grant detected';end if;

 -- Composite team foreign keys guarantee EventID + TeamID isolation.
 if (select count(*) from(select k.table_name,k.constraint_name from information_schema.key_column_usage k
  join information_schema.table_constraints c using(constraint_catalog,constraint_schema,constraint_name,table_name)
  where k.constraint_schema='public' and c.constraint_type='FOREIGN KEY'
  and k.table_name in('formula_race_team_access','formula_race_build_status','formula_race_judging','formula_race_results')
  group by k.table_name,k.constraint_name having array_agg(k.column_name::text order by k.ordinal_position)=array['event_id','team_id']::text[]) scoped_fk)<>4
 then raise exception 'Expected four composite team foreign keys';end if;

 foreach item in array array['formula_race_team_access_session_uidx','formula_race_team_access_event_connected_idx',
  'formula_race_build_event_team_created_idx','formula_race_judging_one_current','formula_race_judging_history_idx',
  'formula_race_results_one_current','formula_race_results_history_idx'] loop
  if to_regclass('public.'||item) is null then raise exception 'Missing required index: %',item;end if;
 end loop;

 -- SECURITY DEFINER functions must pin search_path and scope definitions by event/team.
 foreach item in array array['exos_formula_race_captain_login','exos_formula_race_restore_captain','exos_formula_race_team_status',
  'exos_formula_race_state','exos_set_formula_race_build_status','exos_save_formula_race_judging','exos_save_formula_race_result'] loop
  select pg_get_functiondef(p.oid) into definition from pg_proc p join pg_namespace n on n.oid=p.pronamespace
   where n.nspname='public' and p.proname=item limit 1;
  if definition is null then raise exception 'Missing function: %',item;end if;
  if position('SECURITY DEFINER' in upper(definition))=0 or position('SET search_path TO ''public''' in definition)=0
   then raise exception 'Function % lacks SECURITY DEFINER or pinned search_path',item;end if;
  if position('event_id' in lower(definition))=0 then raise exception 'Function % lacks EventID scoping',item;end if;
 end loop;
end $$;

select 'PASS' as formula_race_migration_verification,
 (select count(*) from pg_indexes where schemaname='public' and indexname like 'formula_race_%') as formula_race_indexes,
 (select count(*) from pg_constraint where connamespace='public'::regnamespace and conrelid::regclass::text like 'formula_race_%') as formula_race_constraints;
