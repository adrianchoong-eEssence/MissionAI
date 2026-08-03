# Sprint 011B — Foundation Gate 4

## Root cause

Programme hierarchy was reconstructed independently from `ProgrammeStages` by Control Centre, participant runtime and projector code. The former engine inferred modules and content from StageNo, display names, MissionID prefixes and an EVT-0004-only projection. Those mutable labels created competing interpretations of the same programme.

## Canonical implementation

`engines/programme_adapter.py` is now the only hierarchy builder. It exposes Event → Programme → Module → Activity → Linked Content, stable-ID runtime resolution, participant-safe views, reporting identity, registered content handlers, integrity validation and a read-only legacy audit.

Legacy ProgrammeStages rows remain readable through generated compatibility IDs. They are reported for migration but are never rewritten, deactivated or treated as an alternative live authority. Runtime payloads with ActivityID resolve only by ActivityID. StageNo is accepted only for pre-stable-ID runtime compatibility and must resolve uniquely.

Control Centre remains the only live mutation authority. Event Centre configures hierarchy records and shows validation errors. Participant, projector and reporting consume the adapter.

## Migration plan and rollback

No schema migration is required for Gate 4. Canonical fields are carried in the existing activity metadata envelope, so no forward or rollback SQL was created.

The future production data correction is explicit and approval-gated:

1. Run `scripts/programme_hierarchy_audit.py` read-only.
2. Review every proposed legacy StageNo → ProgrammeID/ModuleID/ActivityID mapping.
3. Resolve duplicates, missing links and order collisions manually.
4. Back up ProgrammeStages.
5. After separate approval, write stable metadata without deleting history.
6. Validate both canonical and legacy reads, then mark superseded rows only after separate approval.

Rollback for a later approved data correction is restoration of the backed-up ProgrammeStages metadata and removal of only the newly added canonical metadata keys. Participant, submission, credit and runtime identity records remain untouched.

## Safety

- No production deployment.
- No migration applied.
- No production record rewritten or deactivated.
- Gate 3 capability boundary preserved.
- The audit reports `ProductionRecordsChanged: false` by construction.

## Production audit status

The SELECT-only audit was attempted locally on 3 August 2026. It stopped before reading any rows because neither `.streamlit/secrets.toml` nor `mission_ai_service_account.json` is available in this workspace. No fallback data source was used and no production record was changed. The audit utility is ready to run in the credentialed production environment; its results remain an explicit production acceptance gate.
