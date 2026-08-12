# EXOS Core v2 Invariants

These are hard rules for the canonical Standard Core v2 journey. The legacy
Administration and Asset Library screens documented in `EXOS_ARCHITECTURE.md`
are outside that journey and must never become a fallback for it.

## Runtime purity

1. Standard staging Participant, Facilitator/Control Centre, Standard event
   authoring, reports, and Projector use the Standard Core v2 adapter.
2. Canonical Standard runtime has `GOOGLE_SHEETS_RUNTIME_CALLS = 0` and
   `LEGACY_RUNTIME_CALLS = 0`. Do not suppress or reset these counters to make
   an assertion pass.
3. Do not add a Sheets, legacy-table, or non-`exos_v2_*` RPC fallback. Fail
   closed through the adapter/runtime boundary instead.
4. A visible legacy screen is not permission to route Standard runtime data to
   it. If such a screen is brought into the Standard journey, convert and test
   it first.

## Participant identity, recovery, and Streamlit state

1. `ParticipantID`, `EventID`, and `TeamID` are canonical durable identity.
   Browser/session/query state is a cache that must be revalidated against Core.
2. Round-robin/least-populated assignment happens only on first participant
   creation. Same-device restore and cross-device recovery never reassign a
   team or create another participant.
3. A unique known participant on a different device receives a valid recovered
   session for that same `ParticipantID` and `TeamID`. An ambiguous candidate
   must require explicit re-identification; it must not be silently chosen.
4. Query state may persist `event_id`, participant name, join code, and session
   token only as the existing resume mechanism. Do not log session tokens.
5. Do not mutate a widget-owned `st.session_state` key after its widget has
   instantiated in that rerun. Keep pending join data and canonical restored
   identity in non-widget state, then rerun before assigning widget defaults.

## Team identity

1. Resolve display identity in this order: `TeamIdentity` → `TeamName` → raw
   `TeamID` as a diagnostic last resort.
2. Team identity is theme-driven. Country is optional metadata, never a
   required data contract. Emoji, icon, flag, and image remain optional.
3. Core v2 has no global six-team limit. Team count is event configuration.

## Scoring, credits, wallets, and performance

1. Score/points, credits, and wallet balance are separate concepts with
   separate source-of-truth and update semantics. Never relabel one as another.
2. Standard migration 025 review approval writes competitive score ledger rows
   only for `TEAM_COMPETITIVE`; it does not implicitly award credits.
3. `NON_SCORING` contracts contribute no competitive score/ranking payload.
4. Participant evidence never replaces an authored activity target. Target
   performance is aggregate net achievement divided by aggregate target across
   included contracts; it is not an average of percentages.
5. Ranking/performance must use the canonical snapshot and event-scoped team
   identity resolution.

## Programme and event isolation

1. Every Standard write/read is event scoped; no participant, score, runtime,
   broadcast, or projector data may leak between events.
2. Programme duplication copies configuration only: programme, module, and
   activity structure. It must not copy participants, sessions, submissions,
   reviews, score/credit ledgers, marketplace data, or launched state.
3. Break/lunch markers are programme markers, not launchable activities.

## Broadcast, projector, and refresh

1. Broadcast Preview is local and non-live. Apply is the explicit persisted
   event-scoped mutation. Never conflate the two.
2. Projector is event-scoped and display-only. It cannot mutate lifecycle,
   participant identity, submission, review, or score state.
3. Use scoped fragments/polling. A full-app one-second autorefresh is forbidden.

## Release evidence

1. Passing source tests, staging scripts, deployed staging checks, and human
   UAT are different evidence classes. Record them separately.
2. A migration present in Git is not proof of database installation. Record
   only verified installation status and query the target before applying SQL.
3. The frozen Standard baseline is not production certification and is not a
   250-concurrent-participant load certification.
