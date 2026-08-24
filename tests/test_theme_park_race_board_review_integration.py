"""Facilitator review routing for the installed 039 board-review contract.

These tests pin the application integration only: OPEN_MISSION_BOARD facilitator
decisions must reach ``exos_v2_theme_park_race_board_review`` with the canonical
039 parameters, and every other engine/mode must keep the review contract it
already ships with.
"""
from pathlib import Path

import pytest

from data.control_runtime import ControlRuntime
from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import StandardCoreV2Adapter
from screens.theme_park_race import submit_theme_park_race_review


ROOT = Path(__file__).resolve().parents[1]
SUBMISSION = {
    "SubmissionID": "11111111-1111-1111-1111-111111111111",
    "TeamID": "T-1",
    "ActivityID": "A",
    "SubmittedAt": "2026-08-24T09:15:00+00:00",
    "Score": 0,
}


class _RecordingControl:
    """Stand-in Control Centre facade that records the contract it was asked for."""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def review_submission(self, submission_id, score, remarks="", judged="Yes", status="APPROVED"):
        self.calls.append(("review_submission", {
            "SubmissionID": submission_id, "Score": score, "Remarks": remarks, "Status": status,
        }))
        return {"Status": status}

    def review_theme_park_race_board_submission(self, submission_id, expected_submitted_at, decision,
                                                score=0, actor="", reason="", idempotency_key=""):
        self.calls.append(("board_review", {
            "SubmissionID": submission_id, "ExpectedSubmittedAt": expected_submitted_at,
            "Decision": decision, "Score": score, "Actor": actor, "Reason": reason,
            "IdempotencyKey": idempotency_key,
        }))
        if self.error:
            raise self.error
        return {"Status": "APPROVED" if decision == "APPROVE" else "REJECTED"}


def _adapter():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    captured = {}

    def rpc(name, payload, admin=True):
        captured.update({"name": name, "payload": payload, "admin": admin})
        return {"Status": "APPROVED"}

    adapter._rpc = rpc
    return adapter, captured


# 1 / 2 — decisions reach the 039 contract, not the standard one ------------

def test_open_mission_board_approve_routes_to_board_review():
    control = _RecordingControl()
    outcome = submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", SUBMISSION,
        decision="APPROVE", score=40, actor="Kai", notes="Verified queue evidence",
    )
    assert outcome == {"Reviewed": True}
    assert [name for name, _ in control.calls] == ["board_review"]
    assert control.calls[0][1]["Decision"] == "APPROVE"


def test_open_mission_board_reject_routes_to_board_review():
    control = _RecordingControl()
    outcome = submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", SUBMISSION,
        decision="REJECT", score=0, actor="Kai", notes="Exterior photo is not queue entry",
    )
    assert outcome == {"Reviewed": True}
    assert [name for name, _ in control.calls] == ["board_review"]
    assert control.calls[0][1]["Decision"] == "REJECT"
    assert control.calls[0][1]["Score"] == 0


def test_board_review_adapter_calls_the_installed_039_rpc():
    adapter, captured = _adapter()
    adapter.review_theme_park_race_board_submission(
        SUBMISSION["SubmissionID"], SUBMISSION["SubmittedAt"], "APPROVE",
        score=40, actor="Kai", reason="Verified",
    )
    assert captured["name"] == "exos_v2_theme_park_race_board_review"
    assert captured["admin"] is True


# 3 — the exact reviewed revision travels with the decision ----------------

def test_expected_submitted_at_is_passed_for_the_reviewed_revision():
    control = _RecordingControl()
    submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", SUBMISSION,
        decision="APPROVE", score=10, actor="Kai", notes="",
    )
    assert control.calls[0][1]["ExpectedSubmittedAt"] == SUBMISSION["SubmittedAt"]

    adapter, captured = _adapter()
    adapter.review_theme_park_race_board_submission(
        SUBMISSION["SubmissionID"], SUBMISSION["SubmittedAt"], "APPROVE", score=10, actor="Kai",
    )
    assert captured["payload"]["p_expected_submitted_at"] == SUBMISSION["SubmittedAt"]
    assert captured["payload"]["p_submission_id"] == SUBMISSION["SubmissionID"]


# 4 — reviewed score, including the rejection zero -------------------------

def test_reviewed_score_is_passed_and_rejection_scores_zero():
    adapter, captured = _adapter()
    adapter.review_theme_park_race_board_submission(
        SUBMISSION["SubmissionID"], SUBMISSION["SubmittedAt"], "APPROVE", score=37.5, actor="Kai",
    )
    assert captured["payload"]["p_score"] == 37.5
    assert captured["payload"]["p_decision"] == "APPROVE"

    adapter, captured = _adapter()
    adapter.review_theme_park_race_board_submission(
        SUBMISSION["SubmissionID"], SUBMISSION["SubmittedAt"], "REJECT", score=37.5, actor="Kai",
    )
    assert captured["payload"]["p_score"] == 0.0
    assert captured["payload"]["p_decision"] == "REJECT"


# 5 — actor and reason are the facilitator's, not a hardcoded literal ------

def test_actor_and_reason_are_passed_through_to_the_contract():
    control = _RecordingControl()
    submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", SUBMISSION,
        decision="REJECT", score=0, actor="Kai", notes="Resubmit with post-ride evidence",
    )
    assert control.calls[0][1]["Actor"] == "Kai"
    assert control.calls[0][1]["Reason"] == "Resubmit with post-ride evidence"

    adapter, captured = _adapter()
    adapter.review_theme_park_race_board_submission(
        SUBMISSION["SubmissionID"], SUBMISSION["SubmittedAt"], "REJECT",
        actor="  Kai  ", reason="Resubmit with post-ride evidence",
    )
    assert captured["payload"]["p_actor"] == "Kai"
    assert captured["payload"]["p_reason"] == "Resubmit with post-ride evidence"


def test_board_review_refuses_to_call_the_contract_without_revision_or_actor():
    adapter, captured = _adapter()
    with pytest.raises(RuntimeDatabaseError, match="submitted-at revision"):
        adapter.review_theme_park_race_board_submission(
            SUBMISSION["SubmissionID"], "", "APPROVE", score=10, actor="Kai",
        )
    with pytest.raises(RuntimeDatabaseError, match="submitted-at revision"):
        adapter.review_theme_park_race_board_submission(
            SUBMISSION["SubmissionID"], SUBMISSION["SubmittedAt"], "APPROVE", score=10, actor="  ",
        )
    assert captured == {}


def test_request_idempotency_key_is_stable_per_revision_and_decision():
    control = _RecordingControl()
    for _ in range(2):
        submit_theme_park_race_review(
            control, "OPEN_MISSION_BOARD", SUBMISSION,
            decision="APPROVE", score=40, actor="Kai", notes="",
        )
    keys = {payload["IdempotencyKey"] for _, payload in control.calls}
    assert len(keys) == 1
    assert SUBMISSION["SubmittedAt"] in keys.pop()


# 6 / 7 — stale revision is surfaced safely and canonical state reloads ----

def test_stale_revision_failure_is_surfaced_without_reviewing_anything():
    control = _RecordingControl(error=RuntimeDatabaseError(
        'Runtime request failed (400): {"message":"Submission revision is stale"}'
    ))
    outcome = submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", SUBMISSION,
        decision="APPROVE", score=40, actor="Kai", notes="",
    )
    assert outcome["Reviewed"] is False
    assert outcome["Level"] == "warning"
    assert "changed after this page was loaded" in outcome["Message"]


def test_missing_revision_never_reviews_a_newer_submission():
    control = _RecordingControl()
    outcome = submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", {**SUBMISSION, "SubmittedAt": ""},
        decision="APPROVE", score=40, actor="Kai", notes="",
    )
    assert outcome["Reviewed"] is False
    assert control.calls == []


def test_other_review_failures_surface_as_errors_not_silent_success():
    control = _RecordingControl(error=RuntimeDatabaseError(
        'Runtime request failed (400): {"message":"Submission has no canonical OPEN_MISSION_BOARD runtime"}'
    ))
    outcome = submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", SUBMISSION,
        decision="REJECT", score=0, actor="Kai", notes="",
    )
    assert outcome["Reviewed"] is False
    assert outcome["Level"] == "error"


def test_facilitator_screen_reloads_canonical_state_after_every_decision():
    source = (ROOT / "screens/theme_park_race.py").read_text()
    review = source.split('st.markdown("#### Submission review")', 1)[1]
    assert "_render_review_notice(event_id)" in review
    assert review.count("_queue_review_notice(event_id, submit_theme_park_race_review(") == 2
    assert review.count("st.rerun()") == 2
    # The screen keeps no local approved/rejected mirror of the canonical row.
    assert "st.session_state[f\"theme_race_reviewed" not in review


# 8 / 9 / 10 — untouched review contracts ---------------------------------

def test_formula_race_review_path_is_unchanged():
    control_source = (ROOT / "data/control_runtime.py").read_text()
    race_source = (ROOT / "screens/formula_race.py").read_text()
    assert "self.runtime.formula_race_review_checkpoint" in control_source
    assert "control.review_race_checkpoint(" in race_source
    assert "review_theme_park_race_board_submission" not in race_source


def test_non_theme_park_review_path_is_unchanged():
    adapter, captured = _adapter()
    adapter.decide_canonical_submission(
        SUBMISSION["SubmissionID"], "APPROVE", "Facilitator", score=12,
    )
    assert captured["name"] == "exos_v2_standard_review_submission"

    adapter, captured = _adapter()
    adapter.update_submission_score(SUBMISSION["SubmissionID"], 12, "ok")
    assert captured["name"] == "exos_v2_standard_review_submission"

    console = (ROOT / "screens/live_event_console.py").read_text()
    assert "review_theme_park_race_board_submission" not in console


def test_configured_team_route_keeps_its_existing_review_contract():
    control = _RecordingControl()
    submit_theme_park_race_review(
        control, "CONFIGURED_TEAM_ROUTE", SUBMISSION,
        decision="APPROVE", score=25, actor="Kai", notes="ok",
    )
    submit_theme_park_race_review(
        control, "CONFIGURED_TEAM_ROUTE", SUBMISSION,
        decision="REJECT", score=25, actor="Kai", notes="redo",
    )
    assert [name for name, _ in control.calls] == ["review_submission", "review_submission"]
    assert control.calls[0][1] == {
        "SubmissionID": SUBMISSION["SubmissionID"], "Score": 25, "Remarks": "ok", "Status": "APPROVED",
    }
    assert control.calls[1][1] == {
        "SubmissionID": SUBMISSION["SubmissionID"], "Score": 0, "Remarks": "redo", "Status": "REJECTED",
    }


# 11 — the projector/public surface gains nothing private -----------------

def test_board_review_adds_no_private_information_to_public_surfaces():
    screen = (ROOT / "screens/theme_park_race.py").read_text()
    projector = screen.split("def render_theme_park_race_projector", 1)[1]
    for private in (
        "QueueEntryEvidence", "PostRideEvidence", "FacilitatorVerificationRequest",
        "RiderParticipantIDs", "ReviewQueue", "SessionToken", "Reason", "ReviewedBy",
    ):
        assert private not in projector
    engine = (ROOT / "engines/theme_park_race.py").read_text()
    projection = engine.split("def projector_projection", 1)[1]
    assert "ReviewQueue" not in projection
    assert "SubmissionsByActivity" in projection.split("if key not in {", 1)[1].split("}", 1)[0]


# Control Centre capability boundary --------------------------------------

def test_board_review_is_a_control_centre_only_mutation():
    calls = {}

    class _Runtime:
        def review_theme_park_race_board_submission(self, *args):
            calls["args"] = args
            return {"Status": "REJECTED"}

    class _DB:
        runtime = _Runtime()

    control = ControlRuntime(_DB())
    assert control.review_theme_park_race_board_submission(
        SUBMISSION["SubmissionID"], SUBMISSION["SubmittedAt"], "REJECT",
        score=0, actor="Kai", reason="redo", idempotency_key="key-1",
    ) == {"Status": "REJECTED"}
    assert calls["args"] == (
        SUBMISSION["SubmissionID"], SUBMISSION["SubmittedAt"], "REJECT", 0, "Kai", "redo", "key-1",
    )


def test_board_review_never_moves_service_role_work_into_participant_code():
    participant = (ROOT / "screens/participant.py").read_text()
    screen = (ROOT / "screens/theme_park_race.py").read_text()
    participant_surface = screen.split("def render_theme_park_race_participant", 1)[1].split(
        "def render_theme_park_race_facilitator", 1
    )[0]
    assert "review_theme_park_race_board_submission" not in participant
    assert "review_theme_park_race_board_submission" not in participant_surface
    assert "exos_v2_theme_park_race_board_review" not in participant


def test_no_migration_is_added_by_this_integration():
    assert not list((ROOT / "supabase").glob("04*.sql"))
