# EXOS Core v2 — Post-Maxis Stabilisation

## Baseline

- Branch: `stabilize/post-maxis-core-v2`
- Source baseline: `9c204a09e535b4339512ace559b7da8e0947c939`
- Full credential-free regression: `1031 passed, 2 skipped` (2026-09-08)
- Dedicated project migration history: `004`, `020`–`022`, `025`/`025a`,
  `026`/`026a`, `036`/`036a`, `037`/`037a`, `038`–`041`.

## Historical-event protection sentinel

`MAXIS-20260907-MISSION-AI` is historical runtime evidence, not a fixture.
Before stabilisation work its canonical read-only sentinel is:

- Engine/strategy/runtime: `THEME_PARK_RACE` / `OPEN_MISSION_BOARD` / `CLOSED`
- Team Formation phase: `ACTIVE`
- Participants: `68`; submissions: `43`; score transactions: `61`

No migration, test, seed, cleanup or application flow in this branch may update
that event. `MXUAT7`, Formula R.A.C.E., and unrelated EXOS events are likewise
outside all fixtures.

## Promotion decisions

1. Attendance is an additive event/participant record. Roster membership is
   immutable; an absent participant is never deleted or reassigned. Existing
   events without an attendance contract retain their current semantics.
2. Participation scoring is opt-in through a versioned race-station scoring
   contract. New submission/review RPCs will be used only by opted-in events;
   the frozen 037–040 review and score behavior remains unchanged.
3. Captain clear, attendance updates, score adjustments and operator actions
   are service-only canonical RPCs with audit records. There is no AI-only or
   direct-SQL scoring path.
4. A reusable public projector will use an explicit event eligibility flag and
   a narrow read-only projection RPC. The historical Maxis 041 fixed-event
   projector remains unchanged.
5. Hybrid participation-plus-rubric scoring is deferred unless its validation
   can reuse the same immutable submission attendance snapshot without adding
   a second score authority.

## Migration/change log

| Item | Category | Status |
| --- | --- | --- |
| `042_post_maxis_p0_attendance.sql` | additive, event-opt-in canonical attendance contract | installed/certified on authorised dedicated project (2026-09-08) |
| `042_post_maxis_p0_attendance_rollback.sql` | guarded, data-preserving rollback for an unused attendance contract | certified guard source |
| `042_post_maxis_p0_attendance` verifier/certification package | read-only catalogue verification plus exact `CERT-P0A-*` disposable fixture | PASS; zero fixture residue |
| `043_post_maxis_public_projector.sql` | additive reusable public projection | planned |
| Standard participant/facilitator refresh, evidence and review UX | application-only | planned |
| Post-event reporting projection | read-only application/RPC projection | planned |

SQL source is not installation evidence. Any future application is to a
disposable certification event first; it must not use the Maxis event.
