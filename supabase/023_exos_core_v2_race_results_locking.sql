BEGIN;

drop trigger if exists race_results_v2_lock_guard on public.race_results_v2;

drop function if exists public.exos_v2_enforce_race_results_lock();

create function public.exos_v2_enforce_race_results_lock()
returns trigger
language plpgsql
security definer
set search_path = public as
$$
begin
    if old.locked then
        if new.event_id is distinct from old.event_id
            or new.team_id is distinct from old.team_id
            or new.activity_id is distinct from old.activity_id
            or new.checkpoint is distinct from old.checkpoint
            or new.ranking_position is distinct from old.ranking_position
            or new.result_payload is distinct from old.result_payload
            or new.recorded_at is distinct from old.recorded_at
            or new.updated_at is distinct from old.updated_at then
            raise exception 'Race result is locked and immutable until explicit unlock.';
        end if;
    end if;

    return new;
end;
$$;

create trigger race_results_v2_lock_guard
before update on public.race_results_v2
for each row
execute function public.exos_v2_enforce_race_results_lock();

COMMIT;
