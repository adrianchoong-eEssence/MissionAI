from engines.hunt_engine import configuration_errors, is_walk_hunt, participant_hunt_state, project_mission_board


def _configuration():
    return {"SchemaVersion": 1, "EngineKind": "HUNT", "HuntMode": "WALK", "RouteMode": "OPEN_HUNT", "OperationalState": "READY"}


def test_walk_hunt_is_selected_only_by_explicit_configuration():
    assert is_walk_hunt(_configuration())
    assert not is_walk_hunt({"EventName": "George Town Walk Hunt", "HuntMode": "WALK"})


def test_fixture_configuration_requires_reusable_contract_fields():
    errors = configuration_errors(
        _configuration(), checkpoints=[{"CheckpointID": "CP-1", "Name": "Synthetic", "Latitude": 5.4, "Longitude": 100.3, "RadiusMeters": 90}],
        missions=[{"MissionID": "M-1", "ActivityID": "A-1", "Name": "Mission", "MissionType": "PHOTO", "CheckpointID": "CP-1", "EvidenceType": "PHOTO", "Scoring": {"Mode": "TEAM_FULL", "Maximum": 10}}],
    )
    assert errors == []


def test_secret_mission_is_not_client_revealed():
    board = project_mission_board(
        [{"MissionID": "SECRET", "ActivityID": "A", "Name": "Secret", "MissionType": "SECRET", "Secret": True}],
        [],
    )
    assert board[0]["Visible"] is False
    released = project_mission_board(
        [{"MissionID": "SECRET", "ActivityID": "A", "Name": "Secret", "MissionType": "SECRET", "Secret": True}],
        [{"MissionID": "SECRET", "MissionState": "AVAILABLE"}],
    )
    # A runtime state alone is not a release signal; the server supplies the
    # explicit release projection in production. This pure helper remains safe.
    assert released[0]["Visible"] is False


def test_return_and_hold_win_over_live_presentation():
    assert participant_hunt_state("ACTIVE", "LIVE") == "LIVE"
    assert participant_hunt_state("ACTIVE", "HOLD") == "HOLD"
    assert participant_hunt_state("ACTIVE", "RETURN_NOW") == "RETURN_NOW"
    assert participant_hunt_state("ACTIVE", "CLOSED") == "CLOSED"
