# EXOS CORE v2 — QUEUE 12: Real Staging Scale Test (260 pax)

Date: 2026-08-08
Branch: `feature/exos-core-v2`

## Environment gate

- Staging execution mode requested: **STAGING ONLY**
- Runtime/runtime-secrets status in this shell: **BLOCKED / unavailable**
  - Missing: Streamlit secret source (`.streamlit/secrets.toml`)
  - Missing: `mission_ai_service_account.json`
  - Missing: `SUPABASE_URL` and Supabase keys in env

## Real-service result

`python3 scripts/exos_scale_readiness_audit.py --mode staging --event-id EVT-QUE12-RACE --join-code STAGE-RACE --teams 10 --profiles 260 --workers 80 --output ...`

- **260 pax:** **FAIL** (environment blocked before test execution)

Observed blocker is infra/config, not a runtime safety assertion:
- `streamlit.runtime.secrets.StreamlitSecretNotFoundError`
- `FileNotFoundError: mission_ai_service_account.json`

## Non-destructive local fallback campaign executed (for readiness context only)

To preserve progression, a local realistic ramp/burst model was executed with:
- 260 participants
- 50% standard event, 50% RACE event participants (to model concurrent multi-event operation)
- jittered per-request ramp delays
- real reconnect/activity-read/submission/facilitator read bursts
- text + photo metadata + NASI payload families simulated

### 260 pax local burst metrics

- Registration p50: **0.286 ms**
- Registration p95: **0.645 ms**
- Registration p99: **0.885 ms**
- Reconnect p95: **0.007 ms**
- Submission p95: **0.011 ms**
- Error rate: **0.0**
- Duplicates: **0** (participant) / **0** (team assignment)
- Cross-event leakage: **0**
- DB contention: **0 (local model only)**
- Changes required: **None (local contract remains healthy; real staging data still blocked)**
- Primary bottleneck: **Credential/bootstrap dependency (`.streamlit/secrets.toml` + `mission_ai_service_account.json`)**

### Captured local artifact

- `outputs/queue12_260_local_realistic.json`

## Result

Real 260-pax staging scale campaign cannot be completed until staging secrets are wired in this runtime.
