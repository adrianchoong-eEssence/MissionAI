"""Read-only ENCA George Town architecture UAT fixture loader."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from engines.hunt_engine import configuration_errors


PACK_PATH = Path(__file__).with_name("george_town_walk_hunt_v1.json")

_MISSION_CLASSES = {"COMMON", "RANDOM", "SECRET"}
_MISSION_CATEGORIES = {
    "OBSERVATION",
    "PHOTO",
    "VIDEO",
    "AI",
    "CREATIVE",
    "COLLABORATION",
    "HERITAGE",
    "FOOD_CULTURE",
    "CHECKPOINT",
}
_CANDIDATE_ZONE_IDS = {
    "HIN_BUS_DEPOT",
    "KENG_KWEE_PENANG_ROAD_CHENDUL",
    "CAMPBELL_CARNARVON",
    "ARMENIAN_STREET",
    "CANNON_STREET",
    "KHOO_KONGSI",
    "ACHEH_STREET",
    "LITTLE_INDIA_HARMONY",
    "AH_QUEE_STREET",
    "BEACH_STREET",
    "CHEW_JETTY_CLAN_JETTIES",
}


def _content_foundation_errors(pack: dict) -> list[str]:
    """Guard the owner-pending hunt design boundary without materialising content."""
    foundation = dict(pack.get("HuntContentFoundation") or {})
    allocation = dict(foundation.get("AllocationPolicy") or {})
    arena = dict(foundation.get("Arena") or {})
    map_config = dict(foundation.get("Map") or {})
    return_to_base = dict(foundation.get("ReturnToBase") or {})
    zones = list(arena.get("CandidateZones") or [])
    excluded = list(arena.get("ExcludedZones") or [])
    errors: list[str] = []

    if foundation.get("MissionBoardMode") != "OPTIONAL_BALANCED_SUBSETS":
        errors.append("ENCA Hunt requires optional balanced mission subsets.")
    if foundation.get("TargetMasterMissionPool") != 20:
        errors.append("ENCA Hunt target master mission pool must remain 20 owner-pending items.")
    if set(foundation.get("MissionClasses") or []) != _MISSION_CLASSES:
        errors.append("ENCA Hunt requires COMMON, RANDOM, and SECRET mission classes.")
    if set(foundation.get("MissionCategories") or []) != _MISSION_CATEGORIES:
        errors.append("ENCA Hunt mission category foundation is incomplete.")
    if any(
        allocation.get(key) is not expected
        for key, expected in (
            ("SameMissionBoardForEveryTeam", False),
            ("ForcedLinearRoute", False),
            ("GeographicBalancing", True),
            ("CategoryBalancing", True),
            ("CongestionReduction", True),
        )
    ) or (
        allocation.get("SubsetAssignment") != "BALANCED_RANDOM"
        or allocation.get("CompletionExpectation") != "OPTIONAL_NOT_ALL_MISSIONS_REQUIRED"
    ):
        errors.append("ENCA Hunt requires balanced random, non-linear, non-identical team subsets.")

    if arena.get("Mode") != "COMPACT_MISSION_ARENA":
        errors.append("ENCA Hunt must retain its compact mission arena.")
    zone_ids = [zone.get("ZoneID") for zone in zones]
    if set(zone_ids) != _CANDIDATE_ZONE_IDS or len(zone_ids) != len(_CANDIDATE_ZONE_IDS):
        errors.append("ENCA Hunt candidate arena zones do not match the approved owner-pending list.")
    for zone in zones:
        if zone.get("Coordinates") != "OWNER_PENDING" or any(
            key in zone for key in ("Latitude", "Longitude", "CoordinatesDecimal")
        ):
            errors.append("ENCA Hunt candidate zones must not contain final coordinates.")
            break
    hin = next((zone for zone in zones if zone.get("ZoneID") == "HIN_BUS_DEPOT"), {})
    if hin.get("Role") != "HIGH_VALUE_OUTER_MISSION_OR_CHECKPOINT":
        errors.append("Hin Bus Depot must remain available as the high-value outer candidate.")
    if not any(zone.get("ZoneID") == "FORT_CORNWALLIS" and zone.get("Status") == "EXCLUDED" for zone in excluded):
        errors.append("Fort Cornwallis must remain excluded from the ENCA Hunt arena.")

    if map_config.get("ParticipantYouLocation") is not True:
        errors.append("ENCA participant maps must retain the consented You location mode.")
    if map_config.get("MissionCheckpointPins") != "WHEN_FINAL_COORDINATES_APPROVED" or map_config.get(
        "ReturnToBasePin"
    ) != "ALWAYS_CONFIGURED_WHEN_COORDINATES_APPROVED":
        errors.append("ENCA participant map pins must remain coordinate-gated.")
    if map_config.get("ParticipantOtherTeamVisibility") != "OFF" or set(
        map_config.get("AllowedOtherTeamVisibilityModes") or []
    ) != {"OFF", "TEAM_LEADERS"}:
        errors.append("ENCA participant location sharing must default to OFF with TEAM_LEADERS opt-in only.")
    if return_to_base.get("Persistent") is not True or return_to_base.get("Scored") is not False:
        errors.append("Return to Base must be a persistent non-scored operational pin.")
    if return_to_base.get("Coordinates") != "OWNER_PENDING" or return_to_base.get("HumanGuidance") != "OWNER_PENDING":
        errors.append("Return to Base coordinates and guidance remain owner-pending.")
    if set(return_to_base.get("Announcements") or []) != {"30 MINUTES REMAINING", "RETURN TO BASE NOW"}:
        errors.append("Return to Base announcements must retain the two approved operational states.")
    return errors


def _architecture_errors(pack: dict) -> list[str]:
    formation = dict(pack.get("TeamFormation") or {})
    teams = list(formation.get("Teams") or [])
    anchors = list(formation.get("HODAnchors") or [])
    stages = list(pack.get("CompetitionStages") or [])
    errors: list[str] = []
    if formation.get("Mode") != "HYBRID_ANCHORED":
        errors.append("ENCA requires HYBRID_ANCHORED Team Formation.")
    if len(teams) != 10 or len(anchors) != 10:
        errors.append("ENCA requires exactly ten country teams and ten HOD anchors.")
    team_ids = [str(team.get("TeamID") or "") for team in teams]
    if len(set(team_ids)) != 10 or any(not value for value in team_ids):
        errors.append("Every ENCA country slot needs a unique TeamID.")
    if {str(anchor.get("TeamID") or "") for anchor in anchors} != set(team_ids):
        errors.append("Every country slot requires exactly one distinct HOD anchor.")
    if sum(int(team.get("Capacity") or 0) for team in teams) != 134:
        errors.append("ENCA team capacities must total 134.")
    capacities = Counter(int(team.get("Capacity") or 0) for team in teams)
    if capacities != Counter({14: 4, 13: 6}):
        errors.append("ENCA capacities must be four teams of 14 and six teams of 13.")
    if [stage.get("StageID") for stage in stages] != [
        "VISION_TOWER", "CROSSING_THE_BLACK_SEA", "GEORGE_TOWN_HUNT"
    ]:
        errors.append("ENCA requires its three canonical scored stages in order.")
    if any(
        stage.get("Rules") != "PENDING OWNER CONTENT"
        and stage.get("StageID") != "GEORGE_TOWN_HUNT"
        for stage in stages
    ):
        errors.append("Vision Tower and Black Sea rules remain owner-pending.")
    if pack.get("Missions") or pack.get("Checkpoints"):
        errors.append("The ENCA architecture fixture must not invent route or mission content.")
    errors.extend(_content_foundation_errors(pack))
    return errors


def load_pack() -> dict:
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    errors = configuration_errors(
        pack.get("HuntConfiguration"),
        checkpoints=pack.get("Checkpoints", []),
        missions=pack.get("Missions", []),
    ) + _architecture_errors(pack)
    if errors:
        raise ValueError("Invalid ENCA George Town UAT pack: " + "; ".join(errors))
    return pack


def candidate_plan() -> dict:
    """Return an owner-authorisation plan; this function never writes a database."""
    pack = load_pack()
    return {
        "Executed": False,
        "Event": pack["Event"],
        "TeamFormation": pack["TeamFormation"],
        "CompetitionStages": pack["CompetitionStages"],
        "HuntConfiguration": pack["HuntConfiguration"],
        "HuntContentFoundation": pack["HuntContentFoundation"],
        "Location": pack["Location"],
        "NonScoredActivities": pack["NonScoredActivities"],
        "Checkpoints": pack["Checkpoints"],
        "Missions": pack["Missions"],
        "Safety": (
            "Disposable UAT architecture only. HOD Personal Keys are generated outside "
            "the repository; no production event, final countries, routes, checkpoints, "
            "mission rules, coordinates, Return-to-Base guidance, or points are "
            "materialised without owner authorisation."
        ),
    }
