# EXOS CORE v2 — Queue 8: Real Staging Environment Activation

Date: 2026-08-08
Branch: feature/exos-core-v2

## Findings

- **Staging Supabase**: BLOCKED (no authorized staging credentials/URL available in this workspace)
- **Production isolation**: BLOCKED (cannot verify against a separate staging project)
- **Migration 020 status**: NOT EXECUTED (credentialed DB access unavailable)
- **Schema verification**: NOT EXECUTED (no runtime DB session)
- **RLS**: NOT EXECUTED (no runtime DB session)
- **Core v2 Sheets runtime fallback**: PASS for join path (`join_player_by_code` is hard runtime-only). Verified no participant-selected team/legacy fallback in canonical join.
- **Enterprise scoring isolation**: PASS after code change (ENTERPRISE review now yields zero competitive score and zero competitive credits; only TEAM_COMPETITIVE can award score/credits via review UI)
- **Unexplained diff**: RECONCILED (`leaderboard_display.py` mode check explicitly includes `{`Scores`, `Credits`}` for score/credits broadcast compatibility)

## Performed repo changes

- `screens/live_event_console.py`
  - `ENTERPRISE` activity review metrics now return `credits=0.0`
  - Review approval path now awards credits only when `mode == TEAM_COMPETITIVE`
- `screens/leaderboard_display.py`
  - Documented why the `broadcast_state.Mode` check includes both `Scores` and `Credits`
- `tests/test_live_event_console_runtime.py`
  - Updated assertions to enforce non-competitive Enterprise credits behavior

## Not executed due safety/infrastructure constraints

- Staging provisioning in Streamlit cloud
- Runtime schema migration on staging
- Multi-profile Streamlit staging deployment URLs

## Recommendation

Obtain authorized staging credentials and rerun queue8 with:
1) `020_exos_core_v2_schema.sql` apply,
2) preflight/postflight verification SQL,
3) non-destructive runtime smoke checks,
4) staging Streamlit deployments (facilitator/participant/projector) with dedicated staging secrets.
