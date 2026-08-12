# EXOS Core v2 Standard Architecture (Frozen Baseline)

This document is the canonical architecture record for Standard EXOS at the frozen baseline.

## FOUR PRIMARY SURFACES

### ADMIN
Implemented in `MissionAI.py` workspace tabs.

Responsibilities:
- Event creation and visibility (`events_home`, `create_event`)
- Programme and activity configuration (`programme_builder`)
- Team identity/theme configuration (`TeamIdentityConfig`, country/identity pools)
- Programme duplication (`duplicate_programme_configuration`) limited to content structure
- Event metadata update (`update_event`, `update_event_metadata`)

### FACILITATOR
Implemented in `Facilitator.py` + `screens/control_centre.py`.

Responsibilities:
- Event selection and restoration
- Activity runtime launch and stop
- Team management and identity recovery tooling
- Submission review and scoring controls
- Broadcast lifecycle (preview + apply)
- Projector control and display routing
- Runtime diagnostics (non-operational audit)

### PARTICIPANT
Implemented in `Participant.py` + `screens/participant.py`.

Responsibilities:
- Join flow and participant registration
- Pending and restored identity display
- Device/session recovery and recovery prompts
- Current mission display and submission entry
- Review status, performance, and ranking visibility

### PROJECTOR
Implemented as display route (`view=projector`) in `MissionAI.py` and rendered via `screens/leaderboard_display.py`.

Responsibilities:
- Event-scoped presentation only (no operations)
- Ranking and live mission rendering
- Broadcast-controlled presentation mode
- No stage launch/review/score writes

## Canonical adapter/runtime flow

- The canonical mutable path is `data/standard_core_v2_adapter.StandardCoreV2Adapter` against Supabase Core v2.
- `data/runtime_database.py` owns HTTP transport and secret/key handling.
- `data/control_runtime.ControlRuntime` wraps operational writes in staged mutation methods (`control_centre_mutation`).
- `screens/projector_broadcast.py` publishes projector state separately from mission and review operations.

### Runtime safety (staging)

- `StandardCoreV2Adapter._guard()` allows only:
  - `*_v2` tables
  - `rpc/exos_v2_*` procedure calls
- Call counters:
  - `LEGACY_RUNTIME_CALLS`
  - `GOOGLE_SHEETS_RUNTIME_CALLS`
- `assert_core_v2_only()` is required in canonical staging paths.

## Event isolation and recovery model

- Core event identity is keyed by `EventID` in every canonical table and RPC payload.
- Participant/session recovery:
  - same-device/session via session token
  - cross-device via `exos_v2_restore_join` then `exos_v2_recover_participant_access`
  - team membership is preserved unless explicit, audited recovery changes it.
- Query-string persistence supports resume (`event_id`, `participant_name`, `session_token`, `join_code`) in participant flow.

## Performance, ranking, and ledger model

- Programme contract enters runtime through programme/activities metadata.
- Score derivation is performed by canonical engines:
  - `engines.canonical_performance.py`
  - `data/runtime_database` + `standard_core_v2_adapter` score/credit RPCs
- Canonical score storage: `score_transactions_v2`
- Canonical credits: `credit_transactions_v2`
- Points/leaderboard, performance percent, and ranking are derived from contract and submission states.
- `load_performance_snapshot` is shared across participant/facilitator/projector.

## Broadcast and projector architecture

- Facilitator broadcast has local preview and persisted apply phases.
- `projector_state_v2`/event state keeps per-event broadcast data.
- Two simultaneous events must not share projector state due to explicit `event_id` scoping.
- The projector path never writes participant/facilitator lifecycle state.

## Recovery from this architecture

1. Participant submits join and obtains pending state.
2. `exos_v2_join_event_v2` creates/resolves identity and session.
3. Recovery path surfaces candidate and can invoke:
   - resume same session
   - `exos_v2_recover_participant_access` on confirmed cross-device recovery
4. Identity state is restored and normal surfaces continue with same `ParticipantID`/`TeamID`.
