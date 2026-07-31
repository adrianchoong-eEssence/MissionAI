from pathlib import Path
from unittest.mock import patch

from engines.programme_hierarchy import activity_details, encode_activity_details
from screens.participant import render_programme_activity


def bridge_stage():
    return {
        "StageName": "Bridge of Trust",
        "ParticipantMessage": "Cross together.",
        "FacilitatorInstruction": encode_activity_details({
            "FacilitatorInstructions": "Observe communication patterns.",
            "ParticipantNarrative": "The entrance has been sealed.",
            "ParticipantTask": "Cross as one complete expedition team.",
            "EvidenceRequired": True,
            "EvidenceRequirement": "Facilitator verification.",
            "Credits": 0,
        }),
    }


def test_event_activity_content_round_trips_in_stage_metadata():
    details = activity_details(bridge_stage())

    assert details["ParticipantNarrative"] == "The entrance has been sealed."
    assert details["ParticipantTask"] == "Cross as one complete expedition team."
    assert details["EvidenceRequirement"] == "Facilitator verification."
    assert details["FacilitatorInstructions"] == "Observe communication patterns."


@patch("screens.participant.st")
def test_participant_activity_hides_facilitator_notes(streamlit):
    render_programme_activity(bridge_stage())

    rendered = " ".join(
        str(call.args[0])
        for method in (
            streamlit.markdown, streamlit.info, streamlit.success, streamlit.write
        )
        for call in method.call_args_list
        if call.args
    )
    assert "The entrance has been sealed." in rendered
    assert "Cross as one complete expedition team." in rendered
    assert "Facilitator verification." in rendered
    assert "Observe communication patterns." not in rendered


def test_programme_builder_exposes_required_event_activity_fields():
    source = (
        Path(__file__).resolve().parents[1] / "screens" / "programme_builder.py"
    ).read_text(encoding="utf-8")

    for label in (
        "Activity Title", "Participant Narrative", "Participant Task",
        "Evidence Requirement", "Facilitator Notes", "Credits", "Active",
    ):
        assert f'"{label}"' in source
