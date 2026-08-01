from pathlib import Path

from data.runtime_database import SupabaseRuntimeDB


def test_join_rpc_carries_device_scoped_idempotency_input():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    calls = []
    runtime._request = lambda method, path, payload=None, **kwargs: calls.append(
        (method, path, payload)
    ) or [{"ParticipantID": "P1", "SessionToken": "S1"}]

    player = runtime.join_player(" 12dyld ", " Adrian  Choong ", "DEVICE-1")

    assert player["ParticipantID"] == "P1"
    assert calls == [(
        "POST",
        "rpc/exos_join_event",
        {
            "p_join_code": "12DYLD",
            "p_participant_name": "Adrian  Choong",
            "p_device_id": "DEVICE-1",
        },
    )]


def test_atomic_join_migration_has_unique_key_and_conflict_handling():
    source = Path("supabase/010_idempotent_concurrent_join.sql").read_text()
    assert "runtime_participants_event_idempotency_key" in source
    assert "for update" in source.lower()
    assert "on conflict (event_id, idempotency_key)" in source.lower()
    assert "p_device_id text" in source
    assert "order by count(participant.participant_id), team.position" in source
    assert "delete from public.runtime_participants" not in source.lower()


def test_durable_normalized_name_restore_precedes_team_allocation():
    source = Path("supabase/010_idempotent_concurrent_join.sql").read_text()
    join_function = source.split(
        "create or replace function public.exos_join_event", 1
    )[1].split("create or replace function public.exos_restore_join", 1)[0]
    normalized_lookup = "and normalized_name = v_normalized_name"
    allocation = "select team.team_name into v_team_name"
    insert = "insert into public.runtime_participants"

    assert join_function.index(normalized_lookup) < join_function.index(allocation)
    assert join_function.index(normalized_lookup) < join_function.index(insert)
    assert "order by joined_at, participant_id" in join_function
    assert "v_rejoined := true" in join_function


def test_name_recovery_is_not_device_scoped_and_restores_assignment_fields():
    source = Path("supabase/010_idempotent_concurrent_join.sql").read_text()
    restore_function = source.split(
        "create or replace function public.exos_restore_join", 1
    )[1].split("create or replace function public.exos_restore_participant", 1)[0]

    assert "participant.normalized_name = lower(" in restore_function
    assert "participant.idempotency_key = md5(" not in restore_function
    assert "'TeamID'" in restore_function
    assert "'Country'" in restore_function
    assert "'Flag'" in restore_function
    assert "'IsLeader'" in restore_function


def test_runtime_join_normalizes_durable_identity_payload():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    runtime._request = lambda *args, **kwargs: [{
        "ParticipantID": "P1",
        "TeamID": "T1",
        "Status": "COUNTRY:Korea|LEADER",
    }]

    player = runtime.join_player("12DYLD", "Adrian Choong", "DEVICE-2")

    assert player["ParticipantID"] == "P1"
    assert player["TeamID"] == "T1"
    assert player["Country"] == "Korea"
    assert player["IsLeader"] is True


def test_join_ui_disables_resubmission_and_supports_recovery():
    source = Path("screens/participant.py").read_text()
    assert '"Joining…" if pending else "🚀 Join Event"' in source
    assert "disabled=bool(pending)" in source
    assert "Joining your expedition…" in source
    assert "Please do not refresh or tap again." in source
    assert "Your join request is still being processed." in source
    assert "Check Existing Registration" in source
    assert "participant_device_id()" in source
    assert "restore_participant_identity(player" in source
    assert '"participant_team_id"' in source
    assert '"participant_is_leader"' in source


def test_linked_content_reruns_do_not_clear_participant_identity():
    source = Path("screens/participant.py").read_text()
    linked_route = source.split("linked_config = activity_content_config", 1)[1]
    leave_action = linked_route.rsplit('if st.button("🚪 Leave Event"', 1)[1]

    assert "reset_session()" not in linked_route.split(
        'if st.button("🚪 Leave Event"', 1
    )[0]
    assert "reset_session()" in leave_action


def test_prejoin_runtime_lookup_does_not_load_experience_content():
    source = Path("screens/participant.py").read_text()
    function = source.split("def participant_event_by_code", 1)[1].split("\n\n", 1)[0]
    assert "get_runtime_database().get_event_by_join_code" in function
    assert "GoogleSheetsDB" not in function
    assert "get_mission" not in function
    assert "get_assets" not in function
