"""Reusable, pure projections for the EXOS Hunt Engine.

This module owns presentation-safe Hunt vocabulary and configuration validation.
Database RPCs remain the authority for identity, lifecycle, submissions, scoring,
and EventID isolation.  Nothing here derives a participant location or awards
points from GPS data.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


HUNT_MODES = ("WALK", "ROAD")
ROUTE_MODES = ("OPEN_HUNT", "CONFIGURED_ROUTE")
MISSION_TYPES = (
    "CHECKPOINT", "OBSERVATION", "PHOTO", "VIDEO", "AI", "CREATIVE",
    "COLLABORATION", "SECRET",
)
MISSION_STATES = ("AVAILABLE", "IN_PROGRESS", "PENDING_REVIEW", "RETURNED", "COMPLETED")
SCORING_MODES = ("TEAM_FULL", "PARTICIPATION_PRORATED", "FACILITATOR_RUBRIC")
OPERATIONAL_STATES = ("READY", "LIVE", "HOLD", "RETURN_NOW", "CLOSED")
EVIDENCE_TYPES = ("NONE", "PHOTO", "VIDEO", "PHOTO_OR_VIDEO", "TEXT")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any, default: str = "") -> str:
    return _text(value).upper() or default


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _items(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def hunt_configuration(event_or_configuration: dict[str, Any] | None) -> dict[str, Any]:
    """Return one normalised Hunt configuration without event-name heuristics."""
    source = _mapping(event_or_configuration)
    metadata = _mapping(source.get("Metadata") or source.get("event_payload"))
    raw = _mapping(source.get("HuntConfiguration") or metadata.get("HuntConfiguration") or source)
    return {
        "SchemaVersion": _text(raw.get("SchemaVersion")),
        "EngineKind": _upper(raw.get("EngineKind")),
        "HuntMode": _upper(raw.get("HuntMode")),
        "RouteMode": _upper(raw.get("RouteMode"), "OPEN_HUNT"),
        "OperationalState": _upper(raw.get("OperationalState"), "READY"),
        "StartWindowOpensAt": raw.get("StartWindowOpensAt"),
        "StartWindowClosesAt": raw.get("StartWindowClosesAt"),
        "ReturnWindowOpensAt": raw.get("ReturnWindowOpensAt"),
        "ReturnWindowClosesAt": raw.get("ReturnWindowClosesAt"),
    }


def is_hunt_event(event_or_configuration: dict[str, Any] | None) -> bool:
    configuration = hunt_configuration(event_or_configuration)
    return configuration["SchemaVersion"] == "1" and configuration["EngineKind"] == "HUNT"


def is_walk_hunt(event_or_configuration: dict[str, Any] | None) -> bool:
    return is_hunt_event(event_or_configuration) and hunt_configuration(event_or_configuration)["HuntMode"] == "WALK"


def normalise_mission(mission: dict[str, Any] | None) -> dict[str, Any]:
    source = _mapping(mission)
    scoring = _mapping(source.get("Scoring"))
    evidence = _mapping(source.get("Evidence"))
    return {
        "MissionID": _text(source.get("MissionID") or source.get("mission_id")),
        "ActivityID": _text(source.get("ActivityID") or source.get("activity_id")),
        "Name": _text(source.get("Name") or source.get("DisplayName") or source.get("mission_name")),
        "MissionType": _upper(source.get("MissionType") or source.get("mission_type")),
        "CheckpointID": _text(source.get("CheckpointID") or source.get("checkpoint_id")),
        "MissionState": _upper(source.get("MissionState") or source.get("mission_state"), "AVAILABLE"),
        "EvidenceType": _upper(evidence.get("Type") or source.get("EvidenceType") or source.get("evidence_type"), "NONE"),
        "MaximumScore": float(scoring.get("Maximum", source.get("MaximumScore", source.get("maximum_score", 0))) or 0),
        "ScoringMode": _upper(scoring.get("Mode") or source.get("ScoringMode") or source.get("scoring_mode"), "TEAM_FULL"),
        "Instructions": _text(source.get("Instructions") or source.get("ParticipantInstruction") or source.get("instructions")),
        "Secret": bool(source.get("Secret") or source.get("is_secret")),
        "Rubric": _items(scoring.get("Rubric") or source.get("Rubric") or source.get("rubric")),
    }


def normalise_checkpoint(checkpoint: dict[str, Any] | None) -> dict[str, Any]:
    source = _mapping(checkpoint)
    return {
        "CheckpointID": _text(source.get("CheckpointID") or source.get("checkpoint_id")),
        "Name": _text(source.get("Name") or source.get("CheckpointName") or source.get("checkpoint_name")),
        "Latitude": source.get("Latitude", source.get("latitude")),
        "Longitude": source.get("Longitude", source.get("longitude")),
        "RadiusMeters": source.get("RadiusMeters", source.get("radius_meters")),
        "Sequence": source.get("Sequence", source.get("sequence_number")),
        "Active": bool(source.get("Active", source.get("is_active", True))),
        "MissionIDs": [str(value) for value in _items(source.get("MissionIDs") or source.get("mission_ids"))],
        "UATOnly": bool(source.get("UATOnly") or source.get("uat_only")),
    }


def configuration_errors(configuration: dict[str, Any] | None, *, checkpoints: Iterable[dict] = (),
                         missions: Iterable[dict] = ()) -> list[str]:
    """Validate client-side fixtures before the server enforces the same contract."""
    config = hunt_configuration(configuration)
    errors: list[str] = []
    if config["SchemaVersion"] != "1" or config["EngineKind"] != "HUNT":
        errors.append("HuntConfiguration must declare SchemaVersion 1 and EngineKind HUNT.")
    if config["HuntMode"] not in HUNT_MODES:
        errors.append("HuntMode must be WALK or ROAD.")
    if config["RouteMode"] not in ROUTE_MODES:
        errors.append("RouteMode must be OPEN_HUNT or CONFIGURED_ROUTE.")
    if config["OperationalState"] not in OPERATIONAL_STATES:
        errors.append("OperationalState is not supported.")
    checkpoint_ids: set[str] = set()
    for checkpoint in checkpoints:
        row = normalise_checkpoint(checkpoint)
        if not row["CheckpointID"] or not row["Name"]:
            errors.append("Every checkpoint needs a stable ID and name.")
            continue
        if row["CheckpointID"] in checkpoint_ids:
            errors.append(f"Checkpoint {row['CheckpointID']} is duplicated.")
        checkpoint_ids.add(row["CheckpointID"])
        try:
            valid_coordinates = -90 <= float(row["Latitude"]) <= 90 and -180 <= float(row["Longitude"]) <= 180
            valid_radius = 10 <= float(row["RadiusMeters"]) <= 10_000
        except (TypeError, ValueError):
            valid_coordinates = valid_radius = False
        if not valid_coordinates or not valid_radius:
            errors.append(f"Checkpoint {row['CheckpointID']} has invalid coordinates or radius.")
    mission_ids: set[str] = set()
    for mission in missions:
        row = normalise_mission(mission)
        if not row["MissionID"] or not row["Name"] or not row["ActivityID"]:
            errors.append("Every Hunt mission needs an ID, ActivityID, and name.")
            continue
        if row["MissionID"] in mission_ids:
            errors.append(f"Mission {row['MissionID']} is duplicated.")
        mission_ids.add(row["MissionID"])
        if row["MissionType"] not in MISSION_TYPES:
            errors.append(f"Mission {row['MissionID']} has an unsupported type.")
        if row["EvidenceType"] not in EVIDENCE_TYPES:
            errors.append(f"Mission {row['MissionID']} has an unsupported evidence type.")
        if row["ScoringMode"] not in SCORING_MODES or row["MaximumScore"] < 0:
            errors.append(f"Mission {row['MissionID']} has invalid scoring.")
        if row["CheckpointID"] and row["CheckpointID"] not in checkpoint_ids:
            errors.append(f"Mission {row['MissionID']} references an unknown checkpoint.")
    return errors


def project_mission_board(missions: Iterable[dict], team_runtime: Iterable[dict]) -> list[dict[str, Any]]:
    """Overlay event-defined mission metadata with one team's canonical state."""
    state_by_mission = {
        _text(row.get("MissionID") or row.get("mission_id")): _upper(
            row.get("MissionState") or row.get("mission_state"), "AVAILABLE"
        )
        for row in team_runtime or [] if isinstance(row, dict)
    }
    board: list[dict[str, Any]] = []
    for source in missions or []:
        mission = normalise_mission(source)
        mission["MissionState"] = state_by_mission.get(mission["MissionID"], mission["MissionState"])
        # Secret missions stay hidden until a canonical runtime read explicitly
        # moves them beyond AVAILABLE; a client never decides to reveal one.
        mission["Visible"] = not mission["Secret"] or mission["MissionState"] != "AVAILABLE"
        board.append(mission)
    return board


def participant_hunt_state(team_formation_phase: str, operational_state: str) -> str:
    """Project a participant-safe lifecycle from already canonical states."""
    phase = _upper(team_formation_phase)
    operation = _upper(operational_state, "READY")
    if operation == "CLOSED":
        return "CLOSED"
    if operation == "RETURN_NOW":
        return "RETURN_NOW"
    if operation == "HOLD":
        return "HOLD"
    if phase in {"REGISTRATION_OPEN", "FORMATION_LOCKED", "CAPTAIN_SELECTION"}:
        return "TEAM_FORMATION"
    return "LIVE" if operation == "LIVE" and phase == "ACTIVE" else "READY"
