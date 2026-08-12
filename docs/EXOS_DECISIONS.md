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
