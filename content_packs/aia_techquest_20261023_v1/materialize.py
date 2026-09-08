"""Materialise AIA's local configuration without network or database writes."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

PACKAGE_PATH = Path(__file__).with_name("aia_techquest_20261023_v1.json")
EVENT_ID_TOKEN = "{{EVENT_ID}}"


def load_aia_techquest_package() -> dict[str, Any]:
    return json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))


def certification_teams(event_id: str, team_count: int = 25, capacity: int = 10) -> list[dict[str, Any]]:
    if team_count < 1 or capacity < 1:
        raise ValueError("Team count and capacity must be positive.")
    return [{"TeamID": f"{event_id}-TEAM-{number:02d}", "TeamName": f"Quest {number:02d}",
             "TeamIdentity": f"Quest {number:02d}", "Capacity": capacity}
            for number in range(1, team_count + 1)]


def materialize_aia_techquest_content(event_id: str, *, team_count: int = 25, capacity: int = 10) -> dict[str, Any]:
    clean_event_id = str(event_id or "").strip().upper()
    if not clean_event_id or EVENT_ID_TOKEN in clean_event_id:
        raise ValueError("A concrete EventID is required.")
    package = deepcopy(load_aia_techquest_package())
    package["EventBlueprint"]["EventID"] = clean_event_id
    teams = certification_teams(clean_event_id, team_count, capacity)
    mission_rows = []
    operations = {}
    for order, blueprint in enumerate(package["MissionBlueprints"], 1):
        activity_id = f"{clean_event_id}-{blueprint['Code']}"
        secret_state = blueprint.get("SecretState", "RELEASED")
        operations[activity_id] = {"OperationalStatus": "AVAILABLE", "SecretState": secret_state}
        evidence_type = blueprint["EvidenceType"]
        scoring = {"Mode": blueprint.get("ScoringMode", "TEAM_FULL"), "Maximum": blueprint["Maximum"], "Rounding": "HALF_UP"}
        if blueprint.get("Rubric"):
            scoring["Rubric"] = {"Criteria": [
                {"ID": "creativity", "Label": "Creativity", "Weight": 1},
                {"ID": "collaboration", "Label": "Collaboration", "Weight": 1},
                {"ID": "clarity", "Label": "Clarity", "Weight": 1},
            ]}
        mission_rows.append({
            "ActivityID": activity_id, "DisplayOrder": order, "DisplayName": blueprint["DisplayName"],
            "MissionClass": blueprint["MissionClass"], "Category": blueprint["Category"],
            "EvidenceType": evidence_type, "ParticipationProrated": bool(blueprint.get("ParticipationProrated")),
            "ScoringMode": blueprint.get("ScoringMode", "TEAM_FULL"), "Rubric": bool(blueprint.get("Rubric")),
            "Scoring": scoring,
            "Evidence": {
                "Text": {"Required": False, "Label": "Team response"},
                "Photo": {"Required": evidence_type in {"PHOTO", "PHOTO_OR_VIDEO"}, "Label": "Private team photo"},
                "Video": {"Required": evidence_type in {"VIDEO", "PHOTO_OR_VIDEO"}, "Label": "Private short video", "MaximumBytes": 52428800},
                "NumericResult": {"Required": False, "Label": "Result"},
            },
            "RideParticipation": {"RequiredPercent": 80, "Rounding": "CEILING", "EvidencePathways": ["GROUND_CONTROL", "FULL_TEAM", "FACILITATOR_VERIFIED"], "FullParticipationBonus": 0} if blueprint["MissionClass"] == "RIDE" else {},
            "ContentStatus": blueprint["Status"],
        })
    race = package["EventBlueprint"]["RaceConfiguration"]
    race["MissionBoard"]["MissionOperations"] = operations
    capacities = {team["TeamID"]: team["Capacity"] for team in teams}
    return {"Package": package, "EventBlueprint": package["EventBlueprint"], "TeamTemplates": teams,
            "TeamCapacities": capacities, "RaceConfiguration": race, "Missions": mission_rows}
