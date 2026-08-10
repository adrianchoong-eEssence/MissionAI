# Formula RACE Demo deployment command list

Run from `/Users/adrian/Documents/PROD - Mission AI/missionai-production` with `FORMULA_RACE_DATABASE_URL` set to the target PostgreSQL connection string.

The demo seed is intentionally atomic: its single transaction creates the event, teams, marketplace and programme together. Steps 3–6 below are therefore one seed command with four ordered deployment gates; do not run that command more than once in the sequence.

1. Migration 016

   ```bash
   psql "$FORMULA_RACE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -f supabase/016_formula_race_captain_sessions.sql
   ```

2. Migration 017

   ```bash
   psql "$FORMULA_RACE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -f supabase/017_formula_race_operations.sql
   ```

3. Seed Demo Event

   ```bash
   psql "$FORMULA_RACE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -f supabase/seeds/formula_race_demo_seed.sql
   ```

4. Seed Teams

   ```bash
   psql "$FORMULA_RACE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -c "do \$\$ begin if (select count(*) from public.runtime_teams where event_id = 'FORMULA-RACE-DEMO-001') <> 10 then raise exception 'Team seed failed'; end if; end \$\$;"
   ```

5. Seed Marketplace

   ```bash
   psql "$FORMULA_RACE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -c "do \$\$ begin if (select count(*) from public.runtime_marketplace_items where event_id = 'FORMULA-RACE-DEMO-001' and active) <> 12 then raise exception 'Marketplace seed failed'; end if; end \$\$;"
   ```

6. Seed Programme

   ```bash
   psql "$FORMULA_RACE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -c "do \$\$ begin if (select count(*) from public.runtime_missions where event_id = 'FORMULA-RACE-DEMO-001') <> 9 then raise exception 'Programme seed failed'; end if; end \$\$;"
   ```

7. Verify

   ```bash
   psql "$FORMULA_RACE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -f supabase/seeds/formula_race_demo_verify.sql
   ```

8. Smoke Test

   ```bash
   psql "$FORMULA_RACE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -c "do \$\$ begin if not exists (select 1 from public.runtime_events where event_id = 'FORMULA-RACE-DEMO-001' and join_code = 'RACEDEMO' and active) then raise exception 'Smoke test failed'; end if; if (select count(*) from public.formula_race_team_access where event_id = 'FORMULA-RACE-DEMO-001' and active_session_token is null) <> 10 then raise exception 'Smoke test failed: captain access state'; end if; end \$\$;"
   ```

Done.
