# Formula R.A.C.E. Handover

## Boundary

Formula R.A.C.E. is a separate product workflow. Standard Core v2 gives it
shared platform constraints and Core-v2 primitives; it does **not** make R.A.C.E.
feature-complete, staging-validated, human-UAT-passed, production-ready, or
load-certified.

Read this file before changing `FormulaRace.py`, `screens/formula_race.py`,
`screens/formula_race_captain.py`, `data/formula_race_core_v2_adapter.py`, RACE
migrations, or its staging scripts.

## Current implementation — code only

The Core-v2 staging implementation has dedicated surfaces and an adapter:

- Facilitator/race control: `FormulaRace.py` → `screens/formula_race.py`
- Captain: `screens/formula_race_captain.py`, deployed as its own Captain entry
  surface
- Data boundary: `FormulaRaceCoreV2StagingAdapter`
- Staging guard: counters reject forbidden legacy paths and Google-Sheets-like
  paths; the staging shell checks both counters

The current `Participant.py` staging branch stops at the Standard participant
surface before its lower R.A.C.E. router is reachable. Do not claim a Standard
participant join-code handoff to Captain is deployed; use the dedicated Captain
entry surface until that routing is explicitly changed and tested.

Code implements these product-specific capabilities:

- Team/Captain PIN access, one active device/session behavior, same-device
  restoration, and PIN-based cross-device Captain recovery
- Four parallel checkpoint activities, proof submission/evidence, review, and
  resubmission-related state
- Credits earned, wallet/balance, marketplace purchases, and purchase history
- Build status, judging rows, race-result rows with penalties/bonuses, and
  championship/ranking presentation
- EventID/TeamID-scoped reads and writes in the R.A.C.E. adapter

“Implemented” above means a code path and source-contract tests exist. It does
not claim that each operation is atomic under load, successfully deployed, or
observed by a human in staging.

## Current evidence status

- **Automated source contracts:** focused R.A.C.E. adapter, Captain,
  recovery/session, operations, parallel-checkpoint, and staging-path/schema
  tests passed in the 2026-08-12 repository audit (39 tests).
- **Staging runner:** `scripts/exos_core_v2_staging_race_vertical_slice.py`
  exists. Its existence is not proof it ran successfully against the named
  staging event.
- **Human UAT:** no completed 16-step persistent-event client UAT record is
  committed in this repository. Treat Captain login, checkpoint submission,
  review/resubmit, wallet/purchase, reconnect, build, judging, results, and
  championship as requiring human staging UAT.
- **Production/load:** not certified.

## R.A.C.E. migrations and installed-state rule

Core-v2 R.A.C.E. relies on the Core schema foundation plus R.A.C.E.-specific
patches:

- 020 Core v2 schema foundation
- 022 Core-v2 team/Captain access
- 023 Core-v2 race-results locking
- 024 Core-v2 Captain team-access recovery
- 027 Core-v2 R.A.C.E. atomic operations (depends on 020, 022, 023, and 024)
- 028 Core-v2 R.A.C.E. idempotent manual credit adjustments (depends on 020 and 027)
- 030 Configurable R.A.C.E. event architecture (depends on 020, 022–024,
  027–029). It adds event-scoped station, route, scoring, marketplace and
  judging configuration through `events_v2.event_payload`, plus guarded
  station submission/verification/ranking and a disposable-event reset RPC.
  It is a forward migration only; its installed status is **UNKNOWN**.

020’s rollback is not a R.A.C.E. forward migration. The older 015–019 Formula
R.A.C.E. migration series, its rollbacks, seeds, and verification scripts have
their own targets and assumptions; do not add them to a Core-v2 staging chain
without reading their headers and the current deployment checklist.

The repository contains no target-database migration-history export. Every
installation status is UNKNOWN from repository evidence until queried against
the intended staging database.

## What to inherit from Standard Core v2

- Event isolation and generic team identity rendering
- No silent legacy/Google Sheets fallback on the Core-v2 staging path
- Durable session/recovery patterns, adapted to Captain (not participant)
  authorization
- Scoped refresh rather than global full-app polling
- Event-scoped, display-only Projector/Broadcast separation where applicable
- Honest evidence labels: source tests ≠ staging execution ≠ human UAT ≠ load
  certification

## What must remain R.A.C.E.-specific

- Captain rather than Standard participant identity and one-active-device policy
- Checkpoint sequence/parallelism, checkpoint proof, resubmission, and review
- Credits Earned, Wallet, Marketplace, Purchases, and Build Status
- Judging, penalties/bonuses, race result, result locking/unlocking, and
  Championship ranking/tie-break rules

Team Formation V1 is a separate Core capability for events that explicitly opt
in through `event_payload.TeamFormation`. It must not configure, redirect, or
alter Formula R.A.C.E. Team PIN/Captain access. Formula R.A.C.E. events are not
Team Formation fixtures or load-test targets.

Theme Park Race V1 is likewise a separate configuration-selected engine. It
uses only `RaceConfiguration.EngineKind = THEME_PARK_RACE`; its route/Captain
guard returns without action for Formula R.A.C.E. events. It must not be used
to change R.A.C.E. Team PIN, checkpoint, wallet, judging, result or projector
behavior.

Never collapse R.A.C.E. championship score, credits earned, and wallet balance
into one Standard score/credit field. Never apply Standard participant recovery
or Standard programme scoring assumptions to Captain access without an explicit
R.A.C.E. design and test.

## Configurable event architecture — source contract only

The R.A.C.E.-only Event Setup surface is configuration-driven. Station data is
stored as an event-scoped `RaceConfiguration` and mirrored into the existing
`activities_v2.activity_payload.race_station` when configuration is saved.
No R/A/C/E names, fixed station count, team count, or Marketplace catalogue are
Core concepts. Team routes are event/team scoped; a successful Captain
submission advances the route immediately, while verification controls the
official result and Credits separately. The Captain projection shows completed
and current route stations only.

`030_formula_race_configurable_event_architecture.sql` is deliberately not a
claim of deployment. Before an environment uses these paths, query its migration
history, apply the documented dependency chain to staging, and run the
disposable-event reset and route/verification UAT checklist. The protected UAT
event `CORE-V2-RACE-UAT-EVT-4CF0CEAF5F` must not be reset by the setup surface.

## Queue 2 canonical R.A.C.E. contracts

- Championship Score is the event/team sum of `score_transactions_v2.score_delta`.
- Credits Earned is the positive event/team sum of `credit_transactions_v2.amount`.
  Credits Spent is the absolute negative sum; Wallet Balance is their signed sum.
- A checkpoint approval reads separate `activity_payload.score_award` or existing
  `max_score`, and `credit_award` or existing `credits`, with stable submission
  idempotency keys so the values need not be equal.
- `participants_v2` may contain one labelled `RACE_CAPTAIN_TECHNICAL_ACTOR` per
  event/team only to satisfy Core-v2 activity and submission foreign keys. It is
  not Standard participant registration; Captain authority remains Team PIN plus
  team-access session.
- Live Championship Rank is Championship Score descending with TeamID ascending.
  Final locked rank is verified `time_ms + penalty_ms`, then TeamID ascending,
  persisted in `race_results_v2.ranking_position`. Current configuration does
  not make judging or bonus credits final-rank inputs.

## Legacy shell warning

The non-staging Facilitator branch still contains an older Google Sheets R.A.C.E.
shell. It is separate from the Core-v2 staging adapter and does not inherit the
Core-v2-only assertion. Do not use it as a fallback or cite it as R.A.C.E.
Core-v2 staging evidence.
