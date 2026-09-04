from pathlib import Path

from screens.maxis_personal_key import (
    COUNTRY_GREETING,
    EVENT_ID,
    JOIN_CODE,
    _country_reveal,
    claim_personal_key,
    is_maxis_personal_key_request,
)
from services.personal_key_credentials import derive_personal_key_credential


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = (ROOT / "Participant.py").read_text(encoding="utf-8")
SCREEN = (ROOT / "screens" / "maxis_personal_key.py").read_text(encoding="utf-8")
ADAPTER = (ROOT / "data" / "standard_core_v2_adapter.py").read_text(encoding="utf-8")


class _ClaimRuntime:
    def __init__(self):
        self.calls = []

    def claim_preassigned_team_formation_participant(self, *args):
        self.calls.append(args)
        return {
            "EventID": EVENT_ID,
            "ParticipantID": "P-1",
            "TeamID": "T-1",
            "Team": "Japan",
            "Country": "Japan",
            "Flag": "🇯🇵",
            "Name": "Canonical Person",
            "SessionToken": "S-1",
        }


def test_dedicated_url_routes_to_personal_key_screen_first():
    assert "is_maxis_personal_key_request(st.query_params)" in ENTRYPOINT
    assert ENTRYPOINT.index("is_maxis_personal_key_request(st.query_params)") < ENTRYPOINT.index(
        "if _is_theme_park_race_request()"
    )


def test_personal_key_mode_requires_both_fixed_url_controls():
    assert is_maxis_personal_key_request({"join_code": JOIN_CODE, "personal_key": "1"})
    assert not is_maxis_personal_key_request({"join_code": JOIN_CODE})
    assert not is_maxis_personal_key_request({"join_code": "OTHER", "personal_key": "1"})


def test_login_accepts_only_personal_key_and_fixed_join_code():
    form = SCREEN.split('with st.form("maxis_personal_key_form"', 1)[1]
    assert 'st.text_input(\n            "PERSONAL KEY"' in form
    assert 'type="password"' in form
    assert '"ENTER MISSION AI"' in form
    assert "First / Given Name" not in form
    assert "Last / Family Name" not in form
    assert 'st.text_input("Join Code"' not in form
    assert 'JOIN_CODE = "MXKEY7"' in SCREEN
    assert 'EVENT_ID = "MAXIS-UAT-PREASSIGNED"' in SCREEN


def test_claim_uses_existing_preassigned_rpc_as_anon():
    method = ADAPTER.split("def claim_preassigned_team_formation_participant", 1)[1]
    method = method.split("def recover_team_formation_participant", 1)[0]
    assert '"exos_v2_team_formation_claim_preassigned"' in method
    assert '"p_join_code": join_code' in method
    assert '"p_enrollment_credential": enrollment_credential' in method
    assert '"p_device_id": device_id' in method
    assert "admin=False" in method

    runtime = _ClaimRuntime()
    player = claim_personal_key(runtime, " tmBhMb ", "device-1")
    assert player["Name"] == "Canonical Person"
    assert runtime.calls == [(
        JOIN_CODE,
        derive_personal_key_credential(EVENT_ID, "TMBHMB"),
        "device-1",
    )]
    assert runtime.calls[0][1] != "TMBHMB"


def test_identity_fields_are_canonical_and_read_only():
    assert "restore_participant_identity(player)" in SCREEN
    assert 'player.get("Name"' in SCREEN
    assert 'player.get("Country")' in SCREEN
    assert 'player.get("Team")' in SCREEN
    for editable_label in ("First Name", "Last Name", "Display Name", "Team", "Country"):
        assert f'st.text_input("{editable_label}"' not in SCREEN
        assert f'st.selectbox("{editable_label}"' not in SCREEN


def test_country_reveal_has_all_six_approved_countries():
    expected = {
        "Japan": ("🇯🇵", "KONNICHIWA!"),
        "South Korea": ("🇰🇷", "ANNYEONGHASEYO!"),
        "France": ("🇫🇷", "BONJOUR!"),
        "Italy": ("🇮🇹", "CIAO!"),
        "Brazil": ("🇧🇷", "OLÁ!"),
        "Thailand": ("🇹🇭", "SAWASDEE!"),
    }
    for country, (flag, greeting) in expected.items():
        assert country in SCREEN
        assert flag in SCREEN
        assert greeting in SCREEN
        country_value, flag_value, greeting_value = _country_reveal({
            "Country": country,
            "Team": "Browser-supplied value is ignored",
            "Flag": flag,
        })
        assert (country_value, flag_value, greeting_value) == (country, flag, greeting)
    assert set(COUNTRY_GREETING) == set(expected)
    assert "MISSION 01" in SCREEN
    assert "FIND YOUR PEOPLE" in SCREEN


def test_reveal_does_not_fetch_or_render_teammate_roster():
    assert "get_team_roster" not in SCREEN
    assert "TeamMembers" not in SCREEN
    assert "_render_team_experience" not in SCREEN
    assert "MY TEAM" not in SCREEN


def test_refresh_restores_only_from_canonical_session_token():
    restore = SCREEN.split("def _restore_session", 1)[1].split("def _persist_session", 1)[0]
    assert 'runtime.get_player_by_token(session_token)' in restore
    assert "restore_participant_identity(player" in restore
    assert "claim_personal_key" not in restore
    assert 'st.query_params, "participant_name"' not in restore
    assert 'st.query_params, "team"' not in restore


def test_personal_key_is_never_persisted_to_query_params():
    persistence = SCREEN.split("def _persist_session", 1)[1].split("def _country_reveal", 1)[0]
    assert '"personal_key": "1"' in persistence  # non-secret mode switch only
    assert "personal_key_input" not in persistence
    assert "personal_key_value" in persistence
    assert '"enrollment_credential"' in persistence


def test_invalid_key_has_exact_safe_message_and_no_fallback_join():
    assert "That Personal Key was not recognised.\\n" in SCREEN
    assert "Check the code beside your name and try again." in SCREEN
    assert "join_player" not in SCREEN
    assert "register_team_formation_participant" not in SCREEN
    assert "claim_personal_key(runtime, personal_key, device_id)" in SCREEN
