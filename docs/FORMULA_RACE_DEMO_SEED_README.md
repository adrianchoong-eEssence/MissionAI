# Formula RACE Demo seed package

These scripts prepare a complete, isolated demo dataset. They have been generated but must not be executed as part of source deployment.

## Files

- `supabase/seeds/formula_race_demo_seed.sql` — transactional, repeatable seed.
- `supabase/seeds/formula_race_demo_verify.sql` — read-only assertions and summary.
- `supabase/seeds/formula_race_demo_seed_rollback.sql` — event-scoped rollback.

## Demo access

- EventID: `FORMULA-RACE-DEMO-001`
- Event join code: `RACEDEMO`
- Event name: `Formula RACE Demo`
- Team PIN pattern: `F1-01` uses `4101`, through `F1-10` using `4110`.

PINs are hashed with PostgreSQL `pgcrypto`; plaintext values are present only in the demo seed so operators can distribute them. Re-running the seed resets all demo captain sessions and re-hashes the PINs.

## Generated content

- The exact ten fixed Formula RACE teams, with IDs `F1-01` through `F1-10`.
- Nine ordered stages with canonical experience definitions, event assignments and checkpoint lists.
- Twelve marketplace items with prices and starting inventory.
- Ten runtime wallets and ten canonical wallet transactions, each opening at 100 credits.
- Six equal-weight judging criteria, two required judges and average aggregation.
- Time-trial race configuration, penalties, result selection and tie-break rules.
- One `Not Started` build-status row per team.
- Empty purchases, submissions, judging scores and race results for a clean demo start.

## Operator sequence

1. Confirm the prerequisite migrations through `017_formula_race_operations.sql` are deployed.
2. Review all demo values, especially PINs, opening credits, stock and race penalties.
3. Back up the target database.
4. Run `formula_race_demo_seed.sql` in a controlled transaction-capable SQL client.
5. Run `formula_race_demo_verify.sql`; it must complete without exceptions and return one summary row.
6. Perform captain login smoke tests with one team, then log out/reset the test session before the event.
7. Use `formula_race_demo_seed_rollback.sql` only if the demo dataset must be removed.

The rollback is intentionally restricted to EventID `FORMULA-RACE-DEMO-001` and the reserved `FR-DEMO-*` experience identifiers.
