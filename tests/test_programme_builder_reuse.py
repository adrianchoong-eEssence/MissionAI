from copy import deepcopy
import json

from engines.formula_race_checkpoints import is_formula_race_event
from engines.programme_duplication import clone_programme_stages
from engines.programme_hierarchy import activity_details, decode_module_stage_type, encode_module_stage_type
from screens.programme_builder import (
    _build_modules_from_catalogue,
    _normalise_imported_modules,
    _parse_programme_import_payload,
    _program_type_option_label,
    _template_family_catalogue,
)


def _row(number, module, activity):
    return {
        "EventID": "EVT-SOURCE",
        "StageNo": number,
        "StageType": encode_module_stage_type(module, 1),
        "StageName": activity,
        "IsActive": "Yes",
    }


def test_use_template_catalogue_filters_by_programme_type():
    standard = _template_family_catalogue({}, "Standard")
    agile = _template_family_catalogue({}, "AGILE")
    mission_ai = _template_family_catalogue({}, "Mission AI")
    race = _template_family_catalogue({}, "Formula R.A.C.E.")
    walk_hunt = _template_family_catalogue({}, "Walk Hunt")
    road_rally = _template_family_catalogue({}, "Road Rally")
    f1 = _template_family_catalogue({}, "F1 Circuit")

    assert any(row[1] == "Arrival & Registration" for row in standard)
    assert any(row[1] == "Pipeline" for row in agile)
    assert any(row[1] == "Mission AI" for row in mission_ai)
    assert any(row[1] == "RACE Checkpoints" for row in race)
    assert any(row[1] == "Clue Trail" for row in walk_hunt)
    assert any(row[1] == "Rally Start" for row in road_rally)
    assert any(row[1] == "Circuit Briefing" for row in f1)
    assert not any(row[1] == "RACE Checkpoints" for row in standard)


def test_programme_type_label_is_backward_compatible():
    assert _program_type_option_label({"ProgrammeType": "Formula R.A.C.E."}) == "Formula R.A.C.E."
    assert _program_type_option_label({"ProgrammeType": "Enterprise AGILE"}) == "AGILE"
    assert _program_type_option_label({"ProgrammeType": "Mission AI"}) == "Mission AI"
    assert _program_type_option_label({"ProgrammeType": "Walk Hunt"}) == "Walk Hunt"
    assert _program_type_option_label({"ProgrammeType": "Road Rally"}) == "Road Rally"
    assert _program_type_option_label({"ProgrammeType": "F1 Circuit"}) == "F1 Circuit"
    assert _program_type_option_label({}) == "Standard"


def test_build_modules_from_catalogue_generates_ordered_ids_and_payload():
    event_id = "EVT-REUSE"
    modules = _build_modules_from_catalogue(
        event_id,
        [
            (1, "Launch EXOS", ["Launch EXOS"]),
            (1, "NASI", ["NASI"]),
            (2, "Closing", ["Closing"]),
        ],
    )

    assert [module["ModuleName"] for module in modules] == ["Launch EXOS", "NASI", "Closing"]
    assert [module["ModuleOrder"] for module in modules] == [1, 2, 3]
    assert [int(mod["Day"]) for mod in modules] == [1, 1, 2]
    assert len({module["ModuleID"] for module in modules}) == 3
    activity_ids = [activity["ActivityID"] for module in modules for activity in module["Activities"]]
    assert len(activity_ids) == 3
    assert all(identifier.startswith(f"{event_id}-ACT-") for identifier in activity_ids)
    assert activity_details(modules[1]["Activities"][0])["ProgrammeID"] == f"{event_id}-PROGRAMME"


def test_duplicate_configuration_only_copies_destination_configuration():
    source = [
        _row(1, "Pipeline", "Pipeline Challenge"),
        _row(2, "Pipeline", "Pipeline Result"),
        _row(3, "Closing", "Closing"),
    ]
    backup = deepcopy(source)

    cloned, identifiers = clone_programme_stages(source, "EVT-SOURCE", "EVT-DUP")
    assert source == backup
    assert [row["StageName"] for row in cloned] == ["Pipeline Challenge", "Pipeline Result", "Closing"]
    assert all(row["EventID"] == "EVT-DUP" for row in cloned)
    assert all(row["ProgrammeID"] == "EVT-DUP-PROGRAMME" for row in cloned)
    assert all(row["ActivityID"] == expected for row, expected in zip(cloned, [
        "EVT-DUP-ACT-001",
        "EVT-DUP-ACT-002",
        "EVT-DUP-ACT-003",
    ]))
    assert identifiers["ModuleIDs"] == {
        "Pipeline": "EVT-DUP-MOD-01",
        "Closing": "EVT-DUP-MOD-02",
    }
    # new IDs and module names remain aligned with the source structure.
    assert [decode_module_stage_type(row)["ModuleName"] for row in cloned] == ["Pipeline", "Pipeline", "Closing"]
    assert all(activity_details(row)["ActivityID"] == row["ActivityID"] for row in cloned)


def test_race_catalogue_requires_formula_route_for_checkpoint_event():
    # Ensure we keep Formula R.A.C.E. templates intentionally race-aware.
    event = {"ProgrammeType": "Formula R.A.C.E.", "EventName": "EVT-0006"}
    modules = _template_family_catalogue(event, "Formula R.A.C.E.")
    assert any(name == "RACE Checkpoints" for _, name, _ in modules)
    assert is_formula_race_event(event)


def test_import_payload_parser_and_normaliser():
    source = {
        "programme_name": "Team Demo",
        "programme_type": "Standard",
        "modules": [
            {
                "ModuleName": "Mission AI",
                "Day": 1,
                "Activities": [
                    {
                        "StageName": "Mission AI Briefing",
                        "DurationMinutes": 20,
                        "ActivityType": "Briefing",
                    }
                ],
            }
        ],
    }
    payload = _parse_programme_import_payload(json.dumps(source))
    modules = _normalise_imported_modules("EVT-IMPORT", payload["modules"])

    assert payload["programme_name"] == "Team Demo"
    assert len(modules) == 1
    assert modules[0]["ModuleName"] == "Mission AI"
    assert modules[0]["Activities"][0]["StageName"] == "Mission AI Briefing"
    assert activity_details(modules[0]["Activities"][0])["ProgrammeID"] == "EVT-IMPORT-PROGRAMME"
    assert modules[0]["Activities"][0]["ModuleID"].startswith("EVT-IMPORT-MOD")
