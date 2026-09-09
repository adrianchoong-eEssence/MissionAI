#!/usr/bin/env python3
"""AIA 250-client certification launcher; inert until explicitly authorised.

It delegates traffic generation to the certified Team Formation V1 runner. The
runner creates only fresh CERT-TF-/CERT-TPR- fixtures, requires staging host,
publishable/service keys, a test DSN and explicit confirmation, fingerprints
the protected R.A.C.E. sentinel, and cleans every fixture afterwards.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "certify_team_formation_v1.py"
REQUIRED_OPERATIONS = [
    "RANDOM_ASSIGN self-registration and recovery", "automatic PRESENT attendance writes", "workspace/reconnect reads",
    "Captain claim, transfer and recovery contention", "open-board selection", "participation roster selection",
    "photo/video submission contract", "facilitator review and participation/rubric score", "audited bonus adjustment",
    "projector projection and Mission Control/operator reads", "EventID isolation and fixture cleanup",
]
RANDOM_REGISTRATION_ASSERTIONS = [
    "250 canonical participant IDs from the fixed AIA random-registration endpoint",
    "25 teams balanced at 10 with no overfill or dual-team membership",
    "same-device retry returns the same ParticipantID and TeamID idempotently",
    "duplicate/similar display names remain separate canonical identities",
    "one canonical PRESENT attendance write per first registration",
    "same-device reconnect restores identity, team, attendance, and Captain authority",
]


def plan() -> dict:
    return {"Executed": False, "EventScope": "fresh CERT-TF-* and CERT-TPR-* fixtures only", "Participants": 250,
            "Distribution": "25 teams × 10 participants; RANDOM_ASSIGN", "RequiredOperations": REQUIRED_OPERATIONS,
            "AiaRandomRegistration": {"RPC": "exos_v2_aia_tech_register_random", "Assertions": RANDOM_REGISTRATION_ASSERTIONS,
                                      "ExecutionNote": "The installed fixed-event wrapper must be exercised against an empty disposable AIA UAT fixture under separately authorised load credentials; this launcher never reports that wrapper as PASS without that run."},
            "Runner": str(RUNNER.relative_to(ROOT)), "Execute": "EXOS_ENV=staging, CERT_TF_EXPECTED_HOST, SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SECRET_KEY, POSTGRES_TEST_DSN, CERT_TF_CONFIRM=RUN_DISPOSABLE_CERT_TF, then --execute",
            "Safety": "No AIA, Maxis, historical, or live EventID may be supplied or used as a fixture."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--report", default="outputs/aia-250-certification.json")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(plan(), indent=2, sort_keys=True)); return 0
    command = [sys.executable, str(RUNNER), "--execute", "--report", str(ROOT / args.report)]
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
