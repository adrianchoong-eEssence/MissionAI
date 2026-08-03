# RC1 Rollback Checklist

## Before deployment

- [ ] Record current application release identifier and migration history.
- [ ] Create and verify restorable database and Google Sheets backups.
- [ ] Export canonical and legacy row counts/checksums.
- [ ] Review 012, 013 and 014 rollback guards; confirm whether rollback is permitted after live canonical writes.
- [ ] Define abort owners and thresholds for errors, latency, duplication, identity mutation and reconciliation drift.

## Application rollback

1. Pause participant entry and Control Centre mutations.
2. Preserve logs, traces, audit records and failed request identifiers.
3. Restore the prior application release without altering participant records.
4. Run read-only identity, runtime and ledger reconciliation.
5. Resume only after the prior release's schema compatibility is confirmed.

## Migration rollback

1. Do not run a rollback script merely because deployment failed.
2. Determine whether canonical Definitions, Assignments, Submissions, Reviews, Awards or Judge Scores have been written.
3. If rollback guards refuse, preserve the forward schema and roll back the application only; never delete immutable history.
4. If no canonical records exist and rollback is approved, execute rollback scripts in reverse order: 014, 013, 012. Migration 011 requires its separately reviewed restoration procedure and backup.
5. Re-run schema checks, counts, checksums and read-only audits.

## Recovery confirmation

- [ ] No participant identity/team/country/leader changed.
- [ ] No Submission, Review or Award history was lost.
- [ ] Ledger balances and leaderboard reconcile.
- [ ] Broadcast/runtime state is safe before resume.
- [ ] Incident timeline and rollback evidence are archived.

