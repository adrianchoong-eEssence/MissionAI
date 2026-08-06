# Formula R.A.C.E. SQL Deployment Checklist

Target release: `55abb30` or later. Run against an isolated backup-restorable Supabase environment first.

## 1. Scope and order

- [ ] Confirm a current database backup and record its timestamp/checksum.
- [ ] Confirm `pgcrypto`, `runtime_events`, and `runtime_teams` exist.
- [ ] Confirm `runtime_teams` has `UNIQUE (event_id, team_id)`.
- [ ] Confirm prerequisite EXOS migrations 011–014 are installed.
- [ ] Treat migration 015 as superseded by the fixed-team captain model. Do **not** install it for the RACE captain flow. If previously installed, remove only its function with `015_formula_race_preassigned_identity_rollback.sql` after confirming no legacy client depends on it.
- [ ] Apply `016_formula_race_captain_sessions.sql`.
- [ ] Apply `017_formula_race_operations.sql`.
- [ ] Run `formula_race_migrations_verify.sql`; require `PASS` and no exception.

## 2. Schema verification

- [ ] Five Formula tables exist: access, build status, judging, race results, event config.
- [ ] Four operational team tables have composite `(event_id, team_id)` foreign keys to `runtime_teams`.
- [ ] Event config has an EventID foreign key to `runtime_events`.
- [ ] Self-referencing correction foreign keys exist for judging and race-result histories.
- [ ] Session tokens have a partial unique index.
- [ ] Connected-team, build-history, judging-current/history, and result-current/history indexes exist.
- [ ] Only one current judging row and one current race result can exist per EventID/TeamID.
- [ ] Build statuses accept only the six approved values.
- [ ] Judging totals are constrained to 0–60 and RPC input requires the six configured categories with scores 0–10.
- [ ] Race time and penalty are non-negative; race bonus is non-negative.
- [ ] Audit actor and reason fields cannot be blank.

## 3. Security verification

- [ ] RLS is enabled on all five tables.
- [ ] `anon` and `authenticated` have no direct table privileges.
- [ ] Captain login and same-device restoration are the only Formula RPCs granted to `anon, authenticated`.
- [ ] PIN provisioning, status reporting, build updates, judging, and race results are `service_role` only.
- [ ] Every `SECURITY DEFINER` function pins `search_path` to `public`.
- [ ] Plaintext PINs are never stored or returned; only bcrypt hashes produced by `crypt(..., gen_salt('bf'))` are persisted.

## 4. Isolation tests

- [ ] Create two disposable test events with overlapping TeamIDs.
- [ ] Verify a captain session for Event A cannot restore against Event B.
- [ ] Verify an Event A PIN cannot authenticate the same TeamID in Event B.
- [ ] Verify build, judging, and race-result RPCs reject TeamIDs not belonging to the supplied EventID.
- [ ] Verify `exos_formula_race_state(EventA)` returns no Event B rows.
- [ ] Verify wallets, submissions, purchases, and awards remain filtered by EventID and TeamID.
- [ ] Remove disposable data only through the approved test-event cleanup path.

## 5. PIN provisioning

- [ ] Generate ten unique random PINs using an approved password manager; do not commit them.
- [ ] Call `exos_set_formula_race_team_pin(EventID, TeamID, PIN, FacilitatorID)` once per fixed team.
- [ ] Store/distribute PINs through the approved secure channel.
- [ ] Test one correct PIN and one incorrect PIN per team.
- [ ] Verify a second device is rejected while the primary captain session is active.

## 6. Functional smoke test

- [ ] Captain login and same-device reconnect.
- [ ] All ten teams visible before login.
- [ ] Checkpoint submission and duplicate-approval prevention.
- [ ] Credit award and transaction-derived wallet reconciliation.
- [ ] Marketplace purchase, overspend rejection, atomic stock reduction, and duplicate-checkout prevention.
- [ ] All six build-status transitions.
- [ ] Initial judging submission and audited correction.
- [ ] Race result, penalty, bonus, verification, correction, lock and authorized unlock.
- [ ] Final championship totals, ties, and deterministic ranking.
- [ ] Refresh/restart retains state and no cross-event/team data appears.

## 7. Rollback

- [ ] Stop Formula writes before rollback.
- [ ] Export all Formula tables and record checksums.
- [ ] Run rollbacks in reverse order: 017, 016, then optional 015.
- [ ] Expect 016/017 rollback to fail closed when any rows exist.
- [ ] Do not bypass the guards. Preserve operational history and prefer an application rollback when tables contain data.
- [ ] Re-run the broader EXOS smoke suite after any application rollback.
