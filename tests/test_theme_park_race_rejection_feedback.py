"""P0: a rejected Theme Park mission must not look like a never-submitted one.

Genting UAT executed a real REJECT on Velocity's Standard Mission — UAT
submission through the 039 contract, and the mission board reopened for
resubmission, but rendered exactly the blank never-submitted evidence form:
no banner, no facilitator reason. The canonical decision, reviewer, revision
and rationale were already persisted by 039 (reviews_v2 via
exos_v2_theme_park_race_board_review); nothing read them back.
"""
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from data.standard_core_v2_adapter import StandardCoreV2Adapter
from engines.theme_park_race import mission_board, participant_projection
from screens import theme_park_race as TPR


ROOT = Path(__file__).resolve().parents[1]
EVENT_ID = "CERT-GENTING-UAT-20260824"
SUBMISSION_ID = "33333333-3333-4333-8333-333333333333"
REASON = "Photo is blurry — please retake with the mission signage visible."

CONFIG = {
    "SchemaVersion": 1, "EngineKind": "THEME_PARK_RACE",
    "StrategyMode": "OPEN_MISSION_BOARD", "RuntimePhase": "ACTIVE",
}
STATION = {
    "ActivityID": "A1", "DisplayName": "Standard Mission — UAT",
    "MissionClass": "STANDARD", "DisplayOrder": 1,
    "Evidence": {"Text": {"Required": True}},
}


def _event(runtime_phase="ACTIVE", team_formation_phase="ACTIVE"):
    return {
        "EventID": EVENT_ID,
        "_EventPayload": {
            "RaceConfiguration": {**CONFIG, "RuntimePhase": runtime_phase},
            "TeamFormation": {"SchemaVersion": 1, "Phase": team_formation_phase},
        },
    }


def _raw_review_row(decision="REJECT", reason=REASON, reviewed_at="2026-08-25T01:00:00Z"):
    return {
        "submission_id": SUBMISSION_ID, "decision": decision,
        "rationale": reason, "reviewed_at": reviewed_at,
    }


def _workspace_via_adapter(*, status, reviews_rows=None):
    """Drive the real adapter end to end: submissions -> reviews -> projection."""
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    submission = {
        "SubmissionID": SUBMISSION_ID, "EventID": EVENT_ID, "TeamID": "T6",
        "ActivityID": "A1", "Status": status, "SubmittedAt": "2026-08-25T00:10:00Z",
    }
    adapter.get_player_by_token = lambda token: {
        "ParticipantID": "P1", "EventID": EVENT_ID, "TeamID": "T6",
        "Team": "Velocity", "Name": "Adrian Choong",
    }
    adapter.get_event = lambda event_id: _event()
    adapter.get_theme_park_race_players = lambda event_id: [
        {"ParticipantID": "P1", "TeamID": "T6", "Name": "Adrian Choong", "IsTeamFormationCaptain": True},
    ]
    adapter._one = lambda path, query, admin=True: {"device_id": "DEV-1"}
    adapter.get_submissions = lambda event_id: [submission]
    adapter.get_theme_park_race_stations = lambda event_id: [STATION]
    adapter.get_theme_park_race_mission_runtime = lambda event_id, team_id="": []

    calls = []

    def rows(path, query, admin=True):
        calls.append((path, query))
        return reviews_rows if reviews_rows is not None else []

    adapter._rows = rows
    workspace = adapter.theme_park_race_participant_workspace("TOK")
    return workspace, calls


def _render(workspace, *, click=False):
    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        theme_park_race_participant_workspace=lambda token: workspace,
    ))
    with patch.object(TPR, "st", MagicMock()) as fake:
        fake.session_state = {"participant_session_token": "TOK"}
        fake.button.return_value = click
        fake.file_uploader.return_value = None
        fake.text_area.return_value = ""
        fake.expander.return_value.__enter__ = lambda self: None
        fake.expander.return_value.__exit__ = lambda self, *args: False
        TPR.render_theme_park_race_participant(db, device_id="DEV-1")
    return fake


def _texts(fake, *names):
    return [
        str(call.args[0]) for name in names
        for call in getattr(fake, name).call_args_list if call.args
    ]


# A. never-submitted mission has no rejection banner.

def test_never_submitted_mission_has_no_rejection_banner():
    workspace, _ = _workspace_via_adapter(status="")
    fake = _render(workspace)
    assert "⚠️ Resubmission required" not in _texts(fake, "warning")


def test_selected_mission_is_never_confused_with_rejected():
    board = mission_board(
        CONFIG, [STATION], team_id="T6",
        submissions=[],
        mission_runtime=[{
            "TeamID": "T6", "ActivityID": "A1",
            "StatePayload": {"StrategyMode": "OPEN_MISSION_BOARD", "MissionState": "SELECTED"},
        }],
    )
    assert board[0]["MissionState"] == "SELECTED"
    assert board[0]["RejectionReason"] == ""


# B. rejected mission shows "Resubmission required".

def test_rejected_mission_renders_the_resubmission_required_banner():
    workspace, _ = _workspace_via_adapter(status="REJECTED", reviews_rows=[_raw_review_row()])
    assert workspace["MissionBoard"][0]["MissionState"] == "REJECTED"

    fake = _render(workspace)
    markdown_texts = _texts(fake, "markdown")
    assert any("Resubmission Required" in text for text in markdown_texts)
    assert any("reviewed and returned" in text for text in markdown_texts)


def test_rejected_state_reads_distinctly_from_selected_in_the_projection():
    board = mission_board(
        CONFIG, [STATION], team_id="T6",
        submissions=[{"SubmissionID": SUBMISSION_ID, "TeamID": "T6", "ActivityID": "A1", "Status": "REJECTED"}],
        reviews=[{"SubmissionID": SUBMISSION_ID, "Decision": "REJECT", "Reason": REASON, "ReviewedAt": "t1"}],
    )
    assert board[0]["MissionState"] == "REJECTED"
    assert board[0]["CanSubmit"] is True
    assert board[0]["CanSelect"] is False


# C. facilitator reason is visible.

def test_facilitator_rejection_reason_is_visible_to_the_captain():
    workspace, calls = _workspace_via_adapter(status="REJECTED", reviews_rows=[_raw_review_row()])
    assert workspace["MissionBoard"][0]["RejectionReason"] == REASON

    fake = _render(workspace)
    assert REASON in _texts(fake, "write")
    assert "**Facilitator feedback:**" in _texts(fake, "markdown")
    # The query is scoped: only this team's rejected submission, only REJECT rows.
    path, query = calls[0]
    assert path == "reviews_v2"
    assert query["submission_id"] == f"in.({SUBMISSION_ID})"
    assert query["decision"] == "eq.REJECT"


def test_the_latest_reject_review_wins_when_a_submission_was_reviewed_more_than_once():
    reasons = mission_board(
        CONFIG, [STATION], team_id="T6",
        submissions=[{"SubmissionID": SUBMISSION_ID, "TeamID": "T6", "ActivityID": "A1", "Status": "REJECTED"}],
        reviews=[
            {"SubmissionID": SUBMISSION_ID, "Decision": "REJECT", "Reason": "First pass: missing evidence.", "ReviewedAt": "2026-08-25T00:00:00Z"},
            {"SubmissionID": SUBMISSION_ID, "Decision": "REJECT", "Reason": "Second pass: still blurry.", "ReviewedAt": "2026-08-25T02:00:00Z"},
        ],
    )
    assert reasons[0]["RejectionReason"] == "Second pass: still blurry."


def test_a_missing_reason_still_renders_the_banner_without_a_fabricated_message():
    workspace, _ = _workspace_via_adapter(status="REJECTED", reviews_rows=[])
    fake = _render(workspace)
    assert any("Resubmission Required" in text for text in _texts(fake, "markdown"))
    assert not any("Facilitator feedback" in text for text in _texts(fake, "markdown"))


# D. rejected mission can be resubmitted.

def test_rejected_mission_remains_submittable_and_the_form_is_reachable():
    workspace, _ = _workspace_via_adapter(status="REJECTED", reviews_rows=[_raw_review_row()])
    assert workspace["MissionBoard"][0]["CanSubmit"] is True

    with patch.object(TPR, "_render_evidence_form") as evidence_form:
        _render(workspace)
    evidence_form.assert_called_once()
    assert evidence_form.call_args[0][2]["MissionState"] == "REJECTED"


def test_ride_class_rejection_also_shows_the_banner_before_the_ride_form():
    ride_station = dict(STATION, MissionClass="RIDE", RideParticipation={"RequiredPercent": 80})
    workspace, _ = _workspace_via_adapter(status="REJECTED", reviews_rows=[_raw_review_row()])
    workspace["MissionBoard"][0] = dict(workspace["MissionBoard"][0], MissionClass="RIDE")

    with patch.object(TPR, "_render_ride_evidence_form") as ride_form:
        fake = _render(workspace)
    ride_form.assert_called_once()
    assert any("Resubmission Required" in text for text in _texts(fake, "markdown"))


# E. resubmission removes the rejection presentation and returns to awaiting review.

def test_resubmission_clears_the_rejection_banner_and_returns_to_awaiting_review():
    workspace, _ = _workspace_via_adapter(status="SUBMITTED", reviews_rows=[_raw_review_row()])
    board = workspace["MissionBoard"][0]
    assert board["MissionState"] == "SUBMITTED"
    assert board["RejectionReason"] == ""

    fake = _render(workspace)
    assert not any("Resubmission Required" in text for text in _texts(fake, "markdown"))
    assert any("Sent to EXOS" in text for text in _texts(fake, "caption"))


def test_resubmission_reuses_the_same_submission_id_so_the_new_revision_gates_review():
    """The 038 upsert keeps SubmissionID stable across resubmit; only SubmittedAt
    changes, which is exactly what the 039 stale-revision check compares."""
    projection = participant_projection(
        event=_event(), participant={"ParticipantID": "P1", "TeamID": "T6"},
        stations=[STATION],
        submissions=[{"SubmissionID": SUBMISSION_ID, "TeamID": "T6", "ActivityID": "A1", "Status": "SUBMITTED", "SubmittedAt": "t2"}],
        reviews=[{"SubmissionID": SUBMISSION_ID, "Decision": "REJECT", "Reason": REASON, "ReviewedAt": "t1"}],
    )
    board = projection["MissionBoard"][0]
    assert board["MissionState"] == "SUBMITTED"
    assert board["RejectionReason"] == ""


# F. no sensitive/internal field leaks.

def test_rejection_projection_carries_no_reviewer_identity_or_internal_ids():
    board = mission_board(
        CONFIG, [STATION], team_id="T6",
        submissions=[{"SubmissionID": SUBMISSION_ID, "TeamID": "T6", "ActivityID": "A1", "Status": "REJECTED"}],
        reviews=[{"SubmissionID": SUBMISSION_ID, "Decision": "REJECT", "Reason": REASON, "ReviewedAt": "t1", "Reviewer": "Ruth"}],
    )
    row = board[0]
    assert set(row) == {
        "ActivityID", "DisplayName", "MissionClass", "DisplayOrder", "Evidence",
        "OperationalStatus", "MissionState", "Visible", "CanSelect", "CanSubmit",
        "RideRequiredParticipantCount", "RideAttemptStatus", "RejectionReason",
    }
    assert "Ruth" not in repr(row)


def test_the_rejection_review_query_is_scoped_to_this_teams_own_submission():
    _, calls = _workspace_via_adapter(status="REJECTED", reviews_rows=[_raw_review_row()])
    assert len(calls) == 1
    assert calls[0][1]["submission_id"] == f"in.({SUBMISSION_ID})"


def test_no_query_is_issued_for_a_team_with_no_rejected_submission():
    _, calls = _workspace_via_adapter(status="SUBMITTED", reviews_rows=[])
    assert calls == []


def test_no_session_token_or_device_id_appears_in_the_rendered_surface():
    workspace, _ = _workspace_via_adapter(status="REJECTED", reviews_rows=[_raw_review_row()])
    fake = _render(workspace)
    rendered = " ".join(_texts(
        fake, "write", "caption", "info", "warning", "markdown", "subheader",
    ))
    assert "TOK" not in rendered
    assert "DEV-1" not in rendered


# G. APPROVE path unchanged.

def test_approve_path_and_score_semantics_are_unaffected():
    board = mission_board(
        CONFIG, [STATION], team_id="T6",
        submissions=[{"SubmissionID": SUBMISSION_ID, "TeamID": "T6", "ActivityID": "A1", "Status": "APPROVED"}],
        reviews=[{"SubmissionID": SUBMISSION_ID, "Decision": "APPROVE", "Reason": "Nice work.", "ReviewedAt": "t1"}],
    )
    row = board[0]
    assert row["MissionState"] == "APPROVED"
    assert row["RejectionReason"] == ""
    assert row["CanSubmit"] is False


def test_approved_mission_renders_the_existing_success_state_unchanged():
    workspace, _ = _workspace_via_adapter(status="APPROVED", reviews_rows=[])
    fake = _render(workspace)
    assert any("COMPLETED" in text for text in _texts(fake, "markdown"))
    assert any("locked in" in text for text in _texts(fake, "caption"))
    assert not any("Resubmission Required" in text for text in _texts(fake, "markdown"))


def test_facilitator_review_routing_and_stale_revision_protection_are_unchanged():
    """The 039 routing and payload contract from the prior fix are untouched
    by this projection-only change."""
    source = (ROOT / "screens/theme_park_race.py").read_text()
    assert "exos_v2_theme_park_race_board_review" not in source  # lives in the adapter
    assert "review_theme_park_race_board_submission" in source
    assert "_STALE_REVISION_NOTICE" in source


# H. Formula R.A.C.E. unchanged.

def test_formula_race_is_untouched_by_the_rejection_projection_change():
    for path in ("screens/formula_race_captain.py", "screens/formula_race.py"):
        source = (ROOT / path).read_text()
        assert "RejectionReason" not in source
        assert "_theme_park_race_rejection_reviews" not in source
        assert "Resubmission required" not in source


def test_formula_race_captain_module_defines_no_theme_park_mission_board_state():
    source = (ROOT / "screens/formula_race_captain.py").read_text()
    assert "mission_board" not in source.casefold()
