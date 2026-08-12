# EXOS Decisions Log (Core v2 Freeze Baseline)

## 1) Canonical runtime moved to Supabase Core v2 only
**Decision:** All canonical event operations for Standard EXOS must use `StandardCoreV2Adapter` and `*_v2` tables + `rpc/exos_v2_*` functions only.

**Why:**  
- Core runtime files already enforce this in one place (`StandardCoreV2Adapter._guard()`), and staging assertions rely on zero non-v2 call counts.  
- Historical incidents were triggered by mixed runtime readers/writers and implicit fallback behavior.

**Commit evidence:**  
- `26dc830` – convert staging participant flow to Standard Core v2  
- `df34ba3` – restore participant access via canonical recovery RPCs  
- Subsequent follow-up commits maintain `_guard()` and staging assertion checks.

---

## 2) Remove Google Sheets from canonical live participant/facilitator state
**Decision:** `Participant`, `Facilitator`, and `Projector` must not mutate/read live canonical state from Google Sheets in Standard Core v2 paths.

**Why:**  
- Multiple tables now provide durable source of truth in Core v2 (`events_v2`, `teams_v2`, `participants_v2`, `submissions_v2`, score/credit ledgers).  
- Live duplication or drift appears when Sheets are still treated as authoritative.

**Operational rule:**  
- Any legacy Google Sheets path is blocked by runtime call counters and staging assertion; remediation is via migration and adapter hardening, not fallback.

**Commit evidence:**  
- Multiple staged hardening commits culminating in `66a8dd9` and `26dc830` (runtime-path correction).

---

## 3) Team identity must be generic
**Decision:** Team display is resolved as:
`TeamIdentity → TeamName → TeamID`.

**Why:**  
- Teams can be countries, animals, brands, or custom identities.
- Country is display metadata only and cannot be required by contract.

**Supporting code:**  
- `create_event`, `get_teams`, and participant recovery use `TeamIdentityConfig` and `TeamIdentity` metadata (`data/standard_core_v2_adapter.py`).  
- UI resolution helper (`screens/team_identity.py`) is shared by Control Centre, leaderboard, and Projector.

---

## 4) Preserve identity and team on recovery/reconnect
**Decision:** If `ParticipantID` already exists, recovery must reuse it and preserve existing `EventID`, `TeamID` and team identity.

**Why:**  
- Prevents incorrect round-robin reassignment after registration.

**Supporting code:**  
- `exos_v2_restore_join` and `exos_v2_recover_participant_access` in SQL migrations `024`, `025`, and `026`.  
- Participant UI recovery path resolves `Candidate` and then only reclaims a new session token.

---

## 5) Separate Projector as display-only surface
**Decision:** Projector remains a dedicated runtime-display surface controlled by facilitator broadcast state.

**Why:**  
- It must not perform operations like launch/review/recover.
- Broadcast is event-scoped and must be preview/apply separable for safe operator control.

**Supporting code:**  
- `MissionAI.py` route `view=projector` and `screens/projector_broadcast.py`.

---

## 6) Broadcast preview/apply split
**Decision:** Projector broadcast state updates use **Preview** (local) and **Apply** (runtime state mutation).

**Why:**  
- Prevents accidental live-state mutation during review setup.
- Matches facilitator operational safety in `screens/projector_broadcast.py`.

---

## 7) Replace full-app second-based autorefresh with scoped refresh
**Decision:** Use stream fragment-scoped polling (`watch_live_mission_state` in participant, projector/mission polling, timer fragments).

**Why:**  
- Full-app 1s reruns caused interaction regressions and render instability.

---

## 8) Keep score and credits as distinct models
**Decision:** Do not conflate score/points with credits.

**Why:**  
- Score drives ranking and programme contract outcomes.  
- Credits are wallet-like economy and can remain stable even for non-scoring activities.

**Supporting code:**  
- `engines/canonical_performance.py` and ledger tables/paths in `standard_core_v2_adapter.py`.

---

## 9) Programme duplication is configuration-only
**Decision:** Duplicating programme copies structure, not operational/runtime state.

**Why:**  
- Avoids cross-event leakage of participants, sessions, submissions, and live control state.

**Reference:**  
- Verified by duplicate scripts and outputs showing zero runtime participants/sessions/submissions in destination event.

---

## 10) Feature freeze at this baseline
**Decision:** After baseline lock, no runtime behavior changes without explicit unfreeze.

**Why:**  
- Repository is now source-of-truth for future agent handoff; production behavior is frozen in Standard EXOS baseline state.

**Commit:** `41cb91e`
