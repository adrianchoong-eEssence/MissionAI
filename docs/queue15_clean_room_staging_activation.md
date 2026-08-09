# EXOS CORE v2 — Clean-Room Staging Activation (Queue 15)

Date: 2026-08-09  
Branch: `feature/exos-core-v2`  
Staging project: **EXOS Core v2 Staging** (Mumbai, fresh schema)

## Result

- `supabase/020_exos-core_v2_schema.sql` is now guarded for clean-install behavior.
- A dedicated one-click verification SQL is added at:
  - `supabase/verification/exos_core_v2_clean_room_staging_verify.sql`

## Exact manual SQL Editor action (Adrian)

1) Open the SQL Editor in **EXOS Core v2 Staging**.

2) Paste and execute **only**:
   - `supabase/020_exos_core_v2_schema.sql`

3) After success, paste and execute immediately:
   - `supabase/verification/exos_core_v2_clean_room_staging_verify.sql`

4) Confirm the final verification row shows:
   - `EXOS CORE V2 STAGING READY = TRUE`

## Expected execution behavior

- If legacy EXOS runtime objects exist (for example `runtime_events`, `runtime_participants`, old RACE RPCs), migration should fail fast with a clear exception and **must not proceed**.
- On a clean staging DB, migration should complete with no destructive operations.

## Notes from implementation

- Added compatibility guard at the top of `020_exos_core_v2_schema.sql`:
  - aborts when legacy runtime tables are present.
  - aborts when legacy RPC names are present.
- Added service-role RLS policy bootstrap for all new Core v2 tables during install.

## Verification scope in `supabase/verification/exos_core_v2_clean_room_staging_verify.sql`

The verification block reports:

- Core v2 tables (exists)
- RPCs (exists)
- required indexes (exists)
- RLS (enabled)
- constraints/policies/permissions coverage
- pgcrypto/pg_trgm extensions
- legacy object detection
- final readiness flag

Final decision line:

`EXOS CORE V2 STAGING READY | TRUE|FALSE`

## Do not do yet

- Do not seed events.
- Do not create participants.
- Do not run load tests.
- Do not deploy Streamlit.
