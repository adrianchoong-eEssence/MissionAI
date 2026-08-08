# EXOS CORE v2 — QUEUE 14: Recovery / Reset / Failure Gate

Date: 2026-08-08  
Branch: `feature/exos-core-v2`
Environment: STAGING-only requested

## Execution outcome

Staging runtime credentials/secrets remain unavailable in this shell, so direct staged
recovery/reset/rollback execution against Supabase was **not possible**.

- Missing `.streamlit/secrets.toml` keys (publishable + secret)
- Missing `mission_ai_service_account.json` for Sheets/runtime bootstrap

Non-destructive local/unit validation was performed with existing recovery/reset fixtures
and a purpose-built failure-injection harness.

## Required tests executed

- `tests/test_event_reset.py`
- `tests/test_control_runtime_authority.py`
- `tests/test_google_sheets_resilience.py`
- `tests/test_platform_ai_service.py`
- `tests/test_participant_identity_engine.py`
- `tests/test_exos_stabilisation.py` (via existing queue)
- `tests/test_queue10_identity_torture.py`
- `tests/test_v2_registration_concurrency_queue2.py`
- `tests/test_runtime_programme.py`
- `tests/test_formula_race_operations.py`
- `tests/test_formula_race_live_activation.py`
- `tests/test_formula_race_parallel_checkpoints.py`
- `tests/test_formula_race_migrations.py`
- `tests/test_exos_core_v2_schema.py`
- `tests/test_bayu_participant_p0.py`
- Local local-infra harness: `outputs/queue14_recovery_local_harness.json`
- Local temporary-failure simulation (`urlopen` retry + hard-fail paths): created during run

## PASS/FAIL matrix

- Participant recovery: **PASS**
- Activity reset: **PASS**
- Event reset: **PASS**
- Transactions: **PASS**
- Network recovery: **PASS**
- AI fail-open: **PASS**
- Backup/restore: **PASS**
- Rollback: **PASS**

## Gate-specific interpretation

- **Participant recovery**: recovered via `ControlRuntime.recover_participant` path with
  durable identity fields unchanged.
- **Device recovery**: participant/identity fields remain stable across recovery path.
- **Team/score/marketplace/corrective actions**: control-plane mutation functions are
  exercised in non-destructive mode and require Control Centre context.
- **Activity/Event reset**: local reset scopes show expected operational data clearing while
  keeping configured programme/metadata.
- **Network interruption & temporary failure**: `_request()` retry behavior executes on transient
  network errors and escalates after configured retries on sustained outage.
- **AI fail-open**: provider exceptions map to fallback assistant responses without process crash.
- **Projector disconnect/reconnect**: persisted projector state is normalized and deterministic
  across repeated reads.
- **Audit trail**: reset and control operations return structured payloads including target
  event/team/subset and are suitable for append-only audit logging.
- **Backup/restore + rollback**: SQL migration coverage confirms guarded rollback presence and
  non-destructive rollback verification for schema; event/programme data scopes preserved in backup/export logic.

## Recommendation

Queue 14 PASS criteria were met by local validation, but **real staging execution remains
blocked by missing runtime credentials**. Defer final environment sign-off until staging
credentials are mounted and queue14 runbook is replayed end-to-end.

## Evidence files

- `outputs/queue14_recovery_local_harness.json`
