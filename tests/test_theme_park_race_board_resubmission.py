"""P0: a REJECTED OPEN_MISSION_BOARD mission must actually reach board_submit.

Human UAT on CERT-GENTING-UAT-20260824 / Velocity / CERT-GTU-STANDARD: the
Captain attempted resubmission five times after a facilitator REJECT. The UI
showed a pending state each time; submissions_v2 never changed — same
submitted_at, still REJECTED. Kai confirmed the canonical row never moved.

Root cause: `save_theme_park_race_submission` re-derived StrategyMode on every
call via a second `get_player_by_token` + `get_event` round-trip, purely to
choose between `exos_v2_theme_park_race_board_submit` and the generic
`exos_v2_theme_park_race_submit`. That derivation ran unconditionally before
the write RPC, on the participant's own already-loaded workspace state that
already carried the answer, and silently defaulted to the WRONG RPC
(`exos_v2_theme_park_race_submit`) whenever that lookup came back empty. It
also gave no client-visible feedback: no explicit "Submitting…" state, and a
narrow `except (RuntimeDatabaseError, ValueError)` let any other exception
from the photo upload path propagate uncaught, aborting the script mid-submit
with nothing shown to the Captain.
"""
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import StandardCoreV2Adapter
from screens import theme_park_race as TPR


ROOT = Path(__file__).resolve().parents[1]
EVENT_ID = "CERT-GENTING-UAT-20260824"
ACTIVITY_ID = "CERT-GTU-STANDARD"
SESSION_TOKEN = "44444444-4444-4444-8444-444444444444"
BOARD_SUBMIT_RPC = "exos_v2_theme_park_race_board_submit"
GENERIC_SUBMIT_RPC = "exos_v2_theme_park_race_submit"


class _UploadedPhoto:
    """Stands in for a Streamlit UploadedFile handed to a widget."""
    name = "evidence.jpg"


def _mission(state):
    return {
        "ActivityID": ACTIVITY_ID, "DisplayName": "Standard Mission — UAT",
        "MissionClass": "STANDARD", "MissionState": state,
        "Evidence": {"Text": {"Required": True}, "Photo": {"Required": True}},
    }


def _workspace():
    return {"EventID": EVENT_ID, "TeamID": "T6", "StrategyMode": "OPEN_MISSION_BOARD"}


def _render_evidence_form(*, state="REJECTED", click=True, save_raises=None,
                            upload_raises=None, upload_result=None, already_submitting=False):
    calls = []

    def save(session_token, activity_id, payload, strategy_mode=""):
        calls.append({
            "session_token": session_token, "activity_id": activity_id,
            "payload": payload, "strategy_mode": strategy_mode,
        })
        if save_raises:
            raise save_raises
        return {"SubmissionID": "S-1", "Status": "SUBMITTED"}

    db = types.SimpleNamespace(runtime=types.SimpleNamespace(save_theme_park_race_submission=save))
    with patch.object(TPR, "st", MagicMock()) as fake, patch.object(TPR, "upload_photo") as fake_upload:
        fake.session_state = {
            "participant_session_token": SESSION_TOKEN,
            "participant_team": "Velocity", "participant_name": "Adrian Choong",
        }
        if already_submitting:
            fake.session_state[f"theme_race_submitting_{ACTIVITY_ID}"] = True
        fake.text_area.return_value = "Retaken photo, mission signage visible."
        fake.file_uploader.return_value = _UploadedPhoto()
        fake.button.return_value = click
        if upload_raises:
            fake_upload.side_effect = upload_raises
        else:
            fake_upload.return_value = upload_result or {
                "url": "core-v2-storage://exos-submissions/x.jpg", "file_id": "exos-submissions/x.jpg",
            }
        TPR._render_evidence_form(db, _workspace(), _mission(state))
    return fake, calls, fake_upload


# A. REJECTED mission submit invokes board_submit.

def test_rejected_mission_resubmit_invokes_board_submit_via_the_adapter():
    fake, calls, _ = _render_evidence_form(state="REJECTED")
    assert len(calls) == 1
    assert calls[0]["strategy_mode"] == "OPEN_MISSION_BOARD"


def test_the_adapter_routes_open_mission_board_to_the_canonical_board_submit_rpc():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    calls = []
    adapter._rpc = lambda name, payload, admin=True: calls.append((name, payload, admin)) or {}
    adapter.save_theme_park_race_submission(
        SESSION_TOKEN, ACTIVITY_ID, {"Remarks": "x"}, strategy_mode="OPEN_MISSION_BOARD",
    )
    name, payload, admin = calls[0]
    assert name == BOARD_SUBMIT_RPC
    assert admin is False
    assert payload == {
        "p_session_token": SESSION_TOKEN, "p_activity_id": ACTIVITY_ID,
        "p_submission_payload": {"Remarks": "x"},
    }


def test_a_rejected_mission_never_takes_a_ui_branch_that_skips_the_form():
    """MissionState REJECTED must reach the same evidence form as SELECTED."""
    with patch.object(TPR, "_render_evidence_form") as evidence_form, \
            patch.object(TPR, "st", MagicMock()) as fake:
        fake.button.return_value = False
        fake.expander.return_value.__enter__ = lambda self: None
        fake.expander.return_value.__exit__ = lambda self, *args: False
        db = types.SimpleNamespace(runtime=types.SimpleNamespace())
        workspace = dict(_workspace(), MissionBoard=[_mission("REJECTED")])
        TPR._render_open_mission_board(db, workspace, captain_active=True)
    evidence_form.assert_called_once()


def test_the_redundant_participant_lookup_before_the_write_rpc_is_gone():
    """The prior implementation re-derived StrategyMode via a second
    get_player_by_token + get_event round-trip on every submit; a failure or
    empty response from that lookup silently misrouted to the generic RPC.
    Passing strategy_mode from the caller's own workspace eliminates it."""
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    adapter.get_player_by_token = lambda token: pytest.fail("must not re-derive StrategyMode")
    adapter.get_event = lambda event_id: pytest.fail("must not re-derive StrategyMode")
    adapter._rpc = lambda name, payload, admin=True: {}
    adapter.save_theme_park_race_submission(
        SESSION_TOKEN, ACTIVITY_ID, {"Remarks": "x"}, strategy_mode="OPEN_MISSION_BOARD",
    )


def test_a_failed_strategy_mode_lookup_no_longer_silently_misroutes():
    """Without the explicit strategy_mode, the fallback lookup still exists for
    backward compatibility, but a failed/empty lookup must not pretend the
    submission succeeded against the wrong contract — it degrades to the
    generic RPC exactly as before, never claiming board semantics it didn't
    use. The screen path (tested above) no longer depends on this fallback."""
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    adapter.get_player_by_token = lambda token: {}  # simulates a failed/empty lookup
    adapter.get_event = lambda event_id: {}
    calls = []
    adapter._rpc = lambda name, payload, admin=True: calls.append(name) or {}
    adapter.save_theme_park_race_submission(SESSION_TOKEN, ACTIVITY_ID, {"Remarks": "x"})
    assert calls == [GENERIC_SUBMIT_RPC]


# B. Correct CaptainSessionToken is used.

def test_resubmit_uses_the_captains_own_session_token():
    fake, calls, _ = _render_evidence_form(state="REJECTED")
    assert calls[0]["session_token"] == SESSION_TOKEN


def test_resubmit_never_falls_back_to_an_empty_or_fabricated_token():
    fake, calls, _ = _render_evidence_form(state="REJECTED")
    assert calls[0]["session_token"]


# C. Correct ActivityID is used.

def test_resubmit_uses_the_exact_activity_id_of_the_rejected_mission():
    fake, calls, _ = _render_evidence_form(state="REJECTED")
    assert calls[0]["activity_id"] == ACTIVITY_ID


# D. Text evidence payload is sent.

def test_resubmit_payload_carries_the_updated_text_evidence():
    fake, calls, _ = _render_evidence_form(state="REJECTED")
    assert calls[0]["payload"]["Remarks"] == "Retaken photo, mission signage visible."


def test_missing_required_text_blocks_submission_before_any_network_call():
    fake, calls, fake_upload = _render_evidence_form(state="REJECTED")
    with patch.object(TPR, "st", MagicMock()) as fake2, patch.object(TPR, "upload_photo") as upload2:
        fake2.session_state = {"participant_session_token": SESSION_TOKEN}
        fake2.text_area.return_value = "   "
        fake2.file_uploader.return_value = _UploadedPhoto()
        fake2.button.return_value = True
        db = types.SimpleNamespace(runtime=types.SimpleNamespace(
            save_theme_park_race_submission=lambda *a, **k: pytest.fail("must not submit"),
        ))
        TPR._render_evidence_form(db, _workspace(), _mission("REJECTED"))
    upload2.assert_not_called()
    assert fake2.warning.called


# E. Photo evidence payload/reference is serializable.

def test_resubmit_payload_carries_only_the_storage_reference_never_the_upload_object():
    fake, calls, fake_upload = _render_evidence_form(state="REJECTED")
    payload = calls[0]["payload"]
    assert payload["ImageURL"] == "core-v2-storage://exos-submissions/x.jpg"
    assert payload["DriveFileID"] == "exos-submissions/x.jpg"
    import json
    json.dumps(payload)  # must not raise: no UploadedFile, no bytes, no non-JSON type


def test_no_raw_uploaded_file_object_is_ever_passed_to_the_adapter():
    fake, calls, fake_upload = _render_evidence_form(state="REJECTED")
    for value in calls[0]["payload"].values():
        assert isinstance(value, (str, int, float, bool)) or value is None
    # upload_photo received the raw file; the adapter call did not.
    assert fake_upload.call_args.kwargs["uploaded_file"].__class__ is _UploadedPhoto


def test_an_unexpected_upload_failure_is_caught_and_never_reaches_the_rpc():
    fake, calls, fake_upload = _render_evidence_form(state="REJECTED", upload_raises=OSError("disk full"))
    assert calls == []
    assert fake.error.called
    assert "unexpectedly" in str(fake.error.call_args.args[0]).casefold()


# F. Successful resubmit changes client state to awaiting review.

def test_successful_resubmit_shows_awaiting_review_and_refreshes_state():
    fake, calls, _ = _render_evidence_form(state="REJECTED")
    assert fake.success.called
    assert "facilitator review" in str(fake.success.call_args.args[0]).casefold()
    assert fake.rerun.called


def test_successful_resubmit_clears_the_submitting_flag():
    fake, calls, _ = _render_evidence_form(state="REJECTED")
    assert fake.session_state.get(f"theme_race_submitting_{ACTIVITY_ID}") is False


# G. Failed RPC clears pending state and shows error; form stays usable.

def test_a_known_rpc_error_clears_pending_state_and_surfaces_the_real_message():
    fake, calls, _ = _render_evidence_form(
        state="REJECTED",
        save_raises=RuntimeDatabaseError("Only the current submitted board revision may be reviewed"),
    )
    assert fake.error.called
    assert "current submitted board revision" in str(fake.error.call_args.args[0])
    assert not fake.success.called
    assert not fake.rerun.called
    assert fake.session_state.get(f"theme_race_submitting_{ACTIVITY_ID}") is False


def test_an_unexpected_rpc_exception_is_caught_not_left_as_a_silent_hang():
    fake, calls, _ = _render_evidence_form(state="REJECTED", save_raises=ConnectionError("timed out"))
    assert fake.error.called
    assert "unexpectedly" in str(fake.error.call_args.args[0]).casefold()
    assert fake.session_state.get(f"theme_race_submitting_{ACTIVITY_ID}") is False


def test_a_failed_submit_never_claims_indefinite_processing():
    """No code path may leave the submitting flag True after the callback returns."""
    for save_raises in (
        RuntimeDatabaseError("stale"),
        ConnectionError("network"),
        TimeoutError("timeout"),
    ):
        fake, _, _ = _render_evidence_form(state="REJECTED", save_raises=save_raises)
        assert fake.session_state.get(f"theme_race_submitting_{ACTIVITY_ID}") is False


# H. Repeated click does not double-submit.

def test_an_already_in_flight_submission_is_not_submitted_twice():
    fake, calls, fake_upload = _render_evidence_form(state="REJECTED", already_submitting=True)
    assert calls == []
    fake_upload.assert_not_called()


def test_the_submit_button_is_disabled_while_a_submission_is_in_flight():
    fake, calls, _ = _render_evidence_form(state="REJECTED", already_submitting=True, click=False)
    submit_call = next(
        call for call in fake.button.call_args_list
        if call.args and "Submit mission evidence" in call.args[0]
    )
    assert submit_call.kwargs.get("disabled") is True


def test_the_submit_button_is_enabled_when_nothing_is_in_flight():
    fake, calls, _ = _render_evidence_form(state="REJECTED", click=False)
    submit_call = next(
        call for call in fake.button.call_args_list
        if call.args and "Submit mission evidence" in call.args[0]
    )
    assert submit_call.kwargs.get("disabled") is False


# I. SELECTED first submission still works (non-regression).

def test_selected_first_submission_still_invokes_board_submit_the_same_way():
    fake, calls, _ = _render_evidence_form(state="SELECTED")
    assert len(calls) == 1
    assert calls[0]["strategy_mode"] == "OPEN_MISSION_BOARD"
    assert calls[0]["activity_id"] == ACTIVITY_ID
    assert fake.success.called


# J. Formula R.A.C.E. unchanged.

def test_formula_race_submission_paths_are_untouched():
    for path in ("screens/formula_race_captain.py", "screens/formula_race.py"):
        source = (ROOT / path).read_text()
        assert "save_theme_park_race_submission" not in source
        assert BOARD_SUBMIT_RPC not in source


def test_formula_race_captain_login_and_pin_flow_still_present_and_unrelated():
    captain = (ROOT / "screens/formula_race_captain.py").read_text()
    assert "formula_race_captain_login" in captain
    assert "theme_race_submitting_" not in captain


# K. No private credential/session data rendered.

def test_no_session_token_or_storage_credential_appears_in_any_rendered_text():
    fake, calls, _ = _render_evidence_form(state="REJECTED")
    rendered = " ".join(
        str(call.args[0]) for name in ("write", "caption", "info", "warning", "error", "success", "subheader")
        for call in getattr(fake, name).call_args_list if call.args
    )
    assert SESSION_TOKEN not in rendered


def test_the_spinner_and_success_copy_carry_no_internal_identifiers():
    fake, calls, _ = _render_evidence_form(state="REJECTED")
    spinner_labels = [call.args[0] for call in fake.spinner.call_args_list if call.args]
    assert any("Submitting" in label for label in spinner_labels)
    for label in spinner_labels:
        assert SESSION_TOKEN not in label
        assert ACTIVITY_ID not in label
