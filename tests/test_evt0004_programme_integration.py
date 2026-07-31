from pathlib import Path

from engines.programme_hierarchy import (
    activity_content_config,
    encode_activity_details,
    linked_content_stage,
)
from screens.control_centre import _start_programme_activity


def linked_stage(content_type, linked_content=""):
    return {
        "EventID": "EVT-0004",
        "StageNo": 5,
        "StageName": "Operation: The Labyrinth",
        "FacilitatorInstruction": encode_activity_details({
            "ContentType": content_type,
            "LinkedContent": linked_content,
        }),
    }


def test_activity_content_link_round_trips_without_schema_change():
    stage = linked_stage("Experience Board", "Operation: The Labyrinth")

    assert activity_content_config(stage) == {
        "ContentType": "Experience Board",
        "LinkedContent": "Operation: The Labyrinth",
    }
    payload = linked_content_stage(stage, experience_count=17)
    assert payload["LinkedExperienceSet"] == "Operation: The Labyrinth"
    assert payload["ExperienceCount"] == 17


def test_sync_ai_link_publishes_one_resolved_live_payload():
    class DB:
        def set_event_stage(self, event_id, stage):
            self.event_id = event_id
            self.stage = dict(stage)

    db = DB()
    stage = linked_stage("Sync AI", "EVT-0004 Sync AI")

    live = _start_programme_activity(db, "EVT-0004", stage, {})

    assert live["ContentType"] == "Sync AI"
    assert live["LinkedContent"] == "EVT-0004 Sync AI"
    assert db.stage == live


def test_programme_and_control_surfaces_expose_linked_content_contract():
    root = Path(__file__).resolve().parents[1]
    builder = (root / "screens" / "programme_builder.py").read_text()
    control = (root / "screens" / "control_centre.py").read_text()
    participant = (root / "screens" / "participant.py").read_text()

    for label in ("Content Type", "Linked Content"):
        assert f'"{label}"' in builder
    for label in (
        "Linked Content Type", "Linked Content Name", "Participant Preview",
        "Start Activity", "End Activity", "Previous Activity", "Next Activity",
    ):
        assert f'"{label}"' in control
    assert "render_sync_ai_participant" in participant
    assert "ENTER THE LABYRINTH" in participant

