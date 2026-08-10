# Sprint 010 — Production Execution Plan

Current gate: **NO-GO — live read-only audit evidence unavailable**

## Confirmed source state

- `origin/main` contains `c4b516a` and `d2a20e5`.
- Local and remote refs are synchronized at `d2a20e5`.
- No production deployment, migration, or participant mutation has occurred.

## Phase 0 — mandatory read-only audit

Run `supabase/011_participant_identity_preflight_audit.sql` against production with a read-only database role. Export the single JSON result unchanged and record query timestamp, project ref, database role, event ID, and row counts. This query does not require migration 011 and performs no writes.

Engineering must classify every returned record as:

- no action;
- keep separate;
- confirm same participant without merge;
- proposed merge into a named canonical ParticipantID;
- proposed TeamID/country correction;
- proposed leader correction;
- proposed submission reattachment;
- manual review required.

No correction statement may be generated with placeholder IDs.

## Phase 1 — backup and change window

1. Freeze registration and submissions for the target event.
2. Record participant, submission, credit-ledger, and leader checksums/counts.
3. Take and verify a database backup/PITR restore point.
4. Confirm rollback owner and 30-minute change window.
5. Apply `supabase/011_participant_identity_engine.sql` in one SQL Editor transaction where supported.
6. Do not execute any duplicate merge, team correction, or leader correction in this phase.
7. Rerun the read-only audit and compare counts.

## Exact migration SQL

The migration artifact to apply byte-for-byte is `supabase/011_participant_identity_engine.sql` from commit `c4b516a`. Verify its SHA-256 immediately before execution. Do not paste a partial migration or run numbered sections out of order.

Important: migration 011 backfills only previously empty TeamID/country values from the participant's already stored team/status. It does not merge or delete participants. Treat that backfill as an authorised migration write requiring separate approval.

## Production correction plan

Corrections must be generated only after Phase 0 supplies exact ParticipantIDs. For each proposal record:

- canonical and affected ParticipantID;
- current and proposed TeamID/country/flag/leader;
- linked submission IDs;
- credit-ledger transaction IDs and calculated invariant;
- reason and evidence;
- facilitator/product approval;
- exact audited RPC call;
- rollback value.

Permitted audited RPCs after explicit correction approval:

- `exos_admin_duplicate_decision(..., 'KEEP_SEPARATE', ...)`
- `exos_admin_duplicate_decision(..., 'CONFIRM_SAME', ...)`
- `exos_admin_duplicate_decision(..., 'MERGE', ...)`
- `exos_admin_move_participant(...)`
- `exos_admin_transfer_leader(...)`

## Rollback plan

Trigger rollback for migration error, join failure, identity mismatch, team mutation, leader-right loss, duplicate participant/credit, or p95 latency above five seconds.

1. Stop participant traffic and disable submission controls.
2. Capture failing request IDs and audit rows.
3. Roll the application back to commit `359f751` without deleting Sprint 010 audit evidence.
4. Restore the pre-change database snapshot if migration 011 caused data corruption.
5. If schema rollback without restore is required, restore the `exos_join_event`, `exos_restore_join`, and `exos_restore_participant` definitions from `010_idempotent_concurrent_join.sql`; revoke new admin RPC execution; retain new columns and audit tables to avoid destructive data loss.
6. Verify pre-change participant/submission/credit checksums.
7. Reopen traffic only after the original identity smoke test passes.

Never drop identity/audit tables during emergency rollback. Snapshot restore is the authoritative data rollback.

## Deployment plan

1. Complete and approve Phase 0 audit.
2. Approve migration 011 separately.
3. Complete backup and checksum evidence.
4. Apply migration 011.
5. Run database smoke tests using a dedicated synthetic event.
6. Approve application deployment separately.
7. Deploy `d2a20e5` using the existing hosting workflow.
8. Verify displayed build SHA and application health.
9. Execute post-deployment checklist and certification before RACE approval.

## Post-deployment validation

- Fresh join returns one ParticipantID and persisted TeamID/country/flag.
- Same-name/case/space/punctuation re-login finds the existing record.
- Ambiguous full name displays recovery choice and creates nothing.
- Refresh, rerun, deployment restart, and device change restore identity.
- Current leader state and submission rights come from backend.
- Leadership transfer is immediate and original leader cannot reclaim it.
- Event/team overrides enable and reverse safely.
- Duplicate merge is confirmation-gated and audited.
- Participant/submission/credit counts reconcile to pre-change evidence.
- No Experience, Asset Library, programme, Sync AI, or Catalyst behavior changes.

## Physical mobile recovery matrix

Execute 13 scenarios on iOS Safari, iOS Chrome, Android Chrome, and Samsung Internet: fresh/slow/double join, refresh, 30-second and five-minute background, lock/unlock, close/reopen, network loss, same-name login, leader reconnect, member reconnect, and concurrent same-participant requests.

Every cell must preserve ParticipantID, TeamID, country, flag, current leader state, submissions, progress, and credits with zero new participant rows or credit transactions.

## Live telemetry certification

- Join success >= 99.5% without manual retry.
- p50/p95/p99 captured; p95 <= 2 seconds and p99 <= 5 seconds.
- Retryable 429/5xx < 1%; non-retryable server errors = 0.
- Database CPU/connections below 70% sustained; lock-wait p95 < 250 ms.
- Zero duplicates, cross-event leakage, team mutation, leader loss, or duplicate credits.
- Dual-event peak and 30-minute soak pass with >=30% measured headroom.

## Remaining approval decisions

1. Provide/authorise read-only production database access and EVT-0004 audit execution.
2. Approve or reject each exact production record correction after audit review.
3. Approve migration 011, including non-destructive null-field backfill.
4. Approve the production change window and verified backup.
5. Approve Sprint 010 application deployment.
6. Approve RACE only after mobile and live telemetry certification passes.
