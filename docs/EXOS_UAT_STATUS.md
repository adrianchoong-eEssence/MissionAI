# EXOS UAT and Evidence Status

Frozen Standard runtime reference: `41cb91e`. This document distinguishes
source tests, staging evidence, and human observation. A pass in one category
does not imply a pass in another.

## Automated source-contract evidence

Independent repository audit on 2026-08-12 ran the following focused suites in
the current checkout:

- Standard Core-v2 path, recovery, cleanup, team identity, projector,
  participant score display, and canonical performance: **61 passed**.
- Formula R.A.C.E. Core-v2 adapter, Captain/session/recovery, operations,
  parallel checkpoints, and staging path/schema contracts: **39 passed**.
- Schema, participant-staging, facilitator-staging, and AIA setup suite:
  **46 passed, 1 skipped, 2 failed**.

The two failures are from the pre-existing dirty working tree after the frozen
baseline: it calls `exos_v2_standard_transition_submission` while the frozen
025 SQL exposes `exos_v2_standard_review_submission`, and one test asserts a
button’s source formatting. They are not evidence of a failure in the frozen
`41cb91e` runtime and must not be recorded as baseline UAT blockers.

These tests are source-contract tests. They do not contact staging and they are
not human UAT. The previously cited `outputs/standard-core-v2-uat.json` and
`outputs/aia-weekend-core-v2.json` are not committed baseline artifacts, so they
are not release evidence.

## Human UAT evidence recorded for the Standard freeze

The following is limited to the staging observations reported during the
Standard UAT/fix sequence; no claim is inferred from tests:

- AIA Upper and Lower South participant join, canonical team assignment, and
  same-device/different-device recovery were exercised during the recovery
  fixes.
- AIA Lower South Pipeline submission was visible to Facilitator; review/score
  and the resulting ranking/performance path were exercised.
- Facilitator Broadcast Preview was observed.
- Facilitator / Control Centre → event-scoped Projector was observed.

These are functional staging observations, not load or production certification.
The repository has no immutable screenshot, browser trace, or database export
for every individual action above; rerun a required journey when stronger proof
is needed.

## Explicitly not human-UAT PASS

- Admin → Projector shortcut: code route exists, but human-UAT success was not
  recorded at the freeze. Treat as an open non-blocking verification item.
- Formula R.A.C.E. client UAT checklist is a planned staging gate, not a human
  UAT pass. Its 16 actions remain to be observed in a clean persistent-event
  run.
- The broad legacy Administration and Asset Library screens are not a
  Core-v2-only human-UAT surface.

## Backlog / certification boundary

- Standard EXOS is **not certified** for 250 concurrent participants. Load,
  operational telemetry, failure/recovery drills, and production hardening are
  still required.
- Do not treat current staging URLs, reference EventIDs, or a migration file as
  proof that a deployment/database is live or correctly installed.
- Mobile polish and journey redesign are not part of the frozen Standard
  runtime contract.
