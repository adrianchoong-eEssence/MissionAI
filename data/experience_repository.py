"""Supabase configuration repository for Experience Definitions/Assignments."""

from data.runtime_database import RuntimeDatabaseError


DEFINITION_COLUMN_MAP = {
    "ExperienceDefinitionID": "experience_definition_id", "Version": "version",
    "Name": "name", "InternalDescription": "internal_description",
    "ParticipantTitle": "participant_title", "ParticipantNarrative": "participant_narrative",
    "ParticipantTask": "participant_task", "ExperienceType": "experience_type",
    "Difficulty": "difficulty", "DefaultIntelligenceCredits": "default_intelligence_credits",
    "DefaultEvidenceType": "default_evidence_type",
    "DefaultEvidenceInstructions": "default_evidence_instructions",
    "DefaultCharacterID": "default_character_id", "DefaultAIResponse": "default_ai_response",
    "DefaultHint": "default_hint", "ReferenceAssetIDs": "reference_asset_ids", "Tags": "tags",
    "LearningThemes": "learning_themes", "VenueTags": "venue_tags", "Status": "status",
    "CreatedAt": "created_at", "UpdatedAt": "updated_at",
}
ASSIGNMENT_COLUMN_MAP = {
    "ExperienceAssignmentID": "experience_assignment_id", "EventID": "event_id",
    "ProgrammeID": "programme_id", "ModuleID": "module_id", "ActivityID": "activity_id",
    "ExperienceDefinitionID": "experience_definition_id", "DefinitionVersion": "definition_version",
    "AssignmentOrder": "assignment_order", "Active": "active",
    "ParticipantTitleOverride": "participant_title_override", "NarrativeOverride": "narrative_override",
    "TaskOverride": "task_override", "CreditsOverride": "credits_override",
    "EvidenceTypeOverride": "evidence_type_override",
    "EvidenceInstructionsOverride": "evidence_instructions_override",
    "CharacterIDOverride": "character_id_override", "AssetIDsOverride": "asset_ids_override",
    "HintOverride": "hint_override", "AIResponseOverride": "ai_response_override",
    "AvailabilityRule": "availability_rule", "StartRule": "start_rule", "EndRule": "end_rule",
    "UnlockRule": "unlock_rule", "RuntimeEligible": "runtime_eligible",
    "AssignmentVersion": "assignment_version",
    "SubmissionRule": "submission_rule", "AllowsMultipleSubmissions": "allows_multiple_submissions",
}


def _to_db(record, mapping):
    return {column: record.get(field) for field, column in mapping.items() if field in record}


def _from_db(record, mapping):
    return {field: record.get(column) for field, column in mapping.items()}


class SupabaseExperienceRepository:
    """Configuration repository. It cannot open/close live Experiences."""

    def __init__(self, runtime):
        if not runtime.can_publish:
            raise RuntimeDatabaseError("Experience Library requires SUPABASE_SECRET_KEY.")
        self.runtime = runtime

    def definitions(self, include_archived=False):
        query = {"select": "*", "order": "name.asc,version.desc"}
        if not include_archived:
            query["status"] = "neq.ARCHIVED"
        rows = self.runtime._request("GET", "experience_definitions", query=query, admin=True) or []
        return [_from_db(row, DEFINITION_COLUMN_MAP) for row in rows]

    def get_definition(self, definition_id, version):
        rows = self.runtime._request("GET", "experience_definitions", query={
            "experience_definition_id": f"eq.{definition_id}",
            "version": f"eq.{int(version)}", "select": "*", "limit": 1,
        }, admin=True) or []
        return _from_db(rows[0], DEFINITION_COLUMN_MAP) if rows else None

    def save_definition(self, definition):
        rows = self.runtime._request(
            "POST", "experience_definitions", payload=_to_db(definition, DEFINITION_COLUMN_MAP),
            query={"on_conflict": "experience_definition_id,version"}, admin=True,
            retries=1,
        ) or []
        return _from_db(rows[0], DEFINITION_COLUMN_MAP) if rows else definition

    def assignments(self, event_id, activity_id=""):
        query = {"event_id": f"eq.{event_id}", "select": "*", "order": "assignment_order.asc"}
        if activity_id:
            query["activity_id"] = f"eq.{activity_id}"
        rows = self.runtime._request("GET", "event_experience_assignments", query=query, admin=True) or []
        return [_from_db(row, ASSIGNMENT_COLUMN_MAP) for row in rows]

    def get_assignment(self, assignment_id):
        rows = self.runtime._request("GET", "event_experience_assignments", query={
            "experience_assignment_id": f"eq.{assignment_id}", "select": "*", "limit": 1,
        }, admin=True) or []
        return _from_db(rows[0], ASSIGNMENT_COLUMN_MAP) if rows else None

    def save_assignment(self, assignment):
        rows = self.runtime._request(
            "POST", "event_experience_assignments",
            payload=_to_db(assignment, ASSIGNMENT_COLUMN_MAP),
            query={"on_conflict": "experience_assignment_id"}, admin=True, retries=1,
        ) or []
        return _from_db(rows[0], ASSIGNMENT_COLUMN_MAP) if rows else assignment

    def remove_assignment(self, assignment_id):
        self.runtime._request("DELETE", "event_experience_assignments", query={
            "experience_assignment_id": f"eq.{assignment_id}",
        }, admin=True, retries=1)
        return {"ExperienceAssignmentID": assignment_id, "Removed": True, "DefinitionDeleted": False}
