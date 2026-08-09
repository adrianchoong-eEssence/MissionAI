# Formula R.A.C.E. Core v2 Client-Facing Staging Deployment (Freeze)

## Scope
- **Staging-only** Formula R.A.C.E. facilitator and captain clients.
- No production touches.
- No Google Sheets runtime usage.
- No runtime_* / legacy formula_race_* table access.

## Required environment
- `EXOS_ENV=staging`
- `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` / `SUPABASE_SECRET_KEY`
- staging host must not match a known production host.

## Deploy separate Streamlit apps

- Facilitator staging URL: **set by deployment platform**
- Captain staging URL: **set by deployment platform**

Do not point these URLs at:
- `missionai-facilitator.streamlit.app`
- `missionai-participant.streamlit.app`

## Runtime contract validation in staging
- `EXOS CORE V2 — STAGING` visible banner on both screens.
- If staging adapter is active, hard checks require:
  - `LEGACY_RUNTIME_CALLS = 0`
  - `GOOGLE_SHEETS_RUNTIME_CALLS = 0`

## Persistent UAT bootstrap

From local terminal where staging credentials are loaded:

```bash
EXOS_ENV=staging python3 scripts/exos_core_v2_create_staging_race_uat_event.py
```

The script prints:
- `EventID`
- `Join Code`
- `PIN report local path`

Do not clean this event after creation.

## Note

Deployment is environment/tooling-dependent. If Codex cannot deploy directly from this workspace,
follow the normal Streamlit deployment flow manually:
1. Create two separate staging app instances.
2. Configure secrets from the staging environment.
3. Set app entry script:
   - Facilitator: `screens/formula_race.py`
   - Captain: `screens/formula_race_captain.py`
4. Smoke verify both clients against the persistent UAT event.
