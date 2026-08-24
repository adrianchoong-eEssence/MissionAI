"""Configuration and canonical projections for configuration-led Theme Park Races.

This module deliberately has no Genting programme names, station content, team
count, or Formula R.A.C.E. dependencies.  An event opts in only when its
``RaceConfiguration.EngineKind`` is exactly ``THEME_PARK_RACE``.  Routes and
runtime facts are derived from the existing event, team, programme/activity,
participant, submission, review and score records.
"""
from __future__ import annotations

from copy import deepcopy
from math import ceil
from typing import Any


ENGINE_KIND = "THEME_PARK_RACE"
SCHEMA_VERSION = 1
ROUTE_STRATEGY = "CONFIGURED_TEAM_ROUTE"
OPEN_MISSION_BOARD = "OPEN_MISSION_BOARD"
STRATEGY_MODES = (ROUTE_STRATEGY, OPEN_MISSION_BOARD)
RUNTIME_PHASES = ("READY", "ACTIVE", "CLOSED")
PARTICIPANT_LIFECYCLE_STATES = (
    "REGISTRATION",
    "TEAM_FORMATION",
    "FORMATION_LOCKED",
    "CAPTAIN_SELECTION",
    "READY",
    "ACTIVE",
)
EVIDENCE_KINDS = ("TEXT", "PHOTO", "NUMERIC_RESULT")
MISSION_CLASSES = ("STANDARD", "RIDE", "BONUS", "SECRET")
MISSION_STATES = (
    "LOCKED", "AVAILABLE", "SELECTED", "SUBMITTED", "APPROVED", "REJECTED",
    "TEMPORARILY_UNAVAILABLE", "CLOSED",
)
RIDE_ATTEMPT_STATES = ("ATTEMPTED", "COMPLETED", "ABORTED_BY_ATTRACTION", "TEAM_WITHDREW")
RIDE_EVIDENCE_PATHWAYS = ("GROUND_CONTROL", "FULL_TEAM", "FACILITATOR_VERIFIED")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return _text(value).casefold() in {"1", "true", "yes", "on"}


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _upper(value: Any, default: str = "") -> str:
    return _text(value).upper() or default


def strategy_mode(event_or_configuration: dict[str, Any] | None) -> str:
    """Return the generic race strategy, preserving V1 route configurations."""
    raw = race_configuration(event_or_configuration)
    mode = _upper(raw.get("StrategyMode") or raw.get("RouteStrategy"), ROUTE_STRATEGY)
    return mode if mode in STRATEGY_MODES else ROUTE_STRATEGY


def required_ride_participants(team_member_count: int | float | str | None, percent: int | float | str | None = 80) -> int:
    """Ceiling participation threshold over current canonical team membership."""
    members = max(int(_number(team_member_count) or 0), 0)
    percentage = _number(percent)
    if percentage is None:
        percentage = 80
    return int(ceil(members * max(percentage, 0) / 100))


def ride_competitive_score(reviewed_score: int | float | str | None, *, rider_count: int | float | str | None,
                           canonical_team_member_count: int | float | str | None) -> float:
    """Return a reviewed ride score without a 100%-participation multiplier."""
    del rider_count, canonical_team_member_count
    return float(_number(reviewed_score) or 0)


def race_configuration(event_or_configuration: dict[str, Any] | None) -> dict[str, Any]:
    """Return an event's RaceConfiguration without inferring from its name."""
    source = _dict(event_or_configuration)
    if "EngineKind" in source:
        return source
    payload = _dict(source.get("_EventPayload", source.get("EventPayload", source)))
    return _dict(payload.get("RaceConfiguration"))


def is_theme_park_race(event_or_configuration: dict[str, Any] | None) -> bool:
    """Configuration-only engine selection; programme names are never inspected."""
    return _text(race_configuration(event_or_configuration).get("EngineKind")).upper() == ENGINE_KIND


def normalise_configuration(event_or_configuration: dict[str, Any] | None) -> dict[str, Any]:
    """Normalise the versioned generic engine contract for projections and validation."""
    raw = race_configuration(event_or_configuration)
    routes = {
        _text(team_id): [_text(activity_id) for activity_id in route if _text(activity_id)]
        for team_id, route in _dict(raw.get("TeamRoutes")).items()
        if isinstance(route, (list, tuple)) and _text(team_id)
    }
    projector = _dict(raw.get("Projector"))
    board = _dict(raw.get("MissionBoard"))
    operations = {
        _text(activity_id): {
            "OperationalStatus": _upper(_dict(operation).get("OperationalStatus"), "AVAILABLE"),
            "SecretState": _upper(_dict(operation).get("SecretState"), "RELEASED"),
        }
        for activity_id, operation in _dict(board.get("MissionOperations")).items()
        if _text(activity_id)
    }
    runtime_phase = _text(raw.get("RuntimePhase", "READY")).upper() or "READY"
    mode = strategy_mode(raw)
    return {
        "SchemaVersion": int(_number(raw.get("SchemaVersion")) or 0),
        "EngineKind": _text(raw.get("EngineKind")).upper(),
        "StrategyMode": mode,
        "RouteStrategy": _text(raw.get("RouteStrategy", ROUTE_STRATEGY)).upper() or ROUTE_STRATEGY,
        "TeamRoutes": routes,
        "RuntimePhase": runtime_phase if runtime_phase in RUNTIME_PHASES else "READY",
        "MissionBoard": {
            "MaximumConcurrentSelections": max(int(_number(board.get("MaximumConcurrentSelections")) or 1), 1),
            "MissionOperations": operations,
        },
        "Projector": {
            "DefaultView": _text(projector.get("DefaultView", "TEAM_PROGRESS")).upper() or "TEAM_PROGRESS",
            "ShowOverallScoring": _bool(projector.get("ShowOverallScoring"), True),
        },
    }


def configuration_contract() -> dict[str, Any]:
    """Machine-readable V1 contract used by authoring and contract tests."""
    return {
        "SchemaVersion": SCHEMA_VERSION,
        "EngineKind": ENGINE_KIND,
        "StrategyMode": ROUTE_STRATEGY,
        "RouteStrategy": ROUTE_STRATEGY,
        "RuntimePhase": "READY",
        "TeamRoutes": {"<TeamID>": ["<ActivityID>"]},
        "Projector": {
            "DefaultView": "TEAM_PROGRESS",
            "ShowOverallScoring": True,
        },
        "ActivityRaceStation": {
            "Enabled": True,
            "DisplayOrder": 1,
            "DisplayName": "<Mission title>",
            "ParticipantInstruction": "<Participant-visible instruction>",
            "FacilitatorInstruction": "<Facilitator guidance>",
            "Evidence": {
                "Text": {"Required": False, "Label": "Team response"},
                "Photo": {"Required": False, "Label": "Private team photo"},
                "NumericResult": {
                    "Required": False,
                    "Label": "Result",
                    "Minimum": None,
                    "Maximum": None,
                },
            },
            "ReviewRequired": True,
            "Scoring": {"Enabled": True, "Maximum": None},
        },
        "OpenMissionBoard": {
            "StrategyMode": OPEN_MISSION_BOARD,
            "MissionBoard": {
                "MaximumConcurrentSelections": 1,
                "MissionOperations": {
                    "<ActivityID>": {"OperationalStatus": "AVAILABLE", "SecretState": "RELEASED"},
                },
            },
            "ActivityRaceStation": {
                "MissionClass": "RIDE | BONUS | SECRET | STANDARD",
                "RideParticipation": {
                    "RequiredPercent": 80,
                    "Rounding": "CEILING",
                    "EvidencePathways": list(RIDE_EVIDENCE_PATHWAYS),
                    "FullParticipationBonus": 0,
                },
            },
        },
    }


def _station_payload(activity: dict[str, Any]) -> dict[str, Any]:
    row = _dict(activity)
    payload = _dict(row.get("ActivityPayload", row.get("activity_payload")))
    return _dict(row.get("RaceStation", payload.get("race_station")))


def normalise_station(activity: dict[str, Any], fallback_order: int = 1) -> dict[str, Any]:
    """Project one existing activity's ``race_station`` payload into V1 mission data."""
    activity = _dict(activity)
    raw = _station_payload(activity)
    evidence = _dict(raw.get("Evidence"))
    text = _dict(evidence.get("Text"))
    photo = _dict(evidence.get("Photo"))
    numeric = _dict(evidence.get("NumericResult"))
    scoring = _dict(raw.get("Scoring"))
    ride = _dict(raw.get("RideParticipation"))
    activity_id = _text(activity.get("ActivityID", activity.get("activity_id")))
    return {
        "ActivityID": activity_id,
        "Enabled": _bool(raw.get("Enabled"), True),
        "DisplayOrder": int(_number(raw.get("DisplayOrder", activity.get("ActivityOrder", activity.get("activity_order", fallback_order)))) or fallback_order),
        "DisplayName": _text(raw.get("DisplayName", raw.get("Name", activity.get("ParticipantDisplayName", activity.get("StageName", activity.get("activity_name")))))),
        "Zone": _text(raw.get("Zone")),
        "LocationDescription": _text(raw.get("LocationDescription")),
        "ParticipantInstruction": _text(raw.get("ParticipantInstruction", raw.get("Instructions", activity.get("ParticipantTask", activity.get("ParticipantMessage", ""))))),
        "FacilitatorInstruction": _text(raw.get("FacilitatorInstruction", activity.get("FacilitatorNotes", activity.get("FacilitatorInstruction", "")))),
        "Evidence": {
            "Text": {
                "Required": _bool(text.get("Required"), False),
                "Label": _text(text.get("Label", "Team response")) or "Team response",
            },
            "Photo": {
                "Required": _bool(photo.get("Required"), False),
                "Label": _text(photo.get("Label", "Private team photo")) or "Private team photo",
            },
            "NumericResult": {
                "Required": _bool(numeric.get("Required"), False),
                "Label": _text(numeric.get("Label", "Result")) or "Result",
                "Minimum": _number(numeric.get("Minimum")),
                "Maximum": _number(numeric.get("Maximum")),
            },
        },
        "ReviewRequired": _bool(raw.get("ReviewRequired"), True),
        "Scoring": {
            "Enabled": _bool(scoring.get("Enabled"), True),
            "Maximum": _number(scoring.get("Maximum")),
        },
        "MissionClass": _upper(raw.get("MissionClass"), "STANDARD"),
        "PrivateReferenceImage": deepcopy(_dict(raw.get("PrivateReferenceImage"))),
        "SafetyNote": _text(raw.get("SafetyNote")),
        "CompletionState": deepcopy(_dict(raw.get("CompletionState"))),
        "Resubmission": deepcopy(_dict(raw.get("Resubmission"))),
        "ScoreRules": deepcopy(_dict(raw.get("ScoreRules"))),
        "RideParticipation": {
            "RequiredPercent": _number(ride.get("RequiredPercent")),
            "Rounding": _upper(ride.get("Rounding"), "CEILING"),
            "EvidencePathways": [_upper(item) for item in _list(ride.get("EvidencePathways")) if _upper(item)],
            "FullParticipationBonus": _number(ride.get("FullParticipationBonus")) or 0,
        },
        "RawActivity": deepcopy(activity),
    }


def project_stations(activities: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return only enabled activities explicitly configured as Theme Park missions."""
    stations = []
    for position, activity in enumerate(activities or [], 1):
        if not _station_payload(activity):
            continue
        station = normalise_station(activity, position)
        if station["ActivityID"] and station["Enabled"]:
            stations.append(station)
    return sorted(stations, key=lambda row: (row["DisplayOrder"], row["ActivityID"]))


def validate_configuration(
    event_or_configuration: dict[str, Any] | None,
    team_ids: list[str] | tuple[str, ...],
    stations: list[dict[str, Any]] | None,
) -> list[str]:
    """Validate a Theme Park Race without creating content or mutating runtime state."""
    config = normalise_configuration(event_or_configuration)
    errors: list[str] = []
    if config["SchemaVersion"] != SCHEMA_VERSION:
        errors.append(f"Theme Park Race requires SchemaVersion {SCHEMA_VERSION}.")
    if config["EngineKind"] != ENGINE_KIND:
        errors.append("RaceConfiguration.EngineKind must be THEME_PARK_RACE.")
    if config["StrategyMode"] not in STRATEGY_MODES:
        errors.append("Theme Park Race StrategyMode is invalid.")
    if config["StrategyMode"] == ROUTE_STRATEGY and config["RouteStrategy"] != ROUTE_STRATEGY:
        errors.append("Configured-route Theme Park Race requires CONFIGURED_TEAM_ROUTE.")
    expected_teams = {_text(team_id) for team_id in team_ids if _text(team_id)}
    station_ids = [_text(station.get("ActivityID")) for station in stations or []]
    if not station_ids:
        errors.append("At least one enabled activity race_station is required.")
    if len(station_ids) != len(set(station_ids)):
        errors.append("Enabled Theme Park Race activity IDs must be unique.")
    for station in stations or []:
        label = _text(station.get("DisplayName")) or _text(station.get("ActivityID"))
        if not _text(station.get("DisplayName")):
            errors.append(f"{label}: DisplayName is required.")
        numeric = _dict(_dict(station.get("Evidence")).get("NumericResult"))
        minimum, maximum = _number(numeric.get("Minimum")), _number(numeric.get("Maximum"))
        if minimum is not None and maximum is not None and minimum > maximum:
            errors.append(f"{label}: numeric result minimum exceeds maximum.")
        mission_class = _upper(station.get("MissionClass"), "STANDARD")
        if mission_class not in MISSION_CLASSES:
            errors.append(f"{label}: MissionClass is invalid.")
        if mission_class == "RIDE":
            ride = _dict(station.get("RideParticipation"))
            percent = _number(ride.get("RequiredPercent"))
            if percent is None or percent <= 0 or percent > 100:
                errors.append(f"{label}: ride RequiredPercent must be between 1 and 100.")
            if _upper(ride.get("Rounding"), "CEILING") != "CEILING":
                errors.append(f"{label}: ride participation rounding must be CEILING.")
            pathways = {_upper(value) for value in _list(ride.get("EvidencePathways"))}
            if not pathways or not pathways <= set(RIDE_EVIDENCE_PATHWAYS):
                errors.append(f"{label}: ride evidence pathways are invalid.")
            if float(_number(ride.get("FullParticipationBonus")) or 0) != 0:
                errors.append(f"{label}: full participation must not create a score bonus.")
    if config["StrategyMode"] == ROUTE_STRATEGY:
        routes = config["TeamRoutes"]
        for team_id in sorted(expected_teams):
            route = routes.get(team_id, [])
            if not route:
                errors.append(f"{team_id}: no configured route.")
            elif set(route) != set(station_ids) or len(route) != len(station_ids):
                errors.append(f"{team_id}: route must contain each enabled mission exactly once.")
        for team_id in sorted(set(routes) - expected_teams):
            errors.append(f"{team_id}: route belongs to a team outside this event.")
    else:
        board = config["MissionBoard"]
        if not station_ids:
            errors.append("Open Mission Board requires at least one enabled mission.")
        for activity_id, operation in board["MissionOperations"].items():
            if activity_id not in station_ids:
                errors.append(f"{activity_id}: mission operation belongs to an unavailable activity.")
            if _upper(operation.get("OperationalStatus"), "AVAILABLE") not in {
                "AVAILABLE", "TEMPORARILY_UNAVAILABLE", "CLOSED",
            }:
                errors.append(f"{activity_id}: mission operational status is invalid.")
            if _upper(operation.get("SecretState"), "RELEASED") not in {"LOCKED", "RELEASED"}:
                errors.append(f"{activity_id}: secret mission state is invalid.")
    return errors


def ride_submission_errors(
    station: dict[str, Any],
    payload: dict[str, Any] | None,
    *,
    canonical_team_member_count: int | float | str | None,
) -> list[str]:
    """Validate RIDE evidence shape without trusting browser state.

    The server contract repeats membership and Captain-session checks.  This
    pure helper gives authoring/UI tests the same evidence semantics: an
    exterior photo alone is never queue-entry proof, and 100% participation
    never changes points.
    """
    if _upper(station.get("MissionClass"), "STANDARD") != "RIDE":
        return []
    body = _dict(payload)
    ride = _dict(station.get("RideParticipation"))
    pathway = _upper(body.get("RideEvidencePathway"))
    attempt = _upper(body.get("RideAttemptStatus"))
    errors: list[str] = []
    pathways = {_upper(value) for value in _list(ride.get("EvidencePathways"))}
    if pathway not in pathways:
        errors.append("Ride evidence pathway is not configured for this mission.")
    if attempt not in RIDE_ATTEMPT_STATES:
        errors.append("Ride attempt status is invalid.")
    riders = [_text(value) for value in _list(body.get("RiderParticipantIDs")) if _text(value)]
    if len(riders) != len(set(riders)):
        errors.append("Ride participant identities must be unique.")
    required = required_ride_participants(canonical_team_member_count, ride.get("RequiredPercent"))
    if attempt == "COMPLETED" and len(riders) < required:
        errors.append(f"Ride completion requires at least {required} canonical team riders.")
    queue_evidence = _text(body.get("QueueEntryEvidence") or body.get("QueueEntryEvidenceURL"))
    post_ride_evidence = _text(body.get("PostRideEvidence") or body.get("PostRideEvidenceURL"))
    if attempt == "COMPLETED" and pathway in {"GROUND_CONTROL", "FULL_TEAM"}:
        if not queue_evidence:
            errors.append("Official queue-entry evidence is required; an attraction exterior photo is insufficient.")
        if not post_ride_evidence:
            errors.append("Configured post-ride verification evidence is required.")
    if attempt == "COMPLETED" and pathway == "FULL_TEAM":
        members = max(int(_number(canonical_team_member_count) or 0), 0)
        if len(riders) != members:
            errors.append("FULL_TEAM evidence requires every current canonical team member to ride.")
    if attempt == "COMPLETED" and pathway == "FACILITATOR_VERIFIED" and not _text(body.get("FacilitatorVerificationRequest")):
        errors.append("FACILITATOR_VERIFIED evidence requires a facilitator verification request.")
    return errors


def _runtime_payload(row: dict[str, Any]) -> dict[str, Any]:
    return _dict(_dict(row).get("StatePayload", _dict(row).get("state_payload")))


def _runtime_for_team(mission_runtime: list[dict[str, Any]] | None, team_id: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in mission_runtime or []:
        item = _dict(row)
        if _text(item.get("TeamID", item.get("team_id"))) != _text(team_id):
            continue
        activity_id = _text(item.get("ActivityID", item.get("activity_id")))
        if not activity_id:
            continue
        previous = rows.get(activity_id)
        if previous is None or _text(item.get("UpdatedAt", item.get("updated_at"))) >= _text(previous.get("UpdatedAt", previous.get("updated_at"))):
            rows[activity_id] = item
    return rows


def mission_board(
    configuration: dict[str, Any] | None,
    stations: list[dict[str, Any]] | None,
    *,
    team_id: str,
    submissions: list[dict[str, Any]] | None,
    mission_runtime: list[dict[str, Any]] | None = None,
    canonical_team_member_count: int | float | str | None = 0,
) -> list[dict[str, Any]]:
    """Project a team's canonical OPEN_MISSION_BOARD without competitor data."""
    config = normalise_configuration(configuration)
    operations = config["MissionBoard"]["MissionOperations"]
    owned_submissions = {
        _text(row.get("ActivityID", row.get("activity_id"))): _dict(row)
        for row in submissions or []
        if _text(_dict(row).get("TeamID", _dict(row).get("team_id"))) == _text(team_id)
    }
    runtime = _runtime_for_team(mission_runtime, team_id)
    board: list[dict[str, Any]] = []
    for station in stations or []:
        activity_id = _text(station.get("ActivityID"))
        operation = _dict(operations.get(activity_id))
        mission_class = _upper(station.get("MissionClass"), "STANDARD")
        secret_locked = mission_class == "SECRET" and _upper(operation.get("SecretState"), "RELEASED") != "RELEASED"
        operational = _upper(operation.get("OperationalStatus"), "AVAILABLE")
        submission = owned_submissions.get(activity_id, {})
        submitted_status = submission_status(submission) if submission else ""
        runtime_payload = _runtime_payload(runtime.get(activity_id, {}))
        runtime_state = _upper(runtime_payload.get("MissionState"))
        if submitted_status in {"APPROVED", "SUBMITTED", "REJECTED"}:
            state = submitted_status
        elif operational == "CLOSED":
            state = "CLOSED"
        elif operational == "TEMPORARILY_UNAVAILABLE":
            state = "TEMPORARILY_UNAVAILABLE"
        elif secret_locked:
            state = "LOCKED"
        elif runtime_state == "SELECTED":
            state = "SELECTED"
        else:
            state = "AVAILABLE"
        visible = not secret_locked
        ride = _dict(station.get("RideParticipation"))
        required = required_ride_participants(canonical_team_member_count, ride.get("RequiredPercent")) if mission_class == "RIDE" else 0
        board.append({
            **deepcopy(station),
            "MissionClass": mission_class,
            "OperationalStatus": operational,
            "MissionState": state,
            "Visible": visible,
            "CanSelect": state == "AVAILABLE",
            "CanSubmit": state in {"SELECTED", "REJECTED"},
            "RideRequiredParticipantCount": required,
            "RideAttemptStatus": _upper(runtime_payload.get("RideAttemptStatus")),
        })
    return [row for row in sorted(board, key=lambda item: (item["DisplayOrder"], item["ActivityID"])) if row["Visible"]]


def submission_status(row: dict[str, Any]) -> str:
    return _text(_dict(row).get("Status", _dict(row).get("status", "SUBMITTED"))).upper() or "SUBMITTED"


def current_route_mission(route: list[str] | tuple[str, ...], submissions: list[dict[str, Any]] | None) -> tuple[str, str]:
    """Find the canonical current/next mission from persisted submissions.

    A rejected mission becomes current again for revision; a submitted mission
    advances the route immediately, while review remains its own workflow.
    """
    completed = {
        _text(row.get("ActivityID", row.get("activity_id", row.get("MissionID", ""))))
        for row in submissions or []
        if submission_status(row) not in {"REJECTED", "WITHDRAWN"}
    }
    clean_route = [_text(activity_id) for activity_id in route or [] if _text(activity_id)]
    for index, activity_id in enumerate(clean_route):
        if activity_id not in completed:
            return activity_id, (clean_route[index + 1] if index + 1 < len(clean_route) else "")
    return "", ""


def participant_lifecycle(team_formation: dict[str, Any] | None, configuration: dict[str, Any] | None, *, registered: bool = True) -> str:
    """Map canonical Team Formation and engine runtime state to participant UI state."""
    if not registered:
        return "REGISTRATION"
    formation = _dict(team_formation)
    phase = _text(formation.get("Phase")).upper()
    if phase in {"DRAFT", "REGISTRATION_OPEN"}:
        return "TEAM_FORMATION"
    if phase == "FORMATION_LOCKED":
        return "FORMATION_LOCKED"
    if phase == "CAPTAIN_SELECTION":
        return "CAPTAIN_SELECTION"
    config = normalise_configuration(configuration)
    if phase == "ACTIVE" and config["RuntimePhase"] == "ACTIVE":
        return "ACTIVE"
    return "READY"


def team_progress(
    team_id: str,
    route: list[str] | tuple[str, ...],
    submissions: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Event-scoped team progress projection from canonical submission rows."""
    owned = [
        dict(row) for row in submissions or []
        if _text(row.get("TeamID", row.get("team_id"))) == _text(team_id)
    ]
    by_activity = {
        _text(row.get("ActivityID", row.get("activity_id", row.get("MissionID", "")))): row
        for row in owned
    }
    current, following = current_route_mission(list(route or []), owned)
    statuses = [submission_status(row) for row in owned]
    completed = sum(
        1 for activity_id in route or []
        if activity_id in by_activity and submission_status(by_activity[activity_id]) not in {"REJECTED", "WITHDRAWN"}
    )
    return {
        "TeamID": _text(team_id),
        "Route": [_text(item) for item in route or [] if _text(item)],
        "CurrentActivityID": current,
        "NextActivityID": following,
        "Completed": completed,
        "Total": len([item for item in route or [] if _text(item)]),
        "PendingReview": sum(status == "SUBMITTED" for status in statuses),
        "Approved": sum(status == "APPROVED" for status in statuses),
        "Rejected": sum(status == "REJECTED" for status in statuses),
        "SubmissionsByActivity": by_activity,
    }


def participant_projection(
    *,
    event: dict[str, Any],
    participant: dict[str, Any],
    stations: list[dict[str, Any]],
    submissions: list[dict[str, Any]],
    mission_runtime: list[dict[str, Any]] | None = None,
    team_members: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Canonical participant/Captain projection, rebuilt after every reconnect."""
    config = normalise_configuration(event)
    metadata = _dict(_dict(event).get("_EventPayload", _dict(event).get("EventPayload", {})))
    formation = _dict(metadata.get("TeamFormation"))
    team_id = _text(participant.get("TeamID", participant.get("team_id")))
    route = list(config["TeamRoutes"].get(team_id, []))
    board = mission_board(
        config, stations, team_id=team_id, submissions=submissions,
        mission_runtime=mission_runtime, canonical_team_member_count=len(team_members or []),
    ) if config["StrategyMode"] == OPEN_MISSION_BOARD else []
    progress = team_progress(team_id, route, submissions) if config["StrategyMode"] == ROUTE_STRATEGY else {
        "TeamID": team_id,
        "Route": [],
        "CurrentActivityID": "",
        "NextActivityID": "",
        "Completed": sum(row["MissionState"] == "APPROVED" for row in board),
        "Total": len(board),
        "PendingReview": sum(row["MissionState"] == "SUBMITTED" for row in board),
        "Approved": sum(row["MissionState"] == "APPROVED" for row in board),
        "Rejected": sum(row["MissionState"] == "REJECTED" for row in board),
        "SubmissionsByActivity": {
            _text(row.get("ActivityID", row.get("activity_id"))): dict(row)
            for row in submissions or []
            if _text(_dict(row).get("TeamID", _dict(row).get("team_id"))) == team_id
        },
    }
    station_map = {_text(station.get("ActivityID")): station for station in stations or []}
    current = station_map.get(progress["CurrentActivityID"])
    following = station_map.get(progress["NextActivityID"])
    lifecycle = participant_lifecycle(formation, config, registered=bool(participant))
    return {
        "EngineKind": ENGINE_KIND,
        "EventID": _text(event.get("EventID", event.get("event_id"))),
        "ParticipantID": _text(participant.get("ParticipantID", participant.get("participant_id"))),
        "TeamID": team_id,
        "Lifecycle": lifecycle,
        "TeamFormationPhase": _text(formation.get("Phase")),
        "RuntimePhase": config["RuntimePhase"],
        "StrategyMode": config["StrategyMode"],
        "IsCaptain": _bool(participant.get("IsTeamFormationCaptain", participant.get("is_team_formation_captain"))),
        "CaptainSessionActive": _bool(participant.get("CaptainSessionActive")),
        "CaptainParticipantID": _text(participant.get("CaptainParticipantID")),
        "Route": route,
        "CurrentMission": deepcopy(current) if current else None,
        "NextMission": deepcopy(following) if following else None,
        "MissionBoard": board,
        "TeamMembers": [
            {"ParticipantID": _text(row.get("ParticipantID", row.get("participant_id"))),
             "Name": _text(row.get("Name", row.get("display_name")))}
            for row in team_members or []
        ],
        "Progress": progress,
    }


def facilitator_projection(
    *,
    event: dict[str, Any],
    teams: list[dict[str, Any]],
    participants: list[dict[str, Any]],
    stations: list[dict[str, Any]],
    submissions: list[dict[str, Any]],
    leaderboard: list[dict[str, Any]] | None = None,
    mission_runtime: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Facilitator projection for lifecycle, Captain, review and team status."""
    config = normalise_configuration(event)
    metadata = _dict(_dict(event).get("_EventPayload", _dict(event).get("EventPayload", {})))
    formation = _dict(metadata.get("TeamFormation"))
    team_rows = []
    for team in teams or []:
        team_id = _text(team.get("TeamID", team.get("team_id")))
        members = [row for row in participants or [] if _text(row.get("TeamID", row.get("team_id"))) == team_id]
        captain = next((row for row in members if _bool(row.get("IsTeamFormationCaptain", row.get("is_team_formation_captain")))), None)
        board = mission_board(
            config, stations, team_id=team_id, submissions=submissions,
            mission_runtime=mission_runtime, canonical_team_member_count=len(members),
        ) if config["StrategyMode"] == OPEN_MISSION_BOARD else []
        progress = team_progress(team_id, config["TeamRoutes"].get(team_id, []), submissions) if config["StrategyMode"] == ROUTE_STRATEGY else {
            "TeamID": team_id,
            "Route": [], "CurrentActivityID": "", "NextActivityID": "",
            "Completed": sum(item["MissionState"] == "APPROVED" for item in board),
            "Total": len(board),
            "PendingReview": sum(item["MissionState"] == "SUBMITTED" for item in board),
            "Approved": sum(item["MissionState"] == "APPROVED" for item in board),
            "Rejected": sum(item["MissionState"] == "REJECTED" for item in board),
            "SubmissionsByActivity": {},
        }
        team_rows.append({
            "TeamID": team_id,
            "TeamIdentity": _text(team.get("TeamIdentity", team.get("TeamName", team_id))),
            "RegisteredParticipants": len(members),
            "CaptainParticipantID": _text((captain or {}).get("ParticipantID", (captain or {}).get("participant_id"))),
            "CaptainName": _text((captain or {}).get("Name", (captain or {}).get("display_name"))),
            "CaptainSelected": bool(captain),
            "SelectedMissionActivityIDs": [item["ActivityID"] for item in board if item["MissionState"] == "SELECTED"],
            "MissionBoard": board,
            **progress,
        })
    team_rows.sort(key=lambda row: row["TeamID"])
    station_by_id = {_text(row.get("ActivityID")): row for row in stations or []}
    review_queue = [
        dict(row) for row in submissions or []
        if submission_status(row) == "SUBMITTED"
        and _bool(station_by_id.get(_text(row.get("ActivityID", row.get("activity_id"))), {}).get("ReviewRequired"), True)
    ]
    return {
        "EngineKind": ENGINE_KIND,
        "Lifecycle": participant_lifecycle(formation, config, registered=True),
        "TeamFormationPhase": _text(formation.get("Phase")),
        "RuntimePhase": config["RuntimePhase"],
        "StrategyMode": config["StrategyMode"],
        "RegistrationCount": len(participants or []),
        "TeamCount": len(teams or []),
        "CaptainCount": sum(row["CaptainSelected"] for row in team_rows),
        "MissionCount": len(stations or []),
        "PendingReviewCount": len(review_queue),
        "Teams": team_rows,
        "ReviewQueue": review_queue,
        "MissionOperations": [
            {
                "ActivityID": station.get("ActivityID"),
                "DisplayName": station.get("DisplayName"),
                "MissionClass": station.get("MissionClass", "STANDARD"),
                "OperationalStatus": _dict(config["MissionBoard"]["MissionOperations"].get(_text(station.get("ActivityID")))).get("OperationalStatus", "AVAILABLE"),
                "SecretState": _dict(config["MissionBoard"]["MissionOperations"].get(_text(station.get("ActivityID")))).get("SecretState", "RELEASED"),
            }
            for station in stations or []
        ] if config["StrategyMode"] == OPEN_MISSION_BOARD else [],
        "Leaderboard": [dict(row) for row in leaderboard or []],
    }


def projector_projection(facilitator: dict[str, Any], configuration: dict[str, Any] | None) -> dict[str, Any]:
    """Display-only projection for mission status, progress and optional scoring."""
    config = normalise_configuration(configuration)
    teams = [dict(row) for row in _dict(facilitator).get("Teams", [])]
    if config["StrategyMode"] == OPEN_MISSION_BOARD:
        # Board choices are team strategy.  Projector audiences receive only
        # aggregate approved progress, never selected/current activities.
        teams = [{
            key: value for key, value in row.items()
            if key not in {"CurrentActivityID", "NextActivityID", "SelectedMissionActivityIDs", "MissionBoard", "Route", "SubmissionsByActivity"}
        } for row in teams]
    ordered = sorted(teams, key=lambda row: (-int(row.get("Completed", 0)), row.get("TeamID", "")))
    total_missions = max((int(row.get("Total", 0)) for row in teams), default=0)
    mission_operations = [dict(row) for row in _dict(facilitator).get("MissionOperations", [])]
    return {
        "EngineKind": ENGINE_KIND,
        "StrategyMode": config["StrategyMode"],
        "View": config["Projector"]["DefaultView"],
        "ShowOverallScoring": config["Projector"]["ShowOverallScoring"],
        "Lifecycle": _text(_dict(facilitator).get("Lifecycle")),
        "PendingReviewCount": int(_dict(facilitator).get("PendingReviewCount", 0) or 0),
        "TotalMissions": total_missions,
        "Teams": ordered,
        "Leaderboard": [dict(row) for row in _dict(facilitator).get("Leaderboard", [])],
        "MissionAggregate": [
            {
                "ActivityID": row.get("ActivityID", ""),
                "DisplayName": row.get("DisplayName", ""),
                "MissionClass": row.get("MissionClass", "STANDARD"),
                "OperationalStatus": row.get("OperationalStatus", "AVAILABLE"),
                "SecretReleased": _upper(row.get("SecretState"), "RELEASED") == "RELEASED",
            }
            for row in mission_operations
            if _upper(row.get("SecretState"), "RELEASED") == "RELEASED"
        ] if config["StrategyMode"] == OPEN_MISSION_BOARD else [],
        "ReleasedSecretMissionAnnouncements": [
            row.get("DisplayName", row.get("ActivityID", ""))
            for row in mission_operations
            if _upper(row.get("MissionClass")) == "SECRET"
            and _upper(row.get("SecretState"), "RELEASED") == "RELEASED"
        ] if config["StrategyMode"] == OPEN_MISSION_BOARD else [],
    }
