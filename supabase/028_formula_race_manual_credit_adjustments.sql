begin;

create or replace function public.exos_v2_formula_race_manual_credit_adjustment(
 p_event_id text,p_team_id text,p_amount integer,p_reason text,p_actor text,p_idempotency_key text
)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_credit public.credit_transactions_v2%rowtype;
begin
 if p_amount is null or p_amount=0 then raise exception 'Manual credit adjustment must be non-zero'; end if;
 if nullif(trim(p_reason),'') is null then raise exception 'Manual credit adjustment reason is required'; end if;
 if nullif(trim(p_actor),'') is null then raise exception 'Facilitator identity is required'; end if;
 if nullif(trim(p_idempotency_key),'') is null then raise exception 'Manual credit adjustment idempotency key is required'; end if;
 if not exists(select 1 from public.events_v2 where event_id=trim(p_event_id)) then raise exception 'R.A.C.E. event was not found'; end if;
 if not exists(select 1 from public.teams_v2 where event_id=trim(p_event_id) and team_id=trim(p_team_id)) then raise exception 'R.A.C.E. team is not part of this event'; end if;
 perform pg_advisory_xact_lock(hashtextextended(trim(p_event_id)||'|RACE_WALLET|'||trim(p_team_id),31));
 insert into public.credit_transactions_v2(event_id,team_id,participant_id,transaction_type,amount,idempotency_key,reason,created_by)
 values(trim(p_event_id),trim(p_team_id),null,'MANUAL_ADJUSTMENT',p_amount,trim(p_idempotency_key),trim(p_reason),trim(p_actor))
 on conflict(event_id,idempotency_key) do nothing
 returning * into v_credit;
 if not found then
  select * into v_credit from public.credit_transactions_v2
   where event_id=trim(p_event_id) and idempotency_key=trim(p_idempotency_key);
  return jsonb_build_object('CreditTransactionID',v_credit.credit_transaction_id::text,'Duplicate',true,'Amount',v_credit.amount,'TransactionType',v_credit.transaction_type);
 end if;
 return jsonb_build_object('CreditTransactionID',v_credit.credit_transaction_id::text,'Duplicate',false,'Amount',v_credit.amount,'TransactionType',v_credit.transaction_type);
end $$;

revoke all on function public.exos_v2_formula_race_manual_credit_adjustment(text,text,integer,text,text,text) from public;
grant execute on function public.exos_v2_formula_race_manual_credit_adjustment(text,text,integer,text,text,text) to service_role;

commit;
