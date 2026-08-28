"""P0: the human facilitator review surface for OPEN_MISSION_BOARD.

Genting UAT reached a real pending board submission (Velocity / Standard
Mission — UAT) and the facilitator had no usable REJECT.  The 039 routing was
already correct; the review surface was not: the controls sat in a collapsed
panel, were silently disabled without a facilitator identity, and Reject was a
subordinate secondary button labelled only by a raw activity id.
"""
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from data.control_runtime import ControlRuntime
from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import StandardCoreV2Adapter
from screens import theme_park_race as TPR
from screens.theme_park_race import submit_theme_park_race_review


ROOT = Path(__file__).resolve().parents[1]
EVENT_ID = "CERT-GENTING-UAT-20260824"
SUBMISSION_ID = "22222222-2222-4222-8222-222222222222"
REVISION = "2026-08-25T00:10:00+00:00"
BOARD_RPC = "exos_v2_theme_park_race_board_review"
STANDARD_RPC = "exos_v2_standard_review_submission"

SUBMISSION = {
    "SubmissionID": SUBMISSION_ID,
    "TeamID": "T6",
    "ActivityID": "A1",
    "Remarks": "Our team answer for the UAT mission.",
    "ImageURL": "https://example.invalid/private-photo.jpg",
    "DriveFileID": "",
    "SubmittedAt": REVISION,
    "Score": 0,
    "Status": "SUBMITTED",
}


def _workspace(strategy_mode="OPEN_MISSION_BOARD", queue=None):
    return {
        "Lifecycle": "ACTIVE", "TeamFormationPhase": "ACTIVE", "RuntimePhase": "ACTIVE",
        "StrategyMode": strategy_mode,
        "Teams": [{"TeamID": "T6", "TeamIdentity": "Velocity"}],
        "MissionOperations": [{
            "ActivityID": "A1", "DisplayName": "Standard Mission — UAT",
            "MissionClass": "STANDARD", "OperationalStatus": "AVAILABLE",
            "SecretState": "RELEASED",
        }],
        "ReviewQueue": [dict(SUBMISSION)] if queue is None else queue,
        "RegistrationCount": 2, "TeamCount": 2, "CaptainCount": 2,
        "MissionCount": 6, "PendingReviewCount": 1,
    }


def _render(*, actor="Facilitator A", notes="", click=None, workspace=None, control=None):
    """Render the facilitator surface, optionally clicking one review button."""
    workspace = workspace if workspace is not None else _workspace()
    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        theme_park_race_facilitator_workspace=lambda event_id: workspace,
        get_theme_park_race_players=lambda event_id: [],
    ))
    columns = []

    def make_columns(spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        made = []
        for _ in range(count):
            column = MagicMock()
            column.button.return_value = False
            column.__enter__ = lambda self: None
            column.__exit__ = lambda self, *args: False
            made.append(column)
        columns.extend(made)
        return made

    with patch.object(TPR, "st", MagicMock()) as fake, \
            patch.object(TPR, "get_photo_url", lambda url, drive: url or ""):
        fake.session_state = {}
        fake.button.side_effect = lambda label, **kwargs: (
            click is not None and click in str(label) and not kwargs.get("disabled", False)
        )
        fake.text_input.side_effect = lambda label, **kwargs: (
            actor if "identity" in label.casefold() else notes
        )
        fake.number_input.side_effect = lambda label, **kwargs: kwargs.get("value", 0.0)
        fake.selectbox.side_effect = lambda label, options, **kwargs: list(options)[0]
        fake.columns.side_effect = make_columns
        fake.expander.return_value.__enter__ = lambda self: None
        fake.expander.return_value.__exit__ = lambda self, *args: False
        TPR.render_theme_park_race_facilitator(db, control or MagicMock(), EVENT_ID)
    return fake


def _buttons(fake):
    return {
        str(call.args[0]): call.kwargs.get("disabled", False)
        for call in fake.button.call_args_list if call.args
    }


def _review_buttons(fake):
    return {
        label: disabled for label, disabled in _buttons(fake).items()
        if "Approve" in label or "Resubmission" in label
    }


def _board_adapter():
    """Real adapter + ControlRuntime, capturing the RPC the 039 route emits."""
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    calls = []
    adapter._rpc = lambda name, payload, admin=True: (
        calls.append({"name": name, "payload": payload, "admin": admin}) or {"Reviewed": True}
    )
    control = ControlRuntime.__new__(ControlRuntime)
    control.runtime = adapter
    control._run = lambda fn, *args, **kwargs: fn(*args, **kwargs)
    return control, calls


# 1 & 2. A SUBMITTED board submission renders both decisions.

def test_open_mission_board_submitted_renders_approve():
    assert "✓ Approve" in _review_buttons(_render())


def test_open_mission_board_submitted_renders_reject():
    assert "↻ Return for Resubmission" in _review_buttons(_render())


def test_pending_review_is_expanded_and_names_its_team_and_mission():
    fake = _render()
    labels = [str(call.args[0]) for call in fake.expander.call_args_list if call.args]
    review = next(label for label in labels if "Velocity" in label)
    assert "Standard Mission — UAT" in review
    assert "SUBMITTED" in review
    expanded = [
        call.kwargs.get("expanded") for call in fake.expander.call_args_list
        if call.args and "Velocity" in str(call.args[0])
    ]
    assert expanded == [True]


def test_review_surface_shows_the_required_human_workflow_fields():
    fake = _render()
    shown = " ".join(
        str(call.args[0]) for name in ("caption", "write", "markdown")
        for call in getattr(fake, name).call_args_list if call.args
    )
    assert "Velocity" in shown and "Standard Mission — UAT" in shown
    assert "Our team answer" in shown
    assert REVISION in shown
    inputs = [str(call.args[0]) for call in fake.number_input.call_args_list if call.args]
    inputs += [str(call.args[0]) for call in fake.text_input.call_args_list if call.args]
    assert any("Score" in label for label in inputs)
    assert any("reason" in label.casefold() for label in inputs)
    assert fake.image.called


def test_missing_facilitator_identity_is_explained_rather_than_silently_disabled():
    fake = _render(actor="")
    assert all(_review_buttons(fake).values()), "both decisions must be disabled"
    warnings = [str(call.args[0]) for call in fake.warning.call_args_list if call.args]
    assert any("facilitator identity" in text.casefold() for text in warnings)


# 3, 4, 6, 7. REJECT routes to 039 with decision, score 0, revision, actor, reason.

def test_reject_calls_the_039_board_review_route_with_a_zero_score():
    control, calls = _board_adapter()
    _render(notes="Photo does not show the mission.", click="Resubmission", control=control)

    assert len(calls) == 1
    call = calls[0]
    assert call["name"] == BOARD_RPC
    assert call["payload"]["p_decision"] == "REJECT"
    assert call["payload"]["p_score"] == 0.0


def test_reject_supplies_the_exact_submission_and_submitted_at_revision():
    control, calls = _board_adapter()
    _render(notes="Resubmit please.", click="Resubmission", control=control)

    payload = calls[0]["payload"]
    assert payload["p_submission_id"] == SUBMISSION_ID
    assert payload["p_expected_submitted_at"] == REVISION


def test_reject_supplies_facilitator_identity_and_reason():
    control, calls = _board_adapter()
    _render(actor="Ruth", notes="Photo is out of focus.", click="Resubmission", control=control)

    payload = calls[0]["payload"]
    assert payload["p_actor"] == "Ruth"
    assert payload["p_reason"] == "Photo is out of focus."


def test_reject_preserves_server_side_idempotency_for_the_reviewed_revision():
    control, calls = _board_adapter()
    _render(notes="Resubmit.", click="Resubmission", control=control)
    key = calls[0]["payload"]["p_idempotency_key"]
    assert SUBMISSION_ID in key and REVISION in key and "REJECT" in key


def test_reject_requires_a_reason_and_cannot_be_mis_clicked_without_one():
    fake = _render(notes="")
    buttons = _review_buttons(fake)
    assert buttons["↻ Return for Resubmission"] is True
    assert buttons["✓ Approve"] is False


def test_reject_never_approves_and_never_carries_a_score():
    control, calls = _board_adapter()
    # Even with a score typed into the approve input, REJECT must send zero.
    submission = dict(SUBMISSION, Score=95)
    _render(
        notes="No.", click="Resubmission", control=control,
        workspace=_workspace(queue=[submission]),
    )
    payload = calls[0]["payload"]
    assert payload["p_decision"] == "REJECT"
    assert payload["p_score"] == 0.0


# 5. APPROVE routes to the same 039 contract.

def test_approve_calls_the_039_board_review_route_with_the_facilitator_score():
    control, calls = _board_adapter()
    submission = dict(SUBMISSION, Score=12)
    _render(
        actor="Ruth", notes="Clear evidence.", click="Approve", control=control,
        workspace=_workspace(queue=[submission]),
    )
    payload = calls[0]["payload"]
    assert calls[0]["name"] == BOARD_RPC
    assert payload["p_decision"] == "APPROVE"
    assert payload["p_score"] == 12.0
    assert payload["p_expected_submitted_at"] == REVISION
    assert payload["p_actor"] == "Ruth"
    assert payload["p_reason"] == "Clear evidence."


@pytest.mark.parametrize("click,decision", [("Approve", "APPROVE"), ("Resubmission", "REJECT")])
def test_neither_decision_routes_through_the_standard_review_contract(click, decision):
    control, calls = _board_adapter()
    _render(notes="reason", click=click, control=control)
    assert [call["name"] for call in calls] == [BOARD_RPC]
    assert STANDARD_RPC not in [call["name"] for call in calls]
    assert calls[0]["payload"]["p_decision"] == decision


# 8. A stale revision fails safely and reloads canonical state.

def test_a_stale_revision_is_reported_and_never_reviews_the_newer_submission():
    control = MagicMock()
    control.review_theme_park_race_board_submission.side_effect = RuntimeDatabaseError(
        "Theme Park Race board revision is stale",
    )
    outcome = submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", dict(SUBMISSION),
        decision="APPROVE", score=10, actor="Ruth", notes="ok",
    )
    assert outcome["Reviewed"] is False
    assert outcome["Level"] == "warning"
    assert "refreshed" in outcome["Message"]


def test_a_submission_without_a_revision_is_refused_rather_than_reviewed():
    control = MagicMock()
    outcome = submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", dict(SUBMISSION, SubmittedAt=""),
        decision="REJECT", score=0, actor="Ruth", notes="no",
    )
    assert outcome["Reviewed"] is False
    control.review_theme_park_race_board_submission.assert_not_called()


def test_the_adapter_refuses_a_board_review_missing_revision_or_actor():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    adapter._rpc = lambda *a, **k: pytest.fail("must not reach the database")
    for revision, actor in ((REVISION, ""), ("", "Ruth"), ("", "")):
        with pytest.raises(RuntimeDatabaseError):
            adapter.review_theme_park_race_board_submission(
                SUBMISSION_ID, revision, "REJECT", score=0, actor=actor, reason="r",
            )


def test_a_stale_outcome_is_surfaced_to_the_facilitator_on_the_next_render():
    with patch.object(TPR, "st", MagicMock()) as fake:
        fake.session_state = {}
        TPR._queue_review_notice(EVENT_ID, {
            "Reviewed": False, "Level": "warning", "Message": TPR._STALE_REVISION_NOTICE,
        })
        assert fake.session_state
        TPR._render_review_notice(EVENT_ID)
        assert fake.warning.called
        assert not fake.session_state, "the notice is consumed once"


# 9. Other strategies and review paths are unchanged.

def test_configured_team_route_keeps_its_existing_review_contract():
    control = MagicMock()
    for decision, expected in (("APPROVE", "APPROVED"), ("REJECT", "REJECTED")):
        control.reset_mock()
        outcome = submit_theme_park_race_review(
            control, "CONFIGURED_TEAM_ROUTE", dict(SUBMISSION),
            decision=decision, score=8, actor="Ruth", notes="note",
        )
        assert outcome == {"Reviewed": True}
        control.review_theme_park_race_board_submission.assert_not_called()
        control.review_submission.assert_called_once()
        assert control.review_submission.call_args.kwargs["status"] == expected


def test_configured_team_route_reject_still_scores_zero():
    control = MagicMock()
    submit_theme_park_race_review(
        control, "CONFIGURED_TEAM_ROUTE", dict(SUBMISSION),
        decision="REJECT", score=50, actor="Ruth", notes="no",
    )
    assert control.review_submission.call_args.args[1] == 0


# 10. Formula R.A.C.E. is untouched.

def test_formula_race_review_paths_are_untouched():
    theme_park = (ROOT / "screens/theme_park_race.py").read_text()
    assert "formula_race" not in theme_park.casefold().replace(
        "no pin, no formula r.a.c.e. captain shell", "",
    )
    console = (ROOT / "screens/live_event_console.py").read_text()
    assert BOARD_RPC not in console
    assert "review_theme_park_race_board_submission" not in console
    captain = (ROOT / "screens/formula_race_captain.py").read_text()
    assert BOARD_RPC not in captain


# 11. Participant and Projector never receive review controls or private data.

def test_participant_surface_has_no_review_controls():
    workspace = {
        "EventID": EVENT_ID, "Lifecycle": "ACTIVE", "StrategyMode": "OPEN_MISSION_BOARD",
        "TeamIdentity": "Velocity", "IsCaptain": True, "CaptainSessionActive": True,
        "CanClaimCaptain": False, "TeamHasCaptain": True, "CaptainName": "Adrian Choong",
        "Progress": {"Completed": 0, "Total": 1, "SubmissionsByActivity": {}},
        "Route": [], "MissionBoard": [{
            "ActivityID": "A1", "DisplayName": "Standard Mission — UAT",
            "MissionClass": "STANDARD", "MissionState": "SUBMITTED",
            "Zone": "Z", "LocationDescription": "L",
        }],
    }
    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        theme_park_race_participant_workspace=lambda token: workspace,
    ))
    with patch.object(TPR, "st", MagicMock()) as fake:
        fake.session_state = {"participant_session_token": "T"}
        fake.button.return_value = False
        fake.expander.return_value.__enter__ = lambda self: None
        fake.expander.return_value.__exit__ = lambda self, *args: False
        TPR.render_theme_park_race_participant(db, device_id="D")

    labels = [str(call.args[0]) for call in fake.button.call_args_list if call.args]
    assert not any("Approve" in label or "Reject" in label for label in labels)
    shown = " ".join(
        str(call.args[0]) for name in ("caption", "write", "info", "markdown")
        for call in getattr(fake, name).call_args_list if call.args
    )
    assert "Facilitator" not in shown
    assert "Review notes" not in shown


def test_projector_projection_carries_no_review_queue_or_private_evidence():
    from engines.theme_park_race import projector_projection

    facilitator = {
        "StrategyMode": "OPEN_MISSION_BOARD",
        "Teams": [{
            "TeamID": "T6", "TeamIdentity": "Velocity", "Completed": 0, "Total": 1,
            "CurrentActivityID": "A1", "SelectedMissionActivityIDs": ["A1"],
            "MissionBoard": [{"ActivityID": "A1"}],
        }],
        "ReviewQueue": [dict(SUBMISSION)],
    }
    projection = projector_projection(facilitator, {
        "SchemaVersion": 1, "EngineKind": "THEME_PARK_RACE",
        "StrategyMode": "OPEN_MISSION_BOARD", "MissionBoard": {},
    })
    flat = repr(projection)
    assert "ReviewQueue" not in projection
    assert SUBMISSION_ID not in flat
    assert "Our team answer" not in flat
    assert "private-photo" not in flat
    for team in projection.get("Teams", []):
        assert "SelectedMissionActivityIDs" not in team
        assert "MissionBoard" not in team


def test_the_board_review_route_is_confined_to_the_facilitator_surface():
    for path in ("screens/participant.py", "screens/leaderboard_display.py",
                 "screens/projector_broadcast.py"):
        source = (ROOT / path).read_text()
        assert BOARD_RPC not in source
        assert "review_theme_park_race_board_submission" not in source
