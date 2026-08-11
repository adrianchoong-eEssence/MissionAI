from pathlib import Path

from data.runtime_database import SupabaseRuntimeDB
from screens.participant import normalise_join_code, normalise_join_name


SOURCE = (Path(__file__).resolve().parents[1] / "screens" / "participant.py").read_text()


def test_join_keeps_separate_first_and_last_name_fields_without_country():
    assert '"First / Given Name", key="participant_first_name_input"' in SOURCE
    assert '"Last / Family Name", key="participant_last_name_input"' in SOURCE
    assert 'st.selectbox(\n                    "Country"' not in SOURCE
    assert "select your country" not in SOURCE
    assert "country_options" not in SOURCE


def test_join_normalisation_is_whitespace_safe_and_identity_casing_stays_backend_safe():
    assert normalise_join_code(" ab 12 cd ") == "AB12CD"
    assert normalise_join_name("  Ada  ", "  van   Dyke ") == "Ada van Dyke"
    assert 'pending["participant_name"]' in SOURCE
    assert "db.join_player_by_code(" in SOURCE


def test_existing_registration_reconnect_path_is_visible_and_does_not_allocate_again():
    assert "Check Existing Registration" in SOURCE
    assert "Already registered? Use Check Existing Registration to reconnect." in SOURCE
    assert "Existing registration found. Reconnecting you to your original team." in SOURCE
    assert "runtime.restore_join(" in SOURCE


def test_join_widget_buffer_is_separate_from_canonical_join_identity():
    join_block = SOURCE.split('with st.form("participant_join_form"', 1)[1]
    join_block = join_block.split('st.caption(f"Build:', 1)[0]

    assert '"Join Code", key="participant_join_code_input"' in join_block
    assert '"Join Code", key="participant_join_code"' not in join_block
    assert 'st.session_state["participant_join_code"] = join_code' in join_block
    assert 'st.session_state["participant_join_code"] = pending["join_code"]' not in join_block


def test_join_transition_keeps_pending_and_identity_keys_non_widget_owned():
    widget_keys = {
        "participant_join_code_input",
        "participant_first_name_input",
        "participant_last_name_input",
    }
    durable_keys = {
        "participant_join_code",
        "participant_device_id",
        "participant_join_request",
        "participant_id",
        "participant_event_id",
        "participant_name",
        "participant_team",
        "participant_team_id",
        "participant_session_token",
    }

    assert widget_keys.isdisjoint(durable_keys)
    assert 'st.session_state["participant_join_request"] = {' in SOURCE
    assert 'st.session_state.pop("participant_join_request", None)' in SOURCE
    assert 'persist_session_in_query_params()' in SOURCE


def test_prejoin_title_uses_resolved_event_instead_of_fixed_mission_ai():
    prejoin = SOURCE.split('if "participant_event_id" not in st.session_state:', 1)[1]
    prejoin = prejoin.split("db = GoogleSheetsDB()", 1)[0]
    assert 'experience_title(known_event, fallback="EXOS Experience")' in prejoin
    assert 'experience_header("Mission AI")' not in prejoin


def test_join_and_reconnect_keep_the_runtime_assigned_country_and_team():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    calls = []
    assigned = {
        "ParticipantID": "P-1", "EventID": "EVT-AGILE", "Name": "Ada Tan",
        "TeamID": "TEAM-MY", "Team": "Malaysia", "Country": "Malaysia",
        "Flag": "🇲🇾", "SessionToken": "session-1",
    }

    def request(method, path, payload=None, **_):
        calls.append((method, path, payload))
        return [assigned]

    runtime._request = request
    first = runtime.join_player(" agile 01 ", "Ada Tan", "device-a")
    reconnect = runtime.join_player("AGILE01", "  ADA   TAN ", "device-b")

    assert first["TeamID"] == reconnect["TeamID"] == "TEAM-MY"
    assert first["Country"] == reconnect["Country"] == "Malaysia"
    assert all(call[2]["p_requested_team_id"] == "" for call in calls)
    assert all(call[1] == "rpc/exos_join_event_v2" for call in calls)


def test_participant_team_card_displays_assigned_country_after_join():
    assert 'st.markdown("#### Team Members")' in SOURCE
    assert "Your Team" in SOURCE
    assert 'st.session_state["participant_country"]' in SOURCE
