from pathlib import Path

from screens.participant import normalise_join_code, normalise_join_name


SOURCE = (Path(__file__).resolve().parents[1] / "screens" / "participant.py").read_text()


def test_join_keeps_separate_first_and_last_name_fields_without_country():
    assert 'st.text_input("First / Given Name")' in SOURCE
    assert 'st.text_input("Last / Family Name")' in SOURCE
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


def test_prejoin_title_uses_resolved_event_instead_of_fixed_mission_ai():
    prejoin = SOURCE.split('if "participant_event_id" not in st.session_state:', 1)[1]
    prejoin = prejoin.split("db = GoogleSheetsDB()", 1)[0]
    assert 'experience_title(known_event, fallback="EXOS Experience")' in prejoin
    assert 'experience_header("Mission AI")' not in prejoin
