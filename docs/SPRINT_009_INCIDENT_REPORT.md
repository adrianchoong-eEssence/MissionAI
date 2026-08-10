# Sprint 009 — EXOS Engineering Post-Mortem

Status: cross-platform mobile incident investigation required; production telemetry was not available.

## Executive summary

EXOS experienced a **cross-platform mobile participant identity and session persistence failure under live concurrency**. Both Android and iPhone participants were affected. A join could be processed more than once, and a returning participant could be allocated again instead of recovering the originally committed identity, team, country, leader rights, and credit state. The remediation landed in commits `85db331`, `4f3b8c6`, and `359f751` on 1 August 2026.

This incident is not classified as Android-specific. There is no evidence supporting an operating-system-specific root cause.

No claim is made here about incident volume, duration, or affected-user count because production logs and telemetry were not supplied. Those values must not be reconstructed from code history.

## User impact

- Android and iPhone users were logged out.
- Refresh, background, and resume did not reliably restore identity.
- Repeated joins could create duplicate participant records.
- Returning participants could lose durable team/country/leader assignment and submission rights.
- Duplicate clicks and refreshes could race with the first request.
- Slow requests encouraged repeated taps and duplicate entries.
- Pre-join paths could perform more work than required, increasing exposure during a join surge.

## Technical sequence

1. The earlier join flow did not enforce one atomic, database-owned identity decision.
2. Multiple requests could observe state before the participant commit completed.
3. Identity recovery was coupled too closely to device-scoped idempotency.
4. Remediation moved allocation into `exos_join_event`, locked the event row, selected the least-populated team, and committed through a unique event/idempotency key.
5. Follow-up remediation made normalized event/name identity the durable source of truth and restored the earliest committed record before allocation.
6. The UI now disables resubmission while joining and exposes an explicit existing-registration recovery path.

## Root causes

### RC-1 — Non-atomic ownership of join decisions

Participant existence, team allocation, and insert were not guaranteed to occur as one database transaction. Correctness depended on timing across separate operations.

### RC-2 — Incomplete idempotency boundary

Device-scoped request identity prevented some duplicate requests but did not by itself model a person returning on a different browser/device. Durable normalized event/name identity needed to precede allocation.

### RC-3 — Recovery was not a first-class invariant

The system had paths for joining and restoring, but permanent tests did not previously make “same committed participant and team after retry/rejoin” a release gate.

### RC-4 — Missing stabilization gate

Unit tests existed, but there was no single repeatable suite covering concurrency, two-event isolation, transient failure recovery, load thresholds, and readiness evidence.

## Root-cause determination

The repository evidence supports a **combination**, not a single-device cause:

- **Recent architecture regression — supported.** Three consecutive corrective commits changed atomic join, production RPC compatibility, and durable rejoin identity.
- **Non-idempotent join — supported.** The corrective migration introduced the missing event/idempotency uniqueness and conflict handling.
- **Participant lookup failure — supported.** The final correction moved normalized-name lookup ahead of allocation and made the earliest committed participant authoritative.
- **Team allocation before identity restoration — supported.** The migration and regression tests explicitly enforce the opposite ordering.
- **Session-state loss — contributing risk supported.** Identity initially lives in Streamlit session state and is reconstructed from a session token in URL query parameters after a rerun. This is a shared browser path, not an Android path.
- **Production latency — consistent with symptoms but unconfirmed.** The request retry code and user-observed slow joins support investigation, but production latency telemetry was not provided.

Current code persists `device_id` and `session_token` in URL query parameters. No cookie or local-storage persistence layer exists in this production repository. Query persistence can survive ordinary Streamlit reruns, but browser close/reopen, URL rewriting, private browsing, and mobile lifecycle behavior require real-device validation. This remains an open reliability risk rather than a proven historical cause.

## Contributing factors

- Browser reruns and duplicate taps are normal operating conditions for Streamlit/mobile workflows.
- Live event traffic is bursty rather than evenly distributed.
- Google Sheets is appropriate for configuration/reporting, but not as the transactional authority for concurrent registration.
- Production observability evidence was not retained with the repository, limiting quantitative incident reconstruction.

## Corrective actions completed

- Atomic Supabase join RPC with row locking and conflict handling.
- Unique event/idempotency index.
- Durable normalized-name restoration before allocation.
- Stable restoration of team, country, flag, leader status, and session token.
- Join-button resubmission guard and explicit recovery action.
- Permanent Sprint 009 regression and deterministic concurrency/failure suite, including leader rights and Intelligence Credit non-duplication.

## Actions still open

- Run the load profile against an authorised production-equivalent Supabase project.
- Perform a real database backup/restore and measure RPO/RTO.
- Capture platform metrics, database saturation, error rate, and p95/p99 latency.
- Upgrade the production Python runtime from 3.9 and validate OpenSSL compatibility.

## Prevention rule

No registration or recovery change ships unless `python3 -m pytest -q` and `python3 scripts/exos_stabilisation_harness.py` both pass. A production release additionally requires the live checks in the readiness report.
