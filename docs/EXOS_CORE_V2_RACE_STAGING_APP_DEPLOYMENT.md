# Formula R.A.C.E. Core v2 Staging Deployment Instructions

This runbook is for a **staging-only** persistent Formula R.A.C.E. UAT event on Core v2.

## Required environment
- `EXOS_ENV=staging`
- `SUPABASE_URL` and `SUPABASE_SECRET_KEY` for the clean staging project.
- Ensure the staging project is **not** EVT-0006 and is not a production host.

## Staging URLs to use
- Facilitator (Core v2): `https://<staging-facilitator-host>`
- Captain (Core v2): `https://<staging-captain-host>`

Do not replace:
- `missionai-facilitator.streamlit.app`
- `missionai-participant.streamlit.app`

## If Streamlit deploy tooling is unavailable
Deploy manually per existing Streamlit Cloud process:
1. Open the production deployment settings and create a new app instance for staging.
2. Use the same branch currently being tested, but with a separate staging environment name.
3. Set secrets:
   - `EXOS_ENV=staging`
   - `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`
4. Deploy and verify banner `EXOS CORE V2 — STAGING` appears.
5. Perform smoke flow for both:
   - `screens/formula_race.py`
   - `screens/formula_race_captain.py`

## Persistent UAT event bootstrap
Run locally in terminal after credentials are loaded:

```bash
EXOS_ENV=staging python3 scripts/exos_core_v2_create_staging_race_uat_event.py
```

The script prints:
- EventID
- Join Code
- local one-time PIN report path

PIN report must stay local only (`/tmp/...`) and must not be written to database/Git.
