from copy import deepcopy
from pathlib import Path

import pytest

from components.experience_preview import experience_participant_view
from engines.experience_library import (
    ExperienceLibraryService,
    ExperienceResolutionError,
    filter_definitions,
    new_assignment,
    new_definition,
    resolve_experience,
)


ROOT = Path(__file__).resolve().parents[1]


class MemoryRepository:
    def __init__(self):
        self.definitions = {}
        self.assignments = {}

    def save_definition(self, row):
        saved = deepcopy(row)
        self.definitions[(saved["ExperienceDefinitionID"], int(saved["Version"]))] = saved
        return deepcopy(saved)

    def get_definition(self, definition_id, version):
        return deepcopy(self.definitions.get((definition_id, int(version))))

    def save_assignment(self, row):
        self.assignments[row["ExperienceAssignmentID"]] = deepcopy(row)
        return deepcopy(row)

    def get_assignment(self, assignment_id):
        return deepcopy(self.assignments.get(assignment_id))

    def remove_assignment(self, assignment_id):
        self.assignments.pop(assignment_id, None)
        return {"Removed": True, "DefinitionDeleted": False}


def definition(name="Reusable", version=1, status="PUBLISHED"):
    return new_definition({
        "ExperienceDefinitionID": "EXP-1", "Name": name, "ParticipantTitle": name,
        "ParticipantNarrative": "Default narrative", "ParticipantTask": "Default task",
        "DefaultIntelligenceCredits": 100, "DefaultEvidenceType": "PHOTO",
        "DefaultEvidenceInstructions": "Take a photo", "DefaultCharacterID": "CHAR-1",
        "ReferenceAssetIDs": ["ASSET-1"], "DefaultHint": "Default hint",
        "DefaultAIResponse": "Default response", "Version": version, "Status": status,
    }, "EXP-1")


def assignment(event="E1", **updates):
    values = {
        "ExperienceAssignmentID": f"ASN-{event}", "EventID": event,
        "ProgrammeID": f"{event}-PROGRAMME", "ModuleID": "MOD-1", "ActivityID": "ACT-1",
        "ExperienceDefinitionID": "EXP-1", "DefinitionVersion": 1,
        "AssignmentOrder": 1, "Active": True, "RuntimeEligible": True,
    }
    values.update(updates)
    return new_assignment(values, values["ExperienceAssignmentID"])


def test_one_definition_is_assigned_to_two_events_without_copying_content():
    shared = definition()
    first = resolve_experience(shared, assignment("E1"))
    second = resolve_experience(shared, assignment("E2"))
    assert first["ExperienceDefinitionID"] == second["ExperienceDefinitionID"] == "EXP-1"
    assert first["EventID"] != second["EventID"]


def test_sparse_overrides_are_event_isolated():
    shared = definition()
    first = resolve_experience(shared, assignment("E1", ParticipantTitleOverride="Event One", CreditsOverride=50))
    second = resolve_experience(shared, assignment("E2", ParticipantTitleOverride="Event Two", CreditsOverride=200))
    assert (first["ParticipantTitle"], first["IntelligenceCredits"]) == ("Event One", 50)
    assert (second["ParticipantTitle"], second["IntelligenceCredits"]) == ("Event Two", 200)
    assert shared["ParticipantTitle"] == "Reusable"


def test_assets_and_characters_are_referenced_without_duplication_and_missing_asset_is_safe():
    shared = definition()
    asset = {"ASSET-1": {"AssetID": "ASSET-1", "MediaReference": "image.png", "Crop": {"x": 1}}}
    character = {"CHAR-1": {"CharacterID": "CHAR-1", "Name": "Guide"}}
    first = resolve_experience(shared, assignment("E1"), assets=asset, characters=character)
    second = resolve_experience(shared, assignment("E2"), assets=asset, characters=character)
    assert first["Assets"][0] is second["Assets"][0]
    assert first["Character"] is second["Character"]
    missing = resolve_experience(shared, assignment("E3"), assets={}, characters={})
    assert missing["MissingAssetIDs"] == ["ASSET-1"]


def test_published_edit_creates_new_version_and_history_is_unchanged():
    repo = MemoryRepository()
    repo.save_definition(definition())
    service = ExperienceLibraryService(repo)
    revised = service.edit_definition("EXP-1", 1, {"ParticipantTitle": "Revised"})
    assert revised["Version"] == 2 and revised["Status"] == "DRAFT"
    assert repo.get_definition("EXP-1", 1)["ParticipantTitle"] == "Reusable"
    historical = service.assign({**assignment("E1"), "DefinitionVersion": 1})
    assert service.resolve(historical["ExperienceAssignmentID"])["ParticipantTitle"] == "Reusable"


def test_activation_removal_and_reordering_affect_assignment_only():
    repo = MemoryRepository()
    repo.save_definition(definition())
    service = ExperienceLibraryService(repo)
    first = service.assign(assignment("E1"))
    second = service.assign(assignment("E2", AssignmentOrder=3))
    first["Active"] = False
    repo.save_assignment(first)
    assert repo.get_assignment(second["ExperienceAssignmentID"])["Active"] is True
    result = service.remove_assignment(first["ExperienceAssignmentID"])
    assert result["DefinitionDeleted"] is False
    assert repo.get_definition("EXP-1", 1)
    assert second["AssignmentOrder"] == 3


def test_bulk_activation_and_reorder_persist_without_definition_mutation():
    repo = MemoryRepository()
    repo.save_definition(definition())
    service = ExperienceLibraryService(repo)
    first = service.assign(assignment("E1"))
    second = service.assign(assignment("E2"))
    service.set_assignments_active([first["ExperienceAssignmentID"]], False)
    assert repo.get_assignment(first["ExperienceAssignmentID"])["Active"] is False
    service.reorder_assignments([second["ExperienceAssignmentID"], first["ExperienceAssignmentID"]])
    assert repo.get_assignment(second["ExperienceAssignmentID"])["AssignmentOrder"] == 1
    assert repo.get_assignment(first["ExperienceAssignmentID"])["AssignmentOrder"] == 2
    assert repo.get_definition("EXP-1", 1)["ParticipantTitle"] == "Reusable"


def test_library_search_and_all_required_filters_are_definition_based():
    first = definition()
    first.update({"ExperienceType": "Race", "Difficulty": "Hard", "VenueTags": ["Outdoor"],
                  "Tags": ["Teamwork"], "DefaultEvidenceType": "PHOTO"})
    second = definition(name="Quiet Lab")
    second.update({"ExperienceDefinitionID": "EXP-2", "ExperienceType": "Lab",
                   "Difficulty": "Easy", "VenueTags": ["Indoor"], "Tags": ["AI"],
                   "DefaultEvidenceType": "TEXT"})
    result = filter_definitions(
        [first, second], search="reus", experience_types=["Race"],
        difficulties=["Hard"], venues=["Outdoor"], evidence_types=["PHOTO"],
        statuses=["PUBLISHED"], tags=["Teamwork"],
    )
    assert result == [first]


def test_inactive_assignment_and_missing_definition_fail_closed():
    with pytest.raises(ExperienceResolutionError):
        resolve_experience(definition(), assignment("E1", Active=False))
    with pytest.raises(ExperienceResolutionError):
        resolve_experience(None, assignment("E1"))


def test_preview_contract_is_the_real_participant_contract():
    resolved = resolve_experience(definition(), assignment("E1"))
    view = experience_participant_view(resolved)
    assert view == experience_participant_view(resolved)
    participant_source = (ROOT / "screens" / "participant.py").read_text()
    centre_source = (ROOT / "screens" / "experience_foundation.py").read_text()
    assert "render_experience_participant(resolved)" in participant_source
    assert "render_experience_participant(resolve_experience" in centre_source


def test_historical_versions_and_dual_events_resolve_independently():
    v1 = definition(name="Original", version=1)
    v2 = definition(name="Revised", version=2)
    assert resolve_experience(v1, assignment("E1"))["ParticipantTitle"] == "Original"
    assert resolve_experience(v2, assignment("E2", DefinitionVersion=2))["ParticipantTitle"] == "Revised"


def test_schema_and_generic_paths_enforce_separation_and_no_event_shortcuts():
    migration = (ROOT / "supabase" / "013_experience_definition_assignment.sql").read_text()
    assert "experience_definitions" in migration
    assert "event_experience_assignments" in migration
    assert "experience_definition_version" in migration
    generic = "\n".join((
        (ROOT / "engines" / "experience_library.py").read_text(),
        (ROOT / "data" / "experience_repository.py").read_text(),
        (ROOT / "components" / "experience_preview.py").read_text(),
    ))
    for forbidden in ("EVT-0004", "Bayu Beach", "AIA", "Formula RACE", "Mission AI", "Experience 18"):
        assert forbidden not in generic
