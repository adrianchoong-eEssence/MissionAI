from pathlib import Path

import pytest

from data.standard_core_v2_adapter import StandardCoreV2Adapter


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase/026_standard_participant_access_recovery.sql").read_text()
SCREEN = (ROOT / "screens/participant.py").read_text()


@pytest.mark.parametrize("join_code", ["OXO0DT", "C0OCUS"])
def test_standard_recovery_uses_canonical_rpc_for_both_aia_events(join_code):
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    calls = []
    adapter._rpc = lambda name, payload, admin=True: calls.append(
        (name, payload, admin)
    ) or {
        "ParticipantID": "P-1", "EventID": "E-1", "TeamID": "T-1",
        "Team": "Korea", "TeamIdentity": "Korea", "Emoji": "🇰🇷",
        "Name": "Adrian Choong", "SessionToken": "redacted",
    }

    player = adapter.recover_participant_access(
        join_code, "Adrian Choong", "new-device"
    )

    assert player["ParticipantID"] == "P-1"
    assert player["TeamID"] == "T-1"
    assert calls == [(
        "exos_v2_recover_participant_access",
        {
            "p_join_code": join_code,
            "p_participant_name": "Adrian Choong",
            "p_device_id": "new-device",
        },
        False,
    )]


def test_same_device_restore_returns_existing_identity_without_recovery():
    restore = SQL.split(
        "create or replace function public.exos_v2_restore_join", 1
    )[1].split(
        "create or replace function public.exos_v2_recover_participant_access", 1
    )[0]
    assert "lower(trim(v_session.device_id)) <> lower(trim(p_device_id))" in restore
    assert "return v_identity;" in restore
    assert "insert into public.participant_sessions_v2" not in restore


def test_different_device_recovery_reuses_participant_and_team():
    recovery = SQL.split(
        "create or replace function public.exos_v2_recover_participant_access", 1
    )[1]
    assert "select * into v_participant from public.participants_v2" in recovery
    assert "insert into public.participants_v2" not in recovery
    assert "update public.participants_v2\n       set team_id" not in recovery
    assert "v_participant.participant_id" in recovery
    assert "v_participant.team_id" in recovery
    assert "insert into public.participant_sessions_v2" in recovery
    assert "on conflict (event_id, idempotency_key) do update" in recovery


def test_recovery_candidate_has_generic_team_identity_metadata():
    identity = SQL.split(
        "create or replace function public.exos_v2_identity_payload", 1
    )[1].split(
        "create or replace function public.exos_v2_restore_join", 1
    )[0]
    for field in (
        "ParticipantID", "EventID", "TeamID", "TeamName", "TeamIdentity",
        "ThemeType", "ThemeName", "Icon", "Emoji", "Image",
    ):
        assert f"'{field}'" in identity
    assert "coalesce(nullif(identity.item->>'TeamIdentity', ''), t.team_name)" in identity
    assert "Country" not in SCREEN.split("def render_recovery_candidate", 1)[1].split(
        "@st.fragment", 1
    )[0]


def test_unique_recovery_candidate_can_return_to_expedition():
    recovery_ui = SCREEN.split("def render_recovery_candidate", 1)[1].split(
        "@st.fragment", 1
    )[0]
    assert '"Return to Expedition"' in recovery_ui
    assert "runtime.recover_participant_access(" in recovery_ui
    assert "restore_participant_identity(player)" in recovery_ui
    assert "persist_session_in_query_params()" in recovery_ui
    assert 'candidate.get("Ambiguous") or not candidate.get("ParticipantID")' in recovery_ui


def test_recovery_rpc_is_standard_core_v2_only_and_token_safe_in_audit():
    lowered = SQL.lower()
    assert "google" not in lowered
    assert "legacy" not in lowered
    audit = SQL.split("insert into public.audit_log_v2", 1)[1]
    assert "session_token" not in audit.lower()
    assert "grant execute on function public.exos_v2_recover_participant_access" in SQL
