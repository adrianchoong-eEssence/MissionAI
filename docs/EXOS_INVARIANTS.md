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

## Team Formation V1

1. Team Formation is an opt-in Core capability. An event without
   `event_payload.TeamFormation.SchemaVersion = 1` retains existing Standard
   and Formula R.A.C.E. behavior.
2. `RANDOM_ASSIGN` and `PREASSIGNED` use the same canonical `participants_v2`,
   `teams_v2`, participant-session, and audit entities. Do not introduce a
   second participant, team, or event source of truth.
3. For a configured event, only the Team Formation RPCs may create, recover,
   or change Team Formation participant state. Membership is immutable after
   assignment; refresh and recovery preserve `ParticipantID`, `EventID`, and
   `TeamID`.
4. Capacity is mandatory and enforced only for configured Team Formation teams.
   Random assignment may choose only below-capacity teams and must select among
   minimum-occupancy eligible teams server-side. `EVENT_FULL` is a valid result,
   never a client-side fallback.
5. Team Formation enrollment/recovery is an opaque base64url 32-byte credential
   whose SHA-256 hash alone is stored. Display names, names, team names, and
   join codes must never be used as identity or recovery credentials. The
   event-scoped unique hash enforces identity idempotency server-side.
6. PREASSIGNED membership is provisioned in canonical participant rows using a
   roster-supplied credential hash and is claimed with its matching opaque raw
   credential. A participant must never submit a team ID or be silently
   reassigned.
7. A Team Formation Captain must already be a team member. Exactly one
   effective Captain and one active participant-linked Captain session may exist
   per configured event/team. Replacement requires an audited facilitator
   transfer; recovery retains the assigned Captain.
8. Formula R.A.C.E. Team PIN/Captain access is not a Team Formation event and
   must not be redirected, reconfigured, or changed by this capability.

## Theme Park Race V1

1. Theme Park Race selection is exact and configuration-based:
   `RaceConfiguration.EngineKind = THEME_PARK_RACE`. Never infer it from an
   event/programme/client/venue/mission name.
2. It reuses `events_v2`, `participants_v2`, `teams_v2`, Team Formation V1,
   activities, submissions, reviews, ledgers, sessions and projector state.
   Do not introduce a Genting event, team, participant, mission, or app model.
3. `CONFIGURED_TEAM_ROUTE` routes reference only enabled event-local
   `activity_payload.race_station` `ActivityID`s. Its current mission is
   derived from that route and canonical submissions; a rejected row reopens
   its own activity for resubmission. `OPEN_MISSION_BOARD` has no compulsory
   route: availability, Secret release and selection derive server-side from
   RaceConfiguration, activity runtime and canonical submission state.
4. Only the effective Team Formation Captain with an active participant-linked
   Captain session may submit a Theme Park Race mission. Client UI visibility
   is not authorization; 037 is the server-side route/evidence guard.
5. Theme Park Race must be `ACTIVE` only after Team Formation is `ACTIVE`.
   Its canonical lifecycle distinguishes `READY`, `ACTIVE`, `HELD`, and
   terminal `ENDED` (`CLOSED` in persisted runtime configuration). An ended
   Mission must not return to ready/start state, and participant select,
   submit/resubmit, ride, bonus, Secret, and board-operation writes are
   server-blocked. Registration/formation/Captain/ready state and reconnect
   state are derived from canonical records, never a browser-side lifecycle
   source of truth.
6. Formula R.A.C.E. routing, Team PIN/Captain access, checkpoint semantics,
   credits, wallets, judging and result behavior are unchanged by this engine.
7. A board-mode `RIDE` threshold derives from current canonical team
   membership. Full participation has no automatic competitive multiplier;
   Ground Control remains valid. An attraction exterior image is not
   queue-entry proof. Ride closure/temporary unavailability and Secret release
   are facilitator/server state, never browser state.
8. Projector board views must never show private evidence, selected/current
   team missions, or unsubmitted team strategy.

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
