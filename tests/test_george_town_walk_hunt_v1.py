import json
from copy import deepcopy
from pathlib import Path

from content_packs.george_town_walk_hunt_v1.materialize import (
    _architecture_errors,
    candidate_plan,
    load_pack,
)
from scripts.george_town_hunt_load_harness import plan


ROOT = Path(__file__).resolve().parents[1]


def test_enca_fixture_is_a_non_materialising_walk_hunt_architecture():
    pack = load_pack()
    assert pack["Event"]["EventID"] == "ENCA-GEORGETOWN-20261024-UAT"
    assert pack["HuntConfiguration"]["HuntMode"] == "WALK"
    assert pack["HuntConfiguration"]["RouteMode"] == "OPEN_HUNT"
    assert pack["Checkpoints"] == []
    assert pack["Missions"] == []
    assert candidate_plan()["Executed"] is False


def test_content_foundation_is_compact_optional_and_owner_pending():
    pack = load_pack()
    foundation = pack["HuntContentFoundation"]
    arena = foundation["Arena"]

    assert foundation["TargetMasterMissionPool"] == 20
    assert foundation["MissionBoardMode"] == "OPTIONAL_BALANCED_SUBSETS"
    assert set(foundation["MissionClasses"]) == {"COMMON", "RANDOM", "SECRET"}
    assert foundation["AllocationPolicy"]["SameMissionBoardForEveryTeam"] is False
    assert foundation["AllocationPolicy"]["ForcedLinearRoute"] is False
    assert {zone["ZoneID"] for zone in arena["CandidateZones"]} >= {
        "HIN_BUS_DEPOT",
        "ARMENIAN_STREET",
        "CHEW_JETTY_CLAN_JETTIES",
    }
    assert all(zone["Coordinates"] == "OWNER_PENDING" for zone in arena["CandidateZones"])
    assert any(zone["ZoneID"] == "FORT_CORNWALLIS" for zone in arena["ExcludedZones"])
    assert foundation["ReturnToBase"] == {
        "PinID": "RETURN_TO_BASE",
        "Persistent": True,
        "Scored": False,
        "Coordinates": "OWNER_PENDING",
        "HumanGuidance": "OWNER_PENDING",
        "DistanceToBase": "ENABLE_AFTER_COORDINATES_APPROVED",
        "Announcements": ["30 MINUTES REMAINING", "RETURN TO BASE NOW"],
    }
    assert candidate_plan()["HuntContentFoundation"] == foundation


def test_content_foundation_rejects_final_coordinates_before_owner_authorisation():
    pack = deepcopy(load_pack())
    pack["HuntContentFoundation"]["Arena"]["CandidateZones"][0]["Coordinates"] = "5.4100,100.3320"
    assert "ENCA Hunt candidate zones must not contain final coordinates." in _architecture_errors(pack)


def test_hunt_foundation_keeps_gps_out_of_scoring():
    sql = (ROOT / "supabase/051_exos_core_v2_hunt_engine_v1.sql").read_text(encoding="utf-8")
    for token in ("event_hunt_configurations_v2", "event_hunt_missions_v2", "hunt_team_mission_runtime_v2",
                  "p_event_id", "GPSScoring', false", "PARTICIPATION_PRORATED", "FACILITATOR_RUBRIC",
                  "RETURN_NOW", "HOLD", "CLOSED", "exos_v2_hunt_public_projector_projection"):
        assert token in sql
    assert "participant_location_updates_v2" not in sql
    assert "get_live_location_checkpoint_proximity" not in sql


def test_legacy_load_plan_remains_honest_about_non_execution_and_nera():
    harness = plan()
    assert harness["Executed"] is False
    assert "NOT_EXECUTED" in harness["Status"]
    assert "Nera" in json.dumps(harness)
