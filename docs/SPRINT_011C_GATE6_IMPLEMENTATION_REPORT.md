# Sprint 011C — Foundation Gate 6

## Root cause

Legacy submission rows doubled as review state, screens calculated scores and leaderboards independently, `exos_update_submission` overwrote decisions, wallet totals coexisted with a transaction table, and event-specific formulas lived in UI code. These paths could not preserve decision history or reproduce corrected historical results.

## Canonical architecture

Participant Action → canonical Submission → append-only Review Decision → immutable Award Transaction → derived Team Balance → deterministic Leaderboard → read-only Report Projection.

Every record carries stable event/team/participant/programme/module/activity/Definition/Assignment IDs and versions where applicable. Participant creation is authorized in the database from immutable identity, leader state, overrides, current Assignment and Assignment submission rules. Database uniqueness protects retries and concurrent requests. Evidence metadata must exist before the Submission is created.

Control Centre owns review, corrections, manual Awards and final locks. Rejections create no Award. Repeated reviews and Awards are idempotent. Corrections reverse prior Awards with new immutable transactions. Team balances and leaderboards are views derived only from the canonical Award ledger. Reusable multi-judge aggregation supports weighted average, median and highest/lowest exclusion.

## Artifacts

- Engine: `engines/transaction_pipeline.py`
- Forward: `supabase/014_canonical_transaction_pipeline.sql`
- Rollback: `supabase/014_canonical_transaction_pipeline_rollback.sql`
- Dry run: `supabase/014_canonical_transaction_pipeline_dry_run.sql`
- Audit and reconciliation: `scripts/transaction_migration_audit.py`

## Exact migration proposal

1. `runtime_submissions` with complete Gate 5 stable references become canonical Submission candidates.
2. Approved/rejected legacy status becomes a proposed append-only Review Decision, never an automatic write.
3. `runtime_credit_transactions` maps EARN/SPEND/REFUND/ADJUSTMENT/REVERSAL to canonical Award types.
4. Sheet submissions are reporting projections unless a unique runtime source is unavailable and manually verified.
5. Screen-calculated rankings and Team.Score columns are reconciliation inputs only, never migrated authority.
6. Judge rows require explicit JudgeID/CriterionID/configuration mapping before migration.
7. Duplicate, orphaned and historical-only records require manual review; no merge, award, reversal or score correction is automatic.

## Balance and leaderboard reconciliation

The audit groups the legacy ledger by Event/team, compares it with Sheet Team.Score, reports differences without correction, and rebuilds a deterministic `(amount DESC, stable team identifier ASC)` ranking. Migration is blocked until every unexplained difference and duplicate source is resolved.

## Production execution and rollback

Back up and SHA-256 checksum runtime_submissions, runtime_credit_transactions, wallet tables, Sheet Submissions/Teams and report exports. Run both dry runs and the audit. Apply migration 014 only after explicit approval, migrate separately approved records transactionally, compare row counts/balances/rankings, then deploy after separate approval.

Rollback refuses to drop canonical tables after any Submission, Review, Award or Judge Score exists. Export and preserve immutable history first. No production migration, submission, credit, score, report or deployment action was performed in this sprint.

The production audit was attempted locally on 3 August 2026 and stopped before reading any row because `SUPABASE_SECRET_KEY` is unavailable. No fallback authority was used and no production record changed. The audit, mappings, balance reconciliation and leaderboard reconciliation are ready for the credentialed environment.
