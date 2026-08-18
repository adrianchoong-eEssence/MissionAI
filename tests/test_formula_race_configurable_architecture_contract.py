from pathlib import Path


def test_configurable_architecture_is_generic_and_keeps_standard_out_of_scope():
    engine = Path("engines/formula_race_configuration.py").read_text()
    sql = Path("supabase/030_formula_race_configurable_event_architecture.sql").read_text()
    captain = Path("screens/formula_race_captain.py").read_text()
    setup = Path("screens/formula_race.py").read_text()
    assert "FACILITATOR_SCORE" in engine and "LOWEST_TIME" in engine
    assert "HIGHEST_COUNT" in engine and "SUCCESS_COUNT" in engine
    assert "generate_balanced_routes" in engine and "current_station" in engine
    assert "exos_v2_formula_race_submit_station" in sql
    assert "exos_v2_formula_race_verify_station_result" in sql
    assert "exos_v2_formula_race_reconcile_station_ranking" in sql
    assert "exos_v2_formula_race_reset_event" in sql
    assert "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F" in setup
    assert "NextCheckpoint" in captain and "captain_result_entry_method" in captain
    assert "Event Setup" in setup
    assert "Standard" in sql and "does not alter Standard" in sql


def test_configuration_migration_preserves_configuration_during_reset_and_hashes_pins_elsewhere():
    sql = Path("supabase/030_formula_race_configurable_event_architecture.sql").read_text()
    pins = Path("supabase/022_exos_core_v2_team_access.sql").read_text()
    assert "Preserved" in sql and "team_access_credentials_v2" not in sql.split("create or replace function public.exos_v2_formula_race_reset_event", 1)[1]
    assert "extensions.crypt" in pins
