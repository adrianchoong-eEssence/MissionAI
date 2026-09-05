"""Source contracts for Maxis private video evidence and final missions."""
from __future__ import annotations

import json
from pathlib import Path

from engines.theme_park_race import normalise_station, validate_configuration


ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "content_packs/maxis_final_content_delta_v1/maxis_final_content_delta_v1.json"


def _pack() -> dict:
    return json.loads(PACK_PATH.read_text(encoding="utf-8"))


def _station(mission: dict) -> dict:
    return {
        "ActivityID": mission["ActivityID"],
        "RaceStation": {
            "Enabled": True,
            "DisplayName": mission["DisplayName"],
            "MissionClass": mission["MissionClass"],
            "Zone": mission["Zone"],
            "LocationDescription": mission["LocationDescription"],
            "ParticipantInstruction": mission["ParticipantInstruction"],
            "FacilitatorInstruction": mission["FacilitatorInstruction"],
            "EvidenceType": mission["EvidenceType"],
            "Evidence": mission["Evidence"],
            "Scoring": mission["Scoring"],
            "SafetyNote": mission["SafetyNote"],
        },
    }


def test_final_delta_is_engine_scoped_and_explicitly_never_bypasses_active_board_freeze():
    pack = _pack()
    assert pack["PackageKind"] == "THEME_PARK_RACE_CONTENT_DELTA"
    assert pack["EventID"] == "MAXIS-UAT-PREASSIGNED"
    assert pack["EngineKind"] == "THEME_PARK_RACE"
    assert pack["StrategyMode"] == "OPEN_MISSION_BOARD"
    assert pack["ApplyPolicy"] == "NEW_OR_UNSTARTED_BOARD_ONLY"
    assert "authoritative runtime or submissions" in pack["Purpose"]


def test_final_missions_have_the_required_safe_video_or_photo_contracts():
    missions = {mission["DisplayName"]: mission for mission in _pack()["Missions"]}
    mannequin = missions["Mannequin Challenge"]
    boot_camp = missions["Boot Camp Training"]
    assert mannequin["Zone"] == "Studio Plaza"
    assert mannequin["Scoring"]["Maximum"] == 140
    assert boot_camp["Zone"] == "Andromeda Base"
    assert boot_camp["Scoring"]["Maximum"] == 150
    for mission in (mannequin, boot_camp):
        assert mission["EvidenceType"] == "PHOTO_OR_VIDEO"
        assert mission["Evidence"]["Photo"]["Required"] is True
        assert mission["Evidence"]["Video"]["Required"] is True
        assert mission["Evidence"]["Video"]["MaximumBytes"] == 50 * 1024 * 1024
        assert mission["CompletionState"]["OnApprove"] == "APPROVED"
        assert mission["Resubmission"]["Mechanism"] == "EXISTING_SUBMISSION_REVISION"
    assert "5–15 seconds" not in boot_camp["ParticipantInstruction"]
    assert "Virtual Queue" in boot_camp["ParticipantInstruction"]
    assert "before or after" in boot_camp["SafetyNote"]
    assert "walkways" in mannequin["SafetyNote"]


def test_theme_park_projection_preserves_video_evidence_type_without_formula_race_coupling():
    mannequin = next(row for row in _pack()["Missions"] if row["DisplayName"] == "Mannequin Challenge")
    station = normalise_station(_station(mannequin))
    assert station["EvidenceType"] == "PHOTO_OR_VIDEO"
    assert station["Evidence"]["Video"]["MaximumBytes"] == 50 * 1024 * 1024
    errors = validate_configuration(
        {
            "SchemaVersion": 1,
            "EngineKind": "THEME_PARK_RACE",
            "StrategyMode": "OPEN_MISSION_BOARD",
            "MissionBoard": {"MissionOperations": {station["ActivityID"]: {"OperationalStatus": "AVAILABLE", "SecretState": "RELEASED"}}},
        },
        [], [station],
    )
    assert errors == []


def test_video_ui_uses_only_private_storage_and_captain_guarded_board_submission():
    source = (ROOT / "screens/theme_park_race.py").read_text(encoding="utf-8")
    adapter = (ROOT / "data/standard_core_v2_adapter.py").read_text(encoding="utf-8")
    assert "upload_evidence_file" in source
    assert 'evidence_type="VIDEO"' in source
    assert '"EvidenceType": uploaded_evidence_type or evidence_type' in source
    assert "get_private_evidence_bytes" in source
    assert "st.video(video" in source
    assert "save_theme_park_race_submission" in source
    assert "EvidenceType" in adapter
    assert "create_submission_image_url" not in source


def test_mission_ai_image_input_is_transient_and_has_no_gameplay_write_path():
    source = (ROOT / "screens/maxis_participant_experience.py").read_text(encoding="utf-8")
    assert "Add screenshot / photo" in source
    assert "input_image" in source
    assert "never stored, submitted or shared" in source
    assistant_slice = source[source.index("def _render_mission_ai_assistant"):source.index("def render_maxis_theme_park_participant")]
    assert "save_theme_park_race_submission" not in assistant_slice
    assert "select_theme_park_race_mission" not in assistant_slice
