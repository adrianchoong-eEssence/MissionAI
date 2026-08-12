# EXOS UAT Status Baseline

> Date frozen with this baseline: 2026-08-12

## AUTOMATED VERIFIED

Command-level verification executed in this repo state:

- `pytest tests/test_standard_core_v2_vertical_slice.py` → **PASS** (12)
- `pytest tests/test_standard_participant_access_recovery.py tests/test_exos_core_v2_staging_journey_cleanup.py` → **PASS** (17)
- `pytest tests/test_facilitator_team_identity.py tests/test_projector_broadcast.py` → **PASS** (12)
- `pytest tests/test_participant_score_credit_display.py tests/test_live_event_console_runtime.py tests/test_nasi_results.py` → **PASS** (13)
- `outputs/standard-core-v2-uat.json` and `outputs/aia-weekend-core-v2.json` contain:
  - standard UAT pass markers across registration, launch, submissions, review, ranking and destination isolation
  - AIA-WE-260810081110 event IDs and join codes
  - hard assertions for `LEGACY_RUNTIME_CALLS=0` and `GOOGLE_SHEETS_RUNTIME_CALLS=0`

Known automated known-failures in this run (tracked backlog):

- `tests/test_core_v2_facilitator_staging.py` currently has 1 UI text expectation failure against the review button formatting and 1 legacy RPC expectation assertion mismatch with the current canonical RPC (`exos_v2_standard_transition_submission`).

These are non-blocking baseline blockers, kept only for memory of test fixture drift.

## HUMAN UAT VERIFIED (as of baseline evidence)

- Admin Core v2 event visibility
- Programme Builder save/publish and programme validation
- AIA Lower/Upper event isolation
- Participant registration + team assignment
- Participant same-device and different-device recovery path
- Team persistence and identity recovery without reallocation
- Pipeline launch and participant visibility
- Participant submission persistence and visibility
- Facilitator reads submissions
- Review/Scoring
- Helium Stick execution contract
- Non-scoring handling
- Live ranking + projector projection
- Performance views visible to participant/facilitator/projector

## BACKLOG / NOT YET CERTIFIED

- Production hardening for 250+ participant scale remains outside this frozen baseline.
- One-off UI wording/expectation mismatch in facilitator review test fixture (`test_core_v2_facilitator_staging.py`) remains non-blocking for this memory baseline.
- Mobile polish and journey redesign items remain intentionally excluded from core contract changes.
