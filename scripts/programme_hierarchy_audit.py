#!/usr/bin/env python3
"""SELECT-only canonical hierarchy audit for production ProgrammeStages."""

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.google_sheets import get_sheet_records
from engines.programme_adapter import CanonicalProgrammeAdapter


def run_audit():
    rows_by_event = defaultdict(list)
    for row in get_sheet_records("ProgrammeStages"):
        rows_by_event[str(row.get("EventID", "")).strip()].append(row)
    events = []
    for event_id, rows in sorted(rows_by_event.items()):
        if not event_id:
            continue
        snapshot = CanonicalProgrammeAdapter(event_id, rows).snapshot()
        events.append({
            "EventID": event_id,
            "Errors": snapshot.errors,
            "Warnings": snapshot.warnings,
            "Audit": snapshot.legacy_audit,
        })
    return {
        "Mode": "SELECT_ONLY",
        "EventsInspected": len(events),
        "RowsInspected": sum(item["Audit"]["RowsInspected"] for item in events),
        "EventsWithErrors": sum(bool(item["Errors"]) for item in events),
        "ProductionRecordsChanged": False,
        "Events": events,
    }


if __name__ == "__main__":
    print(json.dumps(run_audit(), indent=2, sort_keys=True))
