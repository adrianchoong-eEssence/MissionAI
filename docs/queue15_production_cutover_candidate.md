# EXOS CORE v2 — QUEUE 15: Production Cutover Candidate

Date: 2026-08-08  
Branch: `feature/exos-core-v2`  
Prepared from verified staging/non-production evidence:
- Queue 8 Environment Activation report
- Queue 9 Multi-event migration proof report
- Queue 10 identity torture report
- Queue 12 local realism fallback report (260)
- Queue 13 local realism fallback report (800)
- Queue 14 recovery/reset/failure audit

## Executive decision

**Not ready for production cutover yet.**

Blocking status is infrastructure/verification based, not functional regressions:
- Staging runtime credentials/secrets are not available in this workspace for real staging runs.
- No live staging execution has completed for Queue 8–13 non-NEGOTIABLE flows (programme migration, identity, scale and RACE multi-event).

## 1) Production migration plan (non-destructive prep first)

### A. Pre-migration gates (must pass before any write)
1. Read-only confirmation of:
   - `supabase/020_exos_core_v2_schema.sql` migration history and dependency order.
   - RPC/extension visibility (`pgcrypto`, `pg_trgm`) and `RLS` policy presence.
2. Freeze active writes during preflight window.
3. Export immutable evidence bundle:
   - pre-migration schema snapshot
   - affected table row counts + checksums
   - identity audit and open anomaly list
4. Reconfirm `feature/exos-core-v2` commit is approved for production build package.

### B. Schema and core runtime migrations
1. Apply `supabase/020_exos_core_v2_schema.sql` in production if not already applied.
2. Immediately run `verification/exos_core_v2_preflight.sql`.
3. Run `supabase/011` / `012` / `013` / `014` read-only preflight (or equivalent latest equivalents) for compatibility safety.
4. Only after pass: run `verification/exos_core_v2_postflight.sql`.

### C. Configuration migration (non-production history-preserving)
1. Build deterministic migration scripts per event type (Mission AI / AGILE / RACE).
2. For each event to migrate:
   - create new v2 config IDs (ProgrammeID/ModuleID/ActivityID),
   - copy configuration only (modules/activities/payloads/timings/instructions),
   - preserve participant/session/submission/leaderboard/runtime operational records.
3. Keep operation mode:
   - **copy configuration only**
   - no retroactive session resets, no score edits, no credit mutations.

## 2) Mission AI / AGILE / Formula R.A.C.E. migration plan

### Mission AI
- Destination config: v2 standard/mission family programme type.
- Required: standard and NASI activity mappings, scoring mode defaults, evidence schema.
- Acceptance: registration, launch, submission, facilitator review, NASI results.

### AGILE
- Destination config: AGILE programme family + reusable activity library path.
- Required: module/activity ordering and parallelizable activity behaviour preserved.
- Acceptance: programme save/reload, stable module order, runtime launch.

### Formula R.A.C.E.
- Destination config: RACE programme family + `Formula RACE` checkpoints + captain mode.
- Required: deterministic 10-team isolation, checkpoint runtime and race schema functions.
- Acceptance: captain auth, checkpoints, reviews, marketplace, wallet, judging, championship.

## 3) Active and future event migration

### Active events
- Never run destructive migration on any active event.
- Use operational dual-read if needed:
  1. Prepare event copy in v2 configuration table.
  2. Validate by replay (`join`, `programme load`, `activity launch`, `submission`).
  3. Route new sessions only after explicit cutover approval.

### Future events
- Add “Core v2 canonical-only” switch in admin creation/publish path.
- Default event lifecycle:
  - config creation -> v2 runtime publish -> verification -> route open.

## 4) Production backup plan

1. Freeze target event operations during backup window.
2. Export baseline artifacts:
   - Supabase: canonical runtime + identity/audit/ledger tables and schema version map.
   - Google Sheets: configuration sheets required for historical reference.
3. Verify exports with row counts + SHA digest.
4. Restore-check in isolated restore project and compare.
5. Keep restore location and restoration owner documented before any write operation.

## 5) Rollback plan

### Immediate rollback triggers
- schema check fails after migration
- duplicate `ParticipantID`/`TeamID` anomaly
- EventID/Event-scoped leak signal
- leaderboard/credits reconciliation drift
- migration latency/lock/error budgets materially breached after production launch

### Rollback mechanisms
1. App rollback to previous tagged commit (no DB changes).
2. If safe to apply: run `020_exos_core_v2_schema_rollback.sql`.
3. If rollback SQL is blocked by existing canonical rows, execute application rollback + traffic pause + incident RCA.
4. Restore from backup snapshot where data integrity requires full time-travel recovery.

## 6) Secrets and deployment configuration

- Never store production secrets in repo.
- Required runtime key sets:
  - Streamlit deploy secrets for each surface (Facilitator/Participant/Projector)
  - Supabase URL + anon/publishable + secret role (service role limited to secure execution jobs)
  - OpenAI key only on server-side AI service path
  - deployment runtime marker for v2 mode
- Deployment must use separate staging URL + dedicated secret scopes before production.

## 7) DNS/Streamlit deployment sequence

1. Staging smoke certification complete and signed off.
2. Deploy facilitator app to staging URL (`/`) with v2 runtime marker.
3. Deploy participant + projector endpoints with explicit route separation.
4. Verify:
   - no legacy sheets runtime writes in v2 pathways,
   - correct route rendering (`race=1`, standard participant, facilitator).
5. Only after production credentials and final approvals:
   - production facilitator deploy (or maintenance-maintained traffic slicing),
   - production participant deploy,
   - production projector deploy.

## 8) Smoke-test checklist

### Canonical identity/runtime
- create event -> publish -> join-code immediate resolve
- duplicate first-name and same-name collision handling
- reconnect durability and no duplicate allocations

### Programme and runtime
- builder save/reload/delete/duplicate checks
- standard launch + parallel activity launch
- submission path (text/photo/structured/GPS) + review/approvals

### RACE
- captain auth -> team PIN -> reconnect
- checkpoint runtime
- credits wallet marketplace build/judging/results

### Operations
- reset safety
- backup artifact generation
- audit log emission and admin control operations
- projector broadcast continuity under reconnect

## 9) Cutover verification

- Real-time: p50/p95/p99 for join/reconnect/submit/read.
- Integrity: exact EventID and TeamID isolation across all reads/writes.
- Determinism: no duplicate `ParticipantID` creation under concurrent join.
- Evidence: request IDs + DB row-level counts before/after.
- Manual approval checkpoint before enabling production route to active users.

## 10) Rollback triggers

- Any FAILED audit in:
  - identity duplicate collision,
  - team isolation,
  - enterprise credit leak into competitive leaderboard,
  - cross-event leakage,
  - unreconciled submission/credit/score.
- Any production error budget breach on first release window.
- Any failed migration verification step.

## Readiness matrix

| Area | Status |
|---|---|
| Core v2 database | CONDITIONAL |
| Identity | CONDITIONAL |
| Multi-event | CONDITIONAL |
| Programme Builder | CONDITIONAL |
| Runtime | CONDITIONAL |
| RACE | CONDITIONAL |
| Mission AI | CONDITIONAL |
| AGILE | CONDITIONAL |
| Walk Hunt/Road Rally | CONDITIONAL |
| GPS | CONDITIONAL |
| Projector | CONDITIONAL |
| NASI | CONDITIONAL |
| Exports | CONDITIONAL |
| AI | CONDITIONAL |
| 70 pax | PASS (local only) / BLOCKED staging |
| 260 pax | PASS (local only) / BLOCKED staging |
| 800 pax | PASS (local only) / BLOCKED staging |
| Recovery | PASS |
| Backup | CONDITIONAL |
| Rollback | CONDITIONAL |

Notes:
- The 70/260/800 rows are not production or staged live evidence because live staging execution is blocked by missing runtime credentials in this environment.

## Final recommendation

**NOT READY**

Cutover must be withheld until:
1) staging credentials and isolated staging environment are mounted in this workspace,
2) live staging runs for Queue 8–13 complete without FAIL conditions,
3) backup + rollback drills are signed off,
4) DNS and Streamlit surfaces are validated under real staging credentials.
