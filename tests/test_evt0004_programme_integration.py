from pathlib import Path

from engines.programme_hierarchy import (
    activity_content_config,
    canonical_event_programme,
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

    config = activity_content_config(stage)
    assert config["ContentType"] == "Experience Board"
    assert config["LinkedContentID"] == "Operation: The Labyrinth"
    payload = linked_content_stage(stage, experience_count=17)
    assert payload["LinkedExperienceSet"] == "Operation: The Labyrinth"
    assert payload["ExperienceCount"] == 17


def test_sync_ai_link_publishes_one_resolved_live_payload():
    class DB:
        def set_stage(self, event_id, stage):
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
        "Select Module", "Select Activity", "Start Selected Activity",
        "End Selected Activity", "Previous Activity", "Next Activity",
    ):
        assert f'"{label}"' in control
    assert "render_sync_ai_participant" in participant
    assert "ENTER THE LABYRINTH" in participant


def test_event_ids_do_not_trigger_event_specific_canonical_projection():
    stages = [
        {"EventID": "EVT-0004", "StageNo": index, "StageName": name,
         "DurationMinutes": 15, "IsActive": "Yes"}
        for index, name in enumerate((
            "Registration", "Energiser", "Launch EXOS", "Bridge of Trust",
            "Mission AI Briefing", "Lunch", "SYNC AI Innovation Market",
            "Catalyst Challenge", "Mission AI", "SYNC AI Performance & Judging",
        ), start=1)
    ]

    modules = canonical_event_programme(stages, "EVT-0004")

    assert [module["ModuleName"] for module in modules] == [
        "Registration", "Energiser", "Launch EXOS", "Bridge of Trust",
        "Mission AI Briefing", "Lunch", "SYNC AI Innovation Market",
        "Catalyst Challenge", "Mission AI", "SYNC AI Performance & Judging",
    ]
    assert len({module["ModuleID"] for module in modules}) == 10
    activities = [module["Activities"][0] for module in modules]
    assert len({activity["ActivityID"] for activity in activities}) == 10
    assert all(activity["EventID"] == "EVT-0004" for activity in activities)
