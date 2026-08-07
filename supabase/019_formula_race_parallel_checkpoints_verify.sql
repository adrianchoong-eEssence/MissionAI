do $$ declare active_count integer;
begin
 if not exists(select 1 from information_schema.tables where table_schema='public' and table_name='formula_race_checkpoints') then raise exception 'formula_race_checkpoints missing';end if;
 if not exists(select 1 from information_schema.tables where table_schema='public' and table_name='formula_race_checkpoint_runtime') then raise exception 'formula_race_checkpoint_runtime missing';end if;
 if not exists(select 1 from pg_class where relname='formula_race_checkpoint_event_active_idx') then raise exception 'checkpoint index missing';end if;
 if exists(select 1 from pg_class where relname in ('formula_race_checkpoints','formula_race_checkpoint_runtime') and not relrowsecurity) then raise exception 'RLS missing';end if;
 select count(*) into active_count from formula_race_checkpoints where event_id='EVT-0006' and active;
 if active_count<>4 then raise exception 'EVT-0006 requires exactly four active checkpoints, found %',active_count;end if;
 if (select count(*) from runtime_teams where event_id='EVT-0006')<>10 then raise exception 'Team roster changed';end if;
 if (select count(*) from formula_race_team_access where event_id='EVT-0006' and pin_hash is not null)<>10 then raise exception 'PIN hashes changed';end if;
 if exists(select 1 from formula_race_checkpoints c join runtime_events e on e.event_id=c.event_id where c.event_id<>e.event_id) then raise exception 'Event isolation failed';end if;
end $$;
select exos_formula_race_checkpoint_state('EVT-0006') as checkpoint_state;

