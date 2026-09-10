from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from engines.theme_park_race import participation_prorated_score, project_stations, validate_configuration


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "content_packs" / "aia_techquest_20261023_v1"


def _materializer():
    spec = spec_from_file_location("aia_materializer", PACK / "materialize.py")
    module = module_from_spec(spec); assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_aia_candidate_is_random_assign_configurable_open_board_for_250_people():
    content = _materializer().materialize_aia_techquest_content("AIA-TECH-20261023-UAT")
    package = content["Package"]
    assert package["LocalOnly"] is True
    assert package["EventBlueprint"]["TeamFormationConfiguration"]["Mode"] == "RANDOM_ASSIGN"
    assert content["RaceConfiguration"]["StrategyMode"] == "OPEN_MISSION_BOARD"
    assert len(content["TeamTemplates"]) == 25
    assert sum(content["TeamCapacities"].values()) == 250
    assert {mission["Category"] for mission in content["Missions"]} == {"RIDES / PHYSICAL", "TASKS", "SECRETS"}
    assert all("Genting" not in mission["DisplayName"] for mission in content["Missions"])
    assert {mission["ScoringMode"] for mission in content["Missions"]} == {"TEAM_FULL", "PARTICIPATION_PRORATED", "FACILITATOR_RUBRIC"}
    assert all(operation["SecretState"] == "RELEASED" for mission_id, operation in content["RaceConfiguration"]["MissionBoard"]["MissionOperations"].items() if "SECRET" in mission_id)
    activities = [{"ActivityID": mission["ActivityID"], "RaceStation": {"Enabled": True, **mission}} for mission in content["Missions"]]
    assert validate_configuration({"RaceConfiguration": content["RaceConfiguration"]}, [team["TeamID"] for team in content["TeamTemplates"]], project_stations(activities)) == []


def test_aia_locked_mission_board_has_the_authorised_scores_and_canonical_participation_rounding():
    content = _materializer().materialize_aia_techquest_content("AIA-TECH-20261023-UAT", team_count=7, capacity=13)
    missions = content["Missions"]
    by_name = {mission["DisplayName"]: mission for mission in missions}
    assert len(missions) == 10
    assert "Acorn Adventure" not in by_name
    assert by_name["Rivet Town Roller"]["Scoring"] == {"Mode": "PARTICIPATION_PRORATED", "Maximum": 150, "Rounding": "HALF_UP"}
    assert by_name["Boot Camp Training"]["Scoring"] == {"Mode": "PARTICIPATION_PRORATED", "Maximum": 250, "Rounding": "HALF_UP"}
    assert sum(mission["Scoring"]["Maximum"] for mission in missions) == 1450
    assert [participation_prorated_score(250, participants_completing=count, present_team_size=9) for count in (9, 8, 7, 6)] == [250, 222, 194, 167]
    assert len(content["TeamTemplates"]) == 7
    assert sum(content["TeamCapacities"].values()) == 91


def test_aia_setup_sql_is_an_empty_random_assign_fixture_without_credentials():
    from scripts.prepare_aia_techquest_candidate import build_setup_sql
    sql = build_setup_sql()
    assert "AIA-TECH-20261023-UAT" in sql
    assert "exos_v2_configure_team_formation" in sql
    assert "exos_v2_configure_attendance" in sql
    assert '"AIHelpEnabled":true' in sql
    assert "RANDOM_ASSIGN" in sql
    assert "250" in sql
    assert "EnrollmentCredentialHash" not in sql
    assert "Personal Key" not in sql
    assert "participants_v2 where event_id='AIA-TECH-20261023-UAT' and not is_archived)<>0" in sql


def test_aia_locked_content_update_refuses_started_state_and_is_scoped_to_the_disposable_uat():
    migration = (ROOT / "supabase" / "047_aia_tech_locked_mission_content.sql").read_text()
    assert "AIA-TECH-20261023-UAT" in migration
    assert "RuntimePhase is READY" in migration
    assert "frozen after runtime, submission, or score state exists" in migration
    assert "RIDE-RIVET-TOWN-ROLLER" in migration
    assert "RIDE-ACORN" in migration
    assert "1450" in migration
    assert "MAXIS" not in migration


def test_aia_projector_is_fixed_event_read_only_and_five_second_polled():
    migration = (ROOT / "supabase" / "045_aia_tech_public_projector_projection.sql").read_text()
    client = (ROOT / "services" / "aia_public_projector.py").read_text()
    screen = (ROOT / "screens" / "aia_live_public_projector.py").read_text()
    assert "AIA-TECH-20261023-UAT" in migration and "p_event_id" not in migration
    assert "SECURITY DEFINER" in migration and "SET search_path = ''" in migration
    assert "SUPABASE_SECRET_KEY" not in client + screen
    assert '@st.fragment(run_every=f"{POLL_INTERVAL_SECONDS}s")' in screen


def test_aia_participant_experience_uses_random_identity_and_read_only_advisory_layer():
    source = (ROOT / "screens" / "aia_participant_experience.py").read_text()
    assert "aia_random_registration_event" in source
    assert "render_maxis_theme_park_participant" in source
    assert "Ask Mission AI" in (ROOT / "screens" / "maxis_participant_experience.py").read_text()
