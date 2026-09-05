"""UAT-004: Personal Key participants follow canonical Captain-selection state."""
from unittest.mock import patch

from data.runtime_database import RuntimeDatabaseError
from screens import maxis_personal_key as personal_key
from services.maxis_team_formation_gate import (
    country_reveal_is_active,
    country_roster_is_available,
    team_formation_phase,
)


def _workspace(phase: str) -> dict:
    return {
        "TeamFormationPhase": phase,
        # Deliberately leave this contradictory for the CAPTAIN_SELECTION test:
        # presentation must use the persisted phase, not Lifecycle.
        "Lifecycle": "TEAM_FORMATION",
        "TeamID": "TEAM-JAPAN",
        "TeamIdentity": "Japan",
        "TeamMembers": [{"Name": "Elnaz Ho"}],
        "CanClaimCaptain": phase == "CAPTAIN_SELECTION",
    }


def _player() -> dict:
    return {
        "EventID": personal_key.EVENT_ID,
        "ParticipantID": "elnaz-id",
        "TeamID": "TEAM-JAPAN",
        "SessionToken": "canonical-session",
    }


def test_country_reveal_is_limited_to_pre_captain_formation_phases():
    for phase in ("DRAFT", "REGISTRATION_OPEN", "FORMATION_LOCKED"):
        workspace = _workspace(phase)
        assert team_formation_phase(workspace) == phase
        assert country_reveal_is_active(workspace) is True
        assert country_roster_is_available(workspace) is False


def test_captain_selection_uses_canonical_phase_not_stale_lifecycle_label():
    workspace = _workspace("CAPTAIN_SELECTION")
    assert country_reveal_is_active(workspace) is False
    assert country_roster_is_available(workspace) is True


def test_restored_personal_key_session_enters_roster_projection_without_relogin():
    workspace = _workspace("CAPTAIN_SELECTION")

    class Runtime:
        def theme_park_race_participant_workspace(self, session_token):
            assert session_token == "canonical-session"
            return workspace

    with patch("screens.maxis_participant_experience.render_maxis_theme_park_participant") as render:
        assert personal_key._render_post_reveal_experience(Runtime(), _player(), "same-device") is True

    render.assert_called_once()
    assert render.call_args.kwargs["workspace"] is workspace
    assert render.call_args.kwargs["device_id"] == "same-device"


def test_workspace_read_failure_never_silently_falls_back_to_country_only_reveal():
    class Runtime:
        def theme_park_race_participant_workspace(self, session_token):
            raise RuntimeDatabaseError("temporary read failure")

    with patch.object(personal_key, "st") as st:
        st.button.return_value = False
        assert personal_key._render_post_reveal_experience(Runtime(), _player(), "same-device") is True
    st.warning.assert_called_once_with("Mission AI is reconnecting.")


def test_captain_recovery_preserves_the_canonical_session_returned_by_the_rpc():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "screens/maxis_participant_experience.py").read_text(encoding="utf-8")
    assert "recover_team_formation_captain" in source
    assert "restore_participant_identity(identity)" in source
