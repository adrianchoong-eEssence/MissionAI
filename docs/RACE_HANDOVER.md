# Formula R.A.C.E. Handover to Standard EXOS (Read-Only)

## Purpose

Do **not** modify R.A.C.E. runtime from this file.  
This page documents what Standard EXOS concepts Formula R.A.C.E. should inherit at the repository level and what must remain distinct.

## Canonical R.A.C.E. baseline event (staging)

- EventID: `CORE-V2-RACE-UAT-EVT-4CF0CEAF5F`
- Join code: `RACE4CF0CE`

From:
- `scripts/exos_core_v2_staging_cleanup.py`
- `scripts/exos_core_v2_patch_race_uat_roster.py`

## What RACE should inherit from Standard EXOS

- `NO GOOGLE SHEETS RUNTIME` for canonical event state.
- `NO LEGACY RUNTIME FALLBACK` on canonical flow.
- Event-scoped isolation (no cross-event state bleed).
- Generic identity resolution (`TeamIdentity` first, then `TeamName`, then `TeamID`).
- Participant session persistence and recovery patterns where relevant.
- Scoped refresh over full-app poll loops.
- Canonical ranking snapshots and display patterns.
- Broadcast/Projector separation (display-only projector path).
- `assert_core_v2_only`-style hard checks in staging shell.

## What MUST remain R.A.C.E.-specific

- Captain identity/session model.
- One active captain/device contract.
- One active checkpoint submission model.
- Captain lock/recovery semantics.
- Wallet/build/judging/race-result contracts.
- Marketplace, penalties/bonuses, race result lock/unlock.
- Championships/legacy race totals and tie-break behavior.
- Event-specific race lifecycle controls.

## Do not merge these concepts

- A single global score/credit concept for both systems.
- Mixing Formula R.A.C.E. and Standard EXOS rank metric paths.
- Shared recovery assumptions across captain and participant recovery roles.

## Required metric separation in future integration

R.A.C.E. can expose:
- **Championship Score**
- **Credits Earned**
- **Wallet Balance**
- **Championship Rank**

as independent displays, while preserving each column’s source of truth and update semantics.
