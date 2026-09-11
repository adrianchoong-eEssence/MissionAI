import json
from pathlib import Path

from content_packs.george_town_walk_hunt_v1.materialize import candidate_plan, load_pack
from scripts.george_town_hunt_load_harness import plan


ROOT = Path(__file__).resolve().parents[1]


def test_disposable_pack_is_walk_open_hunt_and_synthetic():
    pack = load_pack()
    assert pack["HuntConfiguration"]["HuntMode"] == "WALK"
    assert pack["HuntConfiguration"]["RouteMode"] == "OPEN_HUNT"
    assert len(pack["TeamFormation"]["Teams"]) == 6
    assert all(row["UATOnly"] for row in pack["Checkpoints"])
    assert "final route" in pack["Purpose"].lower()
    assert candidate_plan()["Executed"] is False


def test_migration_preserves_event_isolation_and_no_gps_scoring_path():
    sql = (ROOT / "supabase/051_exos_core_v2_hunt_engine_v1.sql").read_text(encoding="utf-8")
    for token in ("event_hunt_configurations_v2", "event_hunt_missions_v2", "hunt_team_mission_runtime_v2",
                  "p_event_id", "GPSScoring', false", "PARTICIPATION_PRORATED", "FACILITATOR_RUBRIC",
                  "RETURN_NOW", "HOLD", "CLOSED", "exos_v2_hunt_public_projector_projection"):
        assert token in sql
    assert "participant_location_updates_v2" not in sql
    assert "get_live_location_checkpoint_proximity" not in sql


def test_projector_is_explicitly_enabled_and_never_selects_location_data():
    sql = (ROOT / "supabase/051_exos_core_v2_hunt_engine_v1.sql").read_text(encoding="utf-8")
    projection = sql.split("CREATE OR REPLACE FUNCTION public.exos_v2_hunt_public_projector_projection", 1)[1]
    assert "projector_public_enabled" in projection
    for forbidden in ("participant_location", "Latitude", "Longitude", "Evidence", "SubmissionPayload"):
        assert forbidden not in projection


def test_dedicated_entrypoints_keep_event_identity_server_owned():
    participant = (ROOT / "GeorgeTown_Participant.py").read_text(encoding="utf-8")
    projector = (ROOT / "GeorgeTown_Projector.py").read_text(encoding="utf-8")
    control = (ROOT / "GeorgeTown_MissionControl.py").read_text(encoding="utf-8")
    for source in (participant, projector, control):
        assert "george_town_walk_hunt_event" in source
    assert "join_code" not in participant.casefold().replace("join_code=george_town_walk_hunt_event()[1]", "")


def test_harness_is_honest_about_non_execution_and_nera_fixture():
    harness = plan()
    assert harness["Executed"] is False
    assert "NOT_EXECUTED" in harness["Status"]
    assert "Nera" in json.dumps(harness)
