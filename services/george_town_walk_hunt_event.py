"""George Town UAT deployment defaults.  The values are fixtures, not production data."""
from __future__ import annotations

from services.hunt_event import configured_hunt_event


DEFAULT_EVENT_ID = "GEORGE-TOWN-WALK-20261024-UAT"
DEFAULT_JOIN_CODE = "GTWALKUAT"


def george_town_walk_hunt_event() -> tuple[str, str]:
    return configured_hunt_event("GEORGE_TOWN", DEFAULT_EVENT_ID, DEFAULT_JOIN_CODE)
