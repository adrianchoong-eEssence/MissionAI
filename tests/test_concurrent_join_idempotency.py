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


def test_join_ui_disables_resubmission_and_supports_recovery():
    source = Path("screens/participant.py").read_text()
    assert '"Joining…" if pending else "🚀 Join Event"' in source
    assert "disabled=bool(pending)" in source
    assert "Joining your expedition…" in source
    assert "Please do not refresh or tap again." in source
    assert "Your join request is still being processed." in source
    assert "Check Existing Registration" in source
    assert "participant_device_id()" in source


def test_prejoin_runtime_lookup_does_not_load_experience_content():
    source = Path("screens/participant.py").read_text()
    function = source.split("def participant_event_by_code", 1)[1].split("\n\n", 1)[0]
    assert "get_runtime_database().get_event_by_join_code" in function
    assert "GoogleSheetsDB" not in function
    assert "get_mission" not in function
    assert "get_assets" not in function
