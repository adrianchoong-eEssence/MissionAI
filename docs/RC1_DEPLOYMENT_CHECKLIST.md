# RC1 Production, Migration and Deployment Checklist

Unchecked items are release blockers.

## Production gate

- [ ] Confirm the exact L'Oréal RACE EventID and immutable release commit.
- [ ] Export timestamped backups and row-count/checksum manifests for every affected Supabase table and Google Sheet.
- [ ] Run 011, 012, 013 and 014 SELECT-only preflights against production and archive complete output.
- [ ] Run identity, programme, Experience and transaction audits; resolve every duplicate, orphan, ambiguous identity, balance difference and manual-review item.
- [ ] Confirm migrations 001–010 already match production migration history.
- [ ] Verify production secrets, service roles, RLS, storage permissions and Google access without exposing credentials.
- [ ] Confirm no unresolved P0/P1 operational incident.

## Migration gate

- [ ] Obtain explicit approval for each migration: 011, 012, 013 and 014.
- [ ] Require every dry run to report safe-to-apply/no blocking anomaly.
- [ ] Apply migrations sequentially in a controlled window; stop on the first error.
- [ ] Verify functions, triggers, constraints, indexes, views, RLS and grants after each migration.
- [ ] Re-run all read-only audits and compare counts/checksums.
- [ ] Do not migrate or correct legacy records without a separately approved, record-exact correction manifest.

## Deployment gate

- [ ] Obtain explicit deployment approval.
- [ ] Deploy the immutable RC commit only after database verification.
- [ ] Verify health, application startup, logs and dependency connectivity.
- [ ] Execute all smoke scenarios on an isolated production certification event.
- [ ] Execute concurrent live joins, submissions, approvals, credits and broadcast with telemetry.
- [ ] Execute the full physical mobile browser matrix and all recovery drills.
- [ ] Verify no duplicate participants, submissions or awards and no team/leader mutation.
- [ ] Verify reports and leaderboard exactly reconcile to the canonical award ledger.
- [ ] Obtain facilitator, engineering and event-owner sign-off.

## Recovery gate

- [ ] Prove participant, leader, submission, approval and runtime recovery.
- [ ] Prove manual override and manual credit correction audit trails.
- [ ] Confirm on-call owner, escalation path, maintenance window and abort thresholds.
- [ ] Keep rollback artifacts and verified backups immediately accessible.

## Telemetry acceptance

- [ ] Capture request rate, success/error rate, p50/p95/p99 latency and timeouts for join, restore, submit, review, award and broadcast.
- [ ] Capture database locks, deadlocks, connection saturation, function errors and replication/queue lag where applicable.
- [ ] Capture Streamlit restarts, exceptions and session churn.
- [ ] Define and meet written capacity and error-budget thresholds with at least 30% headroom over forecast peak.

