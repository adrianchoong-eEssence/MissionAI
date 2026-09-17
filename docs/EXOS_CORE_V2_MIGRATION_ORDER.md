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

## Prepared Hunt Engine V1 chain — owner authorisation required

1. Verify the dedicated target's installed 036, 042–044, and 048 foundation
   state. Do not infer it from this repository.
2. Run `supabase/051_exos_core_v2_hunt_engine_v1.sql` only after explicit owner
   authorisation. It is an additive forward migration.
3. Run `supabase/verification/exos_v2_hunt_engine_v1_verify.sql` as a read-only
   postflight check, then use fresh George Town and Nera fixtures for isolation.
4. `051_exos_core_v2_hunt_engine_v1_rollback.sql` is a guarded rollback. It
   refuses to delete Hunt data; use it only after an approved empty-target gate.

## Prepared ENCA hybrid architecture chain — owner authorisation required

1. First verify the target's installed 036/036a Team Formation, 042 attendance,
   044 Captain operations, 048/050 location/announcement, and 051 Hunt
   foundations. Repository files are not installation evidence.
2. Run `supabase/053_enca_hybrid_event_architecture.sql` only after explicit
   owner authorisation. It is additive and creates no event fixture, Personal
   Key, country list, route, checkpoint, mission, or score data.
3. Run `supabase/verification/exos_v2_enca_hybrid_event_architecture_verify.sql`
   read-only. Only then, and only with a separately authorised disposable
   target, use the redacted ENCA plan to configure the EventID.
4. `053_enca_hybrid_event_architecture_rollback.sql` refuses to remove hybrid
   or stage data. Use it only after a verified empty-target gate.
