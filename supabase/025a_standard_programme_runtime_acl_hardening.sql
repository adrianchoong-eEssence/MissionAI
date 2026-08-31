-- Additive ACL hardening for the service-controlled Standard runtime RPCs
-- installed by 025_standard_programme_runtime.sql. Privileges only.
begin;

revoke execute on function public.exos_v2_standard_launch_activity(text,text,text)
from public, anon, authenticated;

revoke execute on function public.exos_v2_standard_review_submission(
    uuid,
    public.exos_v2_review_decision,
    numeric,
    text,
    text,
    text
)
from public, anon, authenticated;

grant execute on function public.exos_v2_standard_launch_activity(text,text,text)
to service_role;

grant execute on function public.exos_v2_standard_review_submission(
    uuid,
    public.exos_v2_review_decision,
    numeric,
    text,
    text,
    text
)
to service_role;

commit;
