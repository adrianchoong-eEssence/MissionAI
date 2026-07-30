from copy import deepcopy

from data.aia_customer_contact import AIA_CUSTOMER_CONTACT_STAGES
from data.aia_customer_contact import migrate_evt0004_programme_hierarchy
from engines.programme_hierarchy import (
    activity_details,
    build_programme_hierarchy,
    current_module_activity,
    encode_activity_details,
    encode_module_stage_type,
    flatten_programme_hierarchy,
)


def test_aia_stages_are_grouped_into_event_modules():
    modules = build_programme_hierarchy(AIA_CUSTOMER_CONTACT_STAGES)
    names = [module["ModuleName"] for module in modules]
    assert "Mission AI" in names
    assert "Sync AI" in names
    assert "Catalyst Challenge" in names
    mission_ai = next(row for row in modules if row["ModuleName"] == "Mission AI")
    assert [row["StageName"] for row in mission_ai["Activities"]] == [
        "Mission AI Briefing",
        "Mission Board Opens",
        "Signal in the Noise",
        "Human × AI Decision Lab",
        "Friction Safari",
        "Elevate the Moment",
        "Submission Review",
        "Credit Release",
        "Mission AI Debrief",
    ]


def test_internal_order_is_event_specific_and_master_is_unchanged():
    master = deepcopy(AIA_CUSTOMER_CONTACT_STAGES)
    event_a = build_programme_hierarchy(master)
    event_b = build_programme_hierarchy(master)
    mission_a = next(row for row in event_a if row["ModuleName"] == "Mission AI")
    mission_a["Activities"][1], mission_a["Activities"][2] = (
        mission_a["Activities"][2],
        mission_a["Activities"][1],
    )
    flattened_a = flatten_programme_hierarchy(event_a)
    flattened_b = flatten_programme_hierarchy(event_b)
    assert flattened_a != flattened_b
    assert master == AIA_CUSTOMER_CONTACT_STAGES


def test_current_module_and_activity_are_resolved_for_runtime():
    module, activity = current_module_activity(AIA_CUSTOMER_CONTACT_STAGES, 17)
    assert module["ModuleName"] == "Sync AI"
    assert activity["MissionID"] == "S01"


def test_evt0004_migration_executes_without_touching_missions():
    class FakeDB:
        saved = None
        current = None

        def get_event(self, event_id):
            return {"EventID": event_id}

        def get_programme_stages(self, event_id):
            return [{"StageNo": 1, "StageName": "Legacy"}]

        def save_programme_stages(self, event_id, stages):
            self.saved = deepcopy(stages)

        def set_event_stage(self, event_id, stage):
            self.current = deepcopy(stage)

        def get_event_missions(self, event_id, include_closed=True):
            return [{"MissionID": "M01"}, {"MissionID": "S01"}]

    db = FakeDB()
    result = migrate_evt0004_programme_hierarchy(db)
    assert result["PreviousStages"] == 1
    assert result["MissionsPreserved"] == 2
    assert db.saved == AIA_CUSTOMER_CONTACT_STAGES
    assert db.current["StageName"] == "Arrival & Registration"


def test_custom_module_and_editable_activity_details_round_trip():
    stage = {
        "StageNo": 1,
        "StageName": "Customer Promise",
        "StageType": encode_module_stage_type("Service Lab", 2, "Activity"),
        "FacilitatorInstruction": encode_activity_details({
            "FacilitatorInstructions": "Ask each team to present.",
            "Questions": "What changes on Monday?",
            "Credits": 50,
            "Rules": "One answer per team.",
        }),
    }
    module = build_programme_hierarchy([stage])[0]
    assert module["ModuleName"] == "Service Lab"
    assert module["Day"] == 2
    assert activity_details(stage)["Credits"] == 50
    assert activity_details(stage)["Questions"] == "What changes on Monday?"
