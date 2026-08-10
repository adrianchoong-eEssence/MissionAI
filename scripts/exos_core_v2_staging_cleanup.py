#!/usr/bin/env python3
"""Audit and optionally delete explicitly allow-listed Core v2 staging events.

Dry-run is the default. This script is intentionally not a general event deleter.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.runtime_database import RuntimeDatabaseError, get_runtime_database


KNOWN_PRODUCTION_HOSTS = {"bqsbkdfzqyiodivhyxnq.supabase.co"}
KEEP_EVENT_IDS = (
    "AIA-WE-260810081110-UPPER",
    "AIA-WE-260810081110-LOWER",
    "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
)
DELETE_ALLOWLIST = {
    "AIA-WE-260810081007-UPPER": "Superseded AIA setup attempt; canonical Upper South is allow-listed KEEP.",
    "AIA-WE-260810081007-LOWER": "Superseded AIA setup attempt; canonical Lower South is allow-listed KEEP.",
    "STD-UAT-260810071644-A": "Standard vertical-slice UAT source event.",
    "STD-UAT-260810071644-B": "Standard vertical-slice duplicated UAT event.",
    "CORE-V2-RACE-UAT-EVT-4F833D6CCD": "Superseded RACE staging demo; canonical RACE UAT is allow-listed KEEP.",
    "CORE-V2-RACE-UAT-EVT-FC70052871": "Historical Formula R.A.C.E. UAT record.",
    "CORE-V2-RACE-UAT-EVT-90B707B835": "Historical Formula R.A.C.E. UAT record.",
    "CORE-V2-UAT-EVT-4898833AFF": "Historical generic Core v2 standard UAT record.",
    "CORE-V2-UAT-EVT-BAFC957BE3": "Historical generic Core v2 standard UAT record.",
}

# Every Core v2 table in migration 020/022 that is event-owned directly or
# through Programme, Submission, Session, Checkpoint, or AI Job identifiers.
DIRECT_EVENT_TABLES = {
    "programmes_v2": "programme_id",
    "teams_v2": "team_id",
    "participants_v2": "participant_id",
    "participant_sessions_v2": "participant_session_id",
    "activity_runtime_v2": "runtime_id",
    "submissions_v2": "submission_id",
    "reviews_v2": "review_id",
    "score_transactions_v2": "score_transaction_id",
    "credit_transactions_v2": "credit_transaction_id",
    "marketplace_items_v2": "item_id",
    "marketplace_transactions_v2": "marketplace_transaction_id",
    "team_access_credentials_v2": "team_access_credential_id",
    "team_access_sessions_v2": "team_access_session_id",
    "build_status_v2": "event_id",
    "judging_scores_v2": "judging_score_id",
    "race_results_v2": "race_result_id",
    "projector_state_v2": "event_id",
    "location_checkpoints_v2": "checkpoint_id",
    "ai_jobs_v2": "ai_job_id",
    "ai_results_v2": "ai_result_id",
    "audit_log_v2": "audit_id",
}
INDIRECT_TABLES = {
    "modules_v2": "module_id",
    "activities_v2": "activity_id",
    "submission_evidence_v2": "evidence_id",
    "location_evidence_v2": "location_evidence_id",
}
DELETE_ORDER = (
    "location_evidence_v2", "submission_evidence_v2", "ai_results_v2",
    "reviews_v2", "score_transactions_v2", "marketplace_transactions_v2",
    "credit_transactions_v2", "team_access_sessions_v2",
    "team_access_credentials_v2", "judging_scores_v2", "race_results_v2",
    "projector_state_v2", "build_status_v2", "location_checkpoints_v2",
    "submissions_v2", "activity_runtime_v2", "participant_sessions_v2",
    "participants_v2", "marketplace_items_v2", "activities_v2",
    "modules_v2", "programmes_v2", "teams_v2", "ai_jobs_v2",
    "audit_log_v2", "events_v2",
)
PRIMARY_KEYS = {
    **DIRECT_EVENT_TABLES,
    **INDIRECT_TABLES,
    "events_v2": "event_id",
}


def require_staging(runtime):
    if str(os.getenv("EXOS_ENV", "")).strip().casefold() != "staging":
        raise RuntimeError("Refusing to run: EXOS_ENV must be exactly 'staging'.")
    host = (urlparse(str(runtime.url)).hostname or "").casefold()
    if not host or host in KNOWN_PRODUCTION_HOSTS:
        raise RuntimeError(f"Refusing non-staging Supabase host: {host or 'missing'}")
    if not runtime.can_publish:
        raise RuntimeError("SUPABASE_SECRET_KEY is required for staging cleanup audit.")


def _rows(runtime, table, query):
    value = runtime._request("GET", table, query=query, admin=True)
    return value if isinstance(value, list) else []


def _ids_filter(column, values):
    clean = [str(value) for value in values if str(value)]
    return {column: f"in.({','.join(clean)})"} if clean else None


def _pluck(runtime, table, key, query):
    rows = _rows(runtime, table, {**query, "select": key})
    return [row[key] for row in rows if row.get(key) is not None]


def capture_event(runtime, event_id):
    dependencies = {}
    for table, key in DIRECT_EVENT_TABLES.items():
        dependencies[table] = _pluck(
            runtime, table, key,
            {"event_id": f"eq.{event_id}"},
        )

    programme_ids = dependencies["programmes_v2"]
    module_ids = _pluck(
        runtime, "modules_v2", "module_id",
        _ids_filter("programme_id", programme_ids) or {"programme_id": "eq.__none__"},
    )
    activity_ids = _pluck(
        runtime, "activities_v2", "activity_id",
        _ids_filter("programme_id", programme_ids) or {"programme_id": "eq.__none__"},
    )
    submission_ids = dependencies["submissions_v2"]
    checkpoint_ids = dependencies["location_checkpoints_v2"]
    session_ids = dependencies["participant_sessions_v2"]
    dependencies["modules_v2"] = module_ids
    dependencies["activities_v2"] = activity_ids
    dependencies["submission_evidence_v2"] = _pluck(
        runtime, "submission_evidence_v2", "evidence_id",
        _ids_filter("submission_id", submission_ids) or {"submission_id": "eq.00000000-0000-0000-0000-000000000000"},
    )

    location_rows = {}
    for column, values in (
        ("checkpoint_id", checkpoint_ids),
        ("submission_id", submission_ids),
        ("participant_session_id", session_ids),
    ):
        query = _ids_filter(column, values)
        if not query:
            continue
        for row in _rows(runtime, "location_evidence_v2", {
            **query, "select": "location_evidence_id",
        }):
            if row.get("location_evidence_id"):
                location_rows[str(row["location_evidence_id"])] = row["location_evidence_id"]
    dependencies["location_evidence_v2"] = list(location_rows.values())
    dependencies["events_v2"] = [event_id] if _rows(runtime, "events_v2", {
        "event_id": f"eq.{event_id}", "select": "event_id",
    }) else []
    return {
        "counts": {table: len(values) for table, values in dependencies.items()},
        "ids": dependencies,
        "submission_reviews_v2_alias": "reviews_v2",
    }


def audit(runtime):
    events = _rows(runtime, "events_v2", {
        "select": "event_id,event_name,join_code,lifecycle_status,event_type,programme_type,created_at,updated_at",
        "order": "created_at.desc",
    })
    event_map = {str(row.get("event_id", "")): row for row in events}
    keep, delete, review = [], [], []
    for event_id, row in event_map.items():
        item = {
            "EventID": event_id,
            "EventName": str(row.get("event_name", "")),
            "JoinCode": str(row.get("join_code", "")),
            "Status": str(row.get("lifecycle_status", "")),
        }
        if event_id in KEEP_EVENT_IDS:
            keep.append({**item, "Reason": "Explicit KEEP allow-list."})
        elif event_id in DELETE_ALLOWLIST:
            proof = capture_event(runtime, event_id)
            delete.append({**item, "Reason": DELETE_ALLOWLIST[event_id], **proof})
        else:
            review.append({**item, "Reason": "Not present in either explicit allow-list."})
    return {
        "GeneratedAt": datetime.now(timezone.utc).isoformat(),
        "TotalEvents": len(events),
        "KEEP": sorted(keep, key=lambda row: row["EventID"]),
        "SAFE_TO_DELETE": sorted(delete, key=lambda row: row["EventID"]),
        "REVIEW": sorted(review, key=lambda row: row["EventID"]),
    }


def _delete_ids(runtime, table, values):
    key = PRIMARY_KEYS[table]
    deleted = 0
    for start in range(0, len(values), 100):
        chunk = values[start:start + 100]
        query = _ids_filter(key, chunk)
        if query:
            runtime._request("DELETE", table, query=query, admin=True)
            deleted += len(chunk)
    return deleted


def execute(runtime, report):
    before_keep = {
        event_id: _rows(runtime, "events_v2", {
            "event_id": f"eq.{event_id}", "select": "*",
        })
        for event_id in KEEP_EVENT_IDS
    }
    steps = []
    for event in report["SAFE_TO_DELETE"]:
        event_id = event["EventID"]
        if event_id not in DELETE_ALLOWLIST:
            raise RuntimeError(f"Refusing non-allow-listed EventID: {event_id}")
        for table in DELETE_ORDER:
            values = list(event["ids"].get(table, []))
            if values:
                steps.append({
                    "EventID": event_id,
                    "Table": table,
                    "RowsRequested": _delete_ids(runtime, table, values),
                    "TransactionScope": "single PostgREST DELETE request",
                })

    leftovers = {
        event_id: capture_event(runtime, event_id)["counts"]
        for event_id in DELETE_ALLOWLIST
    }
    orphan_free = all(
        not any(counts.values()) for counts in leftovers.values()
    )
    after_keep = {
        event_id: _rows(runtime, "events_v2", {
            "event_id": f"eq.{event_id}", "select": "*",
        })
        for event_id in KEEP_EVENT_IDS
    }
    if not orphan_free:
        raise RuntimeError(f"Target-scoped orphan verification failed: {leftovers}")
    if before_keep != after_keep or any(not rows for rows in after_keep.values()):
        raise RuntimeError("KEEP verification failed; one or more protected events changed.")
    return {
        "Executed": True,
        "Steps": steps,
        "TargetScopedOrphanVerification": leftovers,
        "KeepEventsUntouched": True,
        "MultiTableTransaction": False,
        "TransactionNote": (
            "Supabase REST makes each DELETE request transactional; it does not "
            "provide one transaction across multiple table requests. Child-first "
            "deletion stops on the first failure and final verification is mandatory."
        ),
    }


def print_summary(report):
    print("KEEP LIST")
    for row in report["KEEP"]:
        print(f"KEEP {row['EventID']} | {row['EventName']} | {row['JoinCode']}")
    print("\nDELETE LIST")
    for row in report["SAFE_TO_DELETE"]:
        print(f"DELETE {row['EventID']} | {row['EventName']} | {row['JoinCode']}")
        print("  dependent-row counts:", json.dumps(row["counts"], sort_keys=True))
    print("\nREVIEW LIST")
    for row in report["REVIEW"]:
        print(f"REVIEW {row['EventID']} | {row['EventName']} | {row['JoinCode']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Execute the explicit DELETE allow-list.")
    parser.add_argument("--output", default="outputs/core-v2-staging-cleanup-audit.json")
    args = parser.parse_args()
    runtime = get_runtime_database()
    require_staging(runtime)
    report = audit(runtime)
    print_summary(report)
    report["DryRun"] = not args.execute
    report["Execution"] = execute(runtime, report) if args.execute else {
        "Executed": False,
        "Reason": "Dry-run default; pass --execute to delete the explicit allow-list.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nFinal report: {output}")


if __name__ == "__main__":
    main()
