# EXOS Core v2 Standard Architecture

## Authority and scope

This is the architecture record for the frozen Standard runtime at
`41cb91e91a75a36001daef72e0943e7bc84eb81e`. The repository-memory documents
were added afterwards in `fe0faf7`; they are not runtime code and must never be
mistaken for the frozen runtime baseline.

“Standard Core v2” means the canonical Standard event journey: Core-v2 event
authoring, programme configuration, participant registration/recovery,
facilitation, submission/review/score, and projector/broadcast. It does not
mean every historical screen in this repository is already Core-v2-only.

## Primary surfaces

### Admin / authoring

`MissionAI.py` routes Standard authoring to `screens/events_home.py`,
`screens/create_event.py`, `screens/programme_builder.py`, reports, Control
Centre, and the projector route. Standard event, team, and programme changes
use `StandardCoreV2Adapter`.

`screens/administration.py` and `screens/asset_library.py` still instantiate
`GoogleSheetsDB`. They are legacy utilities visible in the broad MissionAI
shell, outside the frozen Standard Core v2 journey. They are not evidence that
the Standard staging journey is Sheets-free, and must not be used as a Standard
Core v2 fallback.

### Facilitator

`Facilitator.py` in `EXOS_ENV=staging` constructs `StandardCoreV2Adapter`,
renders `screens/control_centre.py` (or its standalone projector route), then
calls `assert_core_v2_only()`. The staging branch stops before the non-staging
Formula R.A.C.E./Google Sheets shell.

Responsibilities include event selection, activity launch, team display,
submission review/score, broadcast preview/apply, and operational diagnostics.
Diagnostics are non-operational and must not block the control flow.

### Participant

`Participant.py` in staging stops in `screens/participant.py`, which uses the
Standard adapter. The join flow is Join Code → first name → last name → Join,
then an immediate pending state, canonical registration, identity restoration,
and dashboard. The browser/query state is a resume cache; canonical identity is
returned by Core v2.

### Projector / broadcast

`MissionAI.py` and `Facilitator.py` expose `?view=projector&event_id=<EVENT_ID>`
and render `screens/leaderboard_display.py`. `screens/projector_broadcast.py`
provides a local Preview and a persisted Apply action. Projector is display-only:
it cannot launch, recover, review, or score.

## Canonical Standard data and adapter boundary

- `data/standard_core_v2_adapter.py::StandardCoreV2Adapter` is the Standard
  compatibility boundary. It permits only the explicit `_v2` table allowlist
  and `exos_v2_*` RPCs.
- `data/runtime_database.py` supplies the HTTP transport and resolves Supabase
  configuration. The adapter, not the generic transport, establishes the
  Standard Core-v2-only contract.
- Core records are event scoped. Token-addressed state resolves to its owning
  `EventID`; it is not an exception to event isolation.
- Canonical Standard data includes `events_v2`, `teams_v2`, `programmes_v2`,
  `modules_v2`, `activities_v2`, `participants_v2`,
  `participant_sessions_v2`, `activity_runtime_v2`, `submissions_v2`,
  `reviews_v2`, and the score/credit ledgers.
- Live activity and broadcast control currently live in
  `events_v2.event_payload` (`live_state` and `control_state.ProjectorBroadcast`).
  `projector_state_v2` exists in the schema and cleanup/verification inventory,
  but the frozen Standard broadcast renderer does not use it as its backing
  store.

## Identity and team assignment

- `exos_v2_join_event_v2` creates a participant only for a new, unique
  normalized identity. Its first-creation assignment uses
  `exos_v2_next_team_id` (least assigned team, then `TeamID`).
- Same-device restore returns the existing session/identity. Cross-device
  recovery uses `exos_v2_restore_join` followed, for one unambiguous candidate,
  by `exos_v2_recover_participant_access`.
- Recovery creates/reclaims a session for the existing participant. It does not
  create another participant or run round-robin assignment. `ParticipantID`,
  `EventID`, and `TeamID` remain the canonical identity.
- Team rendering is generic: `TeamIdentity`, then `TeamName`, then raw
  `TeamID` only as a diagnostic fallback. Country, flags, icons, emoji, and
  images are optional theme metadata.

## Team Formation V1 — additive Core capability

Sprint 2 introduces a configuration-gated Core capability for large individual
participant events. It is not a Genting-specific application or identity model.
`participants_v2` remains the canonical participant record and `teams_v2`
remains the canonical team record.

- An event opts in only through `event_payload.TeamFormation.SchemaVersion = 1`.
  Events without that configuration retain the frozen Standard assignment and
  recovery behavior.
- The supported modes are `RANDOM_ASSIGN` and `PREASSIGNED`. The lifecycle is
  `DRAFT` → `REGISTRATION_OPEN` → `FORMATION_LOCKED` →
  `CAPTAIN_SELECTION` → `ACTIVE`.
- Team capacity is stored on the existing `teams_v2` row and is mandatory only
  for a configured Team Formation event. Allocation, recovery, and correction
  are security-definer Core RPCs; no client selects or reassigns its own team.
- Random registration locks the event and an opaque credential hash, considers
  only below-capacity teams, and randomly selects among the least-populated
  eligible teams. The joining device generates and persists a base64url
  32-byte enrollment/recovery credential before its first request; only its
  SHA-256 hash is stored. Display names are presentation data, never identity
  or recovery credentials. Retry/recovery returns the same canonical
  participant and team only when that opaque credential is supplied.
- Preassigned events provision canonical participant/team membership in
  `participants_v2` before registration. The roster contains an opaque
  enrollment-credential hash, while claim and recovery accept the matching
  raw credential; they never accept a requested team.
- A Team Formation Captain is an existing team participant with a database-
  enforced single effective Captain and participant-linked Captain session.
  Facilitator transfer is explicit and audited. This is separate from Formula
  R.A.C.E.'s existing Team PIN access behavior.

## Theme Park Race V1 — generic configured engine

Theme Park Race is an event/programme configuration on Standard Core v2, not
a standalone application and not a Genting-specific data model. An event opts
in only when `event_payload.RaceConfiguration.EngineKind` is exactly
`THEME_PARK_RACE`; no event name, programme name, client, venue, or activity
title selects this engine.

- `RaceConfiguration` is versioned (`SchemaVersion = 1`) and contains a
  selected strategy, runtime phase, and display preferences.
  `StrategyMode = CONFIGURED_TEAM_ROUTE` preserves configured team routes;
  opt-in `StrategyMode = OPEN_MISSION_BOARD` gives teams a server-canonical
  opportunity board. Mission content remains on existing
  `activities_v2.activity_payload.race_station` payloads.
- The participant lifecycle derives from canonical Team Formation phase plus
  the engine runtime phase: `REGISTRATION`, `TEAM_FORMATION`,
  `FORMATION_LOCKED`, `CAPTAIN_SELECTION`, `READY`, `ACTIVE`, `HELD`, and
  terminal `ENDED`. `CLOSED` remains the persisted Core-v2 terminal runtime
  value and is projected as `ENDED`; it cannot be restarted. `HELD` is an
  explicit persisted pause state, never a client-side substitute for `READY`.
- A Team Formation Captain submits only the canonical current activity for
  that team's configured route. The 037 source contract writes the existing
  `activity_runtime_v2` and `submissions_v2` records and uses existing review,
  score and credit ledgers; it creates no Theme Park Race tables. Rejection
  returns the same activity to the route for resubmission.
- The 038 extension retains the 037 source file and route
  strategy, while adding open-board selection/ride-attempt/operational state
  through existing event payload, activity runtime, submission, review and
  score-ledger records. It creates no table. Projector board views never
  receive selected/current team strategy or private evidence.
- Participant, facilitator and projector surfaces rebuild their projections
  from Core records after reconnect. Projector is display-only. The browser
  keeps the Team Formation opaque enrollment credential locally; it is never a
  query parameter and the database retains only its Team Formation hash.
- Formula R.A.C.E. remains on its current dedicated routing. The Theme Park
  guard returns immediately for every engine other than `THEME_PARK_RACE`.

## Programme, review, performance, and ledgers

- Programme duplication uses `clone_programme_stages` and the Standard adapter
  to copy programme/modules/activities only. It must never copy live state,
  participants, sessions, submissions, reviews, or ledgers.
- Migration 025’s Standard review path writes competitive approved scores to
  `score_transactions_v2`. It does not implicitly write credits.
- `credit_transactions_v2` is a separate Core ledger. A wallet/balance is a
  third derived concept; none is interchangeable with a score or a participant
  field such as `intelligence_credits`.
- `engines/canonical_performance.py::load_performance_snapshot` derives the
  shared performance/ranking view from programme contracts, submissions, teams,
  and the canonical leaderboard. `NON_SCORING` contracts are excluded from
  competitive aggregation.

## Refresh and runtime safety

- Standard adapter counters are `LEGACY_RUNTIME_CALLS` and
  `GOOGLE_SHEETS_RUNTIME_CALLS`; staging Facilitator assertion requires both to
  be zero for the canonical Facilitator journey.
- Streamlit refresh must be scoped. Fragment polling is used for timers,
  projector, and participant live mission state; a global one-second app rerun
  is prohibited.
- Widget-owned session-state keys must not be assigned after their widget has
  been instantiated in the same rerun. Use separate transient/pending keys for
  join and recovery transitions.

## Formula R.A.C.E.

Formula R.A.C.E. has a separate Core-v2 staging adapter and product lifecycle.
Read `docs/RACE_HANDOVER.md` before touching it. Standard Core v2 supplies
shared platform constraints, not a replacement R.A.C.E. identity, checkpoint,
wallet, judging, or championship model.
