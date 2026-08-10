# Sprint 009 — Production Readiness Report

Decision: **NO-GO — production evidence incomplete**

The code-level stabilization gate is green. The release remains blocked on authorised live load and backup/restore evidence; a local model cannot certify production infrastructure.

## Checklist

| Area | Gate | Status | Evidence / owner action |
|---|---|---|---|
| Feature freeze | No feature work in Sprint 009 | Pass | Changes are tests, harness, evidence, and runbooks only |
| Regression | Full suite passes | Pass | 180 tests passed |
| Join idempotency | Duplicate request returns committed identity | Pass | Permanent regression + stress harness |
| Team stability | Retry/rejoin preserves team | Pass | Permanent regression + SQL invariant tests |
| Session recovery | Valid session restores; invalid token fails closed | Pass | Permanent regression |
| Transient failure | Bounded retry succeeds/fails explicitly | Pass | Two-failure and exhausted-budget tests |
| Dual-event isolation | Concurrent events do not cross identity | Pass | 200-participant deterministic scenario |
| Durable authorization | TeamID, country, flag, leader rights, and credits survive reconnect | Pass | Permanent cross-device model regression |
| Local stress | Correctness at 500 participants | Pass | Machine-readable results JSON |
| Physical mobile matrix | iOS/Android browser lifecycle scenarios pass | **Blocked** | Execute all 52 browser/scenario cells in the mobile matrix |
| Production load | Live thresholds met | **Blocked** | Supply authorised test project/event and run required profile |
| Capacity | Limit and 30% headroom established | **Blocked** | Requires production metrics |
| Backup restore | RPO/RTO measured in restore drill | **Blocked** | Execute isolated database restore |
| Observability | Dashboards and alert thresholds verified | **Blocked** | Verify Supabase/hosting logs, alerts, and retention |
| Runtime support | Supported Python/OpenSSL runtime | **Fail** | Current tests warn on Python 3.9 EOL and LibreSSL |
| Rollback | Migration rollback/runbook rehearsed | **Blocked** | Rehearse against isolated project |
| Data safety | No completed production event used for tests | Pass | Local harness is non-mutating |

## Release criteria

Change the decision to GO only after every blocked/failed row has dated evidence, an owner, and a passing result. Required sign-off roles: engineering owner, event operations owner, and product owner. Android-only evidence cannot satisfy the mobile gate; iPhone and Android results must be recorded independently.

## Operating runbook

- Regression: `python3 -m pytest -q`
- Deterministic gate: `python3 scripts/exos_stabilisation_harness.py --output outputs/sprint-009/stabilisation-results.json`
- Before a live run: confirm synthetic event, participant prefix, cleanup plan, monitoring dashboard, and rollback owner.
- During a live event: never fall back from Supabase runtime data to Sheets; pause joins if duplicate identity, team mutation, or cross-event leakage is observed.
- After an incident: preserve timestamps, request IDs, event ID, platform/database metrics, and affected participant IDs before cleanup.
