# Sprint 011C — Foundation Gate 5

## Root cause

The legacy `MissionTemplates` → `Missions` workflow copied authored fields into every event. Definition identity, event configuration and live state were therefore conflated. Published templates were mutable, event deletion removed copied content, participant previews were separate from runtime rendering, and historical submissions did not retain Definition/Assignment versions.

## Architecture and ownership

- Experience Centre writes immutable-versioned `experience_definitions`.
- Event Centre writes sparse `event_experience_assignments` containing stable parent IDs, order, activation and optional overrides.
- Control Centre places only an active AssignmentID into authoritative runtime state.
- Participant runtime resolves Assignment → exact Definition version → sparse overrides.
- Intelligence reports retain AssignmentID, DefinitionID, DefinitionVersion and AssignmentVersion stamped when a submission is created.
- Assets and Characters remain referenced by stable IDs. Assignment and crop operations do not copy media.

`engines/experience_library.py` is the resolution/versioning service. `components/experience_preview.py` is the shared participant renderer used by Experience Centre and participant runtime. Missing assets produce a safe fallback; missing definitions and inactive assignments fail closed.

Legacy `MissionTemplates` and `Missions` remain readable migration sources only. Their authoring/assignment UI is no longer routed from Experience Studio.

## Migration artifacts

- Forward: `supabase/013_experience_definition_assignment.sql`
- Rollback: `supabase/013_experience_definition_assignment_rollback.sql`
- SELECT-only preflight: `supabase/013_experience_definition_assignment_dry_run.sql`
- Legacy audit/mapping: `scripts/experience_migration_audit.py`

## Exact proposed mapping

1. Each unique MissionTemplate `(TemplateID, Version)` becomes one Definition version with `ExperienceDefinitionID = TemplateID`.
2. A Mission with a valid TemplateID becomes an Assignment referencing that exact version; only fields differing from the template become overrides.
3. A Mission without TemplateID is fingerprinted from authored fields and proposed as `LEGACY-DEF-<12-char checksum>` for manual review.
4. Assignment IDs are proposed as `ASN-<EventID>-<MissionID>`.
5. DisplayOrder becomes AssignmentOrder. Status maps to Active without modifying legacy rows.
6. Closed/archived Missions are classified historical and are never silently moved to a newer Definition version.
7. Duplicate fingerprints are reported as generated duplicates but are never merged automatically.

## Production execution plan

1. Run both SELECT-only audits and export their JSON.
2. Back up MissionTemplates, Missions, runtime_missions and runtime_submissions; record row counts and SHA-256 checksums.
3. Review every manual Definition mapping, duplicate, orphan and historical version.
4. Obtain explicit approval for migration 013.
5. Apply migration 013 only; validate tables, constraints, RLS and submission stamping trigger.
6. Insert separately approved Definition versions, then Assignments, in a transaction.
7. Compare checksums and counts. Do not delete, deactivate or rewrite legacy rows.
8. Deploy application only after separate approval.

## Rollback

The rollback refuses to run when Assignments or version-stamped submissions exist. Before an approved rollback, export both new tables and all stamped submissions. If no canonical records are in use, remove the trigger/function, drop the new tables and remove the unused submission columns. Legacy content remains unchanged throughout.

## Safety status

No migration, deployment, Experience mutation, merge, deletion, archive or production rewrite was executed.

The production legacy audit was attempted locally on 3 August 2026 and stopped before reading records because the workspace has neither `.streamlit/secrets.toml` nor `mission_ai_service_account.json`. The SELECT-only audit and proposed mapping utility is ready for the credentialed environment. No production record was changed.
