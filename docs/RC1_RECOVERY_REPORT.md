# RC1 Recovery Report

| Recovery path | Local evidence | Production evidence | RC1 status |
|---|---|---|---|
| Participant recovery | Same-name/token restore and durable-field tests pass | Not executed | FAIL |
| Leader recovery | Persistence, transfer and non-reclaim tests pass | Not executed | FAIL |
| Manual override | Reversible, audited submission override tests pass | Not executed | FAIL |
| Manual credits | Immutable adjustment/penalty/spend/refund tests pass | Not executed | FAIL |
| Runtime recovery | Scoped Control recovery and safe reset tests pass | Not executed | FAIL |
| Approval recovery | Idempotent approval, revision and correction tests pass | Not executed | FAIL |
| Submission recovery | Retry/concurrency/evidence-ordering tests pass | Not executed | FAIL |

Production recovery acceptance requires a named facilitator to execute every path on an isolated production certification event, with before/after database snapshots and audit IDs. Participant, team, leader, credits and historical records outside that event must remain unchanged.

