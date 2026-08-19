-- Formula R.A.C.E. canonical Marketplace catalogue enforcement.
-- Forward migration; depends on migrations 030 through 033 being installed.
-- R.A.C.E.-only: preserves wallet, stock and idempotency semantics.
BEGIN;

create or replace function public.exos_v2_formula_race_purchase(p_session_token uuid,p_device_id text,p_item_id text,p_quantity integer,p_idempotency_key text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_session public.team_access_sessions_v2%rowtype; v_item public.marketplace_items_v2%rowtype; v_purchase public.marketplace_transactions_v2%rowtype;
 v_credit_id uuid; v_cost integer; v_balance integer; v_reserved integer; v_configuration jsonb;
begin
 if p_quantity is null or p_quantity<1 then raise exception 'Quantity must be at least 1'; end if;
 if nullif(trim(p_idempotency_key),'') is null then raise exception 'Stable purchase idempotency key is required'; end if;
 select * into v_session from public.team_access_sessions_v2 where session_token=p_session_token and device_id=trim(p_device_id) and is_active=true limit 1 for update;
 if not found then raise exception 'Invalid captain session'; end if;
 perform pg_advisory_xact_lock(hashtextextended(v_session.event_id||'|RACE_WALLET|'||v_session.team_id,31));
 select * into v_purchase from public.marketplace_transactions_v2 where event_id=v_session.event_id and idempotency_key=trim(p_idempotency_key) limit 1 for update;
 if found then
  select coalesce(sum(amount),0)::integer into v_balance from public.credit_transactions_v2 where event_id=v_session.event_id and team_id=v_session.team_id;
  return jsonb_build_object('PurchaseResult','SUCCESS','Duplicate',true,'PurchaseID',v_purchase.marketplace_transaction_id::text,'Balance',v_balance);
 end if;
 select coalesce(event_payload->'RaceConfiguration','{}'::jsonb) into v_configuration from public.events_v2 where event_id=v_session.event_id;
 if v_configuration ? 'Marketplace' and not exists (
  select 1 from jsonb_array_elements(coalesce(v_configuration->'Marketplace','[]'::jsonb)) as configured(item)
  where configured.item->>'ItemID'=trim(p_item_id) and coalesce((configured.item->>'Enabled')::boolean,true)=true
 ) then raise exception 'Marketplace item is not in the current configured catalogue'; end if;
 select * into v_item from public.marketplace_items_v2 where event_id=v_session.event_id and item_id=trim(p_item_id) limit 1 for update;
 if not found or not v_item.is_active then raise exception 'Marketplace item is not active for this event'; end if;
 select coalesce(sum(quantity),0)::integer into v_reserved from public.marketplace_transactions_v2 where event_id=v_session.event_id and item_id=v_item.item_id and status='COMPLETED';
 if v_item.stock_limit is not null and v_reserved+p_quantity>v_item.stock_limit then raise exception 'Insufficient stock'; end if;
 v_cost:=v_item.unit_cost_credits*p_quantity;
 select coalesce(sum(amount),0)::integer into v_balance from public.credit_transactions_v2 where event_id=v_session.event_id and team_id=v_session.team_id;
 if v_balance<v_cost then raise exception 'Insufficient credits'; end if;
 insert into public.credit_transactions_v2(event_id,team_id,participant_id,transaction_type,amount,idempotency_key,reason,created_by)
  values(v_session.event_id,v_session.team_id,null,'PURCHASE',-v_cost,'race-purchase-credit|'||trim(p_idempotency_key),v_item.item_name||' purchase','RACE_CAPTAIN') returning credit_transaction_id into v_credit_id;
 insert into public.marketplace_transactions_v2(event_id,team_id,item_id,credit_transaction_id,quantity,amount_paid,status,idempotency_key)
  values(v_session.event_id,v_session.team_id,v_item.item_id,v_credit_id,p_quantity,v_cost,'COMPLETED',trim(p_idempotency_key)) returning * into v_purchase;
 return jsonb_build_object('PurchaseResult','SUCCESS','Duplicate',false,'PurchaseID',v_purchase.marketplace_transaction_id::text,'Balance',v_balance-v_cost);
end $$;

revoke all on function public.exos_v2_formula_race_purchase(uuid,text,text,integer,text) from public;
grant execute on function public.exos_v2_formula_race_purchase(uuid,text,text,integer,text) to anon,authenticated,service_role;

COMMIT;
