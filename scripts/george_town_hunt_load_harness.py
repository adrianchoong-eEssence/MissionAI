#!/usr/bin/env python3
"""Plan the authorised disposable-event Hunt load run without claiming a pass."""
from __future__ import annotations

import argparse
import json


def plan(*, participants: int = 36, concurrent_event_id: str = "NERA-20261024-UAT") -> dict:
    return {
        "Executed": False,
        "Scope": "Fresh disposable Hunt event plus a separately scoped Nera concurrent-event fixture",
        "ParticipantCount": int(participants),
        "LocationCadenceSeconds": 20,
        "StaleAfterSeconds": 90,
        "Operations": [
            "RANDOM_ASSIGN registration and same-device recovery",
            "automatic PRESENT attendance and Captain lifecycle",
            "individual consent and event-window location updates",
            "operator map reads, individual trails, and separated-team detection",
            "checkpoint proximity reads with no GPS score mutation",
            "private photo/video submission (including safe retry) and review",
            "announcement send, receipt, acknowledgement, and ALL+URGENT confirmation",
            "public projector projection with no GPS, evidence, participant, or service-key field",
            "parallel Nera fixture reads/writes proving EventID isolation",
        ],
        "Assertions": [
            "Each location, checkpoint, announcement, participant, score and projection result retains its EventID.",
            "No cross-event roster, Captain, location, trail, submission, score, or announcement is visible.",
            "No update is accepted before consent, after stop, or outside the configured window.",
            "GPS proximity cannot create score_transactions_v2 rows.",
            "Browser background, screen-lock, network-loss and urban-GPS claims require human iPhone/Android UAT.",
        ],
        "RequiredBeforeExecution": [
            "owner authorisation to install 051 on the dedicated project",
            "verified migration history and a disposable target EventID",
            "test-only publishable/service credentials and browser/mobile runners",
            f"confirmed concurrent-event fixture: {concurrent_event_id}",
        ],
        "Status": "NOT_EXECUTED — this is a harness plan, not a load PASS.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--participants", type=int, default=36)
    parser.add_argument("--concurrent-event-id", default="NERA-20261024-UAT")
    args = parser.parse_args()
    print(json.dumps(plan(participants=args.participants, concurrent_event_id=args.concurrent_event_id), indent=2, sort_keys=True))
