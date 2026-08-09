# Formula R.A.C.E. Client UAT Package (Queue B)

This document is the hands-on package for Adrian after the queue freeze.

## Scope
- Staging-only, Core v2-only Formula R.A.C.E.
- 1 persistent UAT event in staging
- No production references
- No clean-up/deletion of the persistent UAT event

## Runbook

### 1) Create persistent staging UAT event

From a terminal where staging credentials are loaded:

```bash
export EXOS_ENV=staging
export SUPABASE_URL=https://<staging-project-ref>.supabase.co
export SUPABASE_PUBLISHABLE_KEY=<publishable-key>
export SUPABASE_SECRET_KEY=<service-role-key>

EXOS_ENV=staging python3 scripts/exos_core_v2_create_staging_race_uat_event.py
```

Expected output:
- `EventID`
- `Join Code`
- `PIN report local path`
- JSON summary with:
  - `event_id`
  - `join_code`
  - `team_ids` (10 teams)
  - `activity_ids` (4 checkpoints)

Persist that output locally for this UAT.

## Required UAT artifacts

- **Persistent event**
  - 10 teams
  - 10 Team PINs
  - 4 checkpoints
- **Screens**
  - Facilitator: should show `EXOS CORE V2 — STAGING`
  - Captain: should show `EXOS CORE V2 — STAGING`
- **No legacy writes/checks**
  - `LEGACY_RUNTIME_CALLS = 0`
  - `GOOGLE_SHEETS_RUNTIME_CALLS = 0`

## One-time Team PIN report

The script writes one-time plaintext PIN report locally at:
- `/tmp/CORE-V2-RACE-UAT-EVT-..._race_uat_pins.txt`

This file must be kept local-only for UAT handover.

## UAT Staging entry points

- Facilitator staging URL: `https://<adrian-staging-facilitator-app>`
- Captain staging URL: `https://<adrian-staging-captain-app>`

(Do not use production URLs.)

## Adrian UAT checklist

Use this checklist with the persistent EventID / Join Code.

1. Captain login
2. Wrong PIN
3. checkpoint display
4. submit proof
5. facilitator receives submission
6. approve/reject/resubmit action path
7. Credits update
8. wallet update
9. marketplace purchase
10. close browser
11. reconnect
12. same TeamID/session
13. build status
14. judging
15. result
16. championship

## Recommended data capture fields (for return)

- `UAT EventID`
- `Join Code`
- `PIN report path`
- `Facilitator URL`
- `Captain URL`
- `Core v2 only`
- `Legacy runtime calls`
- `Google Sheets runtime calls`

## Gate

READY FOR ADRIAN UAT = YES only after:
- persistent UAT exists and is operational
- both staging URLs render and resolve
- all 16 checklist items are observed in one clean pass
- displayed counters are exactly zero for both screens
