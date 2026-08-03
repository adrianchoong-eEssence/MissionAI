# Sprint 011A — Foundation P0 Gates 1 & 2

Status: implementation complete; **migration and deployment approval still required**.

## P0 Gate 1 — Participant Identity Certification

Implemented:

- `exos_join_event_v2` validates the event, normalizes full name, locks the event, restores identity before allocation and performs one conflict-safe insert only for a new participant.
- Optional country/team selection is supplied to the atomic join as TeamID. The former post-join team/country PATCH is disabled.
- A database trigger makes ParticipantID/EventID immutable and blocks automatic name, TeamID, team, country, flag, leader and merge-state mutation.
- Facilitator team corrections, leader transfers and duplicate merges explicitly enable a transaction-local override and retain audit logging.
- Same-name recovery uses the shared punctuation/space/case normalizer and fails to an explicit ambiguous recovery choice rather than silently selecting or creating a record.
- Team-leader claim is one locked, audited backend RPC. Reconnect never grants or removes leadership.
- Duplicate credit earning is prevented by a unique event/team/source index; the dry run detects existing conflicts before index creation.
- Session-token recovery remains ParticipantID-specific. Browser/session state is a cache only.

## P0 Gate 2 — Runtime Authority Boundary

`data/runtime_authority.py` is the executable ownership contract for all eleven required entities. Supabase owns every live record; Sheets is configuration before publication or an explicit reporting projection; memory/browser state is cache-only.

Conflicting paths removed or blocked:

- Direct Google Sheets participant creation and team allocation.
- Sheet fallback after a configured runtime join-code miss.
- Post-join country/team reassignment.
- Merged Sheet/Supabase participant and submission reads.
- Sheet fallback when runtime participant, submission or programme-state reads fail.
- Sheet fallback for submission scoring writes.
- Sheet-only participant submissions.
- Sheet-owned stage timers, registration state, stage status and projector broadcast.
- Direct participant-row PATCH for leader claim.

Current stage/activity/experience remains in `runtime_events` and `runtime_missions`. Timers and broadcast live in `runtime_events.runtime_control_state`. Submissions and review state use `runtime_submissions`; credits use the transaction ledger; leaderboard is derived from runtime submissions/credits and is not independently mutable.

EventState and other Sheet mirrors may be updated only after a successful authoritative runtime write. A mirror failure produces a warning but cannot reverse or originate live state.

## Migration safety

- Forward: `supabase/012_foundation_identity_runtime_authority.sql`
- Rollback: `supabase/012_foundation_identity_runtime_authority_rollback.sql`
- Preflight: `supabase/012_foundation_identity_runtime_authority_dry_run.sql`

Migration 012 is non-destructive and does not rewrite production participants. It adds one JSON control-state column, functions, a trigger and indexes. The rollback preserves captured control-state data and all identity/audit records. The preflight is SELECT-only.

Do not apply migration 012 when `SafeToApply` is false. Existing duplicate credit sources must be reviewed manually; they are never deleted automatically.

## Verification results

- Python compilation: passed.
- Focused identity/runtime/integration suite: 55 passed.
- Full regression suite: 211 passed.
- Deterministic concurrency: passed at 100, 250 and 500 participants.
- Dual-event isolation: 200 participants passed.
- Failure recovery: two injected transient failures per request passed.
- Concurrent recovery: 100 parallel restores returned identical ParticipantID, TeamID, country, flag, leader state and credits.
- Duplicate identities: zero.
- Restore mismatches: zero.
- Maximum team distribution spread: one.

The concurrency evidence is stored at `outputs/sprint-011a/concurrency-results.json`. It is local deterministic evidence, not production mobile or infrastructure certification.

## Production-readiness impact

P0 Gates 1 and 2 are code-complete and regression-protected. Production behavior will intentionally fail closed if the application is deployed before migrations 011 and 012 are available. Deployment sequence must therefore be: read-only dry run, backup, migration 011 if still pending, migration 012, database smoke tests, then application deploy.

Remaining approval/evidence:

1. Production read-only audit and dry-run output.
2. Explicit approval to apply migrations 011 and 012.
3. Backup/rollback verification.
4. Explicit deployment approval.
5. Physical mobile matrix and live telemetry certification.

Gates 3–6, navigation, programme, Experience, reporting and visual redesign remain untouched.
