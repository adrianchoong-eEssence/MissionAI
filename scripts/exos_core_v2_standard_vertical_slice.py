#!/usr/bin/env python3
"""Run the standard EXOS Core v2 vertical slice against disposable staging."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.standard_core_v2_adapter import get_standard_database
from engines.programme_hierarchy import encode_activity_details, encode_module_stage_type


KNOWN_PRODUCTION_HOSTS = {"bqsbkdfzqyiodivhyxnq.supabase.co"}
ACTIVITIES = [
    ("Pipeline", "PIPELINE", "TEAM", "TEAM_COMPETITIVE", 20),
    ("Helium Stick", "HELIUM", "TEAM", "NON_SCORING", 15),
    ("Key Punch", "KEYPUNCH", "TEAM", "TEAM_COMPETITIVE", 20),
    ("Catalyst Challenge", "CATALYST", "TEAM", "ENTERPRISE", 45),
    ("NASI", "NASI", "INDIVIDUAL", "NON_SCORING", 15),
]


def require_staging(db):
    if os.getenv("EXOS_ENV", "").strip().lower() != "staging":
        raise RuntimeError("EXOS_ENV=staging is mandatory.")
    host = (urlparse(db._client.url).hostname or "").lower()
    if not host or host in KNOWN_PRODUCTION_HOSTS:
        raise RuntimeError(f"Refusing non-staging Supabase host: {host or 'missing'}")
    if not db.can_publish:
        raise RuntimeError("SUPABASE_SECRET_KEY is required for staging UAT.")


def check(report, name, condition, evidence):
    report[name] = {"status": "PASS" if condition else "FAIL", "evidence": evidence}
    if not condition:
        raise AssertionError(f"{name}: {evidence}")


def activity_modules(event_id):
    modules = []
    for position, (name, submission_type, scope, scoring_mode, minutes) in enumerate(ACTIVITIES, 1):
        module_id = f"{event_id}-MOD-{position:02d}"
        activity_id = f"{event_id}-ACT-{position:02d}"
        details = {
            "ActivityID": activity_id, "ModuleID": module_id,
            "ActivityType": "REFLECTION" if submission_type == "NASI" else "STANDARD",
            "ScoringMode": scoring_mode, "SubmissionType": submission_type,
            "ParticipantScope": scope, "EvidenceRequired": True,
            "ParticipantTask": f"Complete and submit the {name} activity.",
            "FacilitatorInstructions": f"Launch, monitor and review {name}.",
            "Credits": 0 if scoring_mode != "TEAM_COMPETITIVE" else 100,
        }
        modules.append({
            "EventID": event_id, "ProgrammeID": f"{event_id}-PROGRAMME",
            "ModuleID": module_id, "ModuleName": name, "ModuleOrder": position,
            "Day": 1, "StartTime": "09:00", "Activities": [{
                "EventID": event_id, "ProgrammeID": f"{event_id}-PROGRAMME",
                "ModuleID": module_id, "ActivityID": activity_id, "ActivityOrder": 1,
                "StageNo": position, "StageName": name,
                "StageType": encode_module_stage_type(name, 1, details["ActivityType"].title()),
                "DurationMinutes": minutes, "IsActive": "Yes",
                "ParticipantMessage": details["ParticipantTask"],
                "FacilitatorInstruction": encode_activity_details(details),
                "SubmissionType": submission_type, "ParticipantScope": scope,
                "ScoringMode": scoring_mode,
            }],
        })
    return modules


def run(prefix="STD-UAT"):
    db = get_standard_database()
    require_staging(db)
    stamp = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    event_id = f"{prefix}-{stamp}-A"
    second_id = f"{prefix}-{stamp}-B"
    join_code = f"S{stamp[-5:]}A"
    second_code = f"S{stamp[-5:]}B"
    report = {"event_id": event_id, "second_event_id": second_id, "started_at": datetime.now(timezone.utc).isoformat()}

    db.create_event(event_id, "EXOS Staging", "UAT", "Standard Programme Vertical Slice",
                    datetime.now(timezone.utc).date().isoformat(), "Staging", "Enterprise AGILE",
                    join_code, 3, "Core v2 UAT")
    check(report, "1_event_creation", bool(db.get_event(event_id)), db.get_event(event_id))

    programme = activity_modules(event_id)
    saved = db._safe_save_programme(event_id, programme, "Standard EXOS UAT")
    check(report, "2_programme_save", saved["ActivityCount"] == 5, saved)
    stages = db.get_programme_stages(event_id)
    check(report, "3_five_activities_configured", [s["StageName"] for s in stages] == [a[0] for a in ACTIVITIES],
          [{"name": s["StageName"], "scope": s.get("ParticipantScope"), "scoring": s.get("ScoringMode")} for s in stages])
    check(report, "4_teams_created", len(db.get_teams(event_id)) == 3, db.get_teams(event_id))

    players = []
    for index in range(6):
        player = db.join_player(join_code, f"UAT Participant {index + 1}", f"uat-device-{stamp}-{index + 1}")
        players.append(player)
    check(report, "5_participant_registration", len({p["ParticipantID"] for p in players}) == 6,
          {"registered": db.get_participant_count(event_id)})
    allocation = Counter(p["TeamID"] for p in players)
    check(report, "6_round_robin_assignment", sorted(allocation.values()) == [2, 2, 2], dict(allocation))

    restored = db.join_player(join_code, "UAT Participant 1", f"uat-device-{stamp}-1")
    check(report, "7_participant_reconnect", restored["ParticipantID"] == players[0]["ParticipantID"] and restored["TeamID"] == players[0]["TeamID"], restored)
    check(report, "8_facilitator_event_load", bool(db.get_event(event_id) and db.get_programme_stages(event_id) and db.get_teams(event_id)),
          {"event": event_id, "activities": len(stages), "teams": len(db.get_teams(event_id))})

    pipeline = stages[0]
    launched = db.set_event_stage(event_id, pipeline)
    check(report, "9_activity_launch", launched.get("ActivityID") == pipeline["ActivityID"], launched)
    visible = db.get_player_by_token(players[0]["SessionToken"])
    check(report, "10_participant_activity_visibility", _stage_id(visible) == pipeline["ActivityID"], visible.get("Stage"))

    representative_by_team = {}
    for player in players:
        representative_by_team.setdefault(player["TeamID"], player)
    for team_id, player in representative_by_team.items():
        db.save_submission(event_id=event_id, mission_id=pipeline["ActivityID"],
                           team_name=player["Team"], participant_name=player["Name"],
                           submission_type="PIPELINE", metric1="10", metric2="9", metric3="1",
                           session_token=player["SessionToken"])
    submissions = [s for s in db.get_submissions(event_id) if s["ActivityID"] == pipeline["ActivityID"]]
    check(report, "11_submission", len(submissions) == 3, {"count": len(submissions)})
    check(report, "12_facilitator_submission_read", len(db.get_canonical_submissions(event_id)) == 3,
          {"submission_ids": [s["SubmissionID"] for s in submissions]})
    for position, submission in enumerate(submissions, 1):
        db.update_submission_score(submission["SubmissionID"], position * 10, "UAT approved")
    reviewed = [s for s in db.get_submissions(event_id) if s["Status"] == "APPROVED"]
    check(report, "13_review_scoring", len(reviewed) == 3 and sum(float(s["Score"]) for s in reviewed) == 60,
          [{"id": s["SubmissionID"], "score": s["Score"]} for s in reviewed])

    next_stage = stages[1]
    db.set_event_stage(event_id, next_stage)
    check(report, "14_next_activity", _stage_id(db.get_player_by_token(players[1]["SessionToken"])) == next_stage["ActivityID"], next_stage["StageName"])

    nasi = stages[-1]
    db.set_event_stage(event_id, nasi)
    for player in players:
        db.save_submission(event_id=event_id, mission_id=nasi["ActivityID"], team_name=player["Team"],
                           participant_name=player["Name"], submission_type="NASI",
                           remarks="N - New Ideas: Test\nA - Areas for Improvement: Test\nS - Strengths: Test\nI - Implementation: Test",
                           session_token=player["SessionToken"])
    nasi_rows = [s for s in db.get_submissions(event_id) if s["ActivityID"] == nasi["ActivityID"]]
    check(report, "15_nasi_individual_submission", len(nasi_rows) == 6 and len({s["ParticipantID"] for s in nasi_rows}) == 6,
          {"count": len(nasi_rows)})
    check(report, "16_nasi_facilitator_readout", all(s["SubmissionType"] == "NASI" for s in nasi_rows),
          [{"participant": s["ParticipantName"], "status": s["Status"]} for s in nasi_rows])
    leaderboard = db.get_canonical_leaderboard(event_id)
    check(report, "17_results_leaderboard", len(leaderboard) == 3 and sum(float(r["Score"]) for r in leaderboard) == 60, leaderboard)

    db.create_event(second_id, "EXOS Staging", "UAT", "Standard Programme Duplicate",
                    datetime.now(timezone.utc).date().isoformat(), "Staging", "Enterprise AGILE",
                    second_code, 2, "Core v2 UAT")
    duplicate = db.duplicate_programme_configuration(event_id, second_id)
    copied = db.get_programme_stages(second_id)
    isolated = not db.get_players(second_id) and not db.get_submissions(second_id) and not any(r["Score"] for r in db.get_canonical_leaderboard(second_id))
    check(report, "18_second_event_isolation", isolated, {
        "participants": len(db.get_players(second_id)), "submissions": len(db.get_submissions(second_id)),
        "leaderboard": db.get_canonical_leaderboard(second_id),
    })
    config_projection = lambda rows: [(r["StageName"], r.get("DurationMinutes"), r.get("SubmissionType"), r.get("ParticipantScope"), r.get("ScoringMode")) for r in rows]
    check(report, "programme_reuse", config_projection(stages) == config_projection(copied) and duplicate["ActivityCount"] == 5,
          {"source": config_projection(stages), "copy": config_projection(copied), "duplicate": duplicate})
    counts = db.assert_core_v2_only()
    check(report, "hard_assertions", counts == {"LEGACY_RUNTIME_CALLS": 0, "GOOGLE_SHEETS_RUNTIME_CALLS": 0}, counts)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


def _stage_id(player):
    return str((player or {}).get("Stage", {}).get("ActivityID", ""))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="STD-UAT")
    parser.add_argument("--output", default="outputs/standard-core-v2-uat.json")
    args = parser.parse_args()
    report = run(args.prefix)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
