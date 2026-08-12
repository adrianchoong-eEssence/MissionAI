# EXOS Core v2 Invariants (Hard Rules)

These are enforced expectations for all future Standard EXOS work.

## 1) Runtime purity

- **No Google Sheets runtime.**  
  Standard runtime must remain in Supabase Core v2.  
  Staging must keep `GOOGLE_SHEETS_RUNTIME_CALLS = 0`.
- **No legacy runtime fallback.**  
  Standard runtime tables/functions must stay `*_v2` + `rpc/exos_v2_*`.
  Staging must keep `LEGACY_RUNTIME_CALLS = 0`.
- **No silent fallback.**  
  Fail explicitly via adapter/runtime errors when a non-standard path is attempted.

## 2) Identity integrity

- Once `ParticipantID` exists, it must persist for that person/event context.
- `EventID` must persist.
- `TeamID` must persist on same-device restore and cross-device recovery unless explicitly recovered to the same identity/team.
- Recovery must never do round-robin reassignment.

## 3) Team identity semantics

- Team display resolution order:
  1. `TeamIdentity`
  2. `TeamName`
  3. `TeamID` (diagnostic final fallback only)
- Country is not a first-class concept in Core.
- Team identity is theme-driven and may be countries, animals, brands, colors, or custom values.
- No global fixed six-team limit in Core v2.

## 4) Scoring and credits separation

- `Score`/`Points` is the competitive metric and ranking basis.
- `Credits` is a distinct economy value.
- Non-scoring activities must not emit competitive score payload for ranking.
- `participant evidence` content does not override `Target` authored in activity contract.

## 5) Ranking and target semantics

- Ranking uses canonical performance snapshot and contracts.
- Target-based percentage is `Σ NetAchievement / Σ Target` across included scoring contracts, not average percentages.

## 6) Programme duplication guarantees

- Programme duplication copies programme structure only.
- It must not copy operational/runtime state:
  - participants
  - sessions
  - submissions
  - reviews
  - score ledgers
  - wallets and runtime state

## 7) Refresh and UX safety

- No full-app 1-second autorefresh for core state.
- Scoped fragments are permitted (mission polling, timer, scoreboard slices).

## 8) Projector safety

- Projector is event-scoped display only and may not write runtime lifecycle state.
- Two live events cannot share projector state.
- Broadcast has preview/apply split.

## 9) Recovery ambiguity handling

- If candidate set is ambiguous, recovery must require explicit user/facilitator confirmation.
- Unambiguous cross-device recovery should complete automatically through canonical recovery path and create a valid session.
