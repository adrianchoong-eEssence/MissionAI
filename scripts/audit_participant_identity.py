#!/usr/bin/env python3
"""Read-only Sprint 010 production participant migration audit."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.runtime_database import RuntimeDatabaseError, get_runtime_database


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime = get_runtime_database()
    if not runtime.can_publish:
        parser.error("Read-only audit requires SUPABASE_URL and SUPABASE_SECRET_KEY.")
    try:
        report = runtime.identity_migration_audit(args.event_id)
    except RuntimeDatabaseError as error:
        print(json.dumps({"Passed": False, "Error": str(error)}, indent=2), file=sys.stderr)
        return 2
    report["ProductionRecordsChanged"] = False
    report["ApprovalRequiredBeforeMigration"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
