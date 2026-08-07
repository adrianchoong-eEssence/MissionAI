"""Canonical Formula R.A.C.E. parallel-checkpoint rules."""
from __future__ import annotations

import hashlib

RACE_MODULE_TYPE = "RACE_CHECKPOINTS"
PROOF_TYPES = ("Photo", "Text", "Photo + Text")
CHECKPOINT_STATUSES = (
    "AVAILABLE", "SUBMITTED", "UNDER REVIEW", "APPROVED", "REJECTED / RESUBMIT",
)


def is_formula_race_event(event):
    event = event or {}
    event_name = str(event.get("EventName", "")).strip().casefold()
    value = " ".join(str(event.get(key, "")) for key in (
        "ProgrammeType", "EventType", "EventName", "ProgrammeName",
    )).casefold()
    return "formula r.a.c.e" in value or "formula race" in value or event_name == "race"


def module_templates(event):
    """Return the product-specific catalogue without removing legacy products."""
    if is_formula_race_event(event):
        return [
            (1, "Launch EXOS", ["Launch EXOS"]),
            (1, "RACE Checkpoints", ["RACE Checkpoints"]),
            (1, "Marketplace / Spend Credits", ["Marketplace / Spend Credits"]),
            (1, "Build", ["Build"]),
            (1, "Team Photo", ["Team Photo"]),
            (1, "Drag Race", ["Drag Race"]),
            (1, "Judging", ["Judging"]),
            (1, "Championship", ["Championship"]),
        ]
    return None


def deterministic_checkpoint_order(checkpoints, event_id, team_id):
    """Stable pseudo-random order scoped to one event and team."""
    def key(row):
        activity_id = str(row.get("ActivityID", row.get("activity_id", "")))
        digest = hashlib.sha256(
            f"{event_id}\x1f{team_id}\x1f{activity_id}".encode("utf-8")
        ).hexdigest()
        return digest, activity_id
    return sorted(list(checkpoints or []), key=key)


def checkpoint_progress(checkpoints):
    rows = list(checkpoints or [])
    approved = sum(
        str(row.get("Status", row.get("status", ""))).upper() == "APPROVED"
        for row in rows
    )
    return {"Approved": approved, "Total": len(rows), "Complete": bool(rows) and approved == len(rows)}


def parallel_runtime_payload(event_id, module_id, checkpoints, status="LIVE"):
    active = [row for row in checkpoints if bool(row.get("Active", row.get("active", True)))]
    return {
        "EventID": str(event_id), "ModuleID": str(module_id),
        "ModuleType": RACE_MODULE_TYPE, "ParallelActivityIDs": [
            str(row.get("ActivityID", row.get("activity_id", ""))) for row in active
        ],
        "CurrentStageStatus": str(status).upper(),
    }
