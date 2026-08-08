# EXOS Core v2 Migration Order

## Phase 1: schema
1. `020_exos_core_v2_schema.sql`

## Phase 2: contract checks (read-only)
1. `verification/exos_core_v2_preflight.sql`

## Phase 3: dry validation
1. Seed fixture data for one event, programme, modules, teams, and one activity row (not provided in this queue; no production mutation).
2. Execute `exos_v2_publish_event`, `exos_v2_join_event_v2`, `exos_v2_restore_join` in a non-production environment.

## Phase 4: post-validation
1. `verification/exos_core_v2_postflight.sql`
2. Replay idempotency and recovery contracts at the app-level test layer.

## Rollback safety
1. Verify all runtime tables are empty for the event subset:
   - `score_transactions_v2`, `credit_transactions_v2`, `submissions_v2`, `reviews_v2`, `participant_sessions_v2`.
2. Execute `020_exos_core_v2_schema_rollback.sql` only when non-destructive gates pass.

## Post-merge
- Run `verification/exos_core_v2_rollback_verify.sql` immediately after non-destructive rollback drills.
