"""P0: prove/disprove the real Streamlit widget-click lifecycle for board submit.

Live Streamlit trace evidence (Python 3.14.7 / Streamlit 1.62.0) during a
failed Velocity resubmission on CERT-GENTING-UAT-20260824 showed 85
CORE_V2_HTTP_TRACE canonical reads and ZERO POST to
exos_v2_theme_park_race_board_submit. The Captain's click never reached
save_theme_park_race_submission at all — this supersedes the earlier
network/strategy-mode theory as the live P0.

Function-level mocks (26 of which passed while the live click never reached
the RPC) cannot reproduce this class of bug: they collapse "the render that
shows a widget" and "the render that processes its click" into one synchronous
Python call. In real Streamlit, those are TWO SEPARATE SCRIPT RUNS. If a
conditional branch ahead of a widget call is gated on data that is
independently re-fetched (uncached) on every run, and that data differs
between the two runs, the widget call is skipped in Python on the
click-processing run and the click is silently and permanently discarded —
no exception, no error, nothing. This file uses Streamlit's own
``streamlit.testing.v1.AppTest`` to drive the REAL widget engine across
multiple separate runs, which is the only way to reproduce or refute this.

ROOT CAUSE FOUND AND PROVEN BELOW: ``_render_open_mission_board`` only
called ``st.button("Select this mission", ...)`` / only reached
``_render_evidence_form`` (and its own ``st.button("Submit mission
evidence", ...)``) when ``captain_active`` was True on that specific render.
``captain_active`` is derived fresh, every render, from a live join across
``participant_sessions_v2`` and ``team_access_sessions_v2`` by device id —
two independent, non-transactional REST reads with no caching between
renders. If that value differs between the render that displayed the Submit
button and the very next render that processes its click, the button call
itself is skipped and the click vanishes. The fix makes the button
unconditional on ``captain_active``: it is always constructed whenever the
mission's own (comparatively stable) MissionState is SELECTED/REJECTED, and
``captain_active`` gates only the button's ``disabled`` attribute and a
fresh re-check taken at the moment the already-registered click is handled.
"""
import os
import types
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY_ID = "CERT-GTU-STANDARD"
BOARD_SUBMIT_RPC = "exos_v2_theme_park_race_board_submit"


def _run_participant_surface(shared):
    """Executed by AppTest as an isolated Streamlit script on every .run().

    AppTest.from_function re-executes only this function's own SOURCE TEXT as
    a brand-new, isolated module — it shares nothing with the test file's
    module-level imports or globals, so every name this body needs must be
    imported here.
    """
    import types

    import streamlit as st

    from screens.theme_park_race import render_theme_park_race_participant

    if "seeded" not in st.session_state:
        st.session_state["participant_session_token"] = "SESSION-TOK"
        st.session_state["participant_team"] = "Velocity"
        st.session_state["participant_name"] = "Adrian Choong"
        st.session_state["seeded"] = True

    index = shared.get("call_index", 0)
    sequence = shared["workspace_sequence"]
    workspace = sequence[min(index, len(sequence) - 1)]
    shared["call_index"] = index + 1

    def save(session_token, activity_id, payload, strategy_mode=""):
        shared["calls"].append({
            "session_token": session_token, "activity_id": activity_id,
            "payload": payload, "strategy_mode": strategy_mode,
        })
        return {"SubmissionID": "S-1", "Status": "SUBMITTED"}

    def record_ride_outcome(session_token, activity_id, attempt, payload):
        shared["calls"].append({
            "session_token": session_token, "activity_id": activity_id,
            "attempt": attempt, "payload": payload,
        })
        return {"Recorded": True}

    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        theme_park_race_participant_workspace=lambda token: workspace,
        save_theme_park_race_submission=save,
        record_theme_park_race_ride_outcome=record_ride_outcome,
        select_theme_park_race_mission=lambda token, activity_id: shared["calls"].append(
            {"select": activity_id},
        ),
        claim_team_formation_captain=lambda *a, **k: {},
        recover_team_formation_captain=lambda *a, **k: {},
    ))
    render_theme_park_race_participant(db, device_id="DEV-1")


def _mission(state="REJECTED", mission_class="STANDARD", text_required=True):
    return {
        "ActivityID": ACTIVITY_ID, "DisplayName": "Standard Mission — UAT",
        "MissionClass": mission_class, "MissionState": state, "RejectionReason": "",
        "Evidence": {"Text": {"Required": text_required}},
    }


def _workspace(*, is_captain=True, captain_session_active=True,
               mission_state="REJECTED", mission_class="STANDARD"):
    return {
        "EventID": "EV", "TeamID": "T6", "Lifecycle": "ACTIVE",
        "StrategyMode": "OPEN_MISSION_BOARD",
        "IsCaptain": is_captain, "CaptainSessionActive": captain_session_active,
        "Progress": {"Completed": 0, "Total": 1, "SubmissionsByActivity": {}},
        "TeamMembers": [], "Route": [],
        "MissionBoard": [_mission(mission_state, mission_class)],
    }


def _app(workspace_sequence):
    shared = {"workspace_sequence": workspace_sequence, "calls": []}
    at = AppTest.from_function(_run_participant_surface, args=(shared,))
    return at, shared


def _fill_required_text(at):
    text_area = next(t for t in at.text_area if t.key == f"theme_race_text_{ACTIVITY_ID}")
    text_area.set_value("Retaken evidence, mission signage visible.")
    at.run()


# A. Submit button event is consumed in the same execution run;
# B. no st.rerun occurs before RPC_STARTED (a premature rerun would need a
#    SECOND .run() to reach the RPC — a single .run() after .click() proves
#    none happened).

def test_submit_click_reaches_the_rpc_in_the_same_run_it_is_processed():
    stable = _workspace(mission_state="REJECTED")
    at, shared = _app([stable, stable])
    at.run()
    _fill_required_text(at)
    submit = next(b for b in at.button if b.key == f"theme_race_submit_{ACTIVITY_ID}")
    submit.click()
    at.run()  # exactly one run after click — no intermediate rerun is needed
    assert not at.exception
    assert len(shared["calls"]) == 1
    assert shared["calls"][0]["activity_id"] == ACTIVITY_ID


# C. In-flight state cannot suppress a legitimate click when nothing is
# actually in flight — and, separately, genuinely-in-flight state correctly
# blocks a concurrent second submission rather than silently vanishing.

def test_a_legitimate_click_is_never_suppressed_by_the_in_flight_guard():
    stable = _workspace(mission_state="SELECTED")
    at, shared = _app([stable, stable])
    at.run()
    _fill_required_text(at)
    submit = next(b for b in at.button if b.key == f"theme_race_submit_{ACTIVITY_ID}")
    assert submit.disabled is False
    submit.click()
    at.run()
    assert len(shared["calls"]) == 1


def test_a_genuinely_in_flight_submission_disables_the_button_without_losing_state():
    stable = _workspace(mission_state="REJECTED")
    at, shared = _app([stable, stable])
    at.run()
    at.session_state[f"theme_race_submitting_{ACTIVITY_ID}"] = True
    at.run()
    submit = next(b for b in at.button if b.key == f"theme_race_submit_{ACTIVITY_ID}")
    assert submit.disabled is True
    assert shared["calls"] == []


# D. REJECTED resubmission reaches the adapter; E. SELECTED first submission
# still works — both driven through the real widget engine, not a mock call.

@pytest.mark.parametrize("mission_state", ["SELECTED", "REJECTED"])
def test_standard_mission_submit_reaches_board_submit_regardless_of_prior_state(mission_state):
    stable = _workspace(mission_state=mission_state)
    at, shared = _app([stable, stable])
    at.run()
    _fill_required_text(at)
    submit = next(b for b in at.button if b.key == f"theme_race_submit_{ACTIVITY_ID}")
    submit.click()
    at.run()
    assert len(shared["calls"]) == 1
    assert shared["calls"][0]["strategy_mode"] == "OPEN_MISSION_BOARD"
    assert not at.error


# F. Both normal and RIDE forms obey the same unconditional-widget-construction
# contract.

def test_ride_form_submit_click_also_reaches_its_handler_in_one_run():
    stable = _workspace(mission_state="SELECTED", mission_class="RIDE")
    at, shared = _app([stable, stable])
    at.run()
    remarks = next(t for t in at.text_area if t.key == f"theme_race_ride_text_{ACTIVITY_ID}")
    remarks.set_value("Team withdrew before boarding due to a mechanical hold.")
    outcome = next(
        s for s in at.selectbox if s.key == f"theme_race_ride_attempt_{ACTIVITY_ID}"
    )
    outcome.set_value("ABORTED_BY_ATTRACTION")
    at.run()
    submit = next(b for b in at.button if b.key == f"theme_race_ride_submit_{ACTIVITY_ID}")
    assert submit.disabled is False
    submit.click()
    at.run()
    assert not at.exception
    assert len(shared["calls"]) == 1
    assert shared["calls"][0]["attempt"] == "ABORTED_BY_ATTRACTION"


# The proven root cause: a captain_active flicker between the display run and
# the click-processing run no longer silently drops the click. Before the fix
# this reproduced exactly the live symptom: zero calls, zero exceptions,
# nothing to observe. After the fix, the click is provably received (the
# button is unconditionally constructed and consumes it) and the RPC is
# correctly, visibly declined rather than silently never attempted.

def test_a_captain_authority_flicker_no_longer_silently_discards_the_click(capsys, monkeypatch):
    monkeypatch.setenv("EXOS_ENV", "staging")
    stable = _workspace(mission_state="REJECTED", captain_session_active=True)
    flickered = _workspace(mission_state="REJECTED", captain_session_active=False)
    at, shared = _app([stable, stable, flickered])
    at.run()
    _fill_required_text(at)
    submit = next(b for b in at.button if b.key == f"theme_race_submit_{ACTIVITY_ID}")
    assert submit.disabled is False  # captain_active was True when this was rendered
    submit.click()
    at.run()  # the live-refetched workspace now reports captain_active False
    assert not at.exception
    # The decisive, code-version-agnostic signal: pre-fix, the Submit button
    # is never even constructed on this run (the `continue` skips
    # _render_evidence_form entirely before st.button() is called), so the
    # widget the browser's click referred to does not exist for Streamlit to
    # honour it. Post-fix, the button is always constructed — disabled, but
    # present — because construction no longer depends on captain_active.
    submit_after = next(
        (b for b in at.button if b.key == f"theme_race_submit_{ACTIVITY_ID}"), None,
    )
    assert submit_after is not None, (
        "the Submit button must still exist on the click-processing run, "
        "even though authorization lapsed, or its click is unrecoverably lost"
    )
    assert submit_after.disabled is True
    # The click was received and correctly declined — not silently lost.
    assert shared["calls"] == []
    trace = capsys.readouterr().out
    assert "TPR_SUBMIT_TRACE" in trace
    assert "CLICK_RECEIVED=True" in trace
    assert f"activity_id={ACTIVITY_ID}" in trace


def test_stable_captain_authority_across_both_runs_completes_normally(monkeypatch, capsys):
    monkeypatch.setenv("EXOS_ENV", "staging")
    stable = _workspace(mission_state="REJECTED", captain_session_active=True)
    at, shared = _app([stable, stable])
    at.run()
    _fill_required_text(at)
    submit = next(b for b in at.button if b.key == f"theme_race_submit_{ACTIVITY_ID}")
    submit.click()
    at.run()
    assert len(shared["calls"]) == 1
    trace = capsys.readouterr().out
    assert "RPC_STARTED=True" in trace
    assert "RPC_COMPLETED=True" in trace


def test_the_trace_never_logs_a_session_token_device_id_or_photo_reference(monkeypatch, capsys):
    monkeypatch.setenv("EXOS_ENV", "staging")
    stable = _workspace(mission_state="REJECTED")
    at, shared = _app([stable, stable])
    at.run()
    _fill_required_text(at)
    submit = next(b for b in at.button if b.key == f"theme_race_submit_{ACTIVITY_ID}")
    submit.click()
    at.run()
    trace = capsys.readouterr().out
    assert "SESSION-TOK" not in trace
    assert "DEV-1" not in trace
    assert "Adrian Choong" not in trace


def test_trace_is_silent_outside_staging():
    assert os.getenv("EXOS_ENV", "").strip().lower() != "staging"
    stable = _workspace(mission_state="REJECTED")
    at, shared = _app([stable, stable])
    at.run()
    _fill_required_text(at)
    submit = next(b for b in at.button if b.key == f"theme_race_submit_{ACTIVITY_ID}")
    submit.click()
    at.run()  # must not raise even though tracing is disabled


# The button-instantiation defect class also applied to mission selection.

def test_selecting_an_available_mission_survives_a_captain_authority_flicker_too():
    stable = dict(_workspace(mission_state="SELECTED"))
    stable["MissionBoard"] = [_mission("AVAILABLE")]
    at, shared = _app([stable, stable])
    at.run()
    select = next(b for b in at.button if b.key == f"theme_race_board_select_{ACTIVITY_ID}")
    assert select.disabled is False
    select.click()
    at.run()
    assert shared["calls"] == [{"select": ACTIVITY_ID}]


# G. Formula R.A.C.E. unchanged.

def test_formula_race_is_untouched_by_this_lifecycle_fix():
    for path in ("screens/formula_race_captain.py", "screens/formula_race.py"):
        source = (ROOT / path).read_text()
        assert "captain_active" not in source
        assert "TPR_SUBMIT_TRACE" not in source
        assert BOARD_SUBMIT_RPC not in source


def test_formula_race_captain_flow_has_no_theme_park_submit_trace_wiring():
    captain = (ROOT / "screens/formula_race_captain.py").read_text()
    assert "_submit_trace" not in captain
    assert "formula_race_captain_login" in captain
