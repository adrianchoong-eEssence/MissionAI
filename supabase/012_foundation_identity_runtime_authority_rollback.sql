-- Sprint 011A compatibility rollback. Non-destructive: preserves all data.
-- Application must be rolled back to d2a20e5/c4b516a before this script.

drop trigger if exists runtime_participant_identity_guard on public.runtime_participants;
drop function if exists public.exos_guard_participant_identity();
drop function if exists public.exos_join_event_v2(text,text,text,text);
drop function if exists public.exos_claim_team_leader(text);
drop function if exists public.exos_runtime_control_state(text);
drop function if exists public.exos_set_runtime_control_state(text,text,jsonb);
drop index if exists public.runtime_credit_earn_once;

-- runtime_control_state is intentionally retained to avoid destroying captured
-- timer/broadcast evidence. Migration 011 RPCs and tables remain available.
