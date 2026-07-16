create extension if not exists pgcrypto;

alter table public.runtime_events
    add column if not exists credit_wallet_enabled boolean not null default false,
    add column if not exists credit_earning_frozen boolean not null default false,
    add column if not exists credit_leaderboard_frozen_at timestamptz;

create table if not exists public.runtime_team_wallets (
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    team_name text not null,
    earned_credits numeric not null default 0,
    spent_credits numeric not null default 0,
    adjusted_credits numeric not null default 0,
    updated_at timestamptz not null default now(),
    primary key (event_id, team_name)
);

create table if not exists public.runtime_credit_transactions (
    transaction_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    team_name text not null,
    transaction_type text not null check (
        transaction_type in ('EARN', 'SPEND', 'REFUND', 'ADJUSTMENT', 'REVERSAL')
    ),
    amount numeric not null check (amount <> 0),
    source_type text not null default 'MANUAL',
    source_id text not null default '',
    item_id text not null default '',
    description text not null default '',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists runtime_credit_transactions_event_team_idx
    on public.runtime_credit_transactions(event_id, team_name, created_at);

create index if not exists runtime_credit_transactions_source_idx
    on public.runtime_credit_transactions(event_id, source_type, source_id);

create table if not exists public.runtime_marketplace_items (
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    item_id text not null,
    item_name text not null,
    description text not null default '',
    credit_cost numeric not null check (credit_cost >= 0),
    stock_quantity integer check (stock_quantity is null or stock_quantity >= 0),
    active boolean not null default true,
    position integer not null default 0,
    updated_at timestamptz not null default now(),
    primary key (event_id, item_id)
);

create table if not exists public.runtime_marketplace_purchases (
    purchase_id uuid primary key default gen_random_uuid(),
    event_id text not null references public.runtime_events(event_id) on delete cascade,
    team_name text not null,
    item_id text not null,
    item_name text not null,
    quantity integer not null check (quantity > 0),
    unit_cost numeric not null check (unit_cost >= 0),
    total_cost numeric not null check (total_cost >= 0),
    participant_id uuid references public.runtime_participants(participant_id) on delete set null,
    participant_name text not null default '',
    status text not null default 'CONFIRMED',
    purchased_at timestamptz not null default now()
);

create index if not exists runtime_marketplace_purchases_event_team_idx
    on public.runtime_marketplace_purchases(event_id, team_name, purchased_at);

alter table public.runtime_team_wallets enable row level security;
alter table public.runtime_credit_transactions enable row level security;
alter table public.runtime_marketplace_items enable row level security;
alter table public.runtime_marketplace_purchases enable row level security;

create or replace function public.exos_configure_credit_wallet(
    p_event_id text,
    p_enabled boolean default true,
    p_reset boolean default false
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_team_count integer;
begin
    update public.runtime_events
       set credit_wallet_enabled = coalesce(p_enabled, true),
           credit_earning_frozen = case when p_reset then false else credit_earning_frozen end,
           credit_leaderboard_frozen_at = case
               when p_reset then null
               else credit_leaderboard_frozen_at
           end,
           updated_at = now()
     where event_id = trim(p_event_id);

    if not found then
        raise exception 'Runtime event % was not found', trim(p_event_id);
    end if;

    if p_reset then
        delete from public.runtime_marketplace_purchases
         where event_id = trim(p_event_id);
        delete from public.runtime_credit_transactions
         where event_id = trim(p_event_id);
        delete from public.runtime_team_wallets
         where event_id = trim(p_event_id);
    end if;

    insert into public.runtime_team_wallets (event_id, team_name)
    select team.event_id, team.team_name
      from public.runtime_teams team
     where team.event_id = trim(p_event_id)
    on conflict (event_id, team_name) do nothing;

    select count(*)
      into v_team_count
      from public.runtime_team_wallets
     where event_id = trim(p_event_id);

    return jsonb_build_object(
        'EventID', trim(p_event_id),
        'Enabled', coalesce(p_enabled, true),
        'Reset', p_reset,
        'Teams', v_team_count
    );
end;
$$;

create or replace function public.exos_publish_marketplace(
    p_event_id text,
    p_items jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_item_count integer;
begin
    if not exists (
        select 1
          from public.runtime_events
         where event_id = trim(p_event_id)
    ) then
        raise exception 'Runtime event % was not found', trim(p_event_id);
    end if;

    delete from public.runtime_marketplace_items
     where event_id = trim(p_event_id);

    insert into public.runtime_marketplace_items (
        event_id,
        item_id,
        item_name,
        description,
        credit_cost,
        stock_quantity,
        active,
        position,
        updated_at
    )
    select trim(p_event_id),
           upper(trim(item.item_id)),
           trim(item.item_name),
           coalesce(item.description, ''),
           greatest(coalesce(item.credit_cost, 0), 0),
           case
               when item.stock_quantity is null then null
               else greatest(item.stock_quantity, 0)
           end,
           coalesce(item.active, true),
           coalesce(item.position, 0),
           now()
      from jsonb_to_recordset(coalesce(p_items, '[]'::jsonb)) as item(
          item_id text,
          item_name text,
          description text,
          credit_cost numeric,
          stock_quantity integer,
          active boolean,
          position integer
      )
     where nullif(trim(item.item_id), '') is not null
       and nullif(trim(item.item_name), '') is not null;

    get diagnostics v_item_count = row_count;

    return jsonb_build_object(
        'EventID', trim(p_event_id),
        'ItemsPublished', v_item_count
    );
end;
$$;

create or replace function public.exos_set_credit_freeze(
    p_event_id text,
    p_frozen boolean
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_event public.runtime_events%rowtype;
begin
    update public.runtime_events
       set credit_earning_frozen = coalesce(p_frozen, false),
           credit_leaderboard_frozen_at = case
               when coalesce(p_frozen, false) then now()
               else null
           end,
           updated_at = now()
     where event_id = trim(p_event_id)
    returning * into v_event;

    if not found then
        raise exception 'Runtime event % was not found', trim(p_event_id);
    end if;

    return jsonb_build_object(
        'EventID', v_event.event_id,
        'Frozen', v_event.credit_earning_frozen,
        'FrozenAt', v_event.credit_leaderboard_frozen_at
    );
end;
$$;

create or replace function public.exos_credit_wallet_status(p_event_id text)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
    select jsonb_build_object(
        'EventID', event.event_id,
        'Enabled', event.credit_wallet_enabled,
        'EarningFrozen', event.credit_earning_frozen,
        'FrozenAt', event.credit_leaderboard_frozen_at,
        'Wallets', coalesce((
            select jsonb_agg(
                jsonb_build_object(
                    'TeamName', wallet.team_name,
                    'EarnedCredits', wallet.earned_credits,
                    'SpentCredits', wallet.spent_credits,
                    'AdjustedCredits', wallet.adjusted_credits,
                    'Balance', wallet.earned_credits - wallet.spent_credits + wallet.adjusted_credits,
                    'UpdatedAt', wallet.updated_at
                ) order by wallet.earned_credits desc, wallet.team_name
            )
              from public.runtime_team_wallets wallet
             where wallet.event_id = event.event_id
        ), '[]'::jsonb),
        'Items', coalesce((
            select jsonb_agg(
                jsonb_build_object(
                    'ItemID', item.item_id,
                    'ItemName', item.item_name,
                    'Description', item.description,
                    'CreditCost', item.credit_cost,
                    'StockQuantity', item.stock_quantity,
                    'Active', item.active,
                    'Position', item.position
                ) order by item.position, item.item_name
            )
              from public.runtime_marketplace_items item
             where item.event_id = event.event_id
        ), '[]'::jsonb),
        'Purchases', coalesce((
            select jsonb_agg(
                jsonb_build_object(
                    'PurchaseID', purchase.purchase_id,
                    'TeamName', purchase.team_name,
                    'ItemID', purchase.item_id,
                    'ItemName', purchase.item_name,
                    'Quantity', purchase.quantity,
                    'UnitCost', purchase.unit_cost,
                    'TotalCost', purchase.total_cost,
                    'ParticipantName', purchase.participant_name,
                    'Status', purchase.status,
                    'PurchasedAt', purchase.purchased_at
                ) order by purchase.purchased_at desc
            )
              from public.runtime_marketplace_purchases purchase
             where purchase.event_id = event.event_id
        ), '[]'::jsonb)
    )
      from public.runtime_events event
     where event.event_id = trim(p_event_id)
     limit 1;
$$;

create or replace function public.exos_team_wallet(p_session_token text)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
    v_participant public.runtime_participants%rowtype;
    v_event public.runtime_events%rowtype;
    v_wallet public.runtime_team_wallets%rowtype;
begin
    select *
      into v_participant
      from public.runtime_participants
     where session_token::text = trim(p_session_token)
     limit 1;

    if not found then
        raise exception 'Invalid participant session';
    end if;

    select *
      into v_event
      from public.runtime_events
     where event_id = v_participant.event_id;

    select *
      into v_wallet
      from public.runtime_team_wallets
     where event_id = v_participant.event_id
       and team_name = v_participant.team_name;

    return jsonb_build_object(
        'EventID', v_participant.event_id,
        'TeamName', v_participant.team_name,
        'Enabled', coalesce(v_event.credit_wallet_enabled, false),
        'EarningFrozen', coalesce(v_event.credit_earning_frozen, false),
        'Wallet', jsonb_build_object(
            'EarnedCredits', coalesce(v_wallet.earned_credits, 0),
            'SpentCredits', coalesce(v_wallet.spent_credits, 0),
            'AdjustedCredits', coalesce(v_wallet.adjusted_credits, 0),
            'Balance', coalesce(v_wallet.earned_credits, 0)
                - coalesce(v_wallet.spent_credits, 0)
                + coalesce(v_wallet.adjusted_credits, 0)
        ),
        'Items', coalesce((
            select jsonb_agg(
                jsonb_build_object(
                    'ItemID', item.item_id,
                    'ItemName', item.item_name,
                    'Description', item.description,
                    'CreditCost', item.credit_cost,
                    'StockQuantity', item.stock_quantity,
                    'Active', item.active,
                    'Position', item.position
                ) order by item.position, item.item_name
            )
              from public.runtime_marketplace_items item
             where item.event_id = v_participant.event_id
               and item.active = true
               and (item.stock_quantity is null or item.stock_quantity > 0)
        ), '[]'::jsonb),
        'Purchases', coalesce((
            select jsonb_agg(
                jsonb_build_object(
                    'PurchaseID', purchase.purchase_id,
                    'ItemName', purchase.item_name,
                    'Quantity', purchase.quantity,
                    'TotalCost', purchase.total_cost,
                    'PurchasedAt', purchase.purchased_at
                ) order by purchase.purchased_at desc
            )
              from public.runtime_marketplace_purchases purchase
             where purchase.event_id = v_participant.event_id
               and purchase.team_name = v_participant.team_name
        ), '[]'::jsonb)
    );
end;
$$;

create or replace function public.exos_purchase_marketplace_item(
    p_session_token text,
    p_item_id text,
    p_quantity integer default 1
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_participant public.runtime_participants%rowtype;
    v_event public.runtime_events%rowtype;
    v_item public.runtime_marketplace_items%rowtype;
    v_wallet public.runtime_team_wallets%rowtype;
    v_quantity integer;
    v_total numeric;
    v_balance numeric;
    v_purchase public.runtime_marketplace_purchases%rowtype;
begin
    v_quantity := greatest(coalesce(p_quantity, 1), 1);

    select *
      into v_participant
      from public.runtime_participants
     where session_token::text = trim(p_session_token)
     limit 1;

    if not found then
        raise exception 'Invalid participant session';
    end if;

    select *
      into v_event
      from public.runtime_events
     where event_id = v_participant.event_id;

    if not coalesce(v_event.credit_wallet_enabled, false) then
        raise exception 'The credit marketplace is not enabled for this event';
    end if;

    select *
      into v_item
      from public.runtime_marketplace_items
     where event_id = v_participant.event_id
       and item_id = upper(trim(p_item_id))
       and active = true
     for update;

    if not found then
        raise exception 'Marketplace item was not found or is inactive';
    end if;

    if v_item.stock_quantity is not null
       and v_item.stock_quantity < v_quantity then
        raise exception 'Only % unit(s) remain', v_item.stock_quantity;
    end if;

    insert into public.runtime_team_wallets (event_id, team_name)
    values (v_participant.event_id, v_participant.team_name)
    on conflict (event_id, team_name) do nothing;

    select *
      into v_wallet
      from public.runtime_team_wallets
     where event_id = v_participant.event_id
       and team_name = v_participant.team_name
     for update;

    v_total := v_item.credit_cost * v_quantity;
    v_balance := v_wallet.earned_credits
        - v_wallet.spent_credits
        + v_wallet.adjusted_credits;

    if v_balance < v_total then
        raise exception 'Insufficient credits. Available: %, required: %',
            v_balance, v_total;
    end if;

    insert into public.runtime_marketplace_purchases (
        event_id,
        team_name,
        item_id,
        item_name,
        quantity,
        unit_cost,
        total_cost,
        participant_id,
        participant_name
    ) values (
        v_participant.event_id,
        v_participant.team_name,
        v_item.item_id,
        v_item.item_name,
        v_quantity,
        v_item.credit_cost,
        v_total,
        v_participant.participant_id,
        v_participant.display_name
    )
    returning * into v_purchase;

    if v_item.stock_quantity is not null then
        update public.runtime_marketplace_items
           set stock_quantity = stock_quantity - v_quantity,
               updated_at = now()
         where event_id = v_item.event_id
           and item_id = v_item.item_id;
    end if;

    update public.runtime_team_wallets
       set spent_credits = spent_credits + v_total,
           updated_at = now()
     where event_id = v_participant.event_id
       and team_name = v_participant.team_name
    returning * into v_wallet;

    insert into public.runtime_credit_transactions (
        event_id,
        team_name,
        transaction_type,
        amount,
        source_type,
        source_id,
        item_id,
        description,
        metadata
    ) values (
        v_participant.event_id,
        v_participant.team_name,
        'SPEND',
        -v_total,
        'PURCHASE',
        v_purchase.purchase_id::text,
        v_item.item_id,
        v_item.item_name,
        jsonb_build_object('quantity', v_quantity, 'unit_cost', v_item.credit_cost)
    );

    return jsonb_build_object(
        'PurchaseID', v_purchase.purchase_id,
        'TeamName', v_participant.team_name,
        'ItemName', v_item.item_name,
        'Quantity', v_quantity,
        'TotalCost', v_total,
        'Balance', v_wallet.earned_credits - v_wallet.spent_credits + v_wallet.adjusted_credits
    );
end;
$$;

create or replace function public.exos_adjust_team_credits(
    p_event_id text,
    p_team_name text,
    p_amount numeric,
    p_description text default 'Facilitator adjustment'
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_wallet public.runtime_team_wallets%rowtype;
    v_new_balance numeric;
begin
    if coalesce(p_amount, 0) = 0 then
        raise exception 'Adjustment amount cannot be zero';
    end if;

    insert into public.runtime_team_wallets (event_id, team_name)
    select trim(p_event_id), team.team_name
      from public.runtime_teams team
     where team.event_id = trim(p_event_id)
       and team.team_name = trim(p_team_name)
    on conflict (event_id, team_name) do nothing;

    select *
      into v_wallet
      from public.runtime_team_wallets
     where event_id = trim(p_event_id)
       and team_name = trim(p_team_name)
     for update;

    if not found then
        raise exception 'Team % was not found for event %', trim(p_team_name), trim(p_event_id);
    end if;

    v_new_balance := v_wallet.earned_credits
        - v_wallet.spent_credits
        + v_wallet.adjusted_credits
        + p_amount;

    if v_new_balance < 0 then
        raise exception 'Adjustment would create a negative balance';
    end if;

    update public.runtime_team_wallets
       set adjusted_credits = adjusted_credits + p_amount,
           updated_at = now()
     where event_id = trim(p_event_id)
       and team_name = trim(p_team_name)
    returning * into v_wallet;

    insert into public.runtime_credit_transactions (
        event_id,
        team_name,
        transaction_type,
        amount,
        source_type,
        description
    ) values (
        trim(p_event_id),
        trim(p_team_name),
        'ADJUSTMENT',
        p_amount,
        'MANUAL',
        coalesce(nullif(trim(p_description), ''), 'Facilitator adjustment')
    );

    return jsonb_build_object(
        'TeamName', v_wallet.team_name,
        'Amount', p_amount,
        'Balance', v_wallet.earned_credits - v_wallet.spent_credits + v_wallet.adjusted_credits
    );
end;
$$;

create or replace function public.exos_update_submission(
    p_submission_id text,
    p_score text default '',
    p_status text default 'APPROVED',
    p_judged text default 'Yes',
    p_remarks text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_submission public.runtime_submissions%rowtype;
    v_wallet public.runtime_team_wallets%rowtype;
    v_wallet_enabled boolean := false;
    v_earning_frozen boolean := false;
    v_current_award numeric := 0;
    v_new_award numeric := 0;
    v_delta numeric := 0;
    v_balance numeric;
begin
    update public.runtime_submissions
       set score = coalesce(p_score, ''),
           status = upper(trim(coalesce(p_status, 'APPROVED'))),
           judged = coalesce(p_judged, 'Yes'),
           remarks = coalesce(p_remarks, ''),
           updated_at = now()
     where submission_id = trim(p_submission_id)
    returning * into v_submission;

    if not found then
        return jsonb_build_object('Updated', false);
    end if;

    select event.credit_wallet_enabled, event.credit_earning_frozen
      into v_wallet_enabled, v_earning_frozen
      from public.runtime_events event
     where event.event_id = v_submission.event_id;

    if coalesce(v_wallet_enabled, false)
       and not coalesce(v_earning_frozen, false)
       and upper(trim(v_submission.submission_type)) not in ('NASI', 'PIPELINE_ENTERPRISE') then

        select coalesce(sum(transaction.amount), 0)
          into v_current_award
          from public.runtime_credit_transactions transaction
         where transaction.event_id = v_submission.event_id
           and transaction.source_type = 'SUBMISSION'
           and transaction.source_id = v_submission.submission_id;

        if upper(trim(v_submission.status)) = 'APPROVED'
           and lower(trim(v_submission.judged)) in ('yes', 'true', 'approved')
           and trim(v_submission.score) ~ '^[0-9]+([.][0-9]+)?$' then
            v_new_award := greatest(trim(v_submission.score)::numeric, 0);
        end if;

        v_delta := v_new_award - v_current_award;

        if v_delta <> 0 then
            insert into public.runtime_team_wallets (event_id, team_name)
            values (v_submission.event_id, v_submission.team_name)
            on conflict (event_id, team_name) do nothing;

            select *
              into v_wallet
              from public.runtime_team_wallets
             where event_id = v_submission.event_id
               and team_name = v_submission.team_name
             for update;

            update public.runtime_team_wallets
               set earned_credits = greatest(earned_credits + v_delta, 0),
                   updated_at = now()
             where event_id = v_submission.event_id
               and team_name = v_submission.team_name
            returning * into v_wallet;

            insert into public.runtime_credit_transactions (
                event_id,
                team_name,
                transaction_type,
                amount,
                source_type,
                source_id,
                description,
                metadata
            ) values (
                v_submission.event_id,
                v_submission.team_name,
                case when v_delta > 0 then 'EARN' else 'REVERSAL' end,
                v_delta,
                'SUBMISSION',
                v_submission.submission_id,
                'Mission ' || v_submission.mission_id || ' approval',
                jsonb_build_object('mission_id', v_submission.mission_id, 'score', v_new_award)
            );
        end if;
    end if;

    if v_wallet.team_name is not null then
        v_balance := v_wallet.earned_credits - v_wallet.spent_credits + v_wallet.adjusted_credits;
    end if;

    return jsonb_build_object(
        'Updated', true,
        'Submission', to_jsonb(v_submission),
        'WalletDelta', v_delta,
        'WalletBalance', v_balance,
        'CreditEarningFrozen', v_earning_frozen
    );
end;
$$;

revoke all on table public.runtime_team_wallets from anon, authenticated;
revoke all on table public.runtime_credit_transactions from anon, authenticated;
revoke all on table public.runtime_marketplace_items from anon, authenticated;
revoke all on table public.runtime_marketplace_purchases from anon, authenticated;

revoke all on function public.exos_configure_credit_wallet(text, boolean, boolean) from public;
revoke all on function public.exos_publish_marketplace(text, jsonb) from public;
revoke all on function public.exos_set_credit_freeze(text, boolean) from public;
revoke all on function public.exos_credit_wallet_status(text) from public;
revoke all on function public.exos_team_wallet(text) from public;
revoke all on function public.exos_purchase_marketplace_item(text, text, integer) from public;
revoke all on function public.exos_adjust_team_credits(text, text, numeric, text) from public;
revoke all on function public.exos_update_submission(text, text, text, text, text) from public;

grant execute on function public.exos_configure_credit_wallet(text, boolean, boolean)
    to service_role;
grant execute on function public.exos_publish_marketplace(text, jsonb)
    to service_role;
grant execute on function public.exos_set_credit_freeze(text, boolean)
    to service_role;
grant execute on function public.exos_credit_wallet_status(text)
    to service_role;
grant execute on function public.exos_team_wallet(text)
    to anon, authenticated, service_role;
grant execute on function public.exos_purchase_marketplace_item(text, text, integer)
    to anon, authenticated, service_role;
grant execute on function public.exos_adjust_team_credits(text, text, numeric, text)
    to service_role;
grant execute on function public.exos_update_submission(text, text, text, text, text)
    to service_role;

insert into storage.buckets (
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types
)
values (
    'exos-mission-media',
    'exos-mission-media',
    false,
    209715200,
    array[
        'image/jpeg',
        'image/png',
        'image/webp',
        'image/gif',
        'video/mp4',
        'video/quicktime',
        'video/webm',
        'application/pdf'
    ]
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- The bucket is private. Mission media uploads and signed downloads are
-- performed only by the Streamlit server using the Supabase secret key.
