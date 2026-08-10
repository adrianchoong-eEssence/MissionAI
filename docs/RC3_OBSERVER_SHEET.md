# RC3 Observer Sheet

Production URL: __________________  EventID: __________  Running commit: __________  UTC start/end: __________________

Record exact IDs, counts, timestamps, request IDs and screenshots. Do not record secret values.

| Test | What to observe and record | Expected result | Actual result | Pass/Fail |
|---|---|---|---|:---:|
| Fresh/double join | ParticipantID, TeamID, country, flag, row count, request ID, latency | One durable participant; no reallocation or duplicate |  |  |
| Refresh | IDs and rights before/after | All values identical |  |  |
| Reconnect | Background, lock, network and browser restart outcome | Automatic restoration; no new allocation |  |  |
| Leader recovery | Leader ID, team, rights, audit entry before/after | Same leader and rights; one leader only |  |  |
| Double submit | SubmissionID and submission count before/after | One canonical submission |  |  |
| Approval | Status, award transaction, credits and leaderboard delta | One approval creates one award once |  |  |
| Broadcast | Payload, time applied, projector display, event scope | Exact message appears; no participant mutation |  |  |
| Load | Users/RPS, requests, success/error, p50/p95/p99, timeouts | All published thresholds met |  |  |
| Database | CPU, connections, lock-wait p95, deadlocks/errors | <70% sustained; lock p95 <250 ms; no deadlocks |  |  |
| Final reconciliation | Participant/submission/award counts and duplicate queries | Expected deltas only; zero duplicates/mutations |  |  |

## Immediate fail conditions

- ParticipantID, TeamID, country, flag or leader status changes unexpectedly.
- Duplicate participant, submission, award or Intelligence Credit appears.
- Participant moves team or leader rights are lost.
- Cross-event data or broadcast appears.
- Non-retryable server error, unrecoverable workflow or unsafe facilitator action occurs.
- Any load threshold fails or 30% headroom is not demonstrated.

Incident/evidence references: ________________________________________________________________

Observer name/signature: ________________________________  Date/time: __________________
