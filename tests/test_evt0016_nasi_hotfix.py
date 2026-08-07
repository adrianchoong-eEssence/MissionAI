from pathlib import Path

from engines.programme_duplication import AGILE_MODULES
from screens.participant import normalise_submission_type


PARTICIPANT = (Path(__file__).resolve().parents[1] / "screens" / "participant.py").read_text()
CONSOLE = (Path(__file__).resolve().parents[1] / "screens" / "live_event_console.py").read_text()
CONTROL_CENTRE = (Path(__file__).resolve().parents[1] / "screens" / "control_centre.py").read_text()
FACILITATOR = (Path(__file__).resolve().parents[1] / "Facilitator.py").read_text()
APP_STATE = (Path(__file__).resolve().parents[1] / "screens" / "app_state.py").read_text()


def test_agile_programme_builder_offers_the_historical_nasi_activity():
    assert (1, "NASI", ["NASI"]) in AGILE_MODULES


def test_programme_builder_nasi_activity_uses_the_existing_individual_form():
    assert normalise_submission_type({"Title": "NASI"}) == "NASI"
    assert 'programme_submission_type == "NASI"' in PARTICIPANT
    assert 'elif submission_type == "NASI":' in PARTICIPANT
    assert "render_submission_form(db, programme_mission, submission_type)" in PARTICIPANT


def test_historical_nasi_fields_and_facilitator_review_are_preserved():
    for field in (
        "N — New Ideas", "A — Areas for Improvement", "S — Strengths",
        "I — Implementation", "📤 Submit NASI",
    ):
        assert field in PARTICIPANT
    assert "Reflection only — no score" in CONSOLE
    assert "### NASI Reflection" in CONSOLE


def test_evt0016_has_a_standard_facilitator_control_and_nasi_queue():
    assert '"Event Control"' in FACILITATOR
    assert "show_control_centre()" in FACILITATOR
    assert 'st.query_params.get("event_id", "")' in FACILITATOR
    assert 'st.query_params["event_id"] = selected_id' in APP_STATE
    for label in (
        "NASI Live Status",
        "Registered participants",
        "NASI submitted",
        "NASI outstanding",
    ):
        assert label in CONTROL_CENTRE
    for label in (
        "First Name",
        "Last Name",
        "Team / Country",
        "New Ideas",
        "Areas of Improvement",
        "Strengths",
        "Implementation",
    ):
        assert label in CONSOLE
