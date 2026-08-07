-- Canonical Formula R.A.C.E. parallel checkpoints, captain proof, and review pipeline.
-- Approval delegates to exos_decide_canonical_submission, whose canonical ledger is award_transactions.
begin;

create table if not exists public.formula_race_checkpoints(
 event_id text not null references public.runtime_events(event_id) on delete cascade,
 module_id text not null,activity_id text not null,name text not null check(length(trim(name))>0),
 instructions text not null default '',credits numeric not null default 0 check(credits>=0),
 proof_type text not null default 'Photo' check(proof_type in ('Photo','Text','Photo + Text')),
 facilitator_notes text not null default '',position integer not null check(position between 1 and 4),
 active boolean not null default true,updated_by text not null,updated_at timestamptz not null default now(),
 primary key(event_id,activity_id),unique(event_id,module_id,position)
);
create unique index if not exists formula_race_max_four_active_slots
 on public.formula_race_checkpoints(event_id,module_id,position) where active;

create table if not exists public.formula_race_checkpoint_runtime(
 event_id text not null references public.runtime_events(event_id) on delete cascade,
 module_id text not null,status text not null default 'READY' check(status in ('READY','LIVE','PAUSED','CLOSED')),
 launched_at timestamptz,closed_at timestamptz,updated_by text not null,updated_at timestamptz not null default now(),
 primary key(event_id,module_id)
);

alter table public.canonical_submissions alter column participant_id drop not null;
alter table public.formula_race_checkpoints enable row level security;
alter table public.formula_race_checkpoint_runtime enable row level security;
revoke all on public.formula_race_checkpoints,public.formula_race_checkpoint_runtime from anon,authenticated;
create index if not exists formula_race_checkpoint_event_active_idx
 on public.formula_race_checkpoints(event_id,module_id,active,position);
create index if not exists canonical_submission_race_progress_idx
 on public.canonical_submissions(event_id,team_id,module_id,status,activity_id);

create or replace function public.exos_formula_race_checkpoint_state(p_event_id text)
returns jsonb language sql stable security definer set search_path=public as $$
 select jsonb_build_object(
  'EventID',trim(p_event_id),
  'ModuleID',coalesce(r.module_id,'EVT-0006-RACE-CHECKPOINTS'),
  'Status',coalesce(r.status,'READY'),
  'Checkpoints',coalesce((select jsonb_agg(jsonb_build_object(
   'EventID',c.event_id,'ModuleID',c.module_id,'ActivityID',c.activity_id,'Name',c.name,
   'Instructions',c.instructions,'Credits',c.credits,'ProofType',c.proof_type,
   'FacilitatorNotes',c.facilitator_notes,'Position',c.position,'Active',c.active)
   order by c.position) from formula_race_checkpoints c where c.event_id=trim(p_event_id)),'[]'::jsonb)
 ) from (select 1) x left join formula_race_checkpoint_runtime r on r.event_id=trim(p_event_id);
$$;

create or replace function public.exos_formula_race_set_checkpoint_runtime(
 p_event_id text,p_module_id text,p_action text,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare s text;ids jsonb;
begin
 s:=case upper(trim(p_action)) when 'LAUNCH' then 'LIVE' when 'PAUSE' then 'PAUSED' when 'CLOSE' then 'CLOSED' else null end;
 if s is null or nullif(trim(p_actor),'') is null then raise exception 'Valid action and actor are required';end if;
 if (select count(*) from formula_race_checkpoints where event_id=trim(p_event_id) and module_id=trim(p_module_id) and active)<>4
 then raise exception 'Exactly four active RACE checkpoints are required';end if;
 insert into formula_race_checkpoint_runtime(event_id,module_id,status,launched_at,closed_at,updated_by)
 values(trim(p_event_id),trim(p_module_id),s,case when s='LIVE' then now() end,case when s='CLOSED' then now() end,trim(p_actor))
 on conflict(event_id,module_id) do update set status=excluded.status,
  launched_at=case when excluded.status='LIVE' then now() else formula_race_checkpoint_runtime.launched_at end,
  closed_at=case when excluded.status='CLOSED' then now() else null end,updated_by=excluded.updated_by,updated_at=now();
 select jsonb_agg(activity_id order by position) into ids from formula_race_checkpoints
  where event_id=trim(p_event_id) and module_id=trim(p_module_id) and active;
 update runtime_events set stage_state='RACE_CHECKPOINTS',stage_name='RACE Checkpoints',display_mode='Credit Leaderboard',
  stage_payload=jsonb_build_object('EventID',trim(p_event_id),'ModuleID',trim(p_module_id),'ModuleType','RACE_CHECKPOINTS',
   'ParallelActivityIDs',ids,'CurrentStageStatus',s),state_version=state_version+1,state_updated_at=now(),updated_at=now()
  where event_id=trim(p_event_id);
 return jsonb_build_object('EventID',trim(p_event_id),'ModuleID',trim(p_module_id),'Status',s,'ParallelActivityIDs',ids);
end $$;

create or replace function public.exos_formula_race_save_checkpoints(
 p_event_id text,p_module_id text,p_checkpoints jsonb,p_actor text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare n integer;active_n integer;
begin
 if jsonb_typeof(p_checkpoints)<>'array' then raise exception 'Checkpoint configuration must be an array';end if;
 n:=jsonb_array_length(p_checkpoints);if n>4 then raise exception 'Maximum four RACE checkpoints';end if;
 select count(*) into active_n from jsonb_array_elements(p_checkpoints) x where coalesce((x->>'Active')::boolean,true);
 if active_n>4 then raise exception 'Maximum four active RACE checkpoints';end if;
 if exists(select 1 from jsonb_array_elements(p_checkpoints) x where
   nullif(trim(x->>'ActivityID'),'') is null or nullif(trim(x->>'Name'),'') is null
   or coalesce(x->>'ProofType','') not in ('Photo','Text','Photo + Text'))
 then raise exception 'Every checkpoint needs ActivityID, Name and valid ProofType';end if;
 delete from formula_race_checkpoints where event_id=trim(p_event_id) and module_id=trim(p_module_id);
 insert into formula_race_checkpoints(event_id,module_id,activity_id,name,instructions,credits,proof_type,
  facilitator_notes,position,active,updated_by)
 select trim(p_event_id),trim(p_module_id),trim(x->>'ActivityID'),trim(x->>'Name'),coalesce(x->>'Instructions',''),
  greatest(coalesce((x->>'Credits')::numeric,0),0),x->>'ProofType',coalesce(x->>'FacilitatorNotes',''),
  ordinality::integer,coalesce((x->>'Active')::boolean,true),trim(p_actor)
 from jsonb_array_elements(p_checkpoints) with ordinality as q(x,ordinality);
 return exos_formula_race_checkpoint_state(trim(p_event_id));
end $$;

create or replace function public.exos_formula_race_captain_workspace(p_session_token text,p_device_id text)
returns jsonb language sql stable security definer set search_path=public as $$
 select jsonb_build_object(
  'EventID',a.event_id,'TeamID',a.team_id,'TeamName',t.team_name,
  'Wallet',jsonb_build_object('EarnedCredits',coalesce(w.earned_credits,0),'SpentCredits',coalesce(w.spent_credits,0),
   'AdjustedCredits',coalesce(w.adjusted_credits,0),'Balance',coalesce(w.earned_credits,0)-coalesce(w.spent_credits,0)+coalesce(w.adjusted_credits,0)),
  'CheckpointRuntime',coalesce((select to_jsonb(r) from formula_race_checkpoint_runtime r where r.event_id=a.event_id),'{}'::jsonb),
  'Checkpoints',coalesce((select jsonb_agg(x.checkpoint order by x.team_order) from(
    select jsonb_build_object('ActivityID',c.activity_id,'ModuleID',c.module_id,'Name',c.name,'Instructions',c.instructions,
      'Credits',c.credits,'ProofType',c.proof_type,'Position',c.position,
      'Status',case s.status when 'PENDING_REVIEW' then 'UNDER REVIEW' when 'RETURNED_FOR_REVISION' then 'REJECTED / RESUBMIT'
       when 'REJECTED' then 'REJECTED / RESUBMIT' when 'APPROVED' then 'APPROVED' else 'AVAILABLE' end,
      'SubmissionID',s.submission_id) checkpoint,
      md5(a.event_id||':'||a.team_id||':'||c.activity_id) team_order
    from formula_race_checkpoints c left join lateral(select * from canonical_submissions cs
      where cs.event_id=c.event_id and cs.team_id=a.team_id and cs.activity_id=c.activity_id
      order by submitted_at desc limit 1)s on true
    where c.event_id=a.event_id and c.active)x),'[]'::jsonb),
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

create or replace function public.exos_formula_race_submit_checkpoint(
 p_session_token text,p_device_id text,p_activity_id text,p_text_response text,
 p_storage_reference text,p_idempotency_key text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare a formula_race_team_access%rowtype;c formula_race_checkpoints%rowtype;s canonical_submissions%rowtype;r formula_race_checkpoint_runtime%rowtype;
begin
 select * into a from formula_race_team_access where active_session_token::text=trim(p_session_token)
  and active_device_id=trim(p_device_id) for update;if not found then raise exception 'Invalid captain session';end if;
 select * into c from formula_race_checkpoints where event_id=a.event_id and activity_id=trim(p_activity_id) and active;
 if not found then raise exception 'Checkpoint is unavailable';end if;
 select * into r from formula_race_checkpoint_runtime where event_id=a.event_id and module_id=c.module_id;
 if not found or r.status<>'LIVE' then raise exception 'RACE Checkpoints are not live';end if;
 if c.proof_type in ('Photo','Photo + Text') and nullif(trim(p_storage_reference),'') is null then raise exception 'Photo proof is required';end if;
 if c.proof_type in ('Text','Photo + Text') and nullif(trim(p_text_response),'') is null then raise exception 'Text proof is required';end if;
 select * into s from canonical_submissions where event_id=a.event_id and team_id=a.team_id and activity_id=c.activity_id
  order by submitted_at desc limit 1 for update;
 if found and s.status in ('PENDING_REVIEW','APPROVED') then return to_jsonb(s)||jsonb_build_object('Duplicate',true);end if;
 if found and s.status in ('REJECTED','RETURNED_FOR_REVISION') then
  update canonical_submissions set text_response=coalesce(p_text_response,''),storage_reference=nullif(trim(p_storage_reference),''),
   evidence_type=upper(c.proof_type),status='PENDING_REVIEW',idempotency_key=trim(p_idempotency_key),submitted_at=now(),last_updated_at=now()
   where submission_id=s.submission_id returning * into s;
 else
  insert into canonical_submissions(submission_id,event_id,team_id,participant_id,programme_id,module_id,activity_id,
   experience_definition_id,experience_assignment_id,definition_version,assignment_version,submission_type,evidence_type,
   text_response,storage_reference,status,idempotency_key,created_by,allows_multiple,audit_metadata)
  values(gen_random_uuid()::text,a.event_id,a.team_id,null,a.event_id||'-PROGRAMME',c.module_id,c.activity_id,c.activity_id,
   a.event_id||':'||c.activity_id,1,1,'RACE_CHECKPOINT',upper(c.proof_type),coalesce(p_text_response,''),
   nullif(trim(p_storage_reference),''),'PENDING_REVIEW',trim(p_idempotency_key),'CAPTAIN:'||a.team_id,false,
   jsonb_build_object('CaptainSession',true)) returning * into s;
 end if;
 return to_jsonb(s)||jsonb_build_object('Duplicate',false);
end $$;

create or replace function public.exos_formula_race_review_checkpoint(
 p_submission_id text,p_decision text,p_reviewer_id text,p_notes text,p_reason text,p_idempotency_key text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare s canonical_submissions%rowtype;c formula_race_checkpoints%rowtype;result jsonb;t runtime_teams%rowtype;
begin
 select * into s from canonical_submissions where submission_id=trim(p_submission_id) for update;
 if not found then raise exception 'Submission not found';end if;
 select * into c from formula_race_checkpoints where event_id=s.event_id and activity_id=s.activity_id;
 if not found then raise exception 'RACE checkpoint definition not found';end if;
 result:=exos_decide_canonical_submission(s.submission_id,
  case upper(trim(p_decision)) when 'APPROVE' then 'APPROVE' when 'REJECT' then 'REJECT' else 'RETURN_FOR_REVISION' end,
  trim(p_reviewer_id),0,case when upper(trim(p_decision))='APPROVE' then c.credits else 0 end,
  coalesce(p_notes,''),coalesce(p_reason,''),trim(p_idempotency_key),'');
 if upper(trim(p_decision))='APPROVE' then
  select * into t from runtime_teams where event_id=s.event_id and team_id=s.team_id;
  insert into runtime_team_wallets(event_id,team_name,team_id) values(t.event_id,t.team_name,t.team_id)
   on conflict(event_id,team_name) do update set team_id=excluded.team_id;
  if not exists(select 1 from runtime_credit_transactions where event_id=s.event_id and team_id=s.team_id
    and source_type='RACE_CHECKPOINT' and source_id=s.submission_id) then
   insert into runtime_credit_transactions(event_id,team_name,team_id,transaction_type,amount,source_type,source_id,description,metadata)
    values(s.event_id,t.team_name,t.team_id,'EARN',c.credits,'RACE_CHECKPOINT',s.submission_id,c.name,jsonb_build_object('ActivityID',c.activity_id));
   update runtime_team_wallets set earned_credits=earned_credits+c.credits,updated_at=now()
    where event_id=s.event_id and team_id=s.team_id;
  end if;
 end if;
 return result;
end $$;

revoke all on function public.exos_formula_race_checkpoint_state(text),public.exos_formula_race_set_checkpoint_runtime(text,text,text,text),public.exos_formula_race_save_checkpoints(text,text,jsonb,text),
 public.exos_formula_race_submit_checkpoint(text,text,text,text,text,text),public.exos_formula_race_review_checkpoint(text,text,text,text,text,text) from public;
grant execute on function public.exos_formula_race_checkpoint_state(text) to service_role;
grant execute on function public.exos_formula_race_set_checkpoint_runtime(text,text,text,text),public.exos_formula_race_save_checkpoints(text,text,jsonb,text),public.exos_formula_race_review_checkpoint(text,text,text,text,text,text) to service_role;
grant execute on function public.exos_formula_race_submit_checkpoint(text,text,text,text,text,text) to anon,authenticated;

commit;
