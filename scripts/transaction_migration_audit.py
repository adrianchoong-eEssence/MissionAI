#!/usr/bin/env python3
"""SELECT-only Gate 6 legacy transaction audit and reconciliation proposal."""

from collections import Counter, defaultdict
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.google_sheets import get_sheet_records
from data.runtime_database import get_runtime_database


def run_audit():
    runtime = get_runtime_database()
    if not runtime.can_publish:
        raise RuntimeError("SUPABASE_SECRET_KEY is required for the SELECT-only transaction audit.")
    runtime_submissions = runtime._request("GET", "runtime_submissions", query={"select": "*"}, admin=True) or []
    legacy_awards = runtime._request("GET", "runtime_credit_transactions", query={"select": "*"}, admin=True) or []
    sheet_submissions = get_sheet_records("Submissions")
    sheet_teams = get_sheet_records("Teams")
    mappings = []
    keys = Counter((row.get("event_id"), row.get("mission_id"), row.get("submission_key")) for row in runtime_submissions)
    for row in runtime_submissions:
        stable = all(row.get(key) for key in (
            "event_id", "submission_id", "participant_id", "experience_assignment_id",
            "experience_definition_id", "experience_definition_version", "experience_assignment_version",
        ))
        classification = (
            "Canonical Submission candidate" if stable else
            "Duplicate" if keys[(row.get('event_id'),row.get('mission_id'),row.get('submission_key'))] > 1 else
            "Historical-only" if str(row.get("status", "")).upper() in {"APPROVED","REJECTED"} else
            "Orphaned or invalid"
        )
        mappings.append({
            "Source": "runtime_submissions", "SourceID": row.get("submission_id"),
            "Classification": classification, "ProposedSubmissionID": row.get("submission_id"),
            "ProposedReviewDecision": (
                "APPROVE" if str(row.get("status", "")).upper()=="APPROVED" else
                "REJECT" if str(row.get("status", "")).upper()=="REJECTED" else None
            ), "AutomaticMigration": False,
        })
    for row in sheet_submissions:
        mappings.append({
            "Source": "Sheet Submissions", "SourceID": row.get("SubmissionID"),
            "Classification": "Reporting projection", "AutomaticMigration": False,
        })
    for row in legacy_awards:
        mappings.append({
            "Source": "runtime_credit_transactions", "SourceID": row.get("transaction_id"),
            "Classification": "Canonical Award Transaction candidate",
            "ProposedAwardType": {
                "EARN":"INTELLIGENCE_CREDITS","SPEND":"MARKETPLACE_SPEND",
                "REFUND":"REFUND","ADJUSTMENT":"MANUAL_ADJUSTMENT","REVERSAL":"CORRECTION",
            }.get(str(row.get("transaction_type", "")).upper()),
            "AutomaticMigration": False,
        })
    legacy_balances = defaultdict(float)
    for row in legacy_awards:
        legacy_balances[(row.get("event_id"),row.get("team_name"))] += float(row.get("amount",0) or 0)
    sheet_balances = {(row.get("EventID"),row.get("TeamName")):float(row.get("Score",0) or 0) for row in sheet_teams}
    reconciliation = [{
        "EventID": key[0], "Team": key[1], "LegacyLedgerNet": value,
        "SheetTeamScore": sheet_balances.get(key), "Difference": (
            None if key not in sheet_balances else value-sheet_balances[key]
        ), "AutomaticCorrection": False,
    } for key,value in sorted(legacy_balances.items())]
    leaderboard = defaultdict(list)
    for row in reconciliation:
        leaderboard[row["EventID"]].append((row["Team"],row["LegacyLedgerNet"]))
    leaderboard_reconciliation = {
        event: sorted(rows,key=lambda item:(-item[1],str(item[0]))) for event,rows in leaderboard.items()
    }
    return {
        "Mode":"SELECT_ONLY","RuntimeSubmissions":len(runtime_submissions),
        "SheetSubmissionProjections":len(sheet_submissions),"LegacyAwards":len(legacy_awards),
        "Mappings":mappings,"BalanceReconciliation":reconciliation,
        "LeaderboardReconciliation":leaderboard_reconciliation,
        "ProductionRecordsChanged":False,
    }


if __name__ == "__main__":
    print(json.dumps(run_audit(),indent=2,sort_keys=True,default=str))
