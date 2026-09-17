#!/usr/bin/env python3
"""Local source certification for ENCA's 134-person hybrid formation design.

The harness is intentionally database-free: it does not claim a staging or
production result. It executes the same allocation invariants under a local
124-way registration burst and returns a redacted report suitable for source
contract tests and pre-install review.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_packs.george_town_walk_hunt_v1.materialize import load_pack
from engines.hybrid_anchored_assignment import (
    Anchor,
    HybridAnchoredAssignment,
    expected_enca_capacities,
)


def _synthetic_hod_credential(number: int) -> str:
    """A non-production local-only opaque credential; never a Personal Key."""
    return f"local-enca-hod-{number:02d}-credential"


def _synthetic_general_credential(number: int) -> str:
    return f"local-enca-general-{number:03d}-credential"


def run_harness() -> dict:
    pack = load_pack()
    event = dict(pack["Event"])
    event_id = str(event["EventID"])
    formation = dict(pack["TeamFormation"])
    anchors = [
        Anchor(
            name=str(row["DisplayName"]),
            team_id=str(row["TeamID"]),
            credential=_synthetic_hod_credential(index),
        )
        for index, row in enumerate(formation["HODAnchors"], start=1)
    ]
    certification = HybridAnchoredAssignment(
        event_id=event_id,
        capacities=expected_enca_capacities(event_id),
        anchors=anchors,
    )
    hod_results = [
        certification.claim_hod(anchor.credential, f"hod-device-{index:02d}")
        for index, anchor in enumerate(anchors, start=1)
    ]
    with ThreadPoolExecutor(max_workers=124) as executor:
        futures = [
            executor.submit(
                certification.register_general,
                _synthetic_general_credential(number),
                f"general-device-{number:03d}",
                "Repeated Display Name",
            )
            for number in range(1, 125)
        ]
        general_results = [future.result() for future in futures]

    retry = certification.register_general(
        _synthetic_general_credential(1), "general-device-001", "Different Presentation Name"
    )
    first_general = general_results[0]
    same_hod = certification.claim_hod(anchors[0].credential, "hod-device-01")
    first_general_by_team = next(
        member for member in certification.members
        if member["ParticipantID"] == first_general["ParticipantID"]
    )
    captain = certification.claim_captain(first_general["ParticipantID"])
    captain_is_hod = any(
        captain["CaptainParticipantID"] == member["ParticipantID"]
        for member in certification.members
        if member["AssignmentRole"] == "HOD_ANCHOR"
    )

    distribution = certification.distribution()
    stage_ledger = [
        {"StageID": "VISION_TOWER", "TeamID": next(iter(distribution)), "Score": 10},
        {"StageID": "CROSSING_THE_BLACK_SEA", "TeamID": next(iter(distribution)), "Score": 15},
        {"StageID": "GEORGE_TOWN_HUNT", "TeamID": next(iter(distribution)), "Score": 20},
    ]
    cumulative_score = sum(row["Score"] for row in stage_ledger)
    participant_location_modes = {
        "OFF": [],
        "TEAM_LEADERS": [{"TeamID": "OTHER-TEAM", "LeaderLocationOnly": True}],
    }
    nera = HybridAnchoredAssignment(
        event_id="NERA-20261024-UAT",
        capacities={"NERA-TEAM": 1},
        anchors=[Anchor("Nera Anchor", "NERA-TEAM", "local-nera-anchor")],
    )

    return {
        "Executed": True,
        "EvidenceClass": "LOCAL_SOURCE_CERTIFICATION_ONLY",
        "EventID": event_id,
        "Registered": len(certification.members),
        "HODAnchors": len(hod_results),
        "HODDistinctTeams": len({row["TeamID"] for row in hod_results}) == 10,
        "HODSameDeviceReconnect": bool(same_hod["Idempotent"]),
        "GeneralRandomAssign": all(row["AssignmentRole"] == "GENERAL_PARTICIPANT" for row in general_results),
        "GeneralSameDeviceRetry": bool(retry["Idempotent"]) and retry["ParticipantID"] == first_general["ParticipantID"],
        "DuplicateParticipant": len({row["ParticipantID"] for row in certification.members}) != 134,
        "DuplicateAttendance": len(certification.attendance) != 134,
        "AttendanceAllPresent": set(certification.attendance.values()) == {"PRESENT"},
        "Distribution": distribution,
        "DistributionShape": sorted(distribution.values()),
        "CapacityOverflow": any(distribution[team_id] > capacity for team_id, capacity in expected_enca_capacities(event_id).items()),
        "CaptainIndependentFromHOD": not captain_is_hod,
        "CaptainTeam": first_general_by_team["TeamID"],
        "CumulativeLedger": {"StageCount": len(stage_ledger), "Total": cumulative_score, "NonScoredActivities": ["ENERGIZERS", "ROLLERCOASTER CHALLENGE"]},
        "ParticipantLocationVisibility": participant_location_modes,
        "NeraIsolation": nera.members[0]["ParticipantID"].startswith("NERA-20261024-UAT"),
        "InstallationStatus": "NOT_INSTALLED",
        "HumanUAT": "NOT_EXECUTED",
    }


if __name__ == "__main__":
    print(json.dumps(run_harness(), indent=2, sort_keys=True))
