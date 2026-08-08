# EXOS CORE v2 — Queue 9: Real Staging Programme Migration + Multi-Event Proof

Date: 2026-08-08
Branch: feature/exos-core-v2

## Result summary

We cannot execute live staging event creation or multi-event simulation from this workspace yet because authenticated staging credentials are not available in the current environment.

- **Production changed:** NO
- **Branch:** `feature/exos-core-v2`

## Execution status

### Environment gate
- Authorized staging/project runtime credentials: **BLOCKED**
- `.streamlit/secrets.toml` or equivalent runtime credentials in this shell: **NOT FOUND**
- Result: live Queue 9 end-to-end staging run **BLOCKED**

### Required flow status (live execution)

| Flow | Status |
|---|---|
| Standard event (A) | **FAIL** *(blocked: staging runtime unavailable)* |
| Formula R.A.C.E. event (B) | **FAIL** *(blocked: staging runtime unavailable)* |
| Location/Walk Hunt event (C) | **FAIL** *(blocked: staging runtime unavailable)* |
| Multi-event simultaneous operation | **FAIL** *(blocked: staging runtime unavailable)* |
| EventID isolation | **FAIL** *(not executed live)* |
| RACE visual verification | **FAIL** *(not executed live)* |
| Google Sheets runtime calls detected in Core v2 | **NO** *(for canonical participant/runtime paths validated below; legacy non-live reads in unrelated screens remain unchanged)* |

## Non-destructive offline verification performed

- **Code-path verification for canonical runtime joins**:
  - `screens/participant.py` join flow uses runtime-only path:
    - `runtime.join_player(...)`
    - `db.join_player_by_code(...)`
    - `runtime.join_player` delegates to runtime RPC in `data/google_sheets.py`.
    - No direct non-runtime Google Sheets insertion path is used for canonical participant join.
  - `screens/formula_race_captain.py` has no Google Sheets imports and only uses `data.runtime_database` runtime methods.
- **Cross-event leakage hardening:**
  - `runtime_database` contract tests and schema assertions already enforce EventID-scoped reads/updates for key tables and RPCs (e.g. identity + programme tests, race migration tests).

## Offline tests executed

The following test suites passed in this environment:

- `python3 -m pytest -q tests/test_programme_builder_reuse.py`
- `python3 -m pytest -q tests/test_formula_race_runtime_paths.py`
- `python3 -m pytest -q tests/test_formula_race_live_activation.py`
- `python3 -m pytest -q tests/test_formula_race_operations.py`
- `python3 -m pytest -q tests/test_formula_race_parallel_checkpoints.py`
- `python3 -m pytest -q tests/test_runtime_programme.py`
- `python3 -m pytest -q tests/test_participant_identity_engine.py`
- `python3 -m pytest -q tests/test_concurrent_join_idempotency.py`
- `python3 -m pytest -q tests/test_v2_registration_concurrency_queue2.py`
- `python3 -m pytest -q tests/test_road_hunt_team_missions.py`
- `python3 -m pytest -q tests/test_exos_stabilisation.py`
- `python3 -m pytest -q tests/test_aia_customer_contact.py`
- `python3 -m pytest -q tests/test_google_sheets_runtime_publication.py`
- `python3 -m pytest -q tests/test_control_runtime_authority.py`
- `python3 -m pytest -q tests/test_runtime_export_services.py`
- `python3 -m pytest -q tests/test_formula_race_identity_policy.py`
- `python3 -m pytest -q tests/test_google_sheets_resilience.py`

All above are non-destructive/local tests and passed in this environment.

## Reproduction plan for live Queue 9 (pending credentials)

1. Provision/verify isolated staging project and streamlit deployment from Queue 8.
2. Create three disposable events via staging runtime:
   - Standard/Mission AI event: registration + standard + NASI.
   - Formula R.A.C.E.: 10 teams with captain login and checkpoint flow.
   - Walk Hunt/Road Rally: GPS checkpoint + answer/photo submission.
3. Execute the three journeys simultaneously.
4. Verify strict EventID/Event scope on every read/write table (participants/teams/sessions/activities/submissions/credits/wallet/marketplace/GPS/projector).
5. Capture final proof JSON and screenshots, then cleanup disposable records.

## Known blockers before Queue 9 can be completed

1. No authorized staging credentials in this shell.
2. No staging runtime project connection details (separate from production) available for safe mutation.
3. No staging Streamlit endpoints to point to dedicated staging runtime in this environment.

### Additional Queue 9 offline test added

- `python3 -m pytest -q tests/test_queue9_core_v2_runtime_paths.py`
- Result: **3 passed**
