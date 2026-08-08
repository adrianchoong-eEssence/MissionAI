# EXOS CORE v2 — Queue 10: Real Identity + Grouping Torture Test

Date: 2026-08-08
Branch: `feature/exos-core-v2`

## Execution scope

- **Mode:** STAGING-only required by objective
- **Staging credentials/secrets in this shell:** **BLOCKED**
- **Production modified:** NO

## Queue 10 identity tests

### TEST A — Double Click

- Request: two near-simultaneous joins for same EventID / First+Last / DeviceID
- Result: **PASS**
- Observed: one persisted `ParticipantID`, one persisted `TeamID`
- Duplicate participant IDs created: **0**
- Duplicate team allocations created: **0**

### TEST B — Repeated Request (10x)

- Request: 10 rapid repeated joins for same EventID / identity / DeviceID
- Result: **PASS**
- Observed: one stable `ParticipantID`, one stable `TeamID`, no second allocation path exercised in local deterministic model

### TEST C — Same Name, Different Device

- Request: same EventID / First+Last on different DeviceID
- Result: **PASS** (contract-path)
- Observed: same-name same-event second request returns `RecoveryRequired=True` and `Ambiguous=True`; no second allocation in mocked recovery contract test.

### TEST D — Duplicate First Name

- Request: `John Tan`, `John Lee`, `John Wong`, `John Lim` across distinct devices
- Result: **PASS**
- Observed: 4 identities and 4 team assignments (`n=4`)

### TEST E — Reconnect

- Request: close/open and restore session on same identity; plus reconnect replay
- Result: **PASS**
- Observed: same `ParticipantID` and same `TeamID` on repeated restores

### TEST F — Admin Recovery

- Request: wrong-device duplicate/collision recovery, reset, and reassignment through audited control-plane calls
- Result: **PASS**
- Observed: recovery helper path is available, and admin control mutations route to:
  - `rpc/exos_admin_set_submission_override`
  - `rpc/exos_admin_transfer_leader`
  - `rpc/exos_admin_move_participant`
  - `rpc/exos_admin_duplicate_decision`
  - `rpc/exos_reset_event_registration`

## Staging execution attempt

Attempted:

```bash
python3 scripts/exos_scale_readiness_audit.py --mode staging --event-id EVT-QUE10 --join-code TEST --output outputs/queue10_identity_staging_probe.json
```

Result: **BLOCKED**

- Failure reason: missing Streamlit/GCP/Supabase secrets and service-account JSON in workspace
  - `streamlit.runtime.secrets.StreamlitSecretNotFoundError`
  - `FileNotFoundError: mission_ai_service_account.json`

## Test baseline run

- `python3 -m pytest -q tests/test_foundation_p0_gates.py tests/test_v2_registration_concurrency_queue2.py tests/test_participant_identity_engine.py tests/test_queue10_identity_torture.py tests/test_queue9_core_v2_runtime_paths.py`
- Result: **46 passed**

## Recommendation

Local identity and grouping correctness is green and consistent with Foundation + Queue 2 contracts.  
Queue 10 cannot be fully completed in this environment until staging secrets/runtime are available, per scope.
