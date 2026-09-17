"""Read-only ENCA George Town architecture UAT fixture loader."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from engines.hunt_engine import configuration_errors


PACK_PATH = Path(__file__).with_name("george_town_walk_hunt_v1.json")


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
        "Location": pack["Location"],
        "NonScoredActivities": pack["NonScoredActivities"],
        "Checkpoints": pack["Checkpoints"],
        "Missions": pack["Missions"],
        "Safety": (
            "Disposable UAT architecture only. HOD Personal Keys are generated outside "
            "the repository; no production event, final countries, routes, checkpoints, "
            "mission rules, or points are materialised without owner authorisation."
        ),
    }
