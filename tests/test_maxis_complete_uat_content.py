"""Contract tests for the isolated Maxis complete-UAT board package."""
from __future__ import annotations

from scripts.prepare_maxis_complete_uat import build_setup_sql, load_pack, validate_pack


def test_maxis_complete_uat_selects_the_existing_generic_open_board_engine():
    pack = load_pack()
    config = pack["RaceConfiguration"]
    assert pack["EventID"] == "MAXIS-UAT-PREASSIGNED"
    assert config["EngineKind"] == "THEME_PARK_RACE"
    assert config["StrategyMode"] == "OPEN_MISSION_BOARD"
    assert config["RuntimePhase"] == "READY"
    assert config["MissionBoard"]["MaximumConcurrentSelections"] == 3


def test_maxis_board_has_visible_rides_tasks_and_secret_missions_with_complete_contracts():
    pack = load_pack()
    missions = pack["Missions"]
    mission_ids = {mission["ActivityID"] for mission in missions}
    assert len(missions) == len(mission_ids) == 11
    assert {"RIDE", "STANDARD", "BONUS", "SECRET"} <= {mission["MissionClass"] for mission in missions}
    assert sum(mission["MissionClass"] == "SECRET" for mission in missions) == 3
    assert set(pack["RaceConfiguration"]["MissionBoard"]["MissionOperations"]) == mission_ids
    assert all(operation == {"OperationalStatus": "AVAILABLE", "SecretState": "RELEASED"}
               for operation in pack["RaceConfiguration"]["MissionBoard"]["MissionOperations"].values())
    for mission in missions:
        assert mission["DisplayName"]
        assert mission["Zone"] and mission["LocationDescription"]
        assert mission["ParticipantInstruction"] and mission["FacilitatorInstruction"]
        assert mission["SafetyNote"]
        assert mission["Scoring"]["Maximum"] > 0
        assert set(mission["Evidence"]) == {"Text", "Photo", "NumericResult"}


def test_only_the_four_verified_rides_use_the_80_percent_ride_contract():
    pack = load_pack()
    rides = [mission for mission in pack["Missions"] if mission["MissionClass"] == "RIDE"]
    assert [mission["DisplayName"] for mission in rides] == [
        "Samba Gliders", "Invasion Planet Apes", "Independence Day Defiance", "Acorn Adventure",
    ]
    assert [mission["Scoring"]["Maximum"] for mission in rides] == [80, 100, 120, 140]
    for mission in rides:
        assert mission["RideParticipation"] == {
            "RequiredPercent": 80,
            "Rounding": "CEILING",
            "EvidencePathways": ["GROUND_CONTROL", "FULL_TEAM", "FACILITATOR_VERIFIED"],
            "FullParticipationBonus": 0,
        }


def test_loader_is_guarded_and_does_not_contain_personal_keys_or_schema_changes():
    pack = load_pack()
    validate_pack(pack)
    sql = build_setup_sql(pack)
    assert "begin;" in sql and sql.rstrip().endswith("commit;")
    assert "exos_v2_theme_park_race_save_configuration" in sql
    assert "already has programme or authoritative play state" in sql
    assert "create table" not in sql.lower()
    assert "alter table" not in sql.lower()
    assert "TMBHMB" not in sql
    assert "DS4365" not in sql


def test_maxis_personal_key_screen_uses_canonical_phase_for_country_only_gate():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    personal_key = (root / "screens/maxis_personal_key.py").read_text(encoding="utf-8")
    experience = (root / "screens/maxis_participant_experience.py").read_text(encoding="utf-8")
    assert "country_reveal_is_active(workspace)" in personal_key
    assert "team_formation_phase(workspace)" in personal_key
    assert "workspace=workspace" in personal_key
    assert "country_roster_is_available(workspace)" in experience
    assert "🎢 RIDES" in experience
    assert "🎯 TASKS" in experience
    assert "🕵️ SECRET MISSIONS" in experience
    assert "Mission briefing" in experience


def test_live_board_keeps_the_choose_wisely_rule_visible():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    experience = (root / "screens/maxis_participant_experience.py").read_text(encoding="utf-8")
    assert 'if lifecycle in {"READY", "ACTIVE", "HELD"}:' in experience
    assert "Not every mission is required. Choose the missions that best fit your team" in experience
