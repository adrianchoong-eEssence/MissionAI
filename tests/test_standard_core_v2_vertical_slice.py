import ast
from pathlib import Path

import pytest

from data.runtime_database import RuntimeDatabaseError, SupabaseRuntimeDB
from data.standard_core_v2_adapter import StandardCoreV2Adapter
from engines.programme_hierarchy import activity_details, encode_activity_details


ROOT = Path(__file__).resolve().parents[1]
STANDARD_SCREENS = [
    "screens/create_event.py", "screens/events_home.py", "screens/programme_builder.py",
    "screens/control_centre.py", "screens/participant.py", "screens/command_centre.py",
    "screens/leaderboard_display.py",
]


def test_standard_journey_has_no_google_sheets_dependency():
    for relative in STANDARD_SCREENS:
        source = (ROOT / relative).read_text()
        assert "data.google_sheets" not in source, relative
        assert "GoogleSheetsDB" not in source, relative
        assert "get_runtime_database(" not in source, relative
        assert "get_standard_database" in source, relative


def test_standard_adapter_has_strict_core_v2_guard():
    source = (ROOT / "data/standard_core_v2_adapter.py").read_text()
    assert "data.google_sheets" not in source
    assert "legacy_runtime_calls" in source
    assert "google_sheets_runtime_calls" in source
    assert "Blocked non-Core-v2" in source
    assert '"runtime_events"' not in source
    assert '"runtime_participants"' not in source
    assert '"runtime_submissions"' not in source


def test_staging_admin_refuses_known_production_host(monkeypatch):
    class Runtime:
        is_configured = True
        url = "https://bqsbkdfzqyiodivhyxnq.supabase.co"

    monkeypatch.setenv("EXOS_ENV", "staging")
    with pytest.raises(RuntimeDatabaseError, match="Staging isolation blocked"):
        StandardCoreV2Adapter(Runtime())


def test_standard_runtime_migration_reuses_existing_v2_tables_only():
    sql = (ROOT / "supabase/025_standard_programme_runtime.sql").read_text().lower()
    assert "create table" not in sql
    assert "drop table" not in sql
    for function in (
        "exos_v2_standard_launch_activity", "exos_v2_standard_participant_state",
        "exos_v2_standard_submit", "exos_v2_standard_review_submission",
    ):
        assert function in sql
    for table in ("events_v2", "activities_v2", "activity_runtime_v2", "submissions_v2", "reviews_v2", "score_transactions_v2"):
        assert table in sql
    assert "activity is not currently launched" in sql
    assert "participant_scope" in sql


def test_activity_normalisation_persists_scope_submission_and_scoring():
    module = {"ModuleID": "E-M1", "ProgrammeID": "E-P", "ModuleName": "NASI"}
    activity = {
        "ActivityID": "E-A1", "StageName": "NASI", "DurationMinutes": 10,
        "ScoringMode": "NON_SCORING", "ParticipantScope": "INDIVIDUAL",
        "SubmissionType": "NASI",
    }
    row = SupabaseRuntimeDB._normalise_activity_payload("E", module, activity)
    assert row["scoring_mode"] == "NON_SCORING"
    assert row["activity_payload"]["participant_scope"] == "INDIVIDUAL"
    assert row["activity_payload"]["submission_type"] == "NASI"


def test_builder_exposes_scoring_and_submission_ownership_controls():
    source = (ROOT / "screens/programme_builder.py").read_text()
    for text in ("Scoring mode", "Submission ownership", "Individual activity", "Team activity", "Submission type"):
        assert text in source


def test_existing_admin_core_v2_staging_controls_are_explicit():
    event_home = (ROOT / "screens/events_home.py").read_text()
    create_event = (ROOT / "screens/create_event.py").read_text()
    builder = (ROOT / "screens/programme_builder.py").read_text()
    assert "Refresh Events" in event_home
    assert 'st.selectbox(\n            "Status"' in create_event
    assert 'with st.expander("Start Blank")' in builder
    assert 'db.save_programme_stages(event_id, [])' in builder


def test_admin_entrypoint_remains_existing_missionai_app():
    source = (ROOT / "MissionAI.py").read_text()
    assert 'if page == "Events":\n    show_events_home()' in source
    assert 'elif page == "Create Event":\n    show_create_event()' in source
    assert 'elif page == "Programme Builder":\n    show_programme_builder()' in source


def test_activity_configuration_round_trips_scope_and_scoring():
    stage = {
        "FacilitatorInstruction": encode_activity_details({
            "ScoringMode": "NON_SCORING", "ParticipantScope": "INDIVIDUAL",
            "SubmissionType": "NASI",
        })
    }
    details = activity_details(stage)
    assert details["ScoringMode"] == "NON_SCORING"
    assert details["ParticipantScope"] == "INDIVIDUAL"
    assert details["SubmissionType"] == "NASI"


def test_uat_runner_covers_all_acceptance_gates_and_hard_assertions():
    source = (ROOT / "scripts/exos_core_v2_standard_vertical_slice.py").read_text()
    tree = ast.parse(source)
    assert tree
    for gate in range(1, 19):
        assert f'"{gate}_' in source
    for value in ("Pipeline", "Helium Stick", "Key Punch", "Catalyst Challenge", "NASI"):
        assert value in source
    assert "programme_reuse" in source
    assert "LEGACY_RUNTIME_CALLS" in source
    assert "GOOGLE_SHEETS_RUNTIME_CALLS" in source
    assert "KNOWN_PRODUCTION_HOSTS" in source


def test_facilitator_standard_path_selects_core_before_race_branch():
    source = (ROOT / "Facilitator.py").read_text()
    core_position = source.index("db = get_standard_database()")
    staging_position = source.index('if _deployment_environment() == "staging":')
    stop_position = source.index("st.stop()", staging_position)
    google_import_position = source.index("from data.google_sheets import GoogleSheetsDB")
    mode_position = source.index('mode = st.sidebar.radio')
    race_position = source.index("db = GoogleSheetsDB()", mode_position)
    assert core_position < staging_position < stop_position < google_import_position
    assert google_import_position < mode_position < race_position
    staging_path = source[staging_position:stop_position]
    assert "show_control_centre(db=db)" in staging_path
    assert "db.assert_core_v2_only()" in staging_path
    assert "GoogleSheetsDB" not in staging_path


def test_control_centre_accepts_the_strict_staging_adapter():
    source = (ROOT / "screens/control_centre.py").read_text()
    assert "def show_control_centre(db=None):" in source
    assert "db = db or get_standard_database()" in source
