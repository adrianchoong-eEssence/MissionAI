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
5. `supabase/036_exos_core_v2_team_formation_v1.sql` — additive Sprint 2 Core
   Team Formation contract. Depends on the live 020/021/022/026 catalog. It
   adds nullable capacity, hashed opaque Team Formation recovery credentials,
   and Captain fields, scoped integrity constraints, guarded Core RPCs, and no
   fixture. It is selected
   only by `event_payload.TeamFormation.SchemaVersion = 1`; existing events
   retain their current behavior. Its guarded rollback is
   `036_exos_core_v2_team_formation_v1_rollback.sql`, and its read-only
   verifier is `verification/exos_core_v2_team_formation_v1_verify.sql`.
6. `supabase/037_theme_park_race_engine.sql` — additive generic Theme Park
   Race V1 contract. Depends on 020/025, 022 and 036. It creates no tables;
   it configures only `RaceConfiguration.EngineKind = THEME_PARK_RACE`, uses
   existing activity `race_station` payloads and routes, and guards Captain
   submissions through existing runtime/submission records. Its guarded
   rollback is `037_theme_park_race_engine_rollback.sql`; its read-only
   verifier is `verification/exos_v2_theme_park_race_engine_verify.sql`.
7. `supabase/037a_theme_park_race_acl_hardening.sql` — additive privilege-only
   remediation for an installed 037 engine. It resets preserved
   `CREATE OR REPLACE` function ACLs to the reviewed 037 role matrix and makes
   no schema, data, trigger, or event changes. It is required before 038 when
   upgrading an earlier 037 installation.
8. `supabase/038_theme_park_race_open_mission_board.sql` — additive
   extension of the generic engine. It depends on 037 but leaves the 037 source
   file unchanged, retains `CONFIGURED_TEAM_ROUTE`, and adds opt-in
   `OPEN_MISSION_BOARD` behavior using existing event payload, activity runtime,
   submissions, reviews, Captain sessions and score ledger records. It creates
   no tables. Its present guarded rollback refuses to run when OPEN_MISSION_BOARD
   configuration, runtime, submission lineage, or audit history exists; otherwise
   it removes only 038-specific objects and restores the approved 037 replaced
   function definitions without deleting operational history. Its verifier is
   `verification/exos_v2_theme_park_race_open_mission_board_verify.sql`.
9. `supabase/039_theme_park_race_review_reopen_contract.sql` — additive
   OPEN_MISSION_BOARD facilitator review/reopen contract. It depends on 036,
   037, 037a, and 038; creates no tables; preserves CONFIGURED_TEAM_ROUTE and
   non-Theme-Park review behavior; and uses a server-derived revision score-ledger
   identity. Its guarded rollback preserves operational history, and its verifier
   is `verification/exos_v2_theme_park_race_review_reopen_contract_verify.sql`.
10. `supabase/040_theme_park_race_terminal_lifecycle.sql` — terminal lifecycle
   extension, dependent on 037/037a/038/039. It adds persisted
   `HELD`, projects the existing persisted `CLOSED` terminal value as `ENDED`,
   and prevents restart or post-end open-board operational writes. It creates
   no tables. Its guarded rollback is
   `040_theme_park_race_terminal_lifecycle_rollback.sql`; its read-only
   verifier is `verification/exos_v2_theme_park_race_terminal_lifecycle_verify.sql`.

### R.A.C.E.-specific migrations, not Standard recovery migrations

- `022_exos_core_v2_team_access.sql` — team PIN/access/session schema and
  functions for Captain access; depends on 020.
- `023_exos_core_v2_race_results_locking.sql` — R.A.C.E. result-lock trigger;
  depends on the `race_results_v2` table from 020.
- `024_exos_core_v2_team_access_recovery.sql` — Captain cross-device team access
  recovery; depends on 022. It is not a Standard participant recovery migration.
- `027_formula_race_core_v2_atomic_operations.sql` — R.A.C.E.-only function
  patch for explicit Captain technical actors, idempotent checkpoint approval,
  atomic purchases, and deterministic final-result locking; depends on 020,
  022, 023, and 024. It does not alter the frozen Standard runtime.
- `028_formula_race_manual_credit_adjustments.sql` — R.A.C.E.-only,
  service-controlled, idempotent manual credit-ledger adjustment function; it
  depends on the Core v2 ledger and does not alter the frozen Standard runtime.
- `030_formula_race_configurable_event_architecture.sql` — R.A.C.E.-only
  configurable station/route/scoring/marketplace/judging/reset contract;
  depends on 020, 022–024, and 027–029. It is not installed from repository
  evidence and does not alter the frozen Standard runtime.

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
is **UNKNOWN from repository evidence**. Kai independently confirmed the Team
Formation V1 RPCs from 036 in the EXOS Core v2 staging PostgreSQL catalog on
2026-08-21; this is staging capability evidence, not migration-history
evidence. The release incident record says 026 was manually installed during
Standard recovery UAT, but that is not a durable database-history artifact.
Verify the live catalog before applying or reapplying any file; migration
history is not capability proof. Do not describe 024 as an installed Standard
migration.

Read-only staging catalog reconciliation during baseline repair established
semantic final-contract equivalence for the 037/037a/038/039 Theme Park Race
chain: expected signatures, function controls, ACLs, and triggers are present.
Staging migration history has no individual 037/037a/038/039 entry, so this is
not byte-identical historical SQL provenance. It is not human-UAT or load
evidence. The same history records 040 terminal lifecycle installation.

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
