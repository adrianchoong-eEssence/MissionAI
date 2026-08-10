# Sprint 009.5 — Production Mobile Certification

Date: 1 August 2026

Decision: **NO-GO FOR RACE**

## Certification outcome

Production mobile certification could not be executed. The repository has no production URL, production credentials, deployment manifest, telemetry connection, or physical-device control. The available browser had no open production tab and no relevant deployment in its recent history.

This is an external-access block, not a passing result. Local tests from Sprint 009 are explicitly excluded as production certification evidence.

## Gate status

| Gate | Status | Evidence |
|---|---|---|
| 52-cell physical device matrix | BLOCKED | No iPhone, Android, or Samsung device/browser session connected |
| Live production load test | BLOCKED | No deployed URL, authorised test event/join code, or Supabase credentials |
| Live telemetry capture | BLOCKED | No Supabase/hosting telemetry access |
| Refresh recovery | BLOCKED | Requires physical device and test participant |
| Background/resume recovery | BLOCKED | Requires physical mobile lifecycle control |
| Browser close/reopen | BLOCKED | Requires physical browser session |
| Network loss/recovery | BLOCKED | Requires device network control |
| Duplicate Join tap | BLOCKED | Requires production test event |
| Same-name re-login | BLOCKED | Requires production test event and backend row evidence |
| Leader loss/reassignment | BLOCKED | Requires facilitator access and authorised state mutation |
| Identity/team/country/flag invariants | UNVERIFIED IN PRODUCTION | Backend and device evidence unavailable |
| Duplicate participant/credits invariants | UNVERIFIED IN PRODUCTION | Participant table and credit-ledger evidence unavailable |

## Access package required to resume

1. Production or production-equivalent participant URL.
2. Dedicated synthetic event ID and join code; confirmation it is safe to create and delete test participants.
3. Connected iPhone with Safari and Chrome.
4. Connected Android with Chrome; Samsung device/Internet where available.
5. Facilitator test account/session authorised to reassign leader status.
6. Read-only Supabase access for participant rows, credit ledger, database metrics, logs, locks, CPU, connections, and rate limits.
7. Hosting telemetry access for request status and end-to-end latency.
8. Approved cleanup procedure and event owner.

## Required evidence per cell

Record ParticipantID, TeamID, country, flag, leader status, participant-row count, credit-ledger transaction IDs/balance, request ID, HTTP status, and latency before and after each scenario. A cell passes only when durable identity is identical, no allocation runs, and neither participant rows nor credits increase unexpectedly.

## Live load gates

- Join success >= 99.5% without manual retry.
- p95 <= 2 seconds and p99 <= 5 seconds.
- Non-retryable server errors = 0; retryable 429/5xx < 1%.
- Zero duplicate participants, team changes, lost leader rights, cross-event leakage, or duplicate credits.
- Database CPU and connections remain below 70% sustained; lock-wait p95 < 250 ms.
- At least 30% measured headroom above forecast RACE peak.

## Release recommendation

Do not release RACE. Resume certification only after the complete access package is available, execute all 52 cells and live load/recovery drills, and attach dated telemetry and backend evidence. Any failed or unevidenced cell keeps the decision at NO-GO.
