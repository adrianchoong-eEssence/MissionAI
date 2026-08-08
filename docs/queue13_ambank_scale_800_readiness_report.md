# EXOS CORE v2 — QUEUE 13: AMBANK SCALE GATE (800 PARTICIPANTS)

Date: 2026-08-08  
Branch: `feature/exos-core-v2`

## Scope

Run as the AmBank readiness gate for 800 participants on **STAGING ONLY**.

## Execution summary

- **Mode requested:** real staging, non-destructive
- **Auth/secrets in this runtime:** **BLOCKED / unavailable**
  - missing Streamlit secrets (`.streamlit/secrets.toml`)
  - missing service account key (`mission_ai_service_account.json`)
  - missing Supabase runtime credential bootstrap in this shell

## Real-service attempt

Command:

```bash
python3 scripts/exos_scale_readiness_audit.py --mode staging --event-id EVT-AMBANK-800 --join-code AMB800 --teams 16 --profiles 800 --workers 160 --output outputs/queue13_800_staging_attempt.json
```

Result: **FAIL** (execution blocked before runtime operations).

Observed failure chain:

- `streamlit.runtime.secrets.StreamlitSecretNotFoundError`
- `FileNotFoundError: 'mission_ai_service_account.json'`

## Non-destructive local fallback probe (for readiness context only)

Because staging credentials are unavailable, a local multi-event burst model was executed:

- 800 total participants
- simultaneous events:
  - `EVT-AMBANK-MISSION` (360)
  - `EVT-AMBANK-RACE` (260)
  - `EVT-AMBANK-GPS` (180)
- concurrent registration, reconnect, activity reads, structured submissions, facilitator reads
- balanced load distribution with idempotent same-device double-join checks

Captured artifact: `outputs/queue13_800_local_realistic.json`

## Required metrics (model result)

- 800 pax: **FAIL**
- Registration p95: **0.208 ms**
- Registration p99: **0.224 ms**
- Reconnect p95: **0.000 ms**
- Submission p95: **0.000 ms**
- Facilitator read p95: **0.000 ms**
- Error rate: **0.0**
- Duplicates: **0** participant, **0** team allocation
- Lost submissions: **0**
- DB peak connections: **not-applicable-local**
- Contention: **0**

## Required guardrails verified in local model

- zero EventID leakage: **PASS (0)**
- zero TeamID leakage: **PASS (0)**
- zero duplicate allocation: **PASS (0)**
- zero silent identity merge: **PASS (0)**

## Recommended safe participant ceiling

**Do not increase; still unknown.**  
Real staging run did not execute; therefore no production claim can be made yet.

**Safe ceiling remains unchanged: Not AmBank-ready until staging 800-pax real-service campaign completes.**

## Final decision

**DO NOT DECLARE AMBANK-READY**
