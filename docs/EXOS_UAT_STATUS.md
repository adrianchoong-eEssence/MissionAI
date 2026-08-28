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

## Team Formation V1 evidence boundary

`036_exos_core_v2_team_formation_v1.sql` is an additive Sprint 2 source
contract. Focused source tests cover configuration gating, opaque hashed
credential identity, duplicate display names, retry/recovery preservation,
capacity, balanced random allocation at 66 and 250 participants, preassigned
claim, concurrent Captain claim, facilitator transfer, Formula R.A.C.E.
non-regression, and the frozen 035 file guard. An optional local PostgreSQL
execution test requires an explicitly supplied local DSN.

The pre-harness credential-free local source baseline was **703 passed, 2
skipped**. The Team Formation certification harness adds five local
source-contract checks; the post-harness credential-free run completed with
**708 passed, 2 skipped**. This remains source-contract evidence only.

`scripts/certify_team_formation_v1.py` now provides the required genuine
concurrent staging harness: 66 RANDOM_ASSIGN, 250 RANDOM_ASSIGN, 250
PREASSIGNED, Captain contention, event isolation, ten-table R.A.C.E. sentinel,
and deterministic `CERT-TF-*` cleanup. It has not run against staging in this
workspace because no staging publishable/service credentials or direct
PostgreSQL cleanup DSN were supplied. Do not mark the database concurrency
certification as PASS until Kai's credentialed run reports both an identical
R.A.C.E. sentinel and zero certification residue.

This is not staging, load, or human-UAT evidence. The required 66- and
250-participant database-concurrency certifications remain pending and must use
disposable events only after migration review.

These tests are source-contract tests. They do not contact staging and they are
not human UAT. The previously cited `outputs/standard-core-v2-uat.json` and
`outputs/aia-weekend-core-v2.json` are not committed baseline artifacts, so they
are not release evidence.

## Theme Park Race V1 evidence boundary

The generic `THEME_PARK_RACE` engine has focused source-contract coverage for
configuration-only selection, activity `race_station` projection, configured
routes, lifecycle derivation, Captain/reconnect projection, rejection and
resubmission routing, facilitator review/status, projector progress/scoring,
and the 037 no-new-table server guard. This is source evidence only. It does
not populate Genting content, create an event, run a staging journey, or
constitute human UAT. Read-only staging catalog reconciliation separately
established the final 037/037a/038/039 semantic contract; that is not human-UAT
or load evidence.

The 66/250 Team Formation concurrent-database certification remains separately
pending. Theme Park Race source tests must never be reported as that harness
having run or as Team Formation load certification.

## OPEN_MISSION_BOARD source boundary

The 038 Theme Park Race source extension has unit/source-contract coverage.
Read-only catalog reconciliation established the expected installed semantic
contract, but does not constitute a staging journey, load test, or human UAT.
Its use remains subject to a disposable-event validation and the separate Team
Formation 66/250 database-concurrency certification.

`039_theme_park_race_review_reopen_contract.sql` adds the scoped
OPEN_MISSION_BOARD facilitator review/reopen contract. Its final semantic
contract was reconciled read-only against staging; that is not disposable-event
certification or completed Genting UAT.

`040_theme_park_race_terminal_lifecycle.sql` addresses the reported End-control
defect by mapping persisted `CLOSED` to terminal `ENDED`, adding persisted
`HELD`, and server-blocking restart and post-end Mission operational writes.
Staging migration history records its installation; that does not constitute
human-UAT evidence.

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
