from concurrent.futures import ThreadPoolExecutor

from data.control_runtime import ControlRuntime
from data.google_sheets import GoogleSheetsDB
from data.runtime_database import SupabaseRuntimeDB
from scripts.exos_stabilisation_harness import RuntimeModel


def test_a_double_click_same_identity_same_device_maps_to_one():
    runtime = RuntimeModel(teams=8)

    def request():
        return runtime.join("EVT-QUE-10", "Ada Lovelace", "DEVICE-DOUBLE")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: request(), range(2)))

    assert first["ParticipantID"] == second["ParticipantID"]
    assert first["TeamID"] == second["TeamID"]


def test_b_ten_repeated_same_device_requests_are_idempotent():
    runtime = RuntimeModel(teams=8)
    first = runtime.join("EVT-QUE-10", "Bob Builder", "DEVICE-FAST")
    for _ in range(9):
        duplicate = runtime.join("EVT-QUE-10", "Bob Builder", "DEVICE-FAST")
        assert duplicate["ParticipantID"] == first["ParticipantID"]
        assert duplicate["TeamID"] == first["TeamID"]


def test_c_same_name_different_device_returns_ambiguous_not_double_allocated():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)

    def request(method, path, payload=None, **_):
        if payload.get("p_device_id") == "DEVICE-A":
            return {
                "RecoveryRequired": False,
                "ParticipantID": "P-ALPHA",
                "TeamID": "TEAM-01",
                "EventID": "EVT-QUE-10",
                "Team": "Team 1",
            }
        return {
            "RecoveryRequired": True,
            "Ambiguous": True,
            "Message": "same name exists for different device/session",
            "EventID": "EVT-QUE-10",
        }

    runtime._request = request

    first = runtime.join_player("JOIN-QUEUE-10", "Taylor Swift", "DEVICE-A")
    second = runtime.join_player("JOIN-QUEUE-10", "Taylor Swift", "DEVICE-B")

    assert first["RecoveryRequired"] is False
    assert first["ParticipantID"] == "P-ALPHA"
    assert second["RecoveryRequired"] is True
    assert second["Ambiguous"] is True


def test_d_same_first_name_distinct_people_get_distinct_participants_and_teams():
    runtime = RuntimeModel(teams=8)
    rows = [
        runtime.join("EVT-QUE-10", "John Tan", "D1"),
        runtime.join("EVT-QUE-10", "John Lee", "D2"),
        runtime.join("EVT-QUE-10", "John Wong", "D3"),
        runtime.join("EVT-QUE-10", "John Lim", "D4"),
    ]

    assert len({row["ParticipantID"] for row in rows}) == 4
    assert len({row["TeamID"] for row in rows}) == 4


def test_e_reconnect_preserves_participant_and_team_assignment():
    runtime = RuntimeModel(teams=4)
    participant = runtime.join("EVT-QUE-10", "Reconnect One", "DEVICE-RECON")
    restored = runtime.restore(participant["SessionToken"])
    restored_again = runtime.restore(participant["SessionToken"])

    assert restored is not None
    assert restored_again is not None
    assert restored_again["ParticipantID"] == participant["ParticipantID"]
    assert restored_again["TeamID"] == participant["TeamID"]


def test_f_admin_recovery_path_is_audited_and_requires_control_rpcs():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    calls = []

    def request(method, path, payload=None, **_):
        calls.append((method, path, payload))
        return {"OK": True}

    runtime._request = request
    runtime.get_players = lambda _event_id: [{
        "ParticipantID": "P-ALPHA",
        "TeamID": "TEAM-01",
        "Team": "Team 01",
        "Country": "Team Country",
        "Flag": "FLAG",
        "IsLeader": False,
        "Points": 0,
        "SessionToken": "session-p-alpha",
        "LastSeenAt": "2026-08-08T00:00:00Z",
    }]

    db = GoogleSheetsDB.__new__(GoogleSheetsDB)
    db.runtime = runtime
    control = ControlRuntime(db)

    recovery = control.recover_participant("EVT-QUE-10", "P-ALPHA")
    assert recovery["ParticipantID"] == "P-ALPHA"
    control.set_submission_override("EVT-QUE-10", "TEAM-01", True, "Facilitator")
    control.transfer_leader("EVT-QUE-10", "TEAM-01", "P-ALPHA", "Facilitator")
    control.move_participant("P-ALPHA", "TEAM-02", "duplicate/collision reconciliation", "Facilitator")
    control.decide_duplicate("EVT-QUE-10", "P-ALPHA", "P-BETA", "KEEP_CANONICAL", "manual review", "Facilitator")
    runtime.reset_event_registration("EVT-QUE-10")

    endpoints = {path for _, path, _ in calls}
    assert "rpc/exos_admin_set_submission_override" in endpoints
    assert "rpc/exos_admin_transfer_leader" in endpoints
    assert "rpc/exos_admin_move_participant" in endpoints
    assert "rpc/exos_admin_duplicate_decision" in endpoints
    assert "rpc/exos_reset_event_registration" in endpoints
