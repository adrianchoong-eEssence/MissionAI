# RC1 Failure Injection Report

Executed: 3 August 2026. Local deterministic coverage is recorded separately from production/browser execution.

| Injection | Required recovery | Actual result | Result |
|---|---|---|---|
| Refresh | Restore same participant and position | Durable restore unit test passed; no physical browser execution | FAIL (production unproven) |
| Reconnect | Restore identity/team/leader | Recovery tests passed; no live network execution | FAIL (production unproven) |
| Network loss | Retry safely without duplication | Two injected transient failures per request passed in model | FAIL (production unproven) |
| Browser restart | Restore from durable token/lookup | Backend-recoverable test passed; no physical browser execution | FAIL (production unproven) |
| Double join | One participant | Concurrent/idempotent join tests and harness passed | PASS (local) |
| Double submit | One Submission | Repeated-tap and concurrent submission tests passed | PASS (local) |
| Leader disappears | Facilitator recovery preserves team authority | Leader recovery/transfer tests passed | PASS (local) |
| Participant changes phone | Same identity and assignment | Device-change test passed | PASS (local) |
| Concurrent approvals | One decision effect and award | Concurrent approval/credit test passed | PASS (local) |
| Concurrent submissions | One canonical Submission | Concurrent team-submission test passed | PASS (local) |
| Broadcast during approvals | Independent event-scoped operations | Authority and broadcast suites pass independently; concurrency not exercised in production | FAIL (production unproven) |
| Invalid activity launch | Reject inactive/invalid stable ID | Adapter fails closed | PASS (local) |
| Invalid Experience assignment | Reject inactive/missing Definition | Experience resolver fails closed | PASS (local) |
| Duplicate credits | One idempotent award | Repeated/concurrent approval tests passed | PASS (local) |
| Duplicate participant | One immutable identity | Join tests and harness passed | PASS (local) |

## Production execution still required

Run the complete physical iOS Safari, iOS Chrome, Android Chrome and Samsung Internet matrix against the deployed RC schema. Capture device/OS/browser versions, timestamps, ParticipantID, TeamID, country, flag, leader state, SubmissionID, AwardID, HTTP status, latency and backend logs. Every scenario must pass; an unexecuted cell is a failure for release certification.

