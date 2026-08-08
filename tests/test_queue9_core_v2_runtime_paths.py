from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_participant_core_runtime_path_has_no_direct_sheets_write_join_call():
    source = (ROOT / "screens" / "participant.py").read_text()
    assert "join_player_by_code(" in source
    assert "runtime.join_player(" in source
    assert "db.join_player(" not in source


def test_formula_race_captain_is_runtime_only():
    source = (ROOT / "screens" / "formula_race_captain.py").read_text()
    assert "from data.runtime_database" in source
    assert "from data.google_sheets" not in source
    assert "runtime.formula_race_captain_login(" in source
    assert "runtime.formula_race_submit_checkpoint(" in source


def test_gates_for_runtime_paths_and_scoping_are_present_in_database_contracts():
    runtime = (ROOT / "data" / "runtime_database.py").read_text()
    migration = (ROOT / "supabase" / "020_exos_core_v2_schema.sql").read_text()

    assert "exos_join_event_v2" in runtime
    assert "def can_participant_submit" in runtime
    assert "event_id" in runtime and "team_id" in runtime
    assert "on conflict (event_id, idempotency_key)" in migration
    assert "participants_v2" in migration
    assert "participant_sessions_v2" in migration
    assert "unique (event_id, participant_id, idempotency_key)" in migration
    assert "delete from runtime_participants" not in migration.lower()
