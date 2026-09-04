"""Canonical presentation gates for the Maxis Personal Key UAT.

The participant workspace is the source of truth.  These helpers deliberately
use Team Formation's persisted phase rather than the convenience Lifecycle
label so a restored participant changes screen as soon as the facilitator
advances canonical state.
"""
from __future__ import annotations


# A participant may see only their private country reveal before Captain
# selection.  FORMATION_LOCKED remains private while the facilitator prepares
# the Captain-selection transition.
COUNTRY_REVEAL_PHASES = frozenset({
    "DRAFT",
    "REGISTRATION_OPEN",
    "FORMATION_LOCKED",
})

ROSTER_PHASES = frozenset({
    "CAPTAIN_SELECTION",
    "ACTIVE",
})


def team_formation_phase(workspace: dict | None) -> str:
    """Return the canonical persisted Team Formation phase, never Lifecycle."""
    return str((workspace or {}).get("TeamFormationPhase") or "").strip().upper()


def country_reveal_is_active(workspace: dict | None) -> bool:
    """Whether the private country-only screen is still authorised."""
    return team_formation_phase(workspace) in COUNTRY_REVEAL_PHASES


def country_roster_is_available(workspace: dict | None) -> bool:
    """Whether country teammates and Captain authority may be shown."""
    return team_formation_phase(workspace) in ROSTER_PHASES
