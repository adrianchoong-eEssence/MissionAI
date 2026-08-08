#!/usr/bin/env python3
"""Print a reproducible EXOS load-test plan. It never sends traffic."""
import argparse
import json

PROFILES = (70, 260, 800)
PHASES = ("registration_burst", "reconnect", "activity_read", "submission_burst", "facilitator_reads")

def plan(participants):
    return {"participants": participants, "target": "local_or_staging_only", "phases": [
        {"name": "registration_burst", "operations": participants},
        {"name": "reconnect", "operations": participants},
        {"name": "activity_read", "operations": participants * 3},
        {"name": "submission_burst", "operations": participants},
        {"name": "facilitator_reads", "operations": 30},
    ], "assertions": ["EventID isolation", "ParticipantID/TeamID reconnect stability", "no duplicate submission", "no cross-team wallet mutation"]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participants", type=int, choices=PROFILES)
    args = parser.parse_args()
    profiles = (args.participants,) if args.participants else PROFILES
    print(json.dumps({"safety": "PLAN ONLY — no network calls", "profiles": [plan(n) for n in profiles], "phases": PHASES}, indent=2))

if __name__ == "__main__":
    main()
