#!/usr/bin/env python3
"""Read-only Gate 5 audit and proposed Definition/Assignment mapping."""

import hashlib
import json

from data.google_sheets import get_sheet_records


AUTHORED_FIELDS = (
    "Title", "ParticipantInstructions", "Story", "MissionType", "Difficulty",
    "CreditValue", "SubmissionType", "EvidenceInstructions", "CharacterSource",
    "ReferenceImageURL", "Hint1", "AIResponse",
)


def fingerprint(row):
    payload = {key: str(row.get(key, "")).strip() for key in AUTHORED_FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def run_audit():
    templates = get_sheet_records("MissionTemplates")
    missions = get_sheet_records("Missions")
    definitions = {}
    for template in templates:
        definition_id = str(template.get("TemplateID", "")).strip() or f"LEGACY-DEF-{fingerprint(template)[:12]}"
        definitions[(definition_id, str(template.get("Version", "1") or "1"))] = template
    mappings = []
    seen_fingerprints = {}
    for mission in missions:
        event_id = str(mission.get("EventID", "")).strip()
        mission_id = str(mission.get("MissionID", "")).strip()
        template_id = str(mission.get("TemplateID", "")).strip()
        digest = fingerprint(mission)
        if not event_id or not mission_id:
            classification = "Orphaned or invalid record"
        elif str(mission.get("Status", "")).upper() in {"CLOSED", "ARCHIVED"}:
            classification = "Historical completed Experience"
        elif template_id and any(key[0] == template_id for key in definitions):
            classification = "Event-specific assignment candidate"
        elif digest in seen_fingerprints:
            classification = "Duplicate generated Experience"
        elif template_id:
            classification = "Orphaned or invalid record"
        else:
            classification = "True event-specific Experience requiring overrides"
        definition_id = template_id or f"LEGACY-DEF-{digest[:12]}"
        mappings.append({
            "Classification": classification,
            "LegacyEventID": event_id,
            "LegacyMissionID": mission_id,
            "ProposedExperienceDefinitionID": definition_id,
            "ProposedDefinitionVersion": str(mission.get("Version", "1") or "1"),
            "ProposedExperienceAssignmentID": f"ASN-{event_id}-{mission_id}",
            "ProposedAssignmentOrder": mission.get("DisplayOrder", ""),
            "AutomaticMigration": False,
            "ManualReviewRequired": classification != "Event-specific assignment candidate",
        })
        seen_fingerprints[digest] = (event_id, mission_id)
    return {
        "Mode": "SELECT_ONLY", "TemplatesInspected": len(templates),
        "EventExperiencesInspected": len(missions),
        "ProposedDefinitionCount": len({row["ProposedExperienceDefinitionID"] for row in mappings}),
        "ProposedAssignmentCount": len(mappings), "Mappings": mappings,
        "ProductionRecordsChanged": False,
    }


if __name__ == "__main__":
    print(json.dumps(run_audit(), indent=2, sort_keys=True, default=str))
