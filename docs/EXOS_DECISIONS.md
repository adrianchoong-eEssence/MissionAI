# EXOS Decisions Log — Standard Core v2 Freeze

## 1. Standard canonical runtime is Core v2 only

**Decision:** The canonical Standard event journey uses
`StandardCoreV2Adapter`, explicitly allowed `_v2` tables, and `exos_v2_*` RPCs.

**Reason:** Mixed writers/readers and silent fallback caused identity and
facilitation regressions. The adapter guards non-v2 paths and staging
Facilitator asserts zero legacy/Sheets counters.

**Scope:** This applies to the Standard journey, not to every legacy utility
still visible in the broad MissionAI shell. Administration and Asset Library
remain documented legacy surfaces and are not an allowed fallback.

## 2. Generic team identity is a Core contract

**Decision:** Render `TeamIdentity`, then `TeamName`, then raw `TeamID` only as
a diagnostic fallback.

**Reason:** Teams may be countries, animals, brands, colours, or custom names.
Country, flag, emoji, icon, and image are optional metadata, not identity.

**Supporting code:** `screens/team_identity.py`, `screens/create_event.py`, and
`StandardCoreV2Adapter.get_teams()`.

## 3. Identity recovery preserves the existing participant/team

**Decision:** Restore and cross-device recovery reuse a canonical participant
and preserve its `EventID` and `TeamID`. New team selection occurs only in the
first-creation path.

**Reason:** Re-running assignment on reconnect creates duplicate participants
and changes a team’s history.

**Supporting implementation:** 020 defines the baseline join/restore contract;
026 replaces identity payload/restore behavior and adds
`exos_v2_recover_participant_access`. 026 is the Standard participant recovery
patch. 024 is a separate Captain/team-access recovery migration for R.A.C.E.

## 4. Widget state and canonical state are separate

**Decision:** A Streamlit widget key cannot be mutated after its widget is
instantiated in the same rerun. Pending join/recovery data uses separate
transient state and then restores canonical identity on a rerun.

**Reason:** This prevents `StreamlitAPIException` while preserving immediate
join progress and exactly-once registration behavior.

**Supporting code:** `screens/participant.py` join and recovery state helpers.

## 5. Score, credits, and wallet are separate models

**Decision:** Do not map score to credits by display convention or approval
side effect.

**Reason:** Standard 025 competitive review writes `score_transactions_v2`.
Credits use `credit_transactions_v2`; a wallet is a derived balance. The Standard
review contract does not automatically grant a credit transaction.

## 6. Projector is display-only with preview/apply broadcast

**Decision:** Projector is event-scoped display. Broadcast Preview is local;
Apply is the explicit persisted operation.

**Reason:** Operators need to see a composition without changing the live
projector. Projector cannot launch activities, recover identities, or score.

**Supporting implementation:** Broadcast state is stored in
`events_v2.event_payload.control_state.ProjectorBroadcast`; the renderer does
not currently use `projector_state_v2` as its active state store.

## 7. Scoped refresh only

**Decision:** Use Streamlit fragments for timer, mission, and projector polling.

**Reason:** Full-app one-second reruns caused disabled controls, unstable forms,
and lost interaction state.

## 8. Programme duplication is configuration-only

**Decision:** Duplicate programme/modules/activities only. Never duplicate
participants, sessions, submissions, reviews, ledgers, live state, or wallets.

**Reason:** Event isolation must survive reuse of a programme template.

**Supporting implementation:** `clone_programme_stages` and
`StandardCoreV2Adapter.duplicate_programme_configuration`.

## 9. Evidence labels must remain honest

**Decision:** Keep automated source tests, staging-runner execution, human UAT,
and production/load certification as separate status labels.

**Reason:** The repository does not contain committed Standard UAT JSON output
or Supabase migration-history evidence. Code/test presence cannot prove a live
deployment, human observation, or installed migration.

## 10. Frozen baseline is a reference, not a branch lock

**Decision:** `41cb91e` is the Standard runtime reference; `fe0faf7` and later
documentation commits are not runtime changes.

**Reason:** Future work may continue on the branch, but it must compare with the
frozen reference, explicitly identify an unfreeze/change scope, and update this
memory set when architectural facts change.

## 11. Team Formation is a Core capability, not a programme implementation

**Decision:** Sprint 2 Team Formation V1 is a configuration-gated Core-v2
capability. It supports `RANDOM_ASSIGN` and `PREASSIGNED` over the existing
event, team, participant, session, and audit entities. Genting and future theme
park events consume it rather than clone it.

**Reason:** Participant-scale events require transactional capacity, balanced
assignment, recovery-safe canonical identity, and a single Captain authority.
Those rules must be reusable and database-enforced, rather than implemented in
a programme-specific Streamlit flow.

**Scope:** The 036 contract is additive. Existing events without the
configuration are unchanged. Formula R.A.C.E. Team PIN access remains on its
dedicated path; the protected R.A.C.E. event is never a Team Formation fixture
or certification target.

**Identity contract:** A display name is not an enrollment or recovery
credential. Each Team Formation participant uses a base64url 32-byte opaque
credential, generated and retained by the joining device before its first
request. The database persists only SHA-256 credential hashes and enforces
event-scoped uniqueness. PREASSIGNED rosters supply those hashes, with raw
credentials distributed outside the database; recovery accepts only the raw
credential and a device identifier.

## 12. Theme Park Race is a configured engine, not a Genting app

**Decision:** Theme Park Race V1 is selected only by
`RaceConfiguration.EngineKind = THEME_PARK_RACE`. `RaceConfiguration` owns
versioned routes/runtime/display configuration; each mission remains an
existing activity with a `race_station` payload. The engine uses Team
Formation V1 Captain authority and the existing submission/review/ledger
entities.

**Reason:** Future theme-park races should be created primarily by
configuration/content, while keeping identity, team, Captain, evidence,
verification, recovery and live display semantics canonical.

**Scope:** 037 adds no tables and no Formula R.A.C.E. changes. Its guarded
submission route applies only to the exact Theme Park engine selection;
Genting content/event population, deployment and the separate 66/250
concurrency certification are outside this implementation boundary.

## 13. Theme Park Race supports an open strategic board without replacing routes

**Decision:** Keep `CONFIGURED_TEAM_ROUTE` unchanged and add opt-in
`RaceConfiguration.StrategyMode = OPEN_MISSION_BOARD`. Board selection,
operational availability, Secret release, ride attempts, submission, review,
and scoring remain canonical Core state; the browser only projects it.

**Reason:** Mission AI teams must choose strategic opportunities rather than
follow a compulsory linear order, while future events such as AIA can vary
ride, bonus and Secret catalogues and point values through configuration.

**Scope:** The 038 source extension uses existing
`events_v2`, `activity_runtime_v2`, submissions, reviews, score ledger,
participant sessions and Captain sessions. It introduces no Genting model or
table, does not modify 037 source, and preserves Formula R.A.C.E. isolation.
Ride thresholds use current canonical membership; 100% participation creates
no score multiplier and exterior-only evidence cannot prove completion.

## 14. Theme Park Race End is terminal and distinct from Ready

**Decision:** `CLOSED` remains the existing persisted terminal runtime value
and projects as lifecycle `ENDED`; `HELD` is an explicit persisted pause.
Once ended, a Theme Park Race cannot be restarted, and Mission controls and
participant writes are blocked server-side while results, Captain history,
Secret history, submissions, reviews, and scores remain intact.

**Reason:** Mapping `CLOSED` to the old Ready fallback exposed a misleading
Start control after End. A canonical terminal projection and irreversible
runtime transition make reconnect behaviour deterministic without adding a
new event or runtime model.

**Scope:** Local 040 source replaces only the Theme Park runtime-phase and
open-board operational-control RPCs. It creates no table and does not modify
035–039, Team Formation V1 semantics, or Formula R.A.C.E.
