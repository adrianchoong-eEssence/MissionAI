# Sprint 009 — Load, Failure Recovery, and Capacity Report

Generated: 1 August 2026

## Verdict

The local stabilization gate passes. Production capacity is **not certified** because no production endpoint or credentials were available. Local throughput is reported only as harness performance and must not be used to size Supabase.

## Executed regression result

- Command: `python3 -m pytest -q`
- Result: 180 passed in 1.91 seconds
- Warnings: Python 3.9 end-of-life, LibreSSL incompatibility warning from urllib3, and corresponding Google auth runtime warning.

## Executed deterministic stress results

| Scenario | Result | p95 | Errors | Identity duplicates | Restore failures | Team spread |
|---|---:|---:|---:|---:|---:|---:|
| 100 participants / 100 workers | Pass | 4.732 ms | 0 | 0 | 0 | 1 |
| 250 participants / 100 workers | Pass | 15.429 ms | 0 | 0 | 0 | 1 |
| 500 participants / 100 workers | Pass | 21.864 ms | 0 | 0 | 0 | 1 |
| 200 participants / 2 events / 100 workers | Pass | 8.811 ms | 0 | 0 | 0 | 1 |
| 100 participants / two injected 503s per request | Pass | 6.111 ms | 0 | 0 | 0 | 1 |

The machine-readable evidence is in `outputs/sprint-009/stabilisation-results.json`.

## Failure recovery tests

- Duplicate clicks: same participant ID returned; no second record.
- Normalized-name rejoin from a different device: original participant and team returned.
- Session restore: exact committed participant restored; invalid token fails closed.
- Cross-device leader reconnect: ParticipantID, TeamID, country, flag, leader rights, and Intelligence Credits are preserved without a second award.
- Transient service failure: two sequential injected failures recover within a three-attempt budget.
- Exhausted retry budget: operation fails explicitly and does not report false success.
- Concurrent two-event traffic: identities remain isolated by event.

## Capacity position

The product requirement is 100+ simultaneous participants and two concurrent events. The deterministic model validates correctness through 500 participants and 100 workers, but does not exercise network, PostgREST, PostgreSQL connections, locks, storage, or platform quotas. Therefore:

- Correctness capacity: demonstrated locally to 500 participants.
- Production service capacity: unknown.
- Approved production operating limit: not established.
- Release headroom: not established.

## Required live profile

Use a dedicated production-equivalent event and synthetic participant prefix. Do not target a completed or active customer event.

1. Warm-up: 10 participants over 30 seconds.
2. Baseline: 100 participants, ramped over 60 seconds.
3. Peak: 150 participants over 30 seconds.
4. Stress: increase by 50 until a gate fails or 500 is reached.
5. Dual event: 100 participants per event in the same 60-second window.
6. Soak: 100 active participants for 30 minutes, including refresh and restore.

Pass gates:

- Successful joins >= 99.5% without manual retry.
- p95 join latency <= 2 seconds; p99 <= 5 seconds.
- Zero duplicate identities, team changes, cross-event leakage, or lost sessions.
- Retryable 5xx/429 responses < 1%; non-retryable server errors = 0.
- Database CPU < 70% sustained, connections < 70% of limit, lock waits p95 < 250 ms.
- At least 30% measured headroom above forecast peak.

## Recovery drill still required

Take a verified backup, record a known participant count/checksum, restore into an isolated project, rerun the checksum and smoke tests, and record measured RPO/RTO. Until that drill succeeds, recoverability remains unverified.

## Physical mobile validation still required

The local harness cannot simulate iOS/Android browser lifecycle behavior. Execute every scenario in `SPRINT_009_MOBILE_DEVICE_MATRIX.md` on iOS Safari, iOS Chrome, Android Chrome, and Samsung Internet where available. Production capacity and mobile session persistence remain uncertified until that matrix passes.
