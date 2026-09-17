"""Canonical EventID-scoped Hunt operations exposed to Kai intent routing."""
from __future__ import annotations

from engines.live_location import derive_team_locations


def hunt_location_lookup(runtime, event_id: str, *, subject: str = "", status: str = "") -> dict:
    """Read a selected event only; Kai never uses a global current-event state."""
    location = runtime.get_live_location_operator_map(event_id)
    rows = list(location.get("Participants") or [])
    token = str(subject or "").casefold().strip()
    requested_status = str(status or "").upper().strip()
    if token:
        rows = [row for row in rows if token in str(row.get("ParticipantName") or "").casefold()
                or token == str(row.get("TeamID") or "").casefold()]
    if requested_status:
        rows = [row for row in rows if str(row.get("Status") or "").upper() == requested_status]
    return {"EventID": str(event_id), "Participants": rows,
            "Teams": derive_team_locations(rows, separation_threshold_meters=float(location.get("SeparationThresholdMeters") or 250))}


def hunt_checkpoint_lookup(runtime, event_id: str, *, checkpoint_id: str = "") -> dict:
    snapshot = runtime.get_hunt_operator_snapshot(event_id)
    checkpoints = list(snapshot.get("Checkpoints") or [])
    if checkpoint_id:
        checkpoints = [row for row in checkpoints if str(row.get("CheckpointID") or "").casefold() == str(checkpoint_id).casefold()]
    return {"EventID": str(event_id), "Checkpoints": checkpoints}


def hunt_operation(runtime, event_id: str, intent: str, **payload) -> dict:
    """Route Kai to the same adapter operations as Mission Control."""
    action = str(intent or "").upper().strip()
    if action == "STATUS":
        return runtime.get_hunt_operator_snapshot(event_id)
    if action == "SET_STATE":
        return runtime.set_hunt_operational_state(event_id, payload.get("state"), payload.get("actor"))
    if action == "ANNOUNCE":
        return runtime.send_event_announcement(event_id, **payload)
    if action == "ADJUST_SCORE":
        return runtime.adjust_hunt_score(event_id, payload.get("team_id"), payload.get("score_delta"),
                                         payload.get("reason"), payload.get("actor"), payload.get("idempotency_key"))
    if action == "HYBRID_ROSTER":
        return runtime.get_hybrid_anchored_operator_roster(event_id)
    if action == "STAGE_STATUS":
        return runtime.get_competition_stage_snapshot(event_id)
    if action == "SET_STAGE_STATE":
        return runtime.set_competition_stage_state(event_id, payload.get("stage_id"), payload.get("stage_state"),
                                                  payload.get("actor"))
    if action == "RECORD_STAGE_SCORE":
        return runtime.record_competition_stage_score(
            event_id, payload.get("stage_id"), payload.get("team_id"), payload.get("score_delta"),
            payload.get("reason"), payload.get("actor"), payload.get("idempotency_key"),
        )
    raise ValueError("Unsupported canonical Hunt operation")
