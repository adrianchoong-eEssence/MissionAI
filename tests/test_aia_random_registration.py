from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_aia_registration_is_fixed_event_random_assign_with_one_attendance_write_path():
    migration = (ROOT / "supabase" / "046_aia_tech_random_registration_attendance.sql").read_text()
    assert "exos_v2_aia_tech_register_random" in migration
    assert "exos_v2_team_formation_register_random" in migration
    assert "exos_v2_set_participant_attendance" in migration
    assert "'AIA-TECH-20261023-UAT'" in migration
    assert "'AIAUAT'" in migration
    assert "p_event_id" not in migration
    assert "SET search_path = ''" in migration
    assert "TO anon, authenticated" in migration


def test_aia_entry_hides_join_code_and_keeps_credential_out_of_query_parameters():
    entry = (ROOT / "AIA_Participant.py").read_text()
    screen = (ROOT / "screens" / "aia_random_registration.py").read_text()
    assert "render_aia_random_registration" in entry
    assert '"FIRST / GIVEN NAME"' in screen
    assert '"LAST / FAMILY NAME"' in screen
    assert "RECONNECT / CONTINUE" in screen
    assert "participant_device_binding" in screen
    assert "participant_device_id()" not in screen
    assert '"device_id"' in screen
    assert '"enrollment_credential"' in screen
    assert '"join_code"' in screen
    assert "register_aia_random_participant" in screen


def test_aia_reconnect_uses_a_stable_browser_binding_before_registration_and_only_shows_retry_after_failure():
    component = (ROOT / "components" / "participant_credential" / "index.html").read_text()
    screen = (ROOT / "screens" / "aia_random_registration.py").read_text()
    assert '"exos.team-formation.v1.enrollment." + eventId' in component
    assert '"exos.team-formation.v1.device." + eventId' in component
    assert "HasStoredCredential: credential.existed" in component
    assert "def _recover_binding" in screen
    assert "runtime.recover_team_formation_participant(join_code, credential, device_id)" in screen
    assert "if not _valid(player, event_id) and binding[\"HasStoredCredential\"]:" in screen
    assert screen.index("_recover_binding(runtime, event_id, join_code, credential, device_id)") < screen.index("with st.form(\"aia_random_registration\"")
    assert screen.count("_render_reconnect(runtime, event_id, join_code, credential, device_id)") == 1


def test_aia_250_harness_records_the_random_registration_proof_requirements():
    source = (ROOT / "scripts" / "aia_250_certification.py").read_text()
    assert "exos_v2_aia_tech_register_random" in source
    assert "one canonical PRESENT attendance write" in source
    assert "same-device retry" in source
    assert "close-tab/reopen" in source
    assert "close-browser/reopen" in source
    assert "no second PRESENT attendance write" in source
    assert "never reports that wrapper as PASS without that run" in source
