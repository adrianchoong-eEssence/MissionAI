-- Additive ACL hardening for the internal identity helper installed by
-- 026_standard_participant_access_recovery.sql. Privileges only.
begin;

revoke execute on function public.exos_v2_identity_payload(text,uuid)
from public, anon, authenticated;

grant execute on function public.exos_v2_identity_payload(text,uuid)
to service_role;

commit;
