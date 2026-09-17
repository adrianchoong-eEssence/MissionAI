"""Fixed ENCA George Town UAT identity; values are never participant input."""
from __future__ import annotations

from services.hunt_event import configured_hunt_event


DEFAULT_EVENT_ID = "ENCA-GEORGETOWN-20261024-UAT"
DEFAULT_JOIN_CODE = "ENCAUAT"


def enca_george_town_event() -> tuple[str, str]:
    """Return the server-owned ENCA UAT EventID and common-QR join code."""
    return configured_hunt_event("ENCA_GEORGETOWN", DEFAULT_EVENT_ID, DEFAULT_JOIN_CODE)
