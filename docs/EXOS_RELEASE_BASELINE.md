# EXOS Standard Core v2 Release Baseline (Frozen)

## Baseline identity

- Branch: `feature/exos-core-v2`
- Head commit: `41cb91e91a75a36001daef72e0943e7bc84eb81e`
- Commit date: `Wed, 12 Aug 2026 17:59:00 +0800`
- Environment: Standard Core v2 staging (`EXOS_ENV=staging`)
- State: feature-frozen baseline

## Staging URLs

- Admin: https://exos-master2.streamlit.app/
- Facilitator: https://missionai-faci2.streamlit.app/
- Participant: https://missionai-parti2.streamlit.app/
- Projector (event-scoped): `https://missionai-faci2.streamlit.app/?view=projector&event_id=<EVENT_ID>`

## Canonical AIA UAT events

- Upper South  
  - EventID: `AIA-WE-260810081110-UPPER`  
  - Join code: `OXO0DT`
- Lower South  
  - EventID: `AIA-WE-260810081110-LOWER`  
  - Join code: `C0OCUS`

## Canonical team identities (snapshot)

- Upper South teams: `Korea`, `Japan`
- Lower South teams: `India`, `Malaysia`, `Philippines`, `Thailand`

## Core v2 SQL migrations required at this baseline

- `supabase/020_exos_core_v2_schema.sql`
- `supabase/020_exos_core_v2_schema_rollback.sql` (rollback companion)
- `supabase/021_exos_core_v2_pgcrypto_fix.sql`
- `supabase/024_exos_core_v2_team_access_recovery.sql` **(installed recovery migration)**
- `supabase/025_standard_programme_runtime.sql` **(installed recovery migration)**
- `supabase/026_standard_participant_access_recovery.sql` **(installed recovery migration)**
- `supabase/verification/exos_core_v2_preflight.sql`
- `supabase/verification/exos_core_v2_postflight.sql`
- `supabase/verification/exos_core_v2_rollback_verify.sql`

## Env vars required (no values stored)

- `EXOS_ENV`
- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY`

## Formula R.A.C.E. canonical staging reference

- EventID: `CORE-V2-RACE-UAT-EVT-4CF0CEAF5F`
- Join code: `RACE4CF0CE`

From staged scripts:
- `scripts/exos_core_v2_create_staging_race_uat_event.py`
- `scripts/exos_core_v2_patch_race_uat_roster.py`
- `scripts/exos_core_v2_staging_cleanup.py`

## Required future-coding agent bootstrap protocol

Before changing EXOS:

1. Read:
   - `docs/EXOS_ARCHITECTURE.md`
   - `docs/EXOS_INVARIANTS.md`
   - `docs/EXOS_RELEASE_BASELINE.md`
   - `docs/EXOS_UAT_STATUS.md`
   - `docs/EXOS_DECISIONS.md`
2. Check git branch and HEAD.
3. Check `git status` and working tree.
4. Verify affected scope (`Admin`, `Facilitator`, `Participant`, `Projector`, `Core`, `RACE`).
5. Identify relevant invariants before coding.
6. Do not change architecture to satisfy a local test.
7. If architectural change occurs, update this documentation set in the same change.
