-- Run only when the legacy individual pre-assignment endpoint is no longer needed.
revoke all on function public.exos_join_preassigned_event(text,text,text,text) from anon,authenticated,public;
drop function if exists public.exos_join_preassigned_event(text,text,text,text);
