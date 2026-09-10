#!/usr/bin/env python3
"""Print the safe, unexecuted 250-client Location + Announcements V1 plan."""
from __future__ import annotations

import json


def plan() -> dict:
    return {
        "Executed": False,
        "FixtureScope": "fresh disposable event only; never AIA, Maxis, George Town, Nera, or historical events",
        "Participants": 250,
        "LocationCadenceSeconds": [15, 20, 30],
        "Operations": [
            "consent enable and decline", "location update throttled by browser cadence",
            "reconnect and app rerun", "CURRENT to STALE deterministic transition",
            "operator map with team separation protection", "announcement receipt and acknowledgement",
            "same-time second event isolation", "retention cleanup",
        ],
        "Assertions": [
            "each update remains EventID and ParticipantID scoped",
            "no location before consent or after stop/window end",
            "no cross-event location or announcement visibility",
            "no score mutation from GPS proximity",
            "no background-tracking PASS claim",
        ],
        "Requirements": "authorised staging URL, publishable key, service key, test DSN, and real browser/mobile runners",
        "Status": "NOT_EXECUTED — credentials and disposable environment authorisation are required.",
    }


if __name__ == "__main__":
    print(json.dumps(plan(), indent=2, sort_keys=True))
