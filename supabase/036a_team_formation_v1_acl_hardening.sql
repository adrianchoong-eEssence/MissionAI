-- Additive ACL hardening for Team Formation V1 functions installed by
-- 036_exos_core_v2_team_formation_v1.sql. Privileges only.
begin;

-- Internal helpers and trigger functions: service role only.
revoke all on function public.exos_v2_team_formation_credential_hash(text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_team_formation_credential_hash(text)
to service_role;

revoke all on function public.exos_v2_team_formation_participant_write_guard()
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_team_formation_participant_write_guard()
to service_role;

revoke all on function public.exos_v2_team_formation_team_write_guard()
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_team_formation_team_write_guard()
to service_role;

revoke all on function public.exos_v2_team_formation_captain_session_guard()
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_team_formation_captain_session_guard()
to service_role;

-- Facilitator lifecycle/configuration RPCs: service role only.
revoke all on function public.exos_v2_configure_team_formation(text,text,jsonb,jsonb,text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_configure_team_formation(text,text,jsonb,jsonb,text)
to service_role;

revoke all on function public.exos_v2_open_team_formation(text,text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_open_team_formation(text,text)
to service_role;

revoke all on function public.exos_v2_lock_team_formation(text,text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_lock_team_formation(text,text)
to service_role;

revoke all on function public.exos_v2_open_team_captain_selection(text,text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_open_team_captain_selection(text,text)
to service_role;

revoke all on function public.exos_v2_activate_team_formation(text,text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_activate_team_formation(text,text)
to service_role;

revoke all on function public.exos_v2_transfer_team_formation_captain(text,text,uuid,text,text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_transfer_team_formation_captain(text,text,uuid,text,text)
to service_role;

-- Participant registration, recovery, and Captain RPCs retain their approved
-- participant and service role matrix explicitly.
revoke all on function public.exos_v2_team_formation_register_random(text,text,text,text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_team_formation_register_random(text,text,text,text)
to anon, authenticated, service_role;

revoke all on function public.exos_v2_team_formation_claim_preassigned(text,text,text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_team_formation_claim_preassigned(text,text,text)
to anon, authenticated, service_role;

revoke all on function public.exos_v2_recover_team_formation_participant(text,text,text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_recover_team_formation_participant(text,text,text)
to anon, authenticated, service_role;

revoke all on function public.exos_v2_claim_team_formation_captain(uuid,text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_claim_team_formation_captain(uuid,text)
to anon, authenticated, service_role;

revoke all on function public.exos_v2_recover_team_formation_captain(text,text,text)
from public, anon, authenticated, service_role;
grant execute on function public.exos_v2_recover_team_formation_captain(text,text,text)
to anon, authenticated, service_role;

commit;
