"""Build idempotent Google Sheets requests for the approved Bayu Beach pack.

The script emits request JSON only. Authentication and the actual write remain
outside the repository so production credentials are never stored in source.
"""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "content_packs" / "bayu_beach_labyrinth_v1.json"
SHEET_ID = 1197814927

HEADERS = [
    "EventID", "MissionID", "Title", "Description", "Points", "Status",
    "SubmissionType", "Clue", "Answer", "Hint1", "Hint2", "Hint3",
    "AIHelpEnabled", "TemplateID", "Story", "ParticipantInstructions",
    "FacilitatorInstructions", "LearningObjectives", "ScoringRule",
    "VideoURL", "ImageURL", "DocumentURL", "DebriefQuestions", "Version",
    "UpdatedAt", "Module", "Category", "IsMandatory", "DisplayOrder",
    "MainQuestion", "AlternativeAnswers", "FacilitatorEvaluationNotes",
    "AIRequired", "AIPrompt", "AIRole", "AIHintPrompt", "MaxAIHints",
    "AIUsageRules", "HintUnlockRules", "HintCreditPenalty",
    "CheckpointName", "LocationDescription", "Latitude", "Longitude",
    "GeofenceRadius", "GPSRequired", "QRRequired", "QRCodeValue",
    "QRValidationRule", "EvidenceRequired", "EvidenceInstructions",
    "MaximumUploads", "CreditValue", "MaximumCredits", "TimeBonus",
    "HintPenalty", "WrongAnswerPenalty", "ManualReviewRequired",
    "AutoApprovalAllowed", "TimeLimitMinutes", "AvailabilityStart",
    "AvailabilityEnd", "CountdownEnabled", "ReferenceImageURL",
    "LearningPoint", "FacilitatorDebriefNotes", "NarrativeTitle",
    "MissionContext", "Transmission", "MissionType", "Interaction",
    "ReasoningPrompt", "Difficulty", "EstimatedTimeMinutes",
    "MissionCompleteMessage", "AIRestrictions", "FacilitatorIntent",
    "LearningIntent", "SafetyNotes", "CropFramingNote",
    "CharacterSource", "CharacterPortraitURL",
]


def cell(value):
    if isinstance(value, bool):
        return {"userEnteredValue": {"boolValue": value}}
    if isinstance(value, (int, float)):
        return {"userEnteredValue": {"numberValue": value}}
    return {"userEnteredValue": {"stringValue": str(value or "")}}


def character_portrait_reference(character):
    slug = {
        "EVA": "eva",
        "Headquarters": "headquarters",
        "Captain Amelia Ross": "captain-amelia-ross",
        "Dr Marcus Hale": "dr-marcus-hale",
        "Unknown Transmission": "unknown-transmission",
    }[character]
    return f"supabase://exos-mission-media/characters/{slug}/portrait"


def row_values(experience, display_order):
    mission_type = experience["type"]
    values = {header: "" for header in HEADERS}
    values.update({
        "EventID": "EVT-0004",
        "MissionID": experience["mission_id"],
        "Title": experience["title"],
        "Description": experience["task"],
        "Points": experience["credits"],
        "Status": "DRAFT",
        "SubmissionType": experience["submission_type"],
        "Clue": experience["crop_note"],
        "AIHelpEnabled": "Yes",
        "TemplateID": f"BAYU-LAB-{experience['source_id']}",
        "Story": experience["story"],
        "ParticipantInstructions": experience["task"],
        "Version": "1.0",
        "Module": "Operation: The Labyrinth",
        "Category": experience["source_id"],
        "IsMandatory": "No",
        "DisplayOrder": display_order,
        "MainQuestion": experience["task"],
        "AIRequired": "Yes",
        "AIRole": experience["character"],
        "MaxAIHints": 0,
        "EvidenceRequired": experience["evidence"],
        "EvidenceInstructions": experience["evidence"],
        "MaximumUploads": 2 if experience["submission_type"] == "MULTIPLE" else 1,
        "CreditValue": experience["credits"],
        "MaximumCredits": experience["credits"],
        "ManualReviewRequired": "Yes",
        "AutoApprovalAllowed": "No",
        "TimeLimitMinutes": experience["estimated_time"],
        "CountdownEnabled": "Yes",
        "ReferenceImageURL": experience["reference_image"],
        "NarrativeTitle": experience["title"],
        "MissionContext": experience["story"],
        "Transmission": experience["transmission"],
        "MissionType": mission_type,
        "Interaction": experience["task"] if mission_type == "Interact" else "",
        "ReasoningPrompt": experience["task"] if mission_type == "Think" else "",
        "Difficulty": experience["difficulty"],
        "EstimatedTimeMinutes": experience["estimated_time"],
        "MissionCompleteMessage": experience["ai_response"],
        "AIRestrictions": (
            "Verify only the submitted evidence for this Experience. "
            "Do not reveal future Experiences or alter the approved task."
        ),
        "SafetyNotes": (
            "Use public routes and approved observation points. Do not touch "
            "venue objects, block circulation, climb, or enter the sea or pool."
        ),
        "CropFramingNote": experience["crop_note"],
        "CharacterSource": experience["character"],
        "CharacterPortraitURL": character_portrait_reference(
            experience["character"]
        ),
    })
    return [cell(values[header]) for header in HEADERS]


def build_requests():
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    experiences = pack["experiences"]
    requests = [
        {
            "appendCells": {
                "sheetId": SHEET_ID,
                "rows": [
                    {"values": row_values(experience, index)}
                    for index, experience in enumerate(experiences, start=1)
                ],
                "fields": "userEnteredValue",
            }
        },
    ]
    return requests


if __name__ == "__main__":
    json.dump(build_requests(), sys.stdout, ensure_ascii=False)
