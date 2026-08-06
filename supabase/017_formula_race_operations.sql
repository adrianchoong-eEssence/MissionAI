-- Event/team-scoped Formula R.A.C.E. operational state. Append-only audit rows
-- preserve corrections; current projections select the latest version.
create table if not exists public.formula_race_build_status(
 build_status_id uuid primary key default gen_random_uuid(),event_id text not null,team_id text not null,
 status text not null check(status in ('Not Started','Collecting Parts','Building','Painting','Ready to Race','Completed')),
 checklist jsonb not null default '{}'::jsonb,reason text not null check(length(trim(reason))>0),created_by text not null check(length(trim(created_by))>0),created_at timestamptz not null default now(),
 foreign key(event_id,team_id) references public.runtime_teams(event_id,team_id) on delete cascade);
create table if not exists public.formula_race_judging(
 judging_score_id uuid primary key default gen_random_uuid(),event_id text not null,team_id text not null,
 scores jsonb not null,total_score numeric not null check(total_score>=0 and total_score<=60),is_current boolean not null default true,
 correction_of uuid references public.formula_race_judging(judging_score_id),
 reason text not null check(length(trim(reason))>0),created_by text not null check(length(trim(created_by))>0),created_at timestamptz not null default now(),
 foreign key(event_id,team_id) references public.runtime_teams(event_id,team_id) on delete cascade);
create table if not exists public.formula_race_results(
 race_result_id uuid primary key default gen_random_uuid(),event_id text not null,team_id text not null,
 finish_time_ms integer not null check(finish_time_ms>=0),penalty_ms integer not null default 0 check(penalty_ms>=0),
 bonus_credits numeric not null default 0 check(bonus_credits>=0),verified boolean not null default false,is_current boolean not null default true,
 correction_of uuid references public.formula_race_results(race_result_id),
 reason text not null check(length(trim(reason))>0),created_by text not null check(length(trim(created_by))>0),created_at timestamptz not null default now(),
 foreign key(event_id,team_id) references public.runtime_teams(event_id,team_id) on delete cascade);
create table if not exists public.formula_race_event_config(
 event_id text primary key references public.runtime_events(event_id) on delete cascade,scoring_config jsonb not null default '{}',
 results_locked boolean not null default false,updated_by text not null check(length(trim(updated_by))>0),updated_at timestamptz not null default now());
alter table public.formula_race_build_status enable row level security;alter table public.formula_race_judging enable row level security;
alter table public.formula_race_results enable row level security;alter table public.formula_race_event_config enable row level security;
revoke all on public.formula_race_build_status,public.formula_race_judging,public.formula_race_results,public.formula_race_event_config from anon,authenticated;
create index if not exists formula_race_build_event_team_created_idx on public.formula_race_build_status(event_id,team_id,created_at desc);
create unique index if not exists formula_race_judging_one_current on public.formula_race_judging(event_id,team_id) where is_current;
create index if not exists formula_race_judging_history_idx on public.formula_race_judging(event_id,team_id,created_at desc);
create unique index if not exists formula_race_results_one_current on public.formula_race_results(event_id,team_id) where is_current;
create index if not exists formula_race_results_history_idx on public.formula_race_results(event_id,team_id,created_at desc);

create or replace function public.exos_formula_race_state(p_event_id text)
returns jsonb language sql stable security definer set search_path=public as $$
 select jsonb_build_object('BuildStatus',coalesce((select jsonb_agg(x) from(select distinct on(team_id) * from formula_race_build_status where event_id=trim(p_event_id) order by team_id,created_at desc)x),'[]'),
 'Judging',coalesce((select jsonb_agg(x) from formula_race_judging x where event_id=trim(p_event_id) and is_current),'[]'),
 'RaceResults',coalesce((select jsonb_agg(x) from formula_race_results x where event_id=trim(p_event_id) and is_current),'[]'),
 'Config',coalesce((select to_jsonb(c) from formula_race_event_config c where event_id=trim(p_event_id)),'{}'));
$$;
create or replace function public.exos_set_formula_race_build_status(p_event_id text,p_team_id text,p_status text,p_checklist jsonb,p_reason text,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$ declare id uuid;
begin if nullif(trim(p_reason),'') is null or nullif(trim(p_actor),'') is null then raise exception 'Reason and facilitator identity are required';end if;
 if not exists(select 1 from runtime_teams where event_id=trim(p_event_id) and team_id=trim(p_team_id)) then raise exception 'Team does not exist in this event';end if;
 insert into formula_race_build_status(event_id,team_id,status,checklist,reason,created_by) values(trim(p_event_id),trim(p_team_id),trim(p_status),coalesce(p_checklist,'{}'),trim(p_reason),trim(p_actor)) returning build_status_id into id;
 return jsonb_build_object('BuildStatusID',id,'EventID',trim(p_event_id),'TeamID',trim(p_team_id));end $$;
create or replace function public.exos_save_formula_race_judging(p_event_id text,p_team_id text,p_scores jsonb,p_reason text,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$ declare current_id uuid;new_id uuid;total numeric;
begin if nullif(trim(p_reason),'') is null or nullif(trim(p_actor),'') is null then raise exception 'Reason and facilitator identity are required';end if;
 if not exists(select 1 from runtime_teams where event_id=trim(p_event_id) and team_id=trim(p_team_id)) then raise exception 'Team does not exist in this event';end if;
 if not p_scores ?& array['Engineering Design','Structural Integrity','Innovation','Creativity','Race Performance','Team Presentation']
 or (select count(*) from jsonb_object_keys(p_scores))<>6
 or exists(select 1 from jsonb_each_text(p_scores) where value::numeric<0 or value::numeric>10)
 then raise exception 'All six judging scores must be between 0 and 10';end if;
 select judging_score_id into current_id from formula_race_judging where event_id=trim(p_event_id) and team_id=trim(p_team_id) and is_current for update;
 total=coalesce((select sum(value::numeric) from jsonb_each_text(p_scores)),0);
 if current_id is not null then update formula_race_judging set is_current=false where judging_score_id=current_id;end if;
 insert into formula_race_judging(event_id,team_id,scores,total_score,correction_of,reason,created_by) values(trim(p_event_id),trim(p_team_id),p_scores,total,current_id,trim(p_reason),trim(p_actor)) returning judging_score_id into new_id;
 return jsonb_build_object('JudgingScoreID',new_id,'Total',total);end $$;
create or replace function public.exos_save_formula_race_result(p_event_id text,p_team_id text,p_time_ms integer,p_penalty_ms integer,p_bonus numeric,p_verified boolean,p_reason text,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$ declare current_id uuid;new_id uuid;locked boolean;
begin select results_locked into locked from formula_race_event_config where event_id=trim(p_event_id);if coalesce(locked,false) then raise exception 'Race results are locked';end if;
 if nullif(trim(p_reason),'') is null or nullif(trim(p_actor),'') is null then raise exception 'Reason and facilitator identity are required';end if;
 if not exists(select 1 from runtime_teams where event_id=trim(p_event_id) and team_id=trim(p_team_id)) then raise exception 'Team does not exist in this event';end if;
 select race_result_id into current_id from formula_race_results where event_id=trim(p_event_id) and team_id=trim(p_team_id) and is_current for update;
 if current_id is not null then update formula_race_results set is_current=false where race_result_id=current_id;end if;
 insert into formula_race_results(event_id,team_id,finish_time_ms,penalty_ms,bonus_credits,verified,correction_of,reason,created_by) values(trim(p_event_id),trim(p_team_id),p_time_ms,p_penalty_ms,p_bonus,p_verified,current_id,trim(p_reason),trim(p_actor)) returning race_result_id into new_id;
 return jsonb_build_object('RaceResultID',new_id);end $$;
revoke all on function public.exos_formula_race_state(text),public.exos_set_formula_race_build_status(text,text,text,jsonb,text,text),public.exos_save_formula_race_judging(text,text,jsonb,text,text),public.exos_save_formula_race_result(text,text,integer,integer,numeric,boolean,text,text) from public;
grant execute on function public.exos_formula_race_state(text),public.exos_set_formula_race_build_status(text,text,text,jsonb,text,text),public.exos_save_formula_race_judging(text,text,jsonb,text,text),public.exos_save_formula_race_result(text,text,integer,integer,numeric,boolean,text,text) to service_role;
