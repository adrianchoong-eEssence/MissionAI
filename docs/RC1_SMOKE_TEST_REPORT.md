# RC1 Smoke Test Report

Executed: 3 August 2026. Scope: committed code and deterministic local test doubles only. No production write, migration or deployment occurred.

## Gate verification

| Gate | Production architecture check | Actual result | Status |
|---|---|---|---|
| 1 Identity | Migration 011/012 present; durable identity and idempotent join tests pass | Production schema and participant data could not be read; migration state unknown | FAIL |
| 2 Runtime Authority | Supabase authority contract and fail-closed mutation tests pass | Production runtime ownership could not be observed | FAIL |
| 3 Control Centre | Scoped mutation capability, recovery, review and broadcast tests pass | Deployed Control Centre and production mutation paths were not exercised | FAIL |
| 4 Programme Adapter | Stable-ID adapter, isolation and invalid-launch tests pass | Production ProgrammeStages audit could not authenticate to Sheets | FAIL |
| 5 Experience Definition/Assignment | Definition/version/assignment tests pass; migration 013 exists | Production content audit could not authenticate; migration state unknown | FAIL |
| 6 Canonical Submission Pipeline | Idempotent submission/review/award/leaderboard tests pass; migration 014 exists | Production transaction audit could not authenticate; migration state unknown | FAIL |

## Smoke scenarios

“PASS (local)” is not a production pass.

| Area | Scenario | Expected result | Actual result | Result |
|---|---|---|---|---|
| Participant | Join, restore, refresh model and device change | Same immutable identity/team/country/flag | Focused identity tests and deterministic harness preserved every durable field | PASS (local) |
| Leader | Reconnect and transfer | Rights persist; transfer is atomic/audited | Identity and Control tests passed | PASS (local) |
| Facilitator | Scoped live mutation and recovery | Only Control Centre can mutate | Direct mutation failed closed; scoped facade passed | PASS (local) |
| Programme | Resolve and launch by stable ActivityID | Correct active linked content; invalid launch rejected | Adapter tests passed | PASS (local) |
| Experience | Resolve Assignment to immutable Definition version | Correct version/overrides; inactive or missing records fail closed | Gate 5 tests passed | PASS (local) |
| Submission | Submit once and retry | One canonical Submission | Repeated and concurrent submission tests passed | PASS (local) |
| Credits | Approve/retry/correct/manual adjustment | One immutable award; corrections reverse; balance derives from ledger | Gate 6 ledger tests passed | PASS (local) |
| Reports | Rebuild event history | Stable IDs and reproducible isolated history | Dual-event report test passed | PASS (local) |
| Leaderboard | Rebuild rankings | Deterministic balances, ties and ordering | Gate 6 leaderboard test passed | PASS (local) |
| Broadcast | Publish/read event broadcast | One event-scoped source; participant cannot mutate it | Broadcast and authority tests passed | PASS (local) |
| Sync AI | Aggregate multiple judges | Configured aggregation and deterministic ranking | Sync AI judging tests passed | PASS (local) |
| Recovery | Recover participant/leader/runtime/submission | Restore durable state or provide Control recovery | Recovery and revision tests passed | PASS (local) |

## Executed commands

- Sandbox-safe Python compilation: PASS.
- Full regression suite: 262 passed, 3 environment warnings.
- Focused RC1 suite: 110 passed, 3 environment warnings.
- Deterministic identity/concurrency harness: 100, 250 and 500 participant scenarios passed; dual-event isolation passed; two injected transient failures per request passed; zero identity or restore mismatches.

The harness is an in-memory transactional model. Its latency and throughput are not production capacity evidence.

## Production audit attempts

- Identity audit for EVT-0004: did not start; `SUPABASE_URL`/`SUPABASE_SECRET_KEY` unavailable.
- Programme audit: did not read rows; Google credentials unavailable.
- Experience audit: did not read rows; Google credentials unavailable.
- Canonical transaction audit: did not start; `SUPABASE_SECRET_KEY` unavailable.
- Production records changed: **none**.

