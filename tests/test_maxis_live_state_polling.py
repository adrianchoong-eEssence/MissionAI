"""Regression contract for Maxis participant live-state polling."""
from __future__ import annotations

from pathlib import Path

from services.maxis_live_state import POLL_INTERVAL_SECONDS, workspace_live_signature


ROOT = Path(__file__).resolve().parents[1]


def _workspace(**overrides) -> dict:
    base = {
        "EventID": "MAXIS-20260907-MISSION-AI",
        "TeamFormationPhase": "CAPTAIN_SELECTION",
        "Lifecycle": "CAPTAIN_SELECTION",
        "RuntimePhase": "READY",
        "CaptainParticipantID": "",
        "CaptainSessionActive": False,
        "CanClaimCaptain": True,
        "TeamScore": 0,
        "Progress": {"Completed": 0, "PendingReview": 0, "Approved": 0, "Rejected": 0},
        "MissionBoard": [{"ActivityID": "M1", "MissionState": "AVAILABLE", "OperationalStatus": "AVAILABLE", "SecretState": "RELEASED"}],
    }
    base.update(overrides)
    return base


def test_maxis_poll_interval_is_a_battery_safe_five_seconds():
    assert POLL_INTERVAL_SECONDS == 5


def test_signature_detects_every_participant_visible_live_transition():
    baseline = _workspace()
    variants = [
        _workspace(TeamFormationPhase="CAPTAIN_SELECTION", Lifecycle="CAPTAIN_SELECTION", CaptainParticipantID="P1", CanClaimCaptain=False),
        _workspace(TeamFormationPhase="ACTIVE", Lifecycle="READY"),
        _workspace(TeamFormationPhase="ACTIVE", Lifecycle="ACTIVE", RuntimePhase="ACTIVE"),
        _workspace(TeamFormationPhase="ACTIVE", Lifecycle="HELD", RuntimePhase="HELD"),
        _workspace(TeamFormationPhase="ACTIVE", Lifecycle="ACTIVE", RuntimePhase="ACTIVE", MissionBoard=[{"ActivityID": "M1", "MissionState": "SUBMITTED"}]),
        _workspace(TeamFormationPhase="ACTIVE", Lifecycle="ACTIVE", RuntimePhase="ACTIVE", MissionBoard=[{"ActivityID": "M1", "MissionState": "REJECTED"}]),
        _workspace(TeamFormationPhase="ACTIVE", Lifecycle="ACTIVE", RuntimePhase="ACTIVE", TeamScore=120, Progress={"Completed": 1, "PendingReview": 0, "Approved": 1, "Rejected": 0}, MissionBoard=[{"ActivityID": "M1", "MissionState": "APPROVED"}]),
    ]
    assert all(workspace_live_signature(candidate) != workspace_live_signature(baseline) for candidate in variants)


def test_signature_is_stable_when_no_canonical_live_state_changed():
    assert workspace_live_signature(_workspace()) == workspace_live_signature(_workspace())


def test_poller_is_read_only_and_only_reruns_after_a_canonical_change():
    source = (ROOT / "services/maxis_live_state.py").read_text(encoding="utf-8")
    assert '@st.fragment(run_every=f"{POLL_INTERVAL_SECONDS}s")' in source
    assert "theme_park_race_participant_workspace(session_token)" in source
    assert "previous is not None and previous != signature" in source
    assert "st.rerun(scope=\"app\")" in source
    assert "board_submit" not in source
    assert "claim_preassigned" not in source
    assert "upload_" not in source


def test_personal_key_shell_starts_the_watcher_for_a_restored_canonical_session():
    source = (ROOT / "screens/maxis_personal_key.py").read_text(encoding="utf-8")
    assert "watch_maxis_live_state(runtime, player[\"SessionToken\"])" in source


def test_workspace_includes_canonical_team_score_for_polling_and_display():
    watcher = (ROOT / "services/maxis_live_state.py").read_text(encoding="utf-8")
    presentation = (ROOT / "screens/maxis_participant_experience.py").read_text(encoding="utf-8")
    assert "get_canonical_leaderboard" in watcher
    assert "get_canonical_leaderboard" in presentation
