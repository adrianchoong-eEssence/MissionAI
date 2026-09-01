-- Final additive ACL hardening for service/admin Core-v2 RPCs installed by
-- 020_exos_core_v2_schema.sql and 022_exos_core_v2_team_access.sql.
-- Privileges only.
begin;

revoke execute on function public.exos_v2_publish_event(text,text,text,jsonb,public.exos_v2_scoring_mode,text)
from public, anon, authenticated;
grant execute on function public.exos_v2_publish_event(text,text,text,jsonb,public.exos_v2_scoring_mode,text)
to service_role;

revoke execute on function public.exos_v2_admin_recover_identity(text,uuid,text,text,text)
from public, anon, authenticated;
grant execute on function public.exos_v2_admin_recover_identity(text,uuid,text,text,text)
to service_role;

revoke execute on function public.exos_v2_admin_merge_participants(text,uuid,uuid,text,text)
from public, anon, authenticated;
grant execute on function public.exos_v2_admin_merge_participants(text,uuid,uuid,text,text)
to service_role;

revoke execute on function public.exos_v2_ledger_score(text,text,uuid,numeric,text,public.exos_v2_scoring_mode,text)
from public, anon, authenticated;
grant execute on function public.exos_v2_ledger_score(text,text,uuid,numeric,text,public.exos_v2_scoring_mode,text)
to service_role;

revoke execute on function public.exos_v2_ledger_credit(text,text,uuid,text,integer,text,text)
from public, anon, authenticated;
grant execute on function public.exos_v2_ledger_credit(text,text,uuid,text,integer,text,text)
to service_role;

revoke execute on function public.exos_v2_set_team_access_pin(text,text,text,text)
from public, anon, authenticated;
grant execute on function public.exos_v2_set_team_access_pin(text,text,text,text)
to service_role;

commit;
