-- Formula R.A.C.E. live captain operations and event-scoped reset.
begin;

alter table public.runtime_team_wallets add column if not exists team_id text;
alter table public.runtime_credit_transactions add column if not exists team_id text;
alter table public.runtime_marketplace_items add column if not exists initial_stock_quantity integer;
alter table public.runtime_marketplace_purchases add column if not exists team_id text;
alter table public.runtime_marketplace_purchases add column if not exists idempotency_key text;

update public.runtime_team_wallets w set team_id=t.team_id from public.runtime_teams t
 where w.event_id=t.event_id and w.team_name=t.team_name and w.team_id is null;
update public.runtime_credit_transactions x set team_id=t.team_id from public.runtime_teams t
 where x.event_id=t.event_id and x.team_name=t.team_name and x.team_id is null;
update public.runtime_marketplace_purchases p set team_id=t.team_id from public.runtime_teams t
 where p.event_id=t.event_id and p.team_name=t.team_name and p.team_id is null;
update public.runtime_marketplace_items set initial_stock_quantity=stock_quantity
 where initial_stock_quantity is null and stock_quantity is not null;

create index if not exists runtime_team_wallets_event_team_id_idx on public.runtime_team_wallets(event_id,team_id);
create index if not exists runtime_credit_transactions_event_team_id_idx on public.runtime_credit_transactions(event_id,team_id,created_at);
create index if not exists runtime_marketplace_purchases_event_team_id_idx on public.runtime_marketplace_purchases(event_id,team_id,purchased_at);
create unique index if not exists runtime_marketplace_purchase_idempotency_uidx
 on public.runtime_marketplace_purchases(event_id,team_id,idempotency_key) where idempotency_key is not null;

do $$ begin
 if not exists(select 1 from pg_constraint where conname='runtime_team_wallets_event_team_fk') then
  alter table public.runtime_team_wallets add constraint runtime_team_wallets_event_team_fk
   foreign key(event_id,team_id) references public.runtime_teams(event_id,team_id) on delete cascade not valid;
 end if;
 if not exists(select 1 from pg_constraint where conname='runtime_credit_transactions_event_team_fk') then
  alter table public.runtime_credit_transactions add constraint runtime_credit_transactions_event_team_fk
   foreign key(event_id,team_id) references public.runtime_teams(event_id,team_id) on delete cascade not valid;
 end if;
 if not exists(select 1 from pg_constraint where conname='runtime_marketplace_purchases_event_team_fk') then
  alter table public.runtime_marketplace_purchases add constraint runtime_marketplace_purchases_event_team_fk
   foreign key(event_id,team_id) references public.runtime_teams(event_id,team_id) on delete cascade not valid;
 end if;
end $$;

create table if not exists public.formula_race_reset_audit(
 reset_audit_id uuid primary key default gen_random_uuid(),event_id text not null,
 event_name text not null,actor text not null,reason text not null,records_cleared jsonb not null,
 created_at timestamptz not null default now()
);
alter table public.formula_race_reset_audit enable row level security;
revoke all on public.formula_race_reset_audit from anon,authenticated;
create index if not exists formula_race_reset_audit_event_created_idx
 on public.formula_race_reset_audit(event_id,created_at desc);

create or replace function public.exos_formula_race_captain_logout(p_session_token text,p_device_id text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare n integer;
begin
 update formula_race_team_access set active_device_id=null,active_session_token=null,
  connected_at=null,last_seen_at=null,updated_at=now()
 where active_session_token::text=trim(p_session_token) and active_device_id=trim(p_device_id);
 get diagnostics n=row_count;
 return jsonb_build_object('LoggedOut',n=1);
end $$;

create or replace function public.exos_formula_race_captain_workspace(p_session_token text,p_device_id text)
returns jsonb language sql stable security definer set search_path=public as $$
 select jsonb_build_object(
  'EventID',a.event_id,'TeamID',a.team_id,'TeamName',t.team_name,
  'Wallet',jsonb_build_object('EarnedCredits',coalesce(w.earned_credits,0),'SpentCredits',coalesce(w.spent_credits,0),
   'AdjustedCredits',coalesce(w.adjusted_credits,0),'Balance',coalesce(w.earned_credits,0)-coalesce(w.spent_credits,0)+coalesce(w.adjusted_credits,0)),
  'Missions',coalesce((select jsonb_agg(m.mission_payload order by (m.mission_payload->>'StageNo')::integer)
    from runtime_missions m where m.event_id=a.event_id),'[]'::jsonb),
  'Marketplace',coalesce((select jsonb_agg(jsonb_build_object('ItemID',i.item_id,'ItemName',i.item_name,
    'Description',i.description,'CreditCost',i.credit_cost,'StockQuantity',i.stock_quantity,'Position',i.position) order by i.position)
    from runtime_marketplace_items i where i.event_id=a.event_id and i.active),'[]'::jsonb),
  'Purchases',coalesce((select jsonb_agg(to_jsonb(p) order by p.purchased_at desc)
    from runtime_marketplace_purchases p where p.event_id=a.event_id and p.team_id=a.team_id),'[]'::jsonb),
  'BuildStatus',coalesce((select to_jsonb(b) from formula_race_build_status b
    where b.event_id=a.event_id and b.team_id=a.team_id order by b.created_at desc limit 1),'{}'::jsonb)
 ) from formula_race_team_access a join runtime_teams t on t.event_id=a.event_id and t.team_id=a.team_id
 left join runtime_team_wallets w on w.event_id=a.event_id and w.team_id=a.team_id
 where a.active_session_token::text=trim(p_session_token) and a.active_device_id=trim(p_device_id);
$$;

create or replace function public.exos_formula_race_purchase(
 p_session_token text,p_device_id text,p_item_id text,p_quantity integer,p_idempotency_key text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare a formula_race_team_access%rowtype;t runtime_teams%rowtype;i runtime_marketplace_items%rowtype;
 w runtime_team_wallets%rowtype;q integer;total numeric;purchase uuid;existing runtime_marketplace_purchases%rowtype;
begin
 if nullif(trim(p_idempotency_key),'') is null then raise exception 'Idempotency key is required';end if;
 q:=greatest(coalesce(p_quantity,1),1);
 select * into a from formula_race_team_access where active_session_token::text=trim(p_session_token)
  and active_device_id=trim(p_device_id) for update;
 if not found then raise exception 'Invalid captain session';end if;
 select * into existing from runtime_marketplace_purchases where event_id=a.event_id and team_id=a.team_id
  and idempotency_key=trim(p_idempotency_key);
 if found then return jsonb_build_object('PurchaseID',existing.purchase_id,'Duplicate',true,'TotalCost',existing.total_cost);end if;
 select * into t from runtime_teams where event_id=a.event_id and team_id=a.team_id;
 select * into i from runtime_marketplace_items where event_id=a.event_id and item_id=upper(trim(p_item_id)) and active for update;
 if not found then raise exception 'Marketplace item is unavailable';end if;
 if i.stock_quantity is not null and i.stock_quantity<q then raise exception 'Insufficient stock';end if;
 insert into runtime_team_wallets(event_id,team_name,team_id) values(a.event_id,t.team_name,t.team_id)
  on conflict(event_id,team_name) do update set team_id=excluded.team_id;
 select * into w from runtime_team_wallets where event_id=a.event_id and team_id=a.team_id for update;
 total:=i.credit_cost*q;
 if w.earned_credits-w.spent_credits+w.adjusted_credits<total then raise exception 'Insufficient credits';end if;
 insert into runtime_marketplace_purchases(event_id,team_name,team_id,item_id,item_name,quantity,unit_cost,total_cost,
  participant_name,idempotency_key) values(a.event_id,t.team_name,t.team_id,i.item_id,i.item_name,q,i.credit_cost,total,
  'Team Captain',trim(p_idempotency_key)) returning purchase_id into purchase;
 update runtime_marketplace_items set stock_quantity=case when stock_quantity is null then null else stock_quantity-q end,
  updated_at=now() where event_id=a.event_id and item_id=i.item_id;
 update runtime_team_wallets set spent_credits=spent_credits+total,updated_at=now()
  where event_id=a.event_id and team_id=a.team_id returning * into w;
 insert into runtime_credit_transactions(event_id,team_name,team_id,transaction_type,amount,source_type,source_id,item_id,description,metadata)
  values(a.event_id,t.team_name,t.team_id,'SPEND',-total,'PURCHASE',purchase::text,i.item_id,i.item_name,
   jsonb_build_object('Quantity',q,'UnitCost',i.credit_cost,'IdempotencyKey',trim(p_idempotency_key)));
 insert into award_transactions(award_transaction_id,event_id,team_id,award_type,amount,source,reason,idempotency_key,created_by,audit_metadata)
  values(gen_random_uuid()::text,a.event_id,a.team_id,'MARKETPLACE_SPEND',-total,'MARKETPLACE',i.item_name,
   'MARKETPLACE:'||trim(p_idempotency_key),a.team_id,jsonb_build_object('PurchaseID',purchase,'Quantity',q))
  on conflict(event_id,idempotency_key) do nothing;
 return jsonb_build_object('PurchaseID',purchase,'Duplicate',false,'EventID',a.event_id,'TeamID',a.team_id,
  'TotalCost',total,'Balance',w.earned_credits-w.spent_credits+w.adjusted_credits);
end $$;

create or replace function public.exos_formula_race_adjust_credits(
 p_event_id text,p_team_id text,p_amount numeric,p_reason text,p_actor text,p_idempotency_key text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare t runtime_teams%rowtype;w runtime_team_wallets%rowtype;
begin
 if coalesce(p_amount,0)=0 or nullif(trim(p_reason),'') is null or nullif(trim(p_actor),'') is null
  or nullif(trim(p_idempotency_key),'') is null then raise exception 'Amount, reason, actor and idempotency key are required';end if;
 select * into t from runtime_teams where event_id=trim(p_event_id) and team_id=trim(p_team_id);
 if not found then raise exception 'Team does not exist in this event';end if;
 if exists(select 1 from award_transactions where event_id=t.event_id and idempotency_key=trim(p_idempotency_key)) then
  select * into w from runtime_team_wallets where event_id=t.event_id and team_id=t.team_id;
  return jsonb_build_object('Duplicate',true,'Balance',coalesce(w.earned_credits-w.spent_credits+w.adjusted_credits,0));
 end if;
 insert into runtime_team_wallets(event_id,team_name,team_id) values(t.event_id,t.team_name,t.team_id)
  on conflict(event_id,team_name) do update set team_id=excluded.team_id;
 update runtime_team_wallets set adjusted_credits=adjusted_credits+p_amount,updated_at=now()
  where event_id=t.event_id and team_id=t.team_id
  and earned_credits-spent_credits+adjusted_credits+p_amount>=0 returning * into w;
 if not found then raise exception 'Adjustment would create a negative balance';end if;
 insert into runtime_credit_transactions(event_id,team_name,team_id,transaction_type,amount,source_type,source_id,description,metadata)
  values(t.event_id,t.team_name,t.team_id,'ADJUSTMENT',p_amount,'FORMULA_RACE',trim(p_idempotency_key),trim(p_reason),jsonb_build_object('Actor',trim(p_actor)));
 insert into award_transactions(award_transaction_id,event_id,team_id,award_type,amount,source,reason,idempotency_key,created_by)
  values(gen_random_uuid()::text,t.event_id,t.team_id,'MANUAL_ADJUSTMENT',p_amount,'FORMULA_RACE',trim(p_reason),trim(p_idempotency_key),trim(p_actor));
 return jsonb_build_object('Duplicate',false,'EventID',t.event_id,'TeamID',t.team_id,'Balance',w.earned_credits-w.spent_credits+w.adjusted_credits);
end $$;

create or replace function public.exos_formula_race_set_results_lock(p_event_id text,p_locked boolean,p_reason text,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$
begin
 if nullif(trim(p_reason),'') is null or nullif(trim(p_actor),'') is null then raise exception 'Reason and actor are required';end if;
 update formula_race_event_config set results_locked=coalesce(p_locked,false),updated_by=trim(p_actor),updated_at=now()
  where event_id=trim(p_event_id);
 if not found then raise exception 'Formula RACE event configuration not found';end if;
 return jsonb_build_object('EventID',trim(p_event_id),'ResultsLocked',coalesce(p_locked,false));
end $$;

create or replace function public.exos_formula_race_reset_event(
 p_event_id text,p_event_name_confirmation text,p_reason text,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare e runtime_events%rowtype;counts jsonb;access_n int;sub_n int;participant_n int;purchase_n int;build_n int;judge_n int;result_n int;
begin
 if nullif(trim(p_reason),'') is null or nullif(trim(p_actor),'') is null then raise exception 'Reason and facilitator identity are required';end if;
 select * into e from runtime_events where event_id=trim(p_event_id) for update;
 if not found then raise exception 'Event not found';end if;
 if trim(p_event_name_confirmation)<>e.event_name then raise exception 'Event name confirmation does not match %',e.event_name;end if;
 update formula_race_team_access set active_device_id=null,active_session_token=null,connected_at=null,last_seen_at=null,updated_at=now()
  where event_id=e.event_id;get diagnostics access_n=row_count;
 delete from review_decisions where event_id=e.event_id;delete from award_transactions where event_id=e.event_id;
 delete from canonical_submissions where event_id=e.event_id;delete from runtime_submissions where event_id=e.event_id;get diagnostics sub_n=row_count;
 delete from runtime_participants where event_id=e.event_id;get diagnostics participant_n=row_count;
 delete from runtime_marketplace_purchases where event_id=e.event_id;get diagnostics purchase_n=row_count;
 delete from runtime_credit_transactions where event_id=e.event_id;
 update runtime_team_wallets set earned_credits=0,spent_credits=0,adjusted_credits=0,updated_at=now() where event_id=e.event_id;
 update runtime_marketplace_items set stock_quantity=initial_stock_quantity,updated_at=now() where event_id=e.event_id;
 delete from formula_race_build_status where event_id=e.event_id;get diagnostics build_n=row_count;
 insert into formula_race_build_status(event_id,team_id,status,checklist,reason,created_by)
  select event_id,team_id,'Not Started','{}','Post-UAT clean state',trim(p_actor) from runtime_teams where event_id=e.event_id;
 delete from formula_race_judging where event_id=e.event_id;get diagnostics judge_n=row_count;
 delete from formula_race_results where event_id=e.event_id;get diagnostics result_n=row_count;
 update formula_race_event_config set results_locked=false,updated_by=trim(p_actor),updated_at=now() where event_id=e.event_id;
 update runtime_events set current_stage_no=0,stage_state='READY',stage_name='Briefing',current_mission_id='RACE-D1-00',
  credit_earning_frozen=false,credit_leaderboard_frozen_at=null,updated_at=now() where event_id=e.event_id;
 counts:=jsonb_build_object('CaptainSessions',access_n,'RuntimeSubmissions',sub_n,'LegacyParticipants',participant_n,'Purchases',purchase_n,
  'BuildHistory',build_n,'Judging',judge_n,'RaceResults',result_n);
 insert into formula_race_reset_audit(event_id,event_name,actor,reason,records_cleared)
  values(e.event_id,e.event_name,trim(p_actor),trim(p_reason),counts);
 return jsonb_build_object('Reset',true,'EventID',e.event_id,'EventName',e.event_name,'RecordsCleared',counts);
end $$;

revoke all on function public.exos_formula_race_captain_logout(text,text),public.exos_formula_race_captain_workspace(text,text),
 public.exos_formula_race_purchase(text,text,text,integer,text),public.exos_formula_race_adjust_credits(text,text,numeric,text,text,text),
 public.exos_formula_race_set_results_lock(text,boolean,text,text),public.exos_formula_race_reset_event(text,text,text,text) from public;
grant execute on function public.exos_formula_race_captain_logout(text,text),public.exos_formula_race_captain_workspace(text,text),
 public.exos_formula_race_purchase(text,text,text,integer,text) to anon,authenticated,service_role;
grant execute on function public.exos_formula_race_adjust_credits(text,text,numeric,text,text,text),
 public.exos_formula_race_set_results_lock(text,boolean,text,text),public.exos_formula_race_reset_event(text,text,text,text) to service_role;

commit;
