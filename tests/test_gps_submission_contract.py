from screens.participant import (
    _normalise_gps_support,
    _mission_evidence_modes,
    _gps_payload_from_position,
)


def test_gps_support_from_mission_modes():
    mission = {
        "GPSRequired": "Yes",
        "EvidenceType": "PHOTO",
    }
    assert _normalise_gps_support(mission) == "GPS_PHOTO"

    mission.update({"EvidenceType": "TEXT"})
    assert _normalise_gps_support(mission) == "GPS_TEXT"

    mission.update({"EvidenceType": "VIDEO, PHOTO"})
    assert _normalise_gps_support(mission) == "GPS_BOTH"

    mission.update({"GPSRequired": "No", "EvidenceType": ""})
    assert _normalise_gps_support(mission) == ""


def test_mission_evidence_modes_falls_back_to_text():
    assert _mission_evidence_modes({}) == ["TEXT"]
    assert _mission_evidence_modes({"EvidenceType": "NONE"}) == []


def test_gps_payload_parses_accuracy_timestamp():
    payload = _gps_payload_from_position({
        "latitude": "3.1",
        "longitude": "4.2",
        "accuracy": "12.5",
        "captured_at": "2026-01-01T00:00:00Z",
    })

    assert payload is not None
    assert payload["latitude"] == 3.1
    assert payload["longitude"] == 4.2
    assert payload["accuracy_meters"] == 12.5
    assert payload["captured_at"] == "2026-01-01T00:00:00Z"
