"""Reusable Experience Definitions and event-scoped Assignment resolution."""

from copy import deepcopy
from datetime import datetime, timezone
import uuid


DEFINITION_FIELDS = (
    "ExperienceDefinitionID", "Name", "InternalDescription", "ParticipantTitle",
    "ParticipantNarrative", "ParticipantTask", "ExperienceType", "Difficulty",
    "DefaultIntelligenceCredits", "DefaultEvidenceType", "DefaultEvidenceInstructions",
    "DefaultCharacterID", "DefaultAIResponse", "DefaultHint", "ReferenceAssetIDs",
    "Tags", "LearningThemes", "VenueTags", "Version", "Status", "CreatedAt", "UpdatedAt",
)
ASSIGNMENT_FIELDS = (
    "ExperienceAssignmentID", "EventID", "ProgrammeID", "ModuleID", "ActivityID",
    "ExperienceDefinitionID", "DefinitionVersion", "AssignmentOrder", "Active",
    "ParticipantTitleOverride", "NarrativeOverride", "TaskOverride", "CreditsOverride",
    "EvidenceTypeOverride", "EvidenceInstructionsOverride", "CharacterIDOverride",
    "AssetIDsOverride", "HintOverride", "AIResponseOverride", "AvailabilityRule",
    "StartRule", "EndRule", "UnlockRule", "RuntimeEligible", "AssignmentVersion",
)


class ExperienceResolutionError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _version(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def new_definition(values, definition_id=""):
    source = dict(values or {})
    stable_id = str(definition_id or source.get("ExperienceDefinitionID") or f"EXP-{uuid.uuid4()}").strip()
    now = _now()
    return {
        "ExperienceDefinitionID": stable_id,
        "Name": str(source.get("Name", "")).strip(),
        "InternalDescription": str(source.get("InternalDescription", "")),
        "ParticipantTitle": str(source.get("ParticipantTitle") or source.get("Name") or ""),
        "ParticipantNarrative": str(source.get("ParticipantNarrative", "")),
        "ParticipantTask": str(source.get("ParticipantTask", "")),
        "ExperienceType": str(source.get("ExperienceType", "Standard")),
        "Difficulty": str(source.get("Difficulty", "Unspecified")),
        "DefaultIntelligenceCredits": int(source.get("DefaultIntelligenceCredits", 0) or 0),
        "DefaultEvidenceType": str(source.get("DefaultEvidenceType", "NONE")),
        "DefaultEvidenceInstructions": str(source.get("DefaultEvidenceInstructions", "")),
        "DefaultCharacterID": str(source.get("DefaultCharacterID", "")),
        "DefaultAIResponse": str(source.get("DefaultAIResponse", "")),
        "DefaultHint": str(source.get("DefaultHint", "")),
        "ReferenceAssetIDs": list(source.get("ReferenceAssetIDs", []) or []),
        "Tags": list(source.get("Tags", []) or []),
        "LearningThemes": list(source.get("LearningThemes", []) or []),
        "VenueTags": list(source.get("VenueTags", []) or []),
        "Version": _version(source.get("Version", 1)),
        "Status": str(source.get("Status", "DRAFT")).upper(),
        "CreatedAt": str(source.get("CreatedAt") or now),
        "UpdatedAt": now,
    }


def new_assignment(values, assignment_id=""):
    source = dict(values or {})
    return {
        "ExperienceAssignmentID": str(
            assignment_id or source.get("ExperienceAssignmentID") or f"ASN-{uuid.uuid4()}"
        ),
        "EventID": str(source.get("EventID", "")),
        "ProgrammeID": str(source.get("ProgrammeID", "")),
        "ModuleID": str(source.get("ModuleID", "")),
        "ActivityID": str(source.get("ActivityID", "")),
        "ExperienceDefinitionID": str(source.get("ExperienceDefinitionID", "")),
        "DefinitionVersion": _version(source.get("DefinitionVersion", 1)),
        "AssignmentOrder": int(source.get("AssignmentOrder", 1) or 1),
        "Active": bool(source.get("Active", True)),
        "ParticipantTitleOverride": source.get("ParticipantTitleOverride"),
        "NarrativeOverride": source.get("NarrativeOverride"),
        "TaskOverride": source.get("TaskOverride"),
        "CreditsOverride": source.get("CreditsOverride"),
        "EvidenceTypeOverride": source.get("EvidenceTypeOverride"),
        "EvidenceInstructionsOverride": source.get("EvidenceInstructionsOverride"),
        "CharacterIDOverride": source.get("CharacterIDOverride"),
        "AssetIDsOverride": source.get("AssetIDsOverride"),
        "HintOverride": source.get("HintOverride"),
        "AIResponseOverride": source.get("AIResponseOverride"),
        "AvailabilityRule": str(source.get("AvailabilityRule", "ALWAYS")),
        "StartRule": str(source.get("StartRule", "FACILITATOR")),
        "EndRule": str(source.get("EndRule", "FACILITATOR")),
        "UnlockRule": str(source.get("UnlockRule", "NONE")),
        "RuntimeEligible": bool(source.get("RuntimeEligible", True)),
        "AssignmentVersion": _version(source.get("AssignmentVersion", 1)),
    }


def resolve_experience(definition, assignment, *, assets=None, characters=None):
    definition = dict(definition or {})
    assignment = dict(assignment or {})
    if not definition:
        raise ExperienceResolutionError("Assigned Experience Definition is missing.")
    if not assignment:
        raise ExperienceResolutionError("Experience Assignment is missing.")
    if definition.get("ExperienceDefinitionID") != assignment.get("ExperienceDefinitionID"):
        raise ExperienceResolutionError("Assignment points to a different Definition ID.")
    if _version(definition.get("Version")) != _version(assignment.get("DefinitionVersion")):
        raise ExperienceResolutionError("Assigned Definition version is unavailable.")
    if not assignment.get("Active") or not assignment.get("RuntimeEligible"):
        raise ExperienceResolutionError("Inactive Experience Assignment cannot launch.")

    def override(key, default):
        value = assignment.get(key)
        return default if value is None or value == "" else value

    asset_ids = list(override("AssetIDsOverride", definition.get("ReferenceAssetIDs", [])) or [])
    character_id = str(override("CharacterIDOverride", definition.get("DefaultCharacterID", "")) or "")
    asset_catalogue = dict(assets or {})
    character_catalogue = dict(characters or {})
    resolved_assets = [asset_catalogue[item] for item in asset_ids if item in asset_catalogue]
    return {
        "ExperienceAssignmentID": assignment["ExperienceAssignmentID"],
        "ExperienceDefinitionID": definition["ExperienceDefinitionID"],
        "DefinitionVersion": _version(definition["Version"]),
        "AssignmentVersion": _version(assignment["AssignmentVersion"]),
        "EventID": assignment["EventID"],
        "ProgrammeID": assignment["ProgrammeID"],
        "ModuleID": assignment["ModuleID"],
        "ActivityID": assignment["ActivityID"],
        "ParticipantTitle": override("ParticipantTitleOverride", definition.get("ParticipantTitle", "")),
        "ParticipantNarrative": override("NarrativeOverride", definition.get("ParticipantNarrative", "")),
        "ParticipantTask": override("TaskOverride", definition.get("ParticipantTask", "")),
        "IntelligenceCredits": int(override("CreditsOverride", definition.get("DefaultIntelligenceCredits", 0)) or 0),
        "EvidenceType": override("EvidenceTypeOverride", definition.get("DefaultEvidenceType", "NONE")),
        "EvidenceInstructions": override("EvidenceInstructionsOverride", definition.get("DefaultEvidenceInstructions", "")),
        "CharacterID": character_id,
        "Character": character_catalogue.get(character_id),
        "AssetIDs": asset_ids,
        "Assets": resolved_assets,
        "MissingAssetIDs": [item for item in asset_ids if item not in asset_catalogue],
        "Hint": override("HintOverride", definition.get("DefaultHint", "")),
        "AIResponse": override("AIResponseOverride", definition.get("DefaultAIResponse", "")),
        "ExperienceType": definition.get("ExperienceType", "Standard"),
        "Difficulty": definition.get("Difficulty", "Unspecified"),
    }


def filter_definitions(definitions, *, search="", experience_types=None,
                       difficulties=None, venues=None, characters=None,
                       evidence_types=None, statuses=None, tags=None):
    """Apply reusable Event Centre library filters without display-name routing."""
    query = str(search or "").strip().casefold()
    filters = {
        "ExperienceType": set(experience_types or []),
        "Difficulty": set(difficulties or []),
        "DefaultCharacterID": set(characters or []),
        "DefaultEvidenceType": set(evidence_types or []),
        "Status": set(statuses or []),
    }
    wanted_venues, wanted_tags = set(venues or []), set(tags or [])
    rows = []
    for definition in definitions or []:
        if query and query not in str(definition.get("Name", "")).casefold():
            continue
        if any(values and definition.get(field) not in values for field, values in filters.items()):
            continue
        if wanted_venues and not wanted_venues.intersection(definition.get("VenueTags", []) or []):
            continue
        if wanted_tags and not wanted_tags.intersection(definition.get("Tags", []) or []):
            continue
        rows.append(definition)
    return rows


class ExperienceLibraryService:
    """Ownership service; repository writes are configuration, never live runtime."""

    def __init__(self, repository):
        self.repository = repository

    def create_definition(self, values):
        definition = new_definition(values)
        return self.repository.save_definition(definition)

    def edit_definition(self, definition_id, version, changes):
        current = self.repository.get_definition(definition_id, version)
        if not current:
            raise ExperienceResolutionError("Experience Definition was not found.")
        updated = deepcopy(current)
        updated.update(dict(changes or {}))
        if str(current.get("Status", "DRAFT")).upper() == "PUBLISHED":
            updated["Version"] = _version(current.get("Version")) + 1
            updated["Status"] = "DRAFT"
            updated["CreatedAt"] = current.get("CreatedAt")
        updated["UpdatedAt"] = _now()
        return self.repository.save_definition(new_definition(updated, definition_id))

    def duplicate_definition(self, definition_id, version):
        current = self.repository.get_definition(definition_id, version)
        duplicate = new_definition(current or {})
        duplicate["ExperienceDefinitionID"] = f"EXP-{uuid.uuid4()}"
        duplicate["Name"] = f"{duplicate['Name']} (Copy)"
        duplicate["Version"] = 1
        duplicate["Status"] = "DRAFT"
        return self.repository.save_definition(duplicate)

    def publish(self, definition_id, version):
        current = self.repository.get_definition(definition_id, version)
        if not current:
            raise ExperienceResolutionError("Experience Definition was not found.")
        current = deepcopy(current)
        current["Status"] = "PUBLISHED"
        current["UpdatedAt"] = _now()
        return self.repository.save_definition(current)

    def archive(self, definition_id, version):
        current = self.repository.get_definition(definition_id, version)
        if not current:
            raise ExperienceResolutionError("Experience Definition was not found.")
        current = deepcopy(current)
        current["Status"] = "ARCHIVED"
        return self.repository.save_definition(current)

    def assign(self, values):
        assignment = new_assignment(values)
        definition = self.repository.get_definition(
            assignment["ExperienceDefinitionID"], assignment["DefinitionVersion"],
        )
        if not definition:
            raise ExperienceResolutionError("Cannot assign a missing Definition version.")
        return self.repository.save_assignment(assignment)

    def remove_assignment(self, assignment_id):
        return self.repository.remove_assignment(assignment_id)

    def set_assignments_active(self, assignment_ids, active):
        updated = []
        for assignment_id in assignment_ids:
            assignment = self.repository.get_assignment(assignment_id)
            if not assignment:
                continue
            assignment["Active"] = bool(active)
            assignment["AssignmentVersion"] = _version(assignment.get("AssignmentVersion")) + 1
            updated.append(self.repository.save_assignment(assignment))
        return updated

    def reorder_assignments(self, assignment_ids):
        updated = []
        for order, assignment_id in enumerate(assignment_ids, 1):
            assignment = self.repository.get_assignment(assignment_id)
            if not assignment:
                continue
            assignment["AssignmentOrder"] = order
            assignment["AssignmentVersion"] = _version(assignment.get("AssignmentVersion")) + 1
            updated.append(self.repository.save_assignment(assignment))
        return updated

    def resolve(self, assignment_id, *, assets=None, characters=None):
        assignment = self.repository.get_assignment(assignment_id)
        if not assignment:
            raise ExperienceResolutionError("Experience Assignment was not found.")
        definition = self.repository.get_definition(
            assignment["ExperienceDefinitionID"], assignment["DefinitionVersion"],
        )
        return resolve_experience(definition, assignment, assets=assets, characters=characters)
