# Sprint 010 — Participant Identity Engine

Status: **READY FOR IDENTITY ENGINE UAT; production migration not applied**

## Regression investigation

- Last known working backend-first same-name restoration: commit `5b17865` (`Build transactional runtime registration`). Its schema retained `unique (event_id, normalized_name)` and looked up the participant before allocation.
- Regression-introducing commit: `a3dcad2` (`Give each participant a unique runtime identity`), specifically `supabase/005_participant_identity.sql`.
- Exact defect: the migration dropped `runtime_participants_event_id_normalized_name_key`, then its replacement `exos_join_event` counted teams and allocated a team before performing any existing-participant lookup. It inserted a new participant unconditionally.
- Later path: `85db331`, `4f3b8c6`, and `359f751` restored atomic/idempotent joins and moved normalized-name lookup before allocation. Sprint 010 turns those fixes into a durable architecture plus facilitator recovery operations.
- Linked-content routing: commit `db511b7` added rerun-heavy linked content, but the participant query-parameter restore path remained present. It increased exposure to session loss; it did not introduce the missing identity lookup.
- Cross-platform conclusion: the defect was in the shared Streamlit/Supabase path. No evidence supports an Android-only or iOS-only cause.

## Implemented identity architecture

`ParticipantID` is the backend authority. Browser/session/query state is a cache. The new migration:

1. Resolves and locks the event from normalized Join Code.
2. Normalizes case, surrounding/repeated spaces, and harmless punctuation.
3. Searches active records before allocation.
4. Returns the one durable record with ParticipantID, TeamID, country, flag, current leader state, submission rights, points, and session token.
5. Returns an explicit ambiguous-recovery result when multiple records share the normalized full name.
6. Only when no record exists, assigns a team once and atomically inserts with a SHA-256 idempotency key.
7. Persists TeamID, country, and flag directly on the participant row.

The participant UI shows “Existing expedition record found” with Resume Expedition and This Is Not Me choices rather than silently creating another record.

## Facilitator recovery controls

Control Centre Team Management now provides:

- participant roster, durable IDs, country, leader, and last-active data;
- audited leadership transfer;
- audited participant team correction through the runtime API;
- reversible event/team submission overrides;
- duplicate/migration audit;
- Confirm Same Participant, Keep Separate, and confirmation-gated Merge Records.

Merge preserves the canonical ParticipantID/team/country, reattaches submissions, keeps the highest participant points, preserves leadership if either confirmed record is the leader, marks the duplicate as merged, and records before/after audit state. Team wallets and credit ledgers are not summed, preventing duplicate credit awards.

## Join-path performance

Network critical path for the Bayu join is two lightweight runtime calls: event lookup and atomic identity join. The join path does not load Experience images, Asset Library, Experience Board, submissions, reports, leaderboard, Drive media, or unrelated worksheets. AI facilitator lookup occurs only after identity has been resolved or explicitly resumed.

Database statements in the faulty new-participant RPC were five: event lock, team count, team selection, participant insert, and event-index update—with no identity lookup. Sprint 010 uses four: event lock, identity count, least-populated-team selection, and conflict-safe participant insert. Existing identity recovery uses event lock, identity count, participant fetch, and last-seen update; allocation is skipped entirely.

Production latency remains unmeasured until deployment telemetry is available.

## Test and concurrency results

- Full suite: 193 passed.
- Deterministic stress: 100, 250, and 500 participants; 200 participants across two events; and two injected transient failures per request.
- Result: zero duplicate identities, zero restore mismatches, and maximum team spread of one.
- Machine evidence: `outputs/sprint-010/concurrency-results.json`.

Permanent tests cover atomic join ordering, normalization, safe ambiguous recovery, full durable payload, refresh/restart/device restoration paths, leadership transfer and non-reclaim, reversible overrides, protected admin calls, migration audit, two-event isolation, and 100 concurrent joins.

## Migration audit

Production inspection was not executed because no Supabase endpoint/service credential is available. No production identity was rewritten or merged.

After migration `011` is applied to a production clone, run:

`python3 scripts/audit_participant_identity.py --event-id EVT-0004 --output outputs/sprint-010/production-identity-audit.json`

The audit returns duplicate candidates, team mutation candidates, leader inconsistencies, and orphaned submissions with `AutomaticChangesApplied: false`. Explicit approval remains mandatory before any production merge or move.

## Deployment and release status

- Code implementation: complete locally.
- Database migration: not applied.
- Production participant mutation: none.
- Commit/push: pending final verification.
- Deployment: not performed; production access is unavailable.
- Production certification still required: physical 52-cell mobile matrix, live load/latency telemetry, migration audit review, backup/rollback rehearsal, and facilitator recovery UAT.
