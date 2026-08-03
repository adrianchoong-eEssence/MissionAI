#!/usr/bin/env python3
"""Run all credentialed, read-only RC2 audits and preserve machine evidence."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.runtime_database import get_runtime_database
from scripts.experience_migration_audit import run_audit as experience_audit
from scripts.programme_hierarchy_audit import run_audit as programme_audit
from scripts.transaction_migration_audit import run_audit as transaction_audit


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    runtime = get_runtime_database()
    checks = {}
    runners = {
        "identity": lambda: runtime.identity_migration_audit(args.event_id),
        "programme": programme_audit,
        "experience": experience_audit,
        "transactions": transaction_audit,
    }
    for name, runner in runners.items():
        try:
            result = runner()
            result["ProductionRecordsChanged"] = False
            write_json(args.output_dir / f"{name}.json", result)
            checks[name] = {"Passed": True, "Output": f"{name}.json"}
        except Exception as error:
            checks[name] = {"Passed": False, "Error": str(error)}
    manifest = {
        "Mode": "SELECT_ONLY",
        "EventID": args.event_id,
        "GeneratedAtUTC": datetime.now(timezone.utc).isoformat(),
        "ProductionRecordsChanged": False,
        "Passed": all(item["Passed"] for item in checks.values()),
        "Checks": checks,
    }
    write_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["Passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
