#!/usr/bin/env python3
"""Prepare the two real AIA weekend events on Standard EXOS Core v2 staging."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
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
COUNTRIES = (
    ("Korea", "🇰🇷"),
    ("Japan", "🇯🇵"),
    ("India", "🇮🇳"),
    ("Malaysia", "🇲🇾"),
    ("Philippines", "🇵🇭"),
    ("Thailand", "🇹🇭"),
)
PROGRAMME = (
    ("Launch App / Country Assignment", "NONE", "TEAM", "NON_SCORING", 15, "Briefing"),
    ("Pipeline", "PIPELINE", "TEAM", "TEAM_COMPETITIVE", 20, "Standard Activity"),
    ("Helium Stick", "HELIUM", "TEAM", "NON_SCORING", 15, "Standard Activity"),
    ("Key Punch", "KEYPUNCH", "TEAM", "TEAM_COMPETITIVE", 20, "Standard Activity"),
    ("Lunch / Break", "NONE", "TEAM", "NON_SCORING", 60, "Break"),
    ("Catalyst Challenge", "CATALYST", "TEAM", "ENTERPRISE", 45, "Catalyst"),
    ("NASI", "NASI", "INDIVIDUAL", "NON_SCORING", 15, "Debrief"),
)


def next_saturday(today=None):
    today = today or date.today()
    return today + timedelta(days=(5 - today.weekday()) % 7)


def require_staging(db):
    if os.getenv("EXOS_ENV", "").strip().lower() != "staging":
        raise RuntimeError("EXOS_ENV=staging is mandatory.")
    host = (urlparse(db._client.url).hostname or "").lower()
    if not host or host in KNOWN_PRODUCTION_HOSTS:
        raise RuntimeError(f"Refusing non-staging Supabase host: {host or 'missing'}")
    if not db.can_publish:
        raise RuntimeError("SUPABASE_SECRET_KEY is required for staging event setup.")


def allocate_country_pool(upper_count, lower_count):
    upper_count, lower_count = int(upper_count), int(lower_count)
    if upper_count < 1 or lower_count < 1:
        raise ValueError("Each event must have at least one active group.")
    if upper_count + lower_count > len(COUNTRIES):
        raise ValueError("The two events cannot exceed six active groups in total.")
    upper = COUNTRIES[:upper_count]
    lower = COUNTRIES[upper_count:upper_count + lower_count]
    return upper, lower


def team_configuration(event_id, country_allocation):
    allocation = list(country_allocation)
    identities = [str(country).strip().casefold() for country, _ in allocation]
    if not allocation or len(identities) != len(set(identities)):
        raise ValueError("An event country allocation must be non-empty and unique.")
    return [
        {
            "TeamID": f"{event_id}-TEAM-{position:02d}",
            "TeamName": country,
            "Country": country,
            "Flag": flag,
        }
        for position, (country, flag) in enumerate(allocation, 1)
    ]


def agile_programme(event_id):
    modules = []
    for position, (name, submission, scope, scoring, minutes, content_type) in enumerate(PROGRAMME, 1):
        module_id = f"{event_id}-MOD-{position:02d}"
        activity_id = f"{event_id}-ACT-{position:02d}"
        details = {
            "ActivityID": activity_id,
            "ModuleID": module_id,
            "ActivityType": "MARKER" if content_type == "Break" else "STANDARD",
            "ContentType": content_type,
            "ScoringMode": scoring,
            "SubmissionType": submission,
            "ParticipantScope": scope,
            "EvidenceRequired": submission not in {"NONE", "HELIUM"},
            "ParticipantTask": (
                "Break marker — no participant submission."
                if content_type == "Break"
                else f"Complete {name} as briefed by the facilitator."
            ),
            "FacilitatorInstructions": (
                "Schedule marker only. Do not launch or score."
                if content_type == "Break"
                else f"Brief, launch and monitor {name}."
            ),
            "Credits": 100 if scoring == "TEAM_COMPETITIVE" else 0,
            "RuntimeEligible": content_type != "Break",
        }
        stage_type = "Lunch / Break" if content_type == "Break" else "Activity"
        activity = {
            "EventID": event_id,
            "ProgrammeID": f"{event_id}-PROGRAMME",
            "ModuleID": module_id,
            "ActivityID": activity_id,
            "ActivityOrder": 1,
            "StageNo": position,
            "StageName": name,
            "StageType": encode_module_stage_type(name, 1, stage_type),
            "DurationMinutes": minutes,
            "IsActive": "Yes",
            "ParticipantMessage": details["ParticipantTask"],
            "FacilitatorInstruction": encode_activity_details(details),
            "ContentType": content_type,
            "SubmissionType": submission,
            "ParticipantScope": scope,
            "ScoringMode": scoring,
        }
        modules.append({
            "EventID": event_id,
            "ProgrammeID": f"{event_id}-PROGRAMME",
            "ModuleID": module_id,
            "ModuleName": name,
            "ModuleOrder": position,
            "Day": 1,
            "Activities": [activity],
        })
    return modules


def _create_event(db, event_id, join_code, name, department, event_date, pax,
                  country_allocation, venue, facilitator, allocation_group_id,
                  paired_event_id):
    teams = len(country_allocation)
    db.create_event(
        event_id, "AIA", department, name, str(event_date), venue,
        "AGILE", join_code, teams, facilitator,
    )
    db.update_event_metadata(event_id, {
        "ExpectedParticipants": int(pax),
        "DurationHours": 8.0,
        "TeamTheme": "Countries",
        "CountryPool": [country for country, _ in COUNTRIES],
        "CountryAllocationGroupID": allocation_group_id,
        "PairedEventID": paired_event_id,
        "AssignedCountries": [country for country, _ in country_allocation],
        "CrossEventAllocationValidated": True,
        "ActiveTeamCount": int(teams),
        "Provisional": True,
    })
    db.replace_event_teams(event_id, team_configuration(event_id, country_allocation))


def _assert_empty_runtime(db, event_id):
    evidence = {
        "participants": len(db.get_players(event_id)),
        "sessions": len(db._rows("participant_sessions_v2", {
            "event_id": f"eq.{event_id}", "select": "session_token",
        })),
        "submissions": len(db.get_submissions(event_id)),
        "scores": len(db._rows("score_transactions_v2", {
            "event_id": f"eq.{event_id}", "select": "score_transaction_id",
        })),
        "runtime_state": db.get_event_state(event_id),
    }
    if any(evidence[key] for key in ("participants", "sessions", "submissions", "scores")) or evidence["runtime_state"]:
        raise AssertionError(f"Destination operational state is not empty: {evidence}")
    return evidence


def prepare(db, *, event_date, upper_pax=26, lower_pax=36, upper_teams=2,
            lower_teams=4, venue="TBC", facilitator="TBC", prefix="AIA-WE"):
    require_staging(db)
    upper_countries, lower_countries = allocate_country_pool(upper_teams, lower_teams)
    stamp = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    upper_id = f"{prefix}-{stamp}-UPPER"
    lower_id = f"{prefix}-{stamp}-LOWER"
    allocation_group_id = f"{prefix}-{stamp}-COUNTRIES"
    upper_code = db.create_new_join_code()

    _create_event(db, upper_id, upper_code, "AIA Upper South", "Upper South",
                  event_date, upper_pax, upper_countries, venue, facilitator,
                  allocation_group_id, lower_id)
    saved = db._safe_save_programme(upper_id, agile_programme(upper_id), "AGILE Standard")
    if saved["ModuleCount"] != 7 or saved["ActivityCount"] != 7:
        raise AssertionError(saved)

    lower_code = db.create_new_join_code()
    _create_event(db, lower_id, lower_code, "AIA Lower South", "Lower South",
                  event_date, lower_pax, lower_countries, venue, facilitator,
                  allocation_group_id, upper_id)
    duplicate = db.duplicate_programme_configuration(upper_id, lower_id)
    isolation = _assert_empty_runtime(db, lower_id)

    upper_stages = db.get_programme_stages(upper_id)
    lower_stages = db.get_programme_stages(lower_id)
    projection = lambda rows: [
        (row["StageName"], row.get("DurationMinutes"), row.get("SubmissionType"),
         row.get("ParticipantScope"), row.get("ScoringMode"), row.get("ContentType"))
        for row in rows
    ]
    if projection(upper_stages) != projection(lower_stages):
        raise AssertionError("Programme configuration duplication mismatch.")
    all_countries = []
    for event_id in (upper_id, lower_id):
        countries = [row["Country"] for row in db.get_teams(event_id)]
        if len(countries) != len({country.casefold() for country in countries}):
            raise AssertionError(f"Duplicate country in {event_id}: {countries}")
        all_countries.extend(countries)
    if len(all_countries) != len({country.casefold() for country in all_countries}):
        raise AssertionError(f"Duplicate country across paired events: {all_countries}")

    counts = db.assert_core_v2_only()
    return {
        "agile_template_ready": True,
        "event_date": str(event_date),
        "upper": {
            "event_id": upper_id, "join_code": upper_code,
            "provisional_pax": int(upper_pax), "provisional_teams": int(upper_teams),
            "countries": [row["Country"] for row in db.get_teams(upper_id)],
        },
        "lower": {
            "event_id": lower_id, "join_code": lower_code,
            "provisional_pax": int(lower_pax), "provisional_teams": int(lower_teams),
            "countries": [row["Country"] for row in db.get_teams(lower_id)],
        },
        "editable_team_count": True,
        "editable_pax_count": True,
        "country_allocation_group_id": allocation_group_id,
        "cross_event_country_uniqueness": "PASS",
        "programme_duplication": "PASS",
        "duplicate_evidence": duplicate,
        "destination_isolation": isolation,
        **counts,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-date", default=str(next_saturday()))
    parser.add_argument("--upper-pax", type=int, default=26)
    parser.add_argument("--lower-pax", type=int, default=36)
    parser.add_argument("--upper-teams", type=int, default=2)
    parser.add_argument("--lower-teams", type=int, default=4)
    parser.add_argument("--venue", default="TBC")
    parser.add_argument("--facilitator", default="TBC")
    parser.add_argument("--prefix", default="AIA-WE")
    parser.add_argument("--output", default="outputs/aia-weekend-core-v2.json")
    args = parser.parse_args()
    report = prepare(
        get_standard_database(), event_date=args.event_date,
        upper_pax=args.upper_pax, lower_pax=args.lower_pax,
        upper_teams=args.upper_teams, lower_teams=args.lower_teams,
        venue=args.venue, facilitator=args.facilitator, prefix=args.prefix,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
