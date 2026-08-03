from pathlib import Path

import pytest

from data.control_runtime import ControlRuntime
from data.runtime_authority import RuntimeAuthorityError
from data.runtime_database import SupabaseRuntimeDB


ROOT = Path(__file__).resolve().parents[1]


def runtime_stub():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    runtime.url = "https://example.invalid"
    runtime.anon_key = "anon"
    runtime.service_key = "service"
    runtime._request = lambda *args, **kwargs: {"Updated": True}
    return runtime


def test_direct_live_mutations_fail_closed():
    runtime = runtime_stub()
    operations = [
        lambda: runtime.set_event_stage("E1", {}),
        lambda: runtime.transfer_team_leader("E1", "T1", "P1"),
        lambda: runtime.update_submission("S1", 10),
        lambda: runtime.adjust_team_credits("E1", "Team", 10, "test"),
        lambda: runtime.set_runtime_control_state("E1", "RegistrationOpen", True),
    ]
    for operation in operations:
        with pytest.raises(RuntimeAuthorityError):
            operation()


def test_control_facade_grants_only_scoped_mutation_capability():
    runtime = runtime_stub()

    class DB:
        def __init__(self):
            self.runtime = runtime

        def set_event_stage(self, event_id, stage):
            return self.runtime.set_event_stage(event_id, stage)

    control = ControlRuntime(DB())
    assert control.set_stage("E1", {"StageNo": 1}) == {"Updated": True}
    with pytest.raises(RuntimeAuthorityError):
        runtime.set_event_stage("E1", {"StageNo": 2})


def test_participant_screen_cannot_mutate_leader_runtime():
    source = (ROOT / "screens" / "participant.py").read_text()
    assert "claim_team_leader(" not in source
    assert "Become Team Leader" not in source


def test_control_centre_owns_recovery_and_facilitator_facade():
    source = (ROOT / "screens" / "control_centre.py").read_text()
    assert "ControlRuntime(db)" in source
    assert "Recover Participant" in source
    assert "Restart Runtime" in source


def test_broadcast_and_review_are_read_only_without_control_facade():
    broadcast = (ROOT / "screens" / "projector_broadcast.py").read_text()
    console = (ROOT / "screens" / "live_event_console.py").read_text()
    assert "control.broadcast(event_id, payload)" in broadcast
    assert "Broadcast controls are read-only outside Control Centre." in broadcast
    assert "Submission review is read-only outside Control Centre." in console
