# RC2 Production Backup and Checksum Plan

This plan is executable only after the exact Supabase project and production workbook access are confirmed. Backups are read-only exports. Do not apply migrations, correct records or clean data while producing them.

## Scope

Supabase:

- `runtime_events`
- `runtime_teams`
- `runtime_participants`
- `runtime_identity_audit_log`
- `runtime_submission_overrides`
- `runtime_missions`
- `runtime_submissions`
- `runtime_credit_transactions`
- `runtime_team_wallets`
- `experience_definitions` if present
- `event_experience_assignments` if present
- `canonical_submissions`, canonical review/award/judge tables and derived views if present

Google Sheets workbook `1XWCW9UVj_1cxA32ItsE8-nAr9q0NEgOhhD5e3C64Hvw`:

- Events
- Participants
- Teams
- ProgrammeStages
- EventState
- MissionTemplates
- Missions
- Submissions
- Conversations
- ProgrammePacks
- Assets

## Procedure

1. Pause configuration edits for the backup window; record UTC start time, operator and running application SHA.
2. Export the Supabase schema, migration history and every scoped table as separate deterministic CSV or JSON files. Filter event-owned operational rows to EVT-0006 but export reusable Definitions referenced by its Assignments in full.
3. Export each scoped Google tab as CSV and export the complete workbook as XLSX.
4. Record for every artifact: source project/workbook, table/tab, filter, row count, byte count, export UTC time and SHA-256.
5. Store the manifest beside the artifacts in access-controlled storage outside the application repository.
6. Re-read production row counts after export. If a count changed, repeat that artifact or retain a consistent database snapshot.
7. Restore the backups into an isolated recovery project/workbook and compare row counts and SHA-256 values before migration approval.

## Acceptance gates

- [ ] Supabase project reference and application SHA are recorded.
- [ ] Migration history is exported.
- [ ] Every required table/view reports present or explicitly not-yet-created.
- [ ] Every artifact has a non-empty SHA-256 and row count.
- [ ] Google workbook ID and revision timestamp are recorded.
- [ ] The recovery restore completes without touching production.
- [ ] Restored counts and content checksums equal the source manifest.
- [ ] Backup location and restore operator are documented.

## Rollback linkage

- Migration 012 rollback: `supabase/012_foundation_identity_runtime_authority_rollback.sql`
- Migration 013 rollback: `supabase/013_experience_definition_assignment_rollback.sql`
- Migration 014 rollback: `supabase/014_canonical_transaction_pipeline_rollback.sql`
- Migration 011: restore from the verified pre-migration database backup and its separately reviewed identity-engine rollback procedure; do not infer an automatic destructive rollback.

Rollback scripts must be checked against the production schema after dry runs. If canonical records have been written and a rollback guard refuses, preserve the forward schema and roll back the application only; never delete immutable submission, review or award history.
