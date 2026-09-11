"""Read-only fixture loader for the George Town Walk Hunt UAT candidate."""
from __future__ import annotations

import json
from pathlib import Path

from engines.hunt_engine import configuration_errors


PACK_PATH = Path(__file__).with_name("george_town_walk_hunt_v1.json")


def load_pack() -> dict:
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    errors = configuration_errors(
        pack.get("HuntConfiguration"),
        checkpoints=pack.get("Checkpoints", []), missions=pack.get("Missions", []),
    )
    if errors:
        raise ValueError("Invalid George Town UAT pack: " + "; ".join(errors))
    return pack


def candidate_plan() -> dict:
    """Return data for owner-authorised materialisation; never writes a database."""
    pack = load_pack()
    return {
        "Executed": False,
        "Event": pack["Event"],
        "HuntConfiguration": pack["HuntConfiguration"],
        "Teams": pack["TeamFormation"],
        "Checkpoints": pack["Checkpoints"],
        "Missions": pack["Missions"],
        "Safety": "Synthetic UAT checkpoint coordinates only; owner authorisation is required before any database mutation.",
    }
