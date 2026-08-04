-- Formula R.A.C.E. pre-assigned participant identity policy.
-- This is deliberately a lookup/recovery RPC: it never inserts, allocates, balances,
-- creates teams, changes countries or changes leader status.

create or replace function public.exos_join_preassigned_event(
    p_join_code text,
    p_first_name text,
    p_last_name text,
    p_device_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_event public.runtime_events%rowtype;
    v_participant public.runtime_participants%rowtype;
    v_name text;
    v_normalized text;
    v_matches integer;
begin
    if nullif(trim(p_first_name), '') is null or nullif(trim(p_last_name), '') is null then
        raise exception 'First name and last name are required';
    end if;
    if nullif(trim(p_device_id), '') is null then
        raise exception 'Participant device identifier is required';
    end if;

    v_name := regexp_replace(trim(p_first_name) || ' ' || trim(p_last_name), '\s+', ' ', 'g');
    v_normalized := public.exos_normalize_participant_name(v_name);

    select * into v_event
      from public.runtime_events
     where join_code = upper(trim(p_join_code)) and active = true
     for update;
    if not found then raise exception 'Invalid or inactive event code'; end if;

    select count(*) into v_matches
      from public.runtime_participants
     where event_id = v_event.event_id
       and public.exos_normalize_participant_name(display_name) = v_normalized
       and merged_into_participant_id is null;

    if v_matches = 0 then
        return jsonb_build_object(
            'PreassignedIdentityRequired', true,
            'Found', false,
            'EventID', v_event.event_id,
            'Name', v_name,
            'Message', 'No pre-assigned participant record matches this name. Ask a facilitator for help.'
        );
    elsif v_matches > 1 then
        return jsonb_build_object(
            'PreassignedIdentityRequired', true,
            'Found', false,
            'Ambiguous', true,
            'EventID', v_event.event_id,
            'Name', v_name,
            'Message', 'Multiple pre-assigned records match this name. Ask a facilitator to recover the correct ParticipantID.'
        );
    end if;

    select * into v_participant
      from public.runtime_participants
     where event_id = v_event.event_id
       and public.exos_normalize_participant_name(display_name) = v_normalized
       and merged_into_participant_id is null
     order by joined_at, participant_id
     limit 1
     for update;

    if nullif(trim(v_participant.team_id), '') is null
       or nullif(trim(v_participant.team_name), '') is null then
        raise exception 'Pre-assigned participant has no canonical team. Ask a facilitator for help.';
    end if;

    -- last_seen_at is operational presence only; durable identity fields are untouched.
    update public.runtime_participants
       set last_seen_at = now()
     where participant_id = v_participant.participant_id;

    return public.exos_identity_payload(v_participant, v_event)
        || jsonb_build_object(
            'Found', true,
            'PreassignedIdentity', true,
            'Rejoined', true,
            'RecoveryRequired', false
        );
end;
$$;

revoke all on function public.exos_join_preassigned_event(text,text,text,text) from public;
grant execute on function public.exos_join_preassigned_event(text,text,text,text) to anon, authenticated;
