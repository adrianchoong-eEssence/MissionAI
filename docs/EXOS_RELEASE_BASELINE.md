# EXOS Standard Core v2 Release Baseline

## Baseline identity

- Frozen Standard runtime commit:
  `41cb91e91a75a36001daef72e0943e7bc84eb81e`
- Runtime commit date: 2026-08-12 17:59:00 +0800
- Branch at freeze: `feature/exos-core-v2`
- Repository-memory documentation commit: `fe0faf76b9b4fcdd071d5851eebfc93272637fda`

The documentation commit is deliberately separate from the runtime baseline.
When a checkout has later commits or a dirty working tree, compare it with
`41cb91e` before describing it as frozen Standard behavior.

## Environment and reference identifiers

- Intended environment: Standard Core v2 staging (`EXOS_ENV=staging`)
- Admin: https://exos-master2.streamlit.app/
- Facilitator: https://missionai-faci2.streamlit.app/
- Participant: https://missionai-parti2.streamlit.app/
- Projector: `https://missionai-faci2.streamlit.app/?view=projector&event_id=<EVENT_ID>`

The following are UAT reference identifiers, not a claim that the events are
currently present or healthy in any database:

- Upper South: `AIA-WE-260810081110-UPPER` / `OXO0DT`; teams Korea, Japan
- Lower South: `AIA-WE-260810081110-LOWER` / `C0OCUS`; teams India, Malaysia,
  Philippines, Thailand
- R.A.C.E. staging reference:
  `CORE-V2-RACE-UAT-EVT-4CF0CEAF5F` / `RACE4CF0CE`

## Core v2 SQL inventory and order

### Standard forward migration chain

1. `supabase/020_exos_core_v2_schema.sql` — schema foundation and initial Core
   v2 functions. Clean-room only; it fails if legacy runtime objects exist.
2. `supabase/021_exos_core_v2_pgcrypto_fix.sql` — function-only patch replacing
   the join function with explicit `extensions.digest`/`gen_random_uuid`
   resolution. Depends on 020.
3. `supabase/025_standard_programme_runtime.sql` — function-only Standard
   activity launch/state/submit/review contract. Depends on 020 (and the 021
   corrected join foundation in the release chain). It creates no tables.
4. `supabase/026_standard_participant_access_recovery.sql` — function-only
   Standard identity/restore/cross-device recovery patch. Depends on the Core
   schema and `extensions.digest`; it creates no tables or columns and never
   changes participant/team assignment.

### R.A.C.E.-specific migrations, not Standard recovery migrations

- `022_exos_core_v2_team_access.sql` — team PIN/access/session schema and
  functions for Captain access; depends on 020.
- `023_exos_core_v2_race_results_locking.sql` — R.A.C.E. result-lock trigger;
  depends on the `race_results_v2` table from 020.
- `024_exos_core_v2_team_access_recovery.sql` — Captain cross-device team access
  recovery; depends on 022. It is not a Standard participant recovery migration.

### Rollback, verification, and diagnostics

- `020_exos_core_v2_schema_rollback.sql` is the guarded rollback companion to
  020; it is not a forward migration.
- `supabase/verification/exos_core_v2_preflight.sql`,
  `exos_core_v2_postflight.sql`, and `exos_core_v2_rollback_verify.sql` are
  verification scripts, not forward migrations.
- Other files in `supabase/verification/`, including reset/cleanup/readiness
  utilities, are diagnostics or controlled test helpers. Classify them by their
  own header before use; never add them to a deployment chain by filename alone.

### Staging installation status

The repository contains no Supabase migration-history export or credentialed
staging query result. Therefore the installed status of 020, 021, 025, and 026
is **UNKNOWN from repository evidence**. The release incident record says 026
was manually installed during Standard recovery UAT, but that is not a durable
database-history artifact. Verify the target database before applying or
reapplying any file. Do not describe 024 as an installed Standard migration.

## Secrets and configuration

No secret values belong in Git or documentation. Runtime reads:

- `EXOS_ENV`
- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY` (or `SUPABASE_ANON_KEY`)
- `SUPABASE_SECRET_KEY` (or `SUPABASE_SERVICE_ROLE_KEY` for service operations)

## Release boundaries

- This baseline freezes Standard Core v2 runtime behavior only; it does not
  certify every historical Admin/legacy screen as Core-v2-only.
- It is staging/UAT evidence, not production certification.
- It is not a 250-concurrent-participant readiness or load certification.
- Formula R.A.C.E. has its own staging adapter, migrations, operational model,
  and UAT gate. Read `docs/RACE_HANDOVER.md`.
