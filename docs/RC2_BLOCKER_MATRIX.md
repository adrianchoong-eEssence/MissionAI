# RC2 Blocker Matrix

RC2 date: 3 August 2026. Engineering work is complete. No production migration, deployment, test mutation or record correction was performed.

| # | Blocker | Root Cause | Type | Can Codex solve? | Action Required | Owner | Estimated Time | Risk | Remaining Dependency |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Production migration state unknown | This workspace has no authenticated production SQL or migration-history connection | Credential / Deployment | Engineering portion solved | Run migrations 011–014 dry runs and schema checks in production; archive output before approving any migration | Adrian / production DBA | 30–60 min | High: wrong ordering can make the deployed app fail closed | Production Supabase SQL access and migration approval |
| 2 | Production identity audit unavailable | Supabase URL/service credential is absent | Credential | Engineering portion solved | Run the unified SELECT-only audit for the confirmed RACE EventID and review `identity.json` | Adrian | 10 min plus review | High: duplicates or ambiguous identities may require manual decisions | Supabase service-role/read-only access; confirmed EventID |
| 3 | Production Programme audit unavailable | Google service-account credentials are absent | Credential | Engineering portion solved | Run the unified SELECT-only audit and review every programme error/warning | Adrian | 10–30 min | High: invalid stable links can block activity launch | Google Sheets service-account access |
| 4 | Production Experience audit unavailable | Google service-account credentials are absent; migration 013 state is unknown | Credential / Deployment | Engineering portion solved | Run the unified SELECT-only audit; review all manual mappings/orphans; verify migration 013 | Adrian | 20–60 min | High: missing Definition/Assignment versions fail closed | Google credentials and production SQL access |
| 5 | Production submission/award reconciliation unavailable | Supabase service credential and Google credentials are absent; migration 014 state is unknown | Credential / Deployment | Engineering portion solved | Run unified audit; reconcile every submission, award, balance and leaderboard difference; verify migration 014 | Adrian | 30–90 min | Critical: incorrect awards or history cannot be accepted | Both credential sets and production SQL access |
| 6 | Duplicate identities unverified | Production participant rows cannot be read | Credential | Engineering portion solved | Review duplicate, ambiguous-name, team mutation, leader, orphan and duplicate-credit sections of `identity.json`; approve record-exact corrections separately | Adrian / facilitator owner | 15–90 min | Critical: identity/team/leader mutation | Successful identity audit and human identity decisions |
| 7 | Production smoke tests incomplete | Gates 1–6 are not deployed to an isolated production certification event | Deployment / Process | No—requires authorised production execution | Deploy only after migration approval, then execute every scenario in the RC1 smoke report and retain request/database evidence | Adrian / release owner | 45–90 min | High: deployment/schema mismatch | Approved deployment and isolated test event |
| 8 | Production failure injection incomplete | No authorised live event, network control or deployed RC exists | Deployment / Process | No—requires authorised production execution | Execute all 15 RC1 injections; every case must recover automatically or through Control Centre | Adrian / QA facilitator | 60–120 min | High: may expose live recovery failures | Deployed RC, test event, facilitator session |
| 9 | Production recovery drills incomplete | Recovery operations are intentional production mutations and require a facilitator | Process / Deployment | No—requires authorised production execution | Execute participant, leader, override, credits, runtime, approval and submission recovery with before/after audit evidence | Adrian / facilitator | 45–90 min | High: incorrect recovery can mutate authority/history | Dedicated test records and recovery approval |
| 10 | Physical mobile matrix incomplete | No connected physical devices or human lifecycle/network control | Environment / Process | Matrix/tooling solved; physical execution cannot be automated here | Complete all 52 rows in `RC2_MOBILE_CERTIFICATION_MATRIX.csv`; attach screenshots/request IDs | Adrian / device QA | 3–5 hours | High: mobile lifecycle incident can recur | iPhone and Android devices; four required browsers |
| 11 | Live load and telemetry incomplete | No production URL/test event, telemetry access or authorised load window | Infrastructure / Credential / Process | Existing load engines and acceptance fields are ready; execution requires production | Run join/submission/two-event load tests, capture application/database telemetry, prove thresholds and 30% headroom | Adrian / platform owner | 60–120 min | Critical: load can affect shared production capacity | Test events, service credentials, telemetry dashboards, approved window |
| 12 | Python/TLS runtime compatibility unverified | Local host is Python 3.9 with LibreSSL; production runtime was unspecified | Environment / Deployment | Engineering solved: Python 3.12.11 pinned and verifier added | Deploy/build with `.python-version`, then run `python3 scripts/verify_runtime_compatibility.py`; result must pass | Adrian / platform owner | 10–30 min | High: unsupported TLS/runtime can fail external calls | Hosting platform must honor Python pin and provide OpenSSL >=1.1.1 |

## Engineering eliminations completed

- Fixed direct execution of Programme, Experience and transaction audits by resolving repository imports from the script location.
- Added `scripts/rc2_production_audits.py`, a fail-closed SELECT-only orchestrator producing separate identity, programme, Experience and transaction JSON plus a manifest.
- Added the exact 52-cell generator and committed `docs/RC2_MOBILE_CERTIFICATION_MATRIX.csv` with every required evidence field.
- Pinned Python 3.12.11 in `.python-version`.
- Added `scripts/verify_runtime_compatibility.py`; it rejects Python below 3.11, LibreSSL and OpenSSL below 1.1.1.
- Added regression tests proving the matrix count/uniqueness, runtime contract, direct audit imports and read-only orchestration contract.
- Exercised the production audit command without credentials. It failed closed for all four audits and confirmed `ProductionRecordsChanged: false`.

## Exact production commands

After supplying production secrets through the approved secret mechanism, not command-line arguments:

```bash
python3 scripts/verify_runtime_compatibility.py
python3 scripts/rc2_production_audits.py --event-id EVT-0004 --output-dir outputs/rc2-production-audit
```

Replace `EVT-0004` only if Adrian confirms a different L'Oréal RACE EventID. Then execute the existing SELECT-only SQL in order:

1. `supabase/011_participant_identity_preflight_audit.sql`
2. `supabase/012_foundation_identity_runtime_authority_dry_run.sql`
3. `supabase/013_experience_definition_assignment_dry_run.sql`
4. `supabase/014_canonical_transaction_pipeline_dry_run.sql`

Do not apply a migration or correct a record during these checks.

========================

## READY FOR ADRIAN

========================

1. Confirm the production RACE EventID, production URL, two isolated test events/join codes, approved load window and rollback owner.
2. Provide the production execution environment with Supabase URL/service-role access, Google Sheets service-account access, and hosting/database telemetry access; do not send secrets in chat or commit them.
3. Run the runtime verifier, the unified audit command and dry-run SQL 011–014; give Codex the complete outputs for analysis. Do not apply migrations or corrections yet.
4. Review and explicitly approve or reject each migration and every record-exact correction proposed from the audit.
5. After migration and deployment approval, deploy the pinned RC commit to the isolated certification event and run smoke, failure-injection, recovery and live-load gates with telemetry.
6. Complete all 52 physical-device rows using iOS Safari, iOS Chrome, Android Chrome and Samsung Internet.
7. Return the audit, migration, smoke, recovery, mobile, load and telemetry evidence for the final READY FOR PRODUCTION decision.
