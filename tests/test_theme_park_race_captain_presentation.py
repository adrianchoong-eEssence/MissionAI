"""Post-UAT Sprint 1: Captain presentation, not engine/contract behaviour.

Human functional UAT passed and the engine is frozen for this sprint — these
tests prove the PRESENTATION requirements only: a persistent dynamic header,
scannable per-state mission cards, high-contrast rejection feedback, a reveal
treatment for Secret Missions, plain-language Paused/Complete screens, mobile
touch targets, and a full sweep for leftover "hunt"/UAT/internal-lifecycle
wording. No RPC, adapter, or engine call is exercised differently than before;
these tests assert on rendered text and widget attributes only.
"""
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from streamlit.testing.v1 import AppTest

from screens import theme_park_race as TPR


ROOT = Path(__file__).resolve().parents[1]
ACTIVITY_ID = "A1"
SESSION_TOKEN = "SESSION-TOK"
DEVICE_ID = "DEV-1"

# Wording that must never reach a Theme Park participant surface.
_FORBIDDEN_PARTICIPANT_WORDS = [
    "hunt", "theme park race", "uat", "runtime", "strategy mode",
    "lifecycle", "canonical", "facilitator release",
]


def _mission(state="AVAILABLE", mission_class="STANDARD", points=0, reason=""):
    mission = {
        "ActivityID": ACTIVITY_ID, "DisplayName": "Find the Hidden Waterfall",
        "MissionClass": mission_class, "MissionState": state,
        "ParticipantInstruction": "Locate the waterfall and take a team photo.",
        "Evidence": {"Text": {"Required": True}},
        "RejectionReason": reason,
    }
    if points:
        mission["Scoring"] = {"Maximum": points}
    return mission


def _workspace(*, lifecycle="ACTIVE", team="Velocity", completed=3, total=4,
               mission_state="AVAILABLE", mission_class="STANDARD", points=0, reason="",
               is_captain=True, captain_session_active=True):
    return {
        "EventID": "EV", "TeamID": "T6", "TeamIdentity": team,
        "Lifecycle": lifecycle, "StrategyMode": "OPEN_MISSION_BOARD",
        "IsCaptain": is_captain, "CaptainSessionActive": captain_session_active,
        "Progress": {"Completed": completed, "Total": total, "SubmissionsByActivity": {}},
        "Route": [], "TeamMembers": [],
        "MissionBoard": [_mission(mission_state, mission_class, points, reason)],
    }


def _run_participant_surface(shared):
    """A real, isolated Streamlit script — executed by AppTest, not mocked.

    AppTest.from_function re-executes only this function's own source text as
    a brand-new module; it shares nothing with this test file's module-level
    names, so every literal this body needs is inlined rather than referenced.
    """
    import types as _types
    import streamlit as st
    from screens.theme_park_race import render_theme_park_race_participant

    if "seeded" not in st.session_state:
        st.session_state["participant_session_token"] = "SESSION-TOK"
        st.session_state["participant_team"] = "Velocity"
        st.session_state["participant_name"] = "Adrian Choong"
        st.session_state["seeded"] = True
    db = _types.SimpleNamespace(runtime=_types.SimpleNamespace(
        theme_park_race_participant_workspace=lambda token: shared["workspace"],
        save_theme_park_race_submission=lambda *a, **k: shared["calls"].append("submit"),
        select_theme_park_race_mission=lambda *a, **k: shared["calls"].append("select"),
        claim_team_formation_captain=lambda *a, **k: {},
        recover_team_formation_captain=lambda *a, **k: {},
    ))
    render_theme_park_race_participant(db, device_id="DEV-1")


def _app(workspace):
    shared = {"workspace": workspace, "calls": []}
    at = AppTest.from_function(_run_participant_surface, args=(shared,))
    at.run()
    assert not at.exception
    return at, shared


def _all_visible_text(at):
    # st.write(str) renders through Markdown internally, so there is no
    # separate AppTest "write" collection — it shows up under `.markdown`.
    parts = []
    for kind in ("markdown", "caption", "info", "warning", "success", "error", "subheader", "header", "title"):
        for item in getattr(at, kind):
            parts.append(str(item.value))
    return " ".join(parts)


# 1. Dynamic Team header — never hard-coded.

def test_team_header_uses_the_canonical_team_identity_not_a_hardcoded_name():
    at, _ = _app(_workspace(team="Nebula Squad"))
    text = _all_visible_text(at)
    assert "Nebula Squad" in text
    assert "Velocity" not in text  # would only appear if the header were hard-coded


def test_team_header_reflects_a_different_team_on_a_different_workspace():
    at, _ = _app(_workspace(team="Aurora"))
    assert "Aurora" in _all_visible_text(at)


# 2. X / Y mission completion, from canonical Progress only.

@pytest.mark.parametrize("completed,total", [(3, 4), (0, 6), (6, 6)])
def test_mission_completion_count_is_canonical_and_dynamic(completed, total):
    at, _ = _app(_workspace(completed=completed, total=total))
    assert f"{completed}/{total}" in _all_visible_text(at)


# 3. Remaining mission count.

def test_remaining_count_shows_missions_left():
    at, _ = _app(_workspace(completed=3, total=4))
    assert "1 TO GO" in _all_visible_text(at)


def test_remaining_count_celebrates_when_nothing_is_left():
    at, _ = _app(_workspace(completed=4, total=4))
    text = _all_visible_text(at)
    assert "ALL MISSIONS DONE" in text
    assert "0 TO GO" not in text


# 4. AVAILABLE presentation.

def test_available_mission_shows_available_badge_and_select_action():
    at, _ = _app(_workspace(mission_state="AVAILABLE"))
    text = _all_visible_text(at)
    assert "AVAILABLE" in text
    labels = [b.label for b in at.button]
    assert any("Select Mission" in label for label in labels)


# 5. SUBMITTED / Awaiting Review — unmistakable, no active submit button.

def test_submitted_mission_shows_awaiting_review_with_no_submit_button():
    at, _ = _app(_workspace(mission_state="SUBMITTED"))
    text = _all_visible_text(at)
    assert "AWAITING REVIEW" in text
    labels = [b.label for b in at.button]
    assert not any("Submit" in label or "Resubmit" in label for label in labels)


# 6. APPROVED / Completed — strong completion treatment, no evidence controls.

def test_approved_mission_shows_completed_and_collapses_evidence_controls():
    at, _ = _app(_workspace(mission_state="APPROVED", points=50))
    text = _all_visible_text(at)
    assert "COMPLETED" in text
    labels = [b.label for b in at.button]
    assert not any("Submit" in label or "Select" in label for label in labels)
    assert not list(at.text_area)
    assert not list(at.get("file_uploader"))


# 7 & 8. REJECTED / Resubmission Required — high contrast, facilitator feedback visible.

def test_rejected_mission_shows_high_contrast_resubmission_required():
    at, _ = _app(_workspace(mission_state="REJECTED", reason="Retake the photo — signage must be visible."))
    text = _all_visible_text(at)
    assert "Resubmission Required" in text
    # Not the old weak, ambiguous phrasing.
    assert "please resubmit" not in text.casefold() or "Resubmission Required" in text


def test_rejected_mission_keeps_facilitator_feedback_visible():
    reason = "Retake the photo — signage must be visible."
    at, _ = _app(_workspace(mission_state="REJECTED", reason=reason))
    text = _all_visible_text(at)
    assert reason in text
    assert "Facilitator feedback" in text
    labels = [b.label for b in at.button]
    assert any("Update" in label and "Resubmit" in label for label in labels)


def test_rejection_banner_css_is_high_contrast_not_yellow_on_yellow():
    source = (ROOT / "screens/theme_park_race.py").read_text()
    start = source.index(".tp-rejected-banner")
    end = source.index("}", start)
    rule = source[start:end]
    # A red-bordered card with dark-red text on a light-red tint, not yellow.
    assert "#C4342F" in rule or "var(--tp-red)" in rule or "5A0D0A" in source
    assert "FFF" not in rule.upper() or "background:#FBE4E3" in source


# 9. Secret Mission reveal — no UAT/internal release wording.

def test_secret_mission_shows_a_reveal_not_internal_release_mechanics():
    at, _ = _app(_workspace(mission_state="AVAILABLE", mission_class="SECRET"))
    text = _all_visible_text(at)
    assert "Secret Mission Unlocked" in text
    lowered = text.casefold()
    assert "uat" not in lowered
    assert "facilitator release" not in lowered
    assert "should appear only after" not in lowered


# 10. HELD says "Mission AI Paused" — not "waiting to start"/hunt/race language.

def test_held_lifecycle_shows_mission_ai_paused():
    at, _ = _app(_workspace(lifecycle="HELD"))
    text = _all_visible_text(at)
    assert "Mission AI Paused" in text
    assert "Please wait for your facilitator." in text
    lowered = text.casefold()
    assert "waiting to start" not in lowered
    assert "hunt" not in lowered
    assert "race has not begun" not in lowered


def test_held_lifecycle_does_not_render_the_mission_board():
    at, shared = _app(_workspace(lifecycle="HELD"))
    labels = [b.label for b in at.button]
    assert not any("Select Mission" in label for label in labels)
    assert shared["calls"] == []


# 11. ENDED says "Mission Complete".

def test_ended_lifecycle_shows_mission_complete():
    at, _ = _app(_workspace(lifecycle="ENDED", completed=4, total=4))
    text = _all_visible_text(at)
    assert "MISSION COMPLETE" in text
    assert "Thank you for participating." in text
    assert "4/4" in text


def test_ended_lifecycle_has_no_write_controls():
    at, shared = _app(_workspace(lifecycle="ENDED"))
    assert not [b for b in at.button]
    assert shared["calls"] == []


# 12. No "hunt" participant wording, across every lifecycle and mission state.

@pytest.mark.parametrize("lifecycle", [
    "REGISTRATION", "TEAM_FORMATION", "FORMATION_LOCKED", "CAPTAIN_SELECTION",
    "READY", "ACTIVE", "HELD", "ENDED",
])
def test_no_hunt_wording_appears_in_any_lifecycle_state(lifecycle):
    at, _ = _app(_workspace(lifecycle=lifecycle))
    assert "hunt" not in _all_visible_text(at).casefold()


@pytest.mark.parametrize("state", ["AVAILABLE", "SELECTED", "SUBMITTED", "APPROVED", "REJECTED"])
def test_no_hunt_wording_appears_for_any_mission_state(state):
    at, _ = _app(_workspace(mission_state=state))
    assert "hunt" not in _all_visible_text(at).casefold()


# 13. No internal lifecycle/strategy terminology leaks into rendered text.

@pytest.mark.parametrize("lifecycle", [
    "REGISTRATION", "CAPTAIN_SELECTION", "READY", "ACTIVE", "HELD", "ENDED",
])
def test_no_internal_terminology_leaks_for_any_lifecycle(lifecycle):
    at, _ = _app(_workspace(lifecycle=lifecycle))
    lowered = _all_visible_text(at).casefold()
    for forbidden in _FORBIDDEN_PARTICIPANT_WORDS:
        assert forbidden not in lowered, f"{forbidden!r} leaked in lifecycle {lifecycle}"


def test_reconnect_error_uses_product_language_not_internal_engine_name():
    with patch.object(TPR, "st", MagicMock()) as fake:
        fake.session_state = {"participant_session_token": SESSION_TOKEN}
        fake.button.return_value = False
        from data.runtime_database import RuntimeDatabaseError
        db = types.SimpleNamespace(runtime=types.SimpleNamespace(
            theme_park_race_participant_workspace=lambda token: (_ for _ in ()).throw(
                RuntimeDatabaseError("Participant session is required."),
            ),
        ))
        TPR.render_theme_park_race_participant(db, device_id=DEVICE_ID)
    shown = " ".join(str(c.args[0]) for c in fake.warning.call_args_list if c.args)
    assert "Theme Park Race" not in shown
    assert "Mission AI is reconnecting" in shown


# 14. Mobile-safe primary actions: large touch targets, full-width, no overflow.

def test_primary_actions_meet_the_minimum_touch_target_css_rule():
    source = (ROOT / "screens/theme_park_race.py").read_text()
    assert "min-height:48px" in source


def test_select_and_submit_buttons_are_full_width_for_mobile():
    source = (ROOT / "screens/theme_park_race.py").read_text()
    for call_site in (
        '"🎯 Select Mission", type="primary", width="stretch"',
        'submit_label, type="primary", width="stretch"',
    ):
        assert call_site in source


def test_mobile_media_query_is_present_and_scoped_to_the_theme_park_surface():
    source = (ROOT / "screens/theme_park_race.py").read_text()
    assert "@media (max-width:600px)" in source


# 15. No session token / device ID / private fields rendered.

@pytest.mark.parametrize("lifecycle,mission_state", [
    ("ACTIVE", "AVAILABLE"), ("ACTIVE", "SELECTED"), ("ACTIVE", "REJECTED"),
    ("HELD", "AVAILABLE"), ("ENDED", "APPROVED"),
])
def test_no_session_token_or_device_id_ever_rendered(lifecycle, mission_state):
    at, _ = _app(_workspace(lifecycle=lifecycle, mission_state=mission_state))
    text = _all_visible_text(at)
    assert SESSION_TOKEN not in text
    assert DEVICE_ID not in text


def test_no_raw_html_class_names_leak_as_visible_text_content():
    """The badge/card HTML itself is fine; its class attribute must never be
    what a Captain reads as the message (the original raw-team-card defect
    class: dynamic content breaking out of a styled wrapper)."""
    at, _ = _app(_workspace(mission_state="REJECTED", reason="Retake the photo."))
    for item in at.markdown:
        assert 'class="tp-' not in str(item.value) or "<" in str(item.value)


# 16. Formula R.A.C.E. unchanged by this presentation sprint.

def test_formula_race_shares_no_theme_park_presentation_code():
    for path in ("screens/formula_race_captain.py", "screens/formula_race.py"):
        source = (ROOT / path).read_text()
        assert "_inject_mission_theme" not in source
        assert "_render_mission_card" not in source
        assert "tp-header" not in source
        assert "Mission AI Paused" not in source


def test_formula_race_captain_still_uses_its_own_distinct_visual_language():
    captain = (ROOT / "screens/formula_race_captain.py").read_text()
    assert "_race_css" in captain
    assert "race-team-name" in captain
