# RC3 Operational Certification — Sign-off

Date/time: __________________  Production URL: ________________________________

EventID: __________  Join code: __________  Running commit: __________  Load profile/window: __________________

| Certification | Required evidence | Result |
|---|---|:---:|
| Physical device certification | Four completed device/browser rows; screenshots/request IDs; identity and duplicate reconciliation | PASS / FAIL |
| Production load certification | Load report, telemetry export, thresholds and ≥30% headroom | PASS / FAIL |
| Leader recovery certification | Before/after IDs and rights, recovery payload and audit entry | PASS / FAIL |
| Join/refresh/reconnect | Device matrix and observer records | PASS / FAIL |
| Submission/approval/credits | SubmissionID, approval and award-ledger reconciliation | PASS / FAIL |
| Broadcast/recovery | Projector evidence and unchanged participant counts | PASS / FAIL |
| Final duplicate check | Zero duplicate participant, submission and credit records | PASS / FAIL |

## Remaining issues

| Issue/incident ID | Severity | Owner | Required action | Retest result |
|---|---|---|---|---|
|  |  |  |  |  |
|  |  |  |  |  |
|  |  |  |  |  |

## Release decision

Select **GO** only when every row above is PASS, no P0/P1 issue remains, evidence is attached and rollback ownership is confirmed.

- [ ] **GO — READY FOR PRODUCTION**
- [ ] **NO GO — BLOCKED**

Evidence location: _________________________________________________________________________

Known limitations accepted by event owner: __________________________________________________

Rollback owner: __________________  On-call contact: __________________  Abort authority: __________________

Facilitator: __________________  Signature: __________________  Time: __________

Observer/QA: __________________  Signature: __________________  Time: __________

Engineering: __________________  Signature: __________________  Time: __________

Event owner (GO/NO GO): __________________  Signature: __________________  Time: __________
