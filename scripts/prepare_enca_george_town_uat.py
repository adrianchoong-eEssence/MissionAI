#!/usr/bin/env python3
"""Prepare a redacted, non-writing ENCA hybrid UAT configuration plan.

Personal Keys remain outside the repository. When an authorised operator gives
this script a local JSON map of exact HOD display name to six-character key,
the output contains only the derived credential hashes needed by the prepared
Core RPC. It never installs a migration, creates an event, or prints a key.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_packs.george_town_walk_hunt_v1.materialize import candidate_plan, load_pack
from services.personal_key_credentials import derive_personal_key_credential, team_formation_credential_hash


def _credential_hashes(personal_keys: dict[str, object]) -> list[dict]:
    pack = load_pack()
    anchors = list(pack["TeamFormation"]["HODAnchors"])
    expected = {str(anchor["DisplayName"]) for anchor in anchors}
    supplied = {str(name) for name in personal_keys}
    if supplied != expected:
        missing = sorted(expected - supplied)
        unexpected = sorted(supplied - expected)
        raise ValueError(f"Personal Key file must cover exactly the ten ENCA HODs; missing={missing}, unexpected={unexpected}")
    return [
        {
            "DisplayName": str(anchor["DisplayName"]),
            "TeamID": str(anchor["TeamID"]),
            "EnrollmentCredentialHash": team_formation_credential_hash(
                derive_personal_key_credential(pack["Event"]["EventID"], str(personal_keys[str(anchor["DisplayName"])]))
            ),
            "AssignmentRole": "HOD_ANCHOR",
        }
        for anchor in anchors
    ]


def materialization_plan(personal_keys: dict[str, object] | None = None) -> dict:
    """Return a reviewed RPC input plan without transmitting or retaining raw keys."""
    plan = candidate_plan()
    teams = list(plan["TeamFormation"]["Teams"])
    plan.update({
        "Executed": False,
        "InstallationStatus": "NOT_INSTALLED",
        "RequiredMigration": "053_enca_hybrid_event_architecture.sql",
        "TeamCapacities": {str(team["TeamID"]): int(team["Capacity"]) for team in teams},
        "HODAnchorRoster": _credential_hashes(personal_keys) if personal_keys is not None else [],
        "ReadyForConfigureRPC": personal_keys is not None,
        "KeyHandling": "Raw Personal Keys are not output, written, or sent by this planning utility.",
    })
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a non-writing ENCA UAT configuration plan.")
    parser.add_argument("--personal-key-file", type=Path,
                        help="Authorised local JSON object mapping exact HOD display names to Personal Keys.")
    args = parser.parse_args()
    supplied = None
    if args.personal_key_file:
        loaded = json.loads(args.personal_key_file.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Personal Key file must be a JSON object.")
        supplied = loaded
    print(json.dumps(materialization_plan(supplied), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
