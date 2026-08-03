# RC2 Secure Production Environment Checklist

Never paste secret values into chat, logs, screenshots, commits, command history or audit output. Configure them in the production hosting secret manager and, for an authorised operator shell, exported environment variables or an untracked `.streamlit/secrets.toml`.

## Verified production configuration

- Repository: `https://github.com/adrianchoong-eEssence/MissionAI`
- Branch: `main`
- Remote main and verified running commit: `cb9dc5f56676a56b523f551028388114f7ff7554`
- Admin application: `https://missionai-eessencemaster.streamlit.app/` (`MissionAI.py`)
- Facilitator application: `https://missionai-facilitator.streamlit.app/` (`Facilitator.py`)
- Participant application: `https://missionai-participant.streamlit.app/` (`Participant.py`)
- Hosting: Streamlit Community Cloud account `adrianchoong-eessence`, connected to repository `missionai`, branch `main`
- Hosting runtime: Python 3.14.6; production dependency installation and HTTPS workbook access succeeded
- Google workbook: `MissionAI_Database`
- Google spreadsheet ID: `1XWCW9UVj_1cxA32ItsE8-nAr9q0NEgOhhD5e3C64Hvw`
- L'Oréal RACE event: `EVT-0006`, event name `RACE`, client `Loreal`, event date `2026-08-19`
- RACE state in the workbook: Draft; ten Teams exist; no Participants, ProgrammeStages, Missions or Submissions exist for EVT-0006.
- Supabase project reference: not present in repository, environment or browser session.

## Required secrets

| Secret name | Enter in | Expected format | Verification that does not reveal the value |
|---|---|---|---|
| `SUPABASE_URL` | Each Streamlit app's Settings → Secrets and authorised audit shell | HTTPS Supabase project endpoint ending in `.supabase.co`, without a trailing path | `SupabaseRuntimeDB().url` is non-empty; a read-only request to `runtime_events?select=event_id&limit=1` returns HTTP 200 |
| `SUPABASE_PUBLISHABLE_KEY` | Each Streamlit app's Settings → Secrets | Supabase publishable/anon key for the same project | `SupabaseRuntimeDB().is_configured` is true and an anonymous read allowed by RLS returns HTTP 200 |
| `SUPABASE_SECRET_KEY` | Each Streamlit app's Settings → Secrets and temporary authorised audit shell only | Supabase service-role/secret key for the same project | `SupabaseRuntimeDB().can_publish` is true; run only the SELECT-only RC2 audit before any approved mutation |
| `gcp_service_account` | Each Streamlit app's Settings → Secrets as a TOML table | Complete Google service-account JSON fields represented as TOML keys; `private_key` retains newline escapes | `get_workbook()` opens spreadsheet ID `1XWCW9UVj_1cxA32ItsE8-nAr9q0NEgOhhD5e3C64Hvw` and reads the Events header |
| `OPENAI_API_KEY` | Each Streamlit app's Settings → Secrets | OpenAI project API key authorised for EXOS Sync AI | Run one isolated Sync AI smoke request and verify a successful response without logging prompt secrets or the key |

Aliases supported by the code are `SUPABASE_ANON_KEY` for the publishable key and `SUPABASE_SERVICE_ROLE_KEY` for the secret key. Configure one canonical name only to prevent drift.

## Access and consistency checks

- [ ] The Supabase project reference in `SUPABASE_URL` matches both keys.
- [ ] The Google service-account email has access to `MissionAI_Database`.
- [ ] Production and audit shells point to the same Supabase project and workbook.
- [ ] The hosting deployment is connected to `adrianchoong-eEssence/MissionAI`, branch `main`.
- [ ] The hosting deployment exposes its running git SHA or build identifier.
- [ ] No secret is present in git status, audit JSON, screenshots or terminal output.
- [ ] `python3 scripts/verify_runtime_compatibility.py` passes in the production runtime.
- [ ] `python3 scripts/rc2_production_audits.py --event-id EVT-0006 --output-dir outputs/rc2-production-audit` completes with `ProductionRecordsChanged: false`.

## Production mutation gate

Read-only access does not authorise migrations, record corrections, deployment, test-data creation or cleanup. Those actions require the explicit approval block defined by the RC2 execution request after backups, audits, dry runs and rollback validation are complete.
