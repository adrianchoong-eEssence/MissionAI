# Team Formation V1 staging certification harness

`scripts/certify_team_formation_v1.py` is the only Team Formation V1
certification runner. It also contains Gate 4, the reusable Theme Park Race
disposable-event UAT. It is a staging-only harness, not a Genting
implementation or an operational UI.

## What it proves

- RANDOM_ASSIGN at 66 participants across 6 teams with capacity 11.
- RANDOM_ASSIGN at 250 participants across 25 teams with capacity 10.
- PREASSIGNED at 250 participants across 25 teams with capacity 10.
- Duplicate display names, opaque-credential idempotent retries, same-device
  retries, correct recovery, wrong-credential rejection, and capacity overflow.
- Concurrent Captain contention from every registered participant in every
  fixture team, Captain refresh/recovery, one effective Captain per team, and
  an audited facilitator Captain transfer.
- Event isolation using cross-event credential and Captain-transfer attacks.
- Before/after fingerprints of all ten R.A.C.E. sentinel tables for
  `CORE-V2-RACE-UAT-EVT-4CF0CEAF5F` / `RACE4CF0CE`.
- Zero `CERT-TF-*` rows across every direct event-owned Core table after cleanup
  and no pre-existing `CERT-TF-*` residue before the harness writes anything.
- Gate 4 uses one `CERT-TPR-*` event with RANDOM_ASSIGN, OPEN_MISSION_BOARD,
  and certification-only RIDE, BONUS, SECRET, and STANDARD activities. It
  exercises server-canonical selection, operations, Captain authority,
  threshold calculation, READY/ACTIVE/CLOSED controls, and the protected-event
  fingerprint/cleanup boundary through the same runner.

The 66 and 250 registration phases use a `threading.Barrier` followed by one
fresh PostgREST RPC request from every worker. They are real concurrent
Supabase/PostgreSQL RPC calls, not sequential SQL described as concurrency.

## Safety boundary

The script does nothing beyond printing a plan unless `--execute` is supplied.
Execution additionally requires all of the following:

```bash
export EXOS_ENV=staging
export CERT_TF_CONFIRM_STAGING=RUN_DISPOSABLE_CERT_TF
export CERT_TF_EXPECTED_HOST=<the exact staging host from SUPABASE_URL>
export SUPABASE_URL=https://<staging-project-ref>.supabase.co
export SUPABASE_PUBLISHABLE_KEY=<staging publishable-or-anon-key>
export SUPABASE_SECRET_KEY=<staging service-or-secret-key>
export POSTGRES_TEST_DSN='postgresql://<privileged-staging-user>:<password>@<host>:5432/<database>?sslmode=require'
```

`psql` must be installed and on `PATH`. The direct PostgreSQL DSN is required
only because the installed Team Formation write guard correctly blocks ordinary
deletes of configured participant rows. The harness uses it for read-only
catalog/sentinel checks and for a per-event guarded cleanup transaction. The
concurrency workload itself uses the public RPC surface through PostgREST.

The runner refuses the known production host, requires an exact expected-host
match, refuses stale `CERT-TF-*` or `CERT-TPR-*` residue, creates only fresh
disposable EventIDs, and never creates or mutates a R.A.C.E. fixture. It
contains no wildcard delete: cleanup addresses only the freshly generated
EventIDs.

## Kai execution handoff

First confirm the script is inert:

```bash
cd '/Users/adrian/Documents/PROD - Mission AI/missionai-race-cert'
python3 scripts/certify_team_formation_v1.py
```

Then, from Kai's credentialed staging shell only:

```bash
cd '/Users/adrian/Documents/PROD - Mission AI/missionai-race-cert'
python3 scripts/certify_team_formation_v1.py \
  --execute \
  --report outputs/team-formation-v1-certification.json
```

The JSON report excludes enrollment credentials and session tokens. A PASS
requires `"Passed": true`, `"Sentinel.Identical": true`, and
`"Cleanup.Passed": true`. If any assertion or cleanup fails, treat the run as
failed; do not rerun over remaining fixtures. Resolve the reported scoped
residue first, then take a fresh sentinel fingerprint before any further work.

After a genuine staging run, rerun the credential-free source regression:

```bash
env -u POSTGRES_TEST_DSN python3 -m pytest -q -p no:cacheprovider
```

The established source baseline before this harness was **703 passed, 2
skipped**. Source regression is separate evidence from the staging concurrency
certification; neither is a Genting implementation or production approval.
