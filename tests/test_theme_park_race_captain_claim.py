"""P0: surface the Theme Park Captain claim during CAPTAIN_SELECTION.

Human UAT on CERT-GENTING-UAT-20260824 reached TeamFormation.Phase =
CAPTAIN_SELECTION with Adrian Choong on Velocity and Ruth on Aurora, and no
participant was ever offered a way to become Team Captain.  The canonical
participant projection never carried the team's effective Captain, so the
surface could not tell "the seat is open" from "a team mate already took it".
"""
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import StandardCoreV2Adapter
from engines.theme_park_race import participant_projection
from screens import theme_park_race as TPR


ROOT = Path(__file__).resolve().parents[1]
EVENT_ID = "CERT-GENTING-UAT-20260824"
SESSION_TOKEN = "11111111-1111-4111-8111-111111111111"
DEVICE_ID = "DEVICE-ADRIAN"

EVENT = {
    "EventID": EVENT_ID,
    "EventName": "Genting Theme Park Race",
    "_EventPayload": {
        "RaceConfiguration": {
            "SchemaVersion": 1, "EngineKind": "THEME_PARK_RACE",
            "StrategyMode": "OPEN_MISSION_BOARD", "RuntimePhase": "READY",
        },
        "TeamFormation": {
            "SchemaVersion": 1, "Phase": "CAPTAIN_SELECTION", "Mode": "RANDOM_ASSIGN",
        },
    },
}

ADRIAN = {"ParticipantID": "P1", "TeamID": "T6", "Name": "Adrian Choong"}
RUTH = {"ParticipantID": "P2", "TeamID": "T6", "Name": "Ruth"}


def _members(captain_participant_id=""):
    return [
        {**row, "IsTeamFormationCaptain": row["ParticipantID"] == captain_participant_id}
        for row in (ADRIAN, RUTH)
    ]


def _workspace_via_adapter(captain_participant_id="", viewer="P1"):
    """Drive the real adapter projection with stubbed canonical reads."""
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    adapter.get_player_by_token = lambda token: {
        "ParticipantID": viewer, "EventID": EVENT_ID, "TeamID": "T6",
        "Team": "Velocity", "Name": "Adrian Choong", "SessionToken": token,
    }
    adapter.get_event = lambda event_id: EVENT
    adapter.get_theme_park_race_players = lambda event_id: _members(captain_participant_id)
    adapter._one = lambda path, query, admin=True: {"device_id": DEVICE_ID}
    adapter.get_submissions = lambda event_id: []
    adapter.get_theme_park_race_stations = lambda event_id: []
    adapter.get_theme_park_race_mission_runtime = lambda event_id, team_id="": []
    return adapter.theme_park_race_participant_workspace(SESSION_TOKEN)


def _render(workspace, *, claim_result=None, claim_error=None, clicked=True):
    """Render the participant surface and capture the canonical RPC call."""
    seen = {}

    def claim(session_token, device_id):
        seen["args"] = (session_token, device_id)
        if claim_error:
            raise claim_error
        return claim_result or {}

    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        theme_park_race_participant_workspace=lambda token: workspace,
        claim_team_formation_captain=claim,
    ))
    with patch.object(TPR, "st", MagicMock()) as fake:
        fake.session_state = {
            "participant_session_token": SESSION_TOKEN,
            "participant_join_code": "GTU824",
        }
        fake.button.return_value = clicked
        TPR.render_theme_park_race_participant(db, device_id=DEVICE_ID)
    return fake, seen


def _texts(fake, *names):
    return [
        str(call.args[0])
        for name in names
        for call in getattr(fake, name).call_args_list
        if call.args
    ]


# 1. CAPTAIN_SELECTION renders a claim action for an eligible participant.

def test_captain_selection_renders_claim_action_for_eligible_participant():
    workspace = _workspace_via_adapter()
    assert workspace["Lifecycle"] == "CAPTAIN_SELECTION"
    assert workspace["CanClaimCaptain"] is True

    fake, _ = _render(workspace, clicked=False)
    labels = [call.args[0] for call in fake.button.call_args_list if call.args]
    assert "Become Team Captain" in labels


def test_claim_action_shows_team_name_and_formation_state():
    fake, _ = _render(_workspace_via_adapter(), clicked=False)
    shown = _texts(fake, "caption", "info", "subheader", "write")
    assert any("Velocity" in text for text in shown)
    assert "Captain Selection" in shown
    assert any("does not have a Team Captain" in text for text in shown)


@pytest.mark.parametrize("phase,expected", [
    ("CAPTAIN_SELECTION", True),
    ("FORMATION_LOCKED", False),
    ("REGISTRATION_OPEN", False),
    ("DRAFT", False),
])
def test_claim_action_is_offered_only_during_captain_selection(phase, expected):
    projection = participant_projection(
        event={"EventID": EVENT_ID, "_EventPayload": {
            **EVENT["_EventPayload"],
            "TeamFormation": {"SchemaVersion": 1, "Phase": phase},
        }},
        participant=ADRIAN, stations=[], submissions=[], team_members=_members(),
    )
    assert projection["CanClaimCaptain"] is expected


# 2 & 3. The claim calls the canonical RPC with the canonical token + device id.

def test_claim_calls_canonical_team_formation_captain_rpc_with_session_and_device():
    fake, seen = _render(_workspace_via_adapter(), claim_result={"Claimed": True})
    assert seen["args"] == (SESSION_TOKEN, DEVICE_ID)


def test_adapter_routes_the_claim_to_the_canonical_contract_without_service_role():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    calls = []
    adapter._rpc = lambda name, payload, admin=True: calls.append((name, payload, admin)) or {}
    adapter.claim_team_formation_captain(SESSION_TOKEN, DEVICE_ID)

    name, payload, admin = calls[0]
    assert name == "exos_v2_claim_team_formation_captain"
    assert payload == {
        "p_participant_session_token": SESSION_TOKEN,
        "p_device_id": DEVICE_ID,
    }
    # The participant's own key, never the service role.
    assert admin is False


def test_claim_never_uses_the_formula_race_pin_or_captain_shell():
    source = (ROOT / "screens/theme_park_race.py").read_text()
    # No import of, or call into, the legacy Formula R.A.C.E. captain shell.
    assert "formula_race" not in source.casefold().replace(
        "no pin, no formula r.a.c.e. captain shell", "",
    )
    # No PIN entry: the claim is settled by the participant's own session.
    assert 'type="password"' not in source
    assert "formula_race_captain_login" not in source
    assert "formula_race_captain_recover" not in source
    assert "claim_team_formation_captain" in source


def test_claim_is_refused_when_the_participant_session_is_missing():
    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        claim_team_formation_captain=lambda *a: pytest.fail("must not call the RPC"),
    ))
    with patch.object(TPR, "st", MagicMock()) as fake:
        fake.session_state = {}
        fake.button.return_value = True
        TPR._render_captain_claim(db, _workspace_via_adapter(), DEVICE_ID)
    assert fake.error.called


# 4. A successful claim refreshes canonical state.

def test_successful_claim_refreshes_canonical_state():
    fake, _ = _render(_workspace_via_adapter(), claim_result={"Claimed": True})
    assert fake.rerun.called
    assert any("Team Captain" in text for text in _texts(fake, "success"))


def test_claimed_captain_is_projected_as_the_effective_captain_after_refresh():
    after = _workspace_via_adapter(captain_participant_id="P1")
    assert after["IsCaptain"] is True
    assert after["TeamHasCaptain"] is True
    assert after["CaptainParticipantID"] == "P1"
    assert after["CanClaimCaptain"] is False


def test_effective_captain_reaches_the_theme_park_mission_board_when_active():
    workspace = _workspace_via_adapter(captain_participant_id="P1")
    workspace["Lifecycle"] = "ACTIVE"
    workspace["CaptainSessionActive"] = True
    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        theme_park_race_participant_workspace=lambda token: workspace,
    ))
    with patch.object(TPR, "_render_open_mission_board") as board, \
            patch.object(TPR, "st", MagicMock()) as fake:
        fake.session_state = {"participant_session_token": SESSION_TOKEN}
        TPR.render_theme_park_race_participant(db, device_id=DEVICE_ID)
    board.assert_called_once()
    assert board.call_args[0][2] is True


# 5. An already-claimed team shows a safe non-claim state.

def test_already_claimed_team_shows_safe_state_and_never_offers_the_claim():
    workspace = _workspace_via_adapter(captain_participant_id="P2")
    assert workspace["CanClaimCaptain"] is False
    assert workspace["CaptainName"] == "Ruth"

    fake, seen = _render(workspace)
    labels = [call.args[0] for call in fake.button.call_args_list if call.args]
    assert "Become Team Captain" not in labels
    assert "args" not in seen
    assert any("Captain already selected" in text for text in _texts(fake, "info"))


def test_losing_a_claim_race_reports_the_safe_already_selected_state():
    fake, _ = _render(
        _workspace_via_adapter(),
        claim_result={"Claimed": False, "CaptainAlreadyClaimed": True},
    )
    assert any("Captain already selected" in text for text in _texts(fake, "info"))
    assert fake.rerun.called


def test_captain_active_on_another_device_is_reported_as_recovery_not_as_taken():
    fake, _ = _render(
        _workspace_via_adapter(),
        claim_result={"Claimed": False, "RecoveryRequired": True},
    )
    warnings = _texts(fake, "warning")
    assert any("different device" in text for text in warnings)
    assert not any("already selected" in text for text in _texts(fake, "info"))


def test_a_failed_claim_surfaces_the_error_without_crashing_the_surface():
    fake, _ = _render(
        _workspace_via_adapter(),
        claim_error=RuntimeDatabaseError("Captain claim is not open for this event"),
    )
    assert any("not open" in text for text in _texts(fake, "error"))


# 6. Non-captains remain in the participant/team waiting state.

def test_non_captain_remains_in_the_participant_waiting_state():
    workspace = _workspace_via_adapter(captain_participant_id="P2")
    fake, _ = _render(workspace, clicked=False)
    shown = _texts(fake, "subheader", "info", "caption")
    assert "Captain Selection" in shown
    assert any("Velocity" in text for text in shown)
    # No mission board before the hunt is active.
    assert not any("Mission opportunity board" in text for text in _texts(fake, "markdown"))


def test_non_captain_never_receives_captain_authority_when_active():
    workspace = _workspace_via_adapter(captain_participant_id="P2")
    workspace["Lifecycle"] = "ACTIVE"
    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        theme_park_race_participant_workspace=lambda token: workspace,
    ))
    with patch.object(TPR, "_render_open_mission_board") as board, \
            patch.object(TPR, "st", MagicMock()) as fake:
        fake.session_state = {"participant_session_token": SESSION_TOKEN}
        TPR.render_theme_park_race_participant(db, device_id=DEVICE_ID)
    assert board.call_args[0][2] is False


def test_a_reconnecting_workspace_offers_a_retry_instead_of_a_dead_end():
    def raises(token):
        raise RuntimeDatabaseError("Participant session is required.")

    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        theme_park_race_participant_workspace=raises,
    ))
    with patch.object(TPR, "st", MagicMock()) as fake:
        fake.session_state = {"participant_session_token": SESSION_TOKEN}
        fake.button.return_value = False
        TPR.render_theme_park_race_participant(db, device_id=DEVICE_ID)
    assert "Retry" in [call.args[0] for call in fake.button.call_args_list if call.args]


# 7. Formula R.A.C.E. captain flow is untouched.

def test_formula_race_captain_flow_is_untouched_by_theme_park_captain_claim():
    captain = (ROOT / "screens/formula_race_captain.py").read_text()
    assert "formula_race_captain_login" in captain
    assert "claim_team_formation_captain" not in captain
    assert "CanClaimCaptain" not in captain

    entrypoint = (ROOT / "Participant.py").read_text()
    assert 'st.query_params.get("race", "")' in entrypoint
    assert "show_formula_race_captain()" in entrypoint
    # The Theme Park routing fix from 4658827 still guards the legacy shell.
    assert entrypoint.index("if _is_theme_park_race_request():") < entrypoint.index(
        "show_formula_race_captain()",
    )


def test_random_assign_registration_and_recovery_contracts_are_unchanged():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    calls = []
    adapter._rpc = lambda name, payload, admin=True: calls.append((name, admin)) or {}
    adapter.get_event_by_join_code = lambda code: EVENT
    adapter.event_metadata = lambda event: event["_EventPayload"]
    adapter._identity = StandardCoreV2Adapter._identity

    adapter.register_team_formation_participant("GTU824", "Adrian Choong", DEVICE_ID, "C" * 43)
    adapter.recover_team_formation_participant("GTU824", "C" * 43, DEVICE_ID)
    assert calls == [
        ("exos_v2_team_formation_register_random", False),
        ("exos_v2_recover_team_formation_participant", False),
    ]


# 8. No secret or session credential is ever rendered.

def test_no_session_or_credential_value_is_rendered_publicly():
    for workspace in (
        _workspace_via_adapter(),
        _workspace_via_adapter(captain_participant_id="P2"),
        _workspace_via_adapter(captain_participant_id="P1"),
    ):
        fake, _ = _render(workspace, claim_result={"Claimed": True}, clicked=False)
        rendered = " ".join(_texts(
            fake, "write", "caption", "info", "success", "warning", "error",
            "subheader", "markdown", "title", "header",
        ))
        assert SESSION_TOKEN not in rendered
        assert DEVICE_ID not in rendered
        assert "GTU824" not in rendered


def test_projection_exposes_no_session_token_device_or_credential():
    workspace = _workspace_via_adapter(captain_participant_id="P2")
    flat = repr(workspace)
    assert SESSION_TOKEN not in flat
    assert DEVICE_ID not in flat
    for key in workspace:
        assert "SessionToken" not in key
        assert "Credential" not in key
        assert "DeviceID" not in key


def test_captain_identity_is_limited_to_a_display_name():
    workspace = _workspace_via_adapter(captain_participant_id="P2")
    assert set(workspace["TeamMembers"][0]) == {"ParticipantID", "Name", "IsCaptain"}
    assert workspace["CaptainName"] == "Ruth"
