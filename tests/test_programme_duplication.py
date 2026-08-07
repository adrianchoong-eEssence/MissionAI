from copy import deepcopy

from engines.programme_duplication import (
    clone_experience_assignments,
    clone_programme_stages,
    programme_family,
    templates_for_event,
)
from engines.programme_hierarchy import (
    activity_details,
    decode_module_stage_type,
    encode_activity_details,
    encode_module_stage_type,
)


def _stage(number, module, activity, mission_id=""):
    return {
        "EventID": "EVT-SOURCE", "StageNo": number,
        "StageName": activity, "StageType": encode_module_stage_type(module, 1),
        "MissionID": mission_id, "DurationMinutes": 30, "DisplayMode": "Projector",
        "FacilitatorInstruction": encode_activity_details({
            "ModuleID": f"SRC-{module}", "ActivityID": f"SRC-ACT-{number}",
            "Credits": 100, "Scoring": "Fastest valid result", "Rules": "Keep all items moving",
        }),
    }


def test_clone_programme_is_destination_owned_and_preserves_configuration():
    source = [_stage(1, "Pipeline", "Pipeline Challenge", "P01"),
              _stage(2, "Pipeline", "Pipeline Results")]
    original = deepcopy(source)

    cloned, identifiers = clone_programme_stages(source, "EVT-SOURCE", "EVT-0016")

    assert source == original
    assert [row["StageName"] for row in cloned] == ["Pipeline Challenge", "Pipeline Results"]
    assert all(row["EventID"] == "EVT-0016" for row in cloned)
    assert all(row["ProgrammeID"] == "EVT-0016-PROGRAMME" for row in cloned)
    assert cloned[0]["DisplayMode"] == "Projector"
    assert activity_details(cloned[0])["Credits"] == 100
    assert activity_details(cloned[0])["Scoring"] == "Fastest valid result"
    assert decode_module_stage_type(cloned[0])["ModuleName"] == "Pipeline"
    assert identifiers["ActivityIDs"]["SRC-ACT-1"] == "EVT-0016-ACT-001"
    cloned[0]["StageName"] = "Destination edit"
    assert source[0]["StageName"] == "Pipeline Challenge"


def test_experience_assignments_reuse_definition_with_new_assignment_and_scope():
    stages = [_stage(1, "Pipeline", "Pipeline Challenge")]
    _, identifiers = clone_programme_stages(stages, "EVT-SOURCE", "EVT-0016")
    assignments = [{
        "ExperienceAssignmentID": "ASN-OLD", "EventID": "EVT-SOURCE",
        "ProgrammeID": "OLD", "ModuleID": "SRC-Pipeline", "ActivityID": "SRC-ACT-1",
        "ExperienceDefinitionID": "EXP-PIPELINE", "DefinitionVersion": 3,
    }]

    cloned = clone_experience_assignments(assignments, "EVT-0016", identifiers)

    assert cloned[0]["ExperienceAssignmentID"] != "ASN-OLD"
    assert cloned[0]["EventID"] == "EVT-0016"
    assert cloned[0]["ExperienceDefinitionID"] == "EXP-PIPELINE"
    assert cloned[0]["ActivityID"] == "EVT-0016-ACT-001"


def test_product_specific_template_filtering():
    mission = [(1, "Mission AI", ["Missions"])]
    race = [(1, "RACE Checkpoints", ["RACE Checkpoints"])]
    assert programme_family({"ProgrammeType": "Enterprise AGILE"}) == "AGILE"
    assert programme_family({"ProgrammeType": "Formula R.A.C.E."}) == "RACE"
    assert programme_family({"ProgrammeType": "Mission AI"}) == "MISSION_AI"
    assert any(row[1] == "Pipeline" for row in templates_for_event({"ProgrammeType": "AGILE"}, mission, race))
    assert any(row[1] == "RACE Checkpoints" for row in templates_for_event({"ProgrammeType": "Formula R.A.C.E."}, mission, race))
    assert not any(row[1] == "Mission AI" for row in templates_for_event({"ProgrammeType": "Corporate Training"}, mission, race))


def test_legacy_rows_remain_in_one_programme_module():
    legacy = [
        {"EventID": "EVT-SOURCE", "StageNo": 1, "StageName": "Registration", "StageType": "Registration"},
        {"EventID": "EVT-SOURCE", "StageNo": 2, "StageName": "Pipeline Challenge", "StageType": "MissionBriefing"},
    ]
    cloned, _ = clone_programme_stages(legacy, "EVT-SOURCE", "EVT-0016")
    assert len({activity_details(row)["ModuleID"] for row in cloned}) == 1
    assert all(decode_module_stage_type(row)["ModuleName"] == "Programme" for row in cloned)
