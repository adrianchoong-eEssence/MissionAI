# Sprint 009 — Cross-Platform Mobile Validation Matrix

Status: **required; not yet executed on physical devices**

Every cell must be tested against the same production-equivalent backend build. Capture device model, OS/browser version, event ID, ParticipantID, TeamID, request ID, timestamps, and a screen recording.

## Browsers

- iOS Safari
- iOS Chrome
- Android Chrome
- Samsung Internet, where available

## Scenarios

| # | Scenario | Required observation |
|---:|---|---|
| 1 | Fresh join | One committed participant row |
| 2 | Slow join | UI remains pending; no second allocation |
| 3 | Repeated Join tap | One request identity and participant row |
| 4 | Refresh | Durable identity restored |
| 5 | Background for 30 seconds | Resume restores current identity |
| 6 | Background for 5 minutes | Resume restores current identity |
| 7 | Screen lock and unlock | Identity and rights unchanged |
| 8 | Browser closed and reopened | Identity restored without allocation |
| 9 | Network lost and restored | Bounded retry/recovery; no duplicate |
| 10 | Same-name re-login | Earliest committed participant restored |
| 11 | Leader reconnect | Leader and submission rights restored |
| 12 | Member reconnect | Member status restored; no promotion |
| 13 | Two concurrent requests for same participant | One ParticipantID and row |

## Required invariant for every cell

- Same ParticipantID, TeamID, country, flag, and current leader status.
- No new allocation, duplicate row, team movement, or duplicate Intelligence Credit award.
- Submission authorization matches the restored current leader status.

## Evidence checklist

- Before/after participant-row query and row count.
- Before/after credit-ledger transaction IDs and balance.
- Browser-visible result plus backend response/request identifiers.
- p50, p95, p99 latency and HTTP status for join/restore calls.
- Pass/fail recorded separately for each browser and scenario; do not infer one browser from another.
