"""Canonical event-scoped data helpers for Kai/operator intents.

The conversational layer supplies intent parsing. These helpers never use a
global event and never insert directly into database tables.
"""
from __future__ import annotations

from engines.live_location import derive_team_locations


def location_lookup(runtime, event_id: str, *, subject: str = "", status: str = "") -> dict:
    snapshot = runtime.get_live_location_operator_map(event_id)
    participants = list(snapshot.get("Participants") or [])
    token = str(subject or "").casefold().strip()
    desired_status = str(status or "").upper().strip()
    if token:
        participants = [row for row in participants if token in str(row.get("ParticipantName", "")).casefold()
                        or token == str(row.get("TeamID", "")).casefold()]
    if desired_status:
        participants = [row for row in participants if str(row.get("Status", "")).upper() == desired_status]
    return {"EventID": str(event_id), "Participants": participants,
            "Teams": derive_team_locations(participants, separation_threshold_meters=float(snapshot.get("SeparationThresholdMeters", 250) or 250))}


def send_announcement(runtime, event_id: str, **payload) -> dict:
    """Kai uses the exact same audited canonical send operation as Mission Control."""
    return runtime.send_event_announcement(event_id, **payload)
