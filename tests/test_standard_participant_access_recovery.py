from pathlib import Path

import pytest

from data.standard_core_v2_adapter import StandardCoreV2Adapter
from screens.participant import (
    hydrate_recovery_candidate,
    standard_event_uses_road_hunt,
)


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


def test_minimal_join_recovery_response_is_hydrated_before_ui_branch():
    class Runtime:
        def __init__(self):
            self.calls = []

        def restore_join(self, join_code, participant_name, device_id):
            self.calls.append((join_code, participant_name, device_id))
            return {
                "RecoveryRequired": True,
                "Ambiguous": False,
                "ParticipantID": "P-UPPER",
                "EventID": "AIA-WE-260810081110-UPPER",
                "TeamID": "UPPER-TEAM-01",
                "TeamIdentity": "Korea",
                "Emoji": "🇰🇷",
                "Name": "Adrian Choong",
            }

    runtime = Runtime()
    candidate = hydrate_recovery_candidate(
        runtime,
        {
            "RecoveryRequired": True,
            "Ambiguous": False,
            "EventID": "AIA-WE-260810081110-UPPER",
            "Name": "Adrian Choong",
            "Message": "Same name exists for different device/session.",
        },
        "OXO0DT",
        "Adrian Choong",
        "new-device",
    )

    assert candidate["ParticipantID"] == "P-UPPER"
    assert candidate["TeamID"] == "UPPER-TEAM-01"
    assert candidate["TeamIdentity"] == "Korea"
    assert runtime.calls == [("OXO0DT", "Adrian Choong", "new-device")]


def test_ambiguous_join_response_is_never_silently_hydrated():
    class Runtime:
        def restore_join(self, *_):
            raise AssertionError("ambiguous identity must not be selected")

    original = {
        "RecoveryRequired": True,
        "Ambiguous": True,
        "Name": "Adrian Choong",
    }
    assert hydrate_recovery_candidate(
        Runtime(), original, "OXO0DT", "Adrian Choong", "new-device"
    ) is original


def test_repeated_device_recovery_preserves_participant_and_team_five_times():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    calls = []
    canonical = {
        "ParticipantID": "P-LOWER",
        "EventID": "AIA-WE-260810081110-LOWER",
        "TeamID": "AIA-WE-260810081110-LOWER-TEAM-01",
        "Team": "India",
        "TeamIdentity": "India",
        "Name": "Adrian Choong",
    }
    adapter._rpc = lambda name, payload, admin=True: calls.append(
        (name, payload, admin)
    ) or dict(canonical, SessionToken=f"session-{len(calls)}")

    recovered = [
        adapter.recover_participant_access(
            "C0OCUS", "Adrian Choong", f"device-{attempt}"
        )
        for attempt in range(5)
    ]

    assert {row["ParticipantID"] for row in recovered} == {"P-LOWER"}
    assert {row["EventID"] for row in recovered} == {
        "AIA-WE-260810081110-LOWER"
    }
    assert {row["TeamID"] for row in recovered} == {
        "AIA-WE-260810081110-LOWER-TEAM-01"
    }
    assert len(calls) == 5
    assert all(call[0] == "exos_v2_recover_participant_access" for call in calls)


def test_agile_activity_does_not_route_to_road_hunt():
    class Database:
        @staticmethod
        def get_event(_event_id):
            return {
                "ProgrammeType": "AGILE",
                "_EventPayload": {"RoadHuntEnabled": False},
            }

    assert standard_event_uses_road_hunt(
        Database(),
        "AIA-WE-260810081110-LOWER",
        {"ContentType": "Standard Activity"},
    ) is False


def test_road_hunt_requires_explicit_canonical_configuration():
    class Database:
        @staticmethod
        def get_event(_event_id):
            return {
                "ProgrammeType": "STANDARD",
                "_EventPayload": {"RoadHuntEnabled": True},
            }

    assert standard_event_uses_road_hunt(Database(), "ROAD-1", {}) is True


def test_standard_adapter_road_hunt_placeholder_matches_renderer_contract():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    state = adapter.get_road_hunt_unlocked_missions("session-redacted")

    assert isinstance(state, dict)
    assert state == {
        "Enabled": False,
        "AvailableMissions": [],
        "TotalMissions": 0,
        "UnlockedMissions": 0,
        "SubmittedMissions": 0,
    }


def test_recovery_sql_never_reassigns_or_recreates_participant():
    recovery = SQL.split(
        "create or replace function public.exos_v2_recover_participant_access", 1
    )[1]
    assert "insert into public.participants_v2" not in recovery
    assert "set team_id" not in recovery
    assert "insert into public.participant_sessions_v2" in recovery
