from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from engines.theme_park_race import project_stations, validate_configuration


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "content_packs" / "aia_techquest_20261023_v1"


def _materializer():
    spec = spec_from_file_location("aia_materializer", PACK / "materialize.py")
    module = module_from_spec(spec); assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_aia_candidate_is_preassigned_configurable_open_board_for_250_people():
    content = _materializer().materialize_aia_techquest_content("AIA-TECH-20261023-UAT")
    package = content["Package"]
    assert package["LocalOnly"] is True
    assert package["EventBlueprint"]["TeamFormationConfiguration"]["Mode"] == "PREASSIGNED"
    assert content["RaceConfiguration"]["StrategyMode"] == "OPEN_MISSION_BOARD"
    assert len(content["TeamTemplates"]) == 25
    assert sum(content["TeamCapacities"].values()) == 250
    assert {mission["Category"] for mission in content["Missions"]} == {"RIDES", "TASKS", "SECRET MISSIONS"}
    assert all("Genting" not in mission["DisplayName"] for mission in content["Missions"])
    assert {mission["ScoringMode"] for mission in content["Missions"]} == {"TEAM_FULL", "PARTICIPATION_PRORATED", "FACILITATOR_RUBRIC"}
    assert all(operation["SecretState"] == "RELEASED" for mission_id, operation in content["RaceConfiguration"]["MissionBoard"]["MissionOperations"].items() if "SECRET" in mission_id)
    activities = [{"ActivityID": mission["ActivityID"], "RaceStation": {"Enabled": True, **mission}} for mission in content["Missions"]]
    assert validate_configuration({"RaceConfiguration": content["RaceConfiguration"]}, [team["TeamID"] for team in content["TeamTemplates"]], project_stations(activities)) == []


def test_aia_setup_sql_has_only_hashes_and_disposable_synthetic_roster():
    from scripts.prepare_aia_techquest_candidate import build_setup_sql, owner_test_account
    sql = build_setup_sql()
    assert "AIA-TECH-20261023-UAT" in sql
    assert "exos_v2_configure_team_formation" in sql
    assert "exos_v2_configure_attendance" in sql
    assert '"AIHelpEnabled":true' in sql
    assert "PREASSIGNED" in sql
    assert "250" in sql
    assert "Q00001" not in sql
    assert "Personal Key" not in sql
    assert owner_test_account() == {"Name": "AIA Certification 001", "Team": "AIA-TECH-20261023-UAT-TEAM-01", "PersonalKey": "Q00001"}


def test_aia_projector_is_fixed_event_read_only_and_five_second_polled():
    migration = (ROOT / "supabase" / "045_aia_tech_public_projector_projection.sql").read_text()
    client = (ROOT / "services" / "aia_public_projector.py").read_text()
    screen = (ROOT / "screens" / "aia_live_public_projector.py").read_text()
    assert "AIA-TECH-20261023-UAT" in migration and "p_event_id" not in migration
    assert "SECURITY DEFINER" in migration and "SET search_path = ''" in migration
    assert "SUPABASE_SECRET_KEY" not in client + screen
    assert '@st.fragment(run_every=f"{POLL_INTERVAL_SECONDS}s")' in screen


def test_aia_participant_experience_uses_aia_identity_and_read_only_advisory_layer():
    source = (ROOT / "screens" / "aia_participant_experience.py").read_text()
    assert "aia_personal_key_event" in source
    assert "render_maxis_theme_park_participant" in source
    assert "Ask Mission AI" in (ROOT / "screens" / "maxis_participant_experience.py").read_text()
