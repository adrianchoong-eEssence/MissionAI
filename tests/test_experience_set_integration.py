from data.google_sheets import GoogleSheetsDB
from engines.programme_hierarchy import (
    build_programme_hierarchy,
    encode_activity_details,
    encode_module_stage_type,
    experience_set_config,
    experience_set_stage,
)
from screens.control_centre import _start_programme_activity
from screens.participant import active_experience_set_missions


def linked_module():
    stage = {
        "StageNo": 1,
        "StageName": "Mission AI",
        "StageType": encode_module_stage_type(
            "Mission AI", 1, "Experience Set",
        ),
        "FacilitatorInstruction": encode_activity_details({
            "FacilitatorInstructions": "Open the morning operation.",
            "ModuleDetails": {
                "ModuleType": "Experience Set",
                "LinkedExperienceSet": "Operation: The Labyrinth",
            },
        }),
    }
    return build_programme_hierarchy([stage])[0]


def test_module_metadata_round_trips_experience_set_link_without_schema_change():
    module = linked_module()

    assert experience_set_config(module) == {
        "ModuleType": "Experience Set",
        "LinkedExperienceSet": "Operation: The Labyrinth",
    }
    stage = experience_set_stage(module["Activities"][0], module, 17)
    assert stage["LinkedExperienceSet"] == "Operation: The Labyrinth"
    assert stage["ExperienceCount"] == 17


def test_activate_experience_set_publishes_active_records_only():
    class Runtime:
        can_publish = True

        def publish_programme(self, event_id, missions):
            self.published = (event_id, list(missions))
            return {"MissionsPublished": len(missions)}

    db = GoogleSheetsDB.__new__(GoogleSheetsDB)
    db.runtime = Runtime()
    db.get_event_missions = lambda event_id: [
        {"MissionID": "M01", "Module": "The Labyrinth", "Status": "ACTIVE"},
        {"MissionID": "M02", "Module": "The Labyrinth", "Status": "INACTIVE"},
        {"MissionID": "J01", "Module": "Jurassic", "Status": "ACTIVE"},
    ]

    result = db.activate_experience_set("EVT-TEST", "The Labyrinth")

    assert result["ExperiencesPublished"] == 1
    assert [row["MissionID"] for row in db.runtime.published[1]] == ["M01"]


def test_control_centre_activates_set_before_publishing_live_stage():
    class DB:
        def activate_experience_set(self, event_id, experience_set):
            self.activated = (event_id, experience_set)
            return {"ExperiencesPublished": 17}

        def set_event_stage(self, event_id, stage):
            self.live_stage = dict(stage)

    db = DB()
    module = linked_module()
    stage = module["Activities"][0]

    live_stage = _start_programme_activity(db, "EVT-0004", stage, module)

    assert db.activated == ("EVT-0004", "Operation: The Labyrinth")
    assert live_stage["ModuleType"] == "Experience Set"
    assert db.live_stage["ExperienceCount"] == 17


def test_participant_board_hides_inactive_experiences():
    class DB:
        @staticmethod
        def get_event_missions(event_id):
            return [
                {"MissionID": "J01", "Module": "Jurassic", "Status": "ACTIVE"},
                {"MissionID": "J02", "Module": "Jurassic", "Status": "INACTIVE"},
                {"MissionID": "R01", "Module": "Road Rally", "Status": "ACTIVE"},
            ]

    missions = active_experience_set_missions(DB(), "EVT-TEST", "Jurassic")

    assert [row["MissionID"] for row in missions] == ["J01"]
