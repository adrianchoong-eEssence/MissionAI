"""Source-contract coverage for the reusable configuration-led race engine."""
from pathlib import Path

from engines.theme_park_race import (
    ENGINE_KIND,
    configuration_contract,
    current_route_mission,
    facilitator_projection,
    is_theme_park_race,
    participant_lifecycle,
    participant_projection,
    projector_projection,
    project_stations,
    validate_configuration,
)
from data.standard_core_v2_adapter import StandardCoreV2Adapter


ROOT = Path(__file__).resolve().parents[1]


def _event(runtime_phase="READY", formation_phase="ACTIVE"):
    return {
        "EventID": "PARK-1",
        "EventName": "Any future event name is permitted",
        "_EventPayload": {
            "TeamFormation": {"SchemaVersion": 1, "Mode": "RANDOM_ASSIGN", "Phase": formation_phase},
            "RaceConfiguration": {
                "SchemaVersion": 1,
                "EngineKind": "THEME_PARK_RACE",
                "RouteStrategy": "CONFIGURED_TEAM_ROUTE",
                "RuntimePhase": runtime_phase,
                "TeamRoutes": {"T-1": ["A", "B"], "T-2": ["B", "A"]},
                "Projector": {"DefaultView": "TEAM_PROGRESS", "ShowOverallScoring": True},
            },
        },
    }


def _activities():
    return [
        {
            "ActivityID": "A", "StageName": "A legacy title is harmless", "ActivityOrder": 1,
            "RaceStation": {
                "Enabled": True, "DisplayOrder": 1, "DisplayName": "Mission A",
                "ParticipantInstruction": "Find the first clue.",
                "Evidence": {"Text": {"Required": True}, "Photo": {"Required": True}},
                "ReviewRequired": True,
            },
        },
        {
            "ActivityID": "B", "StageName": "Another activity", "ActivityOrder": 2,
            "RaceStation": {
                "Enabled": True, "DisplayOrder": 2, "DisplayName": "Mission B",
                "Evidence": {"NumericResult": {"Required": True, "Label": "Count", "Minimum": 1, "Maximum": 9}},
                "ReviewRequired": False,
            },
        },
        {"ActivityID": "NOT-A-MISSION", "StageName": "Programme marker"},
    ]


def test_engine_selection_is_exactly_configuration_based_not_event_or_programme_name_based():
    assert is_theme_park_race(_event())
    assert not is_theme_park_race({"EventName": "Genting Theme Park Race"})
    assert not is_theme_park_race({"EventName": "Theme Park Race", "_EventPayload": {
        "RaceConfiguration": {"EngineKind": "FORMULA_RACE"},
    }})
    assert configuration_contract()["EngineKind"] == ENGINE_KIND


def test_activity_race_station_projection_and_route_contract_are_generic():
    stations = project_stations(_activities())
    assert [row["ActivityID"] for row in stations] == ["A", "B"]
    assert stations[0]["Evidence"]["Text"]["Required"] is True
    assert stations[0]["Evidence"]["Photo"]["Required"] is True
    assert stations[1]["Evidence"]["NumericResult"]["Maximum"] == 9
    assert validate_configuration(_event(), ["T-1", "T-2"], stations) == []
    broken = _event()
    broken["_EventPayload"]["RaceConfiguration"]["TeamRoutes"]["T-2"] = ["A"]
    assert "T-2: route must contain each enabled mission exactly once." in validate_configuration(broken, ["T-1", "T-2"], stations)


def test_lifecycle_is_derived_from_team_formation_then_engine_runtime_phase():
    config = _event()["_EventPayload"]["RaceConfiguration"]
    assert participant_lifecycle({}, config, registered=False) == "REGISTRATION"
    assert participant_lifecycle({"Phase": "REGISTRATION_OPEN"}, config) == "TEAM_FORMATION"
    assert participant_lifecycle({"Phase": "FORMATION_LOCKED"}, config) == "FORMATION_LOCKED"
    assert participant_lifecycle({"Phase": "CAPTAIN_SELECTION"}, config) == "CAPTAIN_SELECTION"
    assert participant_lifecycle({"Phase": "ACTIVE"}, config) == "READY"
    config["RuntimePhase"] = "ACTIVE"
    assert participant_lifecycle({"Phase": "ACTIVE"}, config) == "ACTIVE"


def test_route_progress_is_canonical_and_rejection_reopens_the_same_mission_for_resubmission():
    assert current_route_mission(["A", "B"], []) == ("A", "B")
    assert current_route_mission(["A", "B"], [{"ActivityID": "A", "Status": "SUBMITTED"}]) == ("B", "")
    assert current_route_mission(["A", "B"], [{"ActivityID": "A", "Status": "REJECTED"}]) == ("A", "B")
    workspace = participant_projection(
        event=_event("ACTIVE"),
        participant={"ParticipantID": "P-1", "TeamID": "T-1", "IsTeamFormationCaptain": True, "CaptainSessionActive": True},
        stations=project_stations(_activities()),
        submissions=[{"TeamID": "T-1", "ActivityID": "A", "Status": "REJECTED"}],
    )
    assert workspace["Lifecycle"] == "ACTIVE"
    assert workspace["IsCaptain"] is True and workspace["CaptainSessionActive"] is True
    assert workspace["CurrentMission"]["ActivityID"] == "A"


def test_facilitator_and_projector_projections_cover_registration_captains_progress_review_and_scores():
    event = _event("ACTIVE")
    stations = project_stations(_activities())
    facilitator = facilitator_projection(
        event=event,
        teams=[{"TeamID": "T-1", "TeamName": "Alpha"}, {"TeamID": "T-2", "TeamName": "Bravo"}],
        participants=[
            {"ParticipantID": "P-1", "TeamID": "T-1", "Name": "Alex", "IsTeamFormationCaptain": True},
            {"ParticipantID": "P-2", "TeamID": "T-2", "Name": "Bea", "IsTeamFormationCaptain": False},
        ],
        stations=stations,
        submissions=[
            {"SubmissionID": "S-1", "TeamID": "T-1", "ActivityID": "A", "Status": "SUBMITTED"},
            {"SubmissionID": "S-2", "TeamID": "T-2", "ActivityID": "B", "Status": "APPROVED"},
        ],
        leaderboard=[{"TeamID": "T-2", "TeamName": "Bravo", "Score": 12}],
    )
    assert facilitator["RegistrationCount"] == 2
    assert facilitator["CaptainCount"] == 1
    assert facilitator["PendingReviewCount"] == 1
    projector = projector_projection(facilitator, event)
    assert projector["ShowOverallScoring"] is True
    assert projector["Teams"][0]["TeamID"] == "T-1"
    assert projector["Leaderboard"][0]["Score"] == 12


def test_engine_surfaces_and_migration_reuse_existing_core_entities_without_formula_race_routing():
    migration = (ROOT / "supabase" / "037_theme_park_race_engine.sql").read_text()
    rollback = (ROOT / "supabase" / "037_theme_park_race_engine_rollback.sql").read_text()
    verifier = (ROOT / "supabase" / "verification" / "exos_v2_theme_park_race_engine_verify.sql").read_text()
    adapter = (ROOT / "data" / "standard_core_v2_adapter.py").read_text()
    participant = (ROOT / "screens" / "participant.py").read_text()
    facilitator = (ROOT / "screens" / "control_centre.py").read_text()
    projector = (ROOT / "screens" / "leaderboard_display.py").read_text()
    assert "create table public" not in migration.lower()
    assert "exos_v2_theme_park_race_submit" in migration
    assert "exos_v2_theme_park_race_submission_guard" in migration
    assert "Only the effective Theme Park Race Captain may submit" in migration
    assert "Only the configured current Theme Park Race mission can be submitted" in migration
    assert "FORMULA_RACE" not in migration
    assert "Rollback blocked" in rollback
    assert "exos_v2_theme_park_race_submission_guard_trg" in verifier
    assert "theme_park_race_participant_workspace" in adapter
    assert "save_theme_park_race_submission" in adapter
    assert "render_theme_park_race_participant" in participant
    assert "render_theme_park_race_facilitator" in facilitator
    assert "render_theme_park_race_projector" in projector


class _ThemeParkRuntime:
    is_configured = True
    can_publish = True
    url = "https://staging.example.test"

    def get_programme_hierarchy(self, _event_id):
        return _activities()

    def _request(self, method, path, payload=None, query=None, **_kwargs):
        if path == "rpc/exos_v2_standard_participant_state":
            return {"EventID": "PARK-1", "ParticipantID": "P-1", "TeamID": "T-1", "Name": "Alex", "SessionToken": "SESSION"}
        if path == "events_v2":
            return [{
                "event_id": "PARK-1", "event_name": "Unrelated title", "join_code": "PARK01",
                "programme_type": "STANDARD", "scoring_mode": "TEAM_COMPETITIVE", "lifecycle_status": "LIVE",
                "event_payload": _event("ACTIVE")["_EventPayload"],
            }]
        if path == "participants_v2":
            return [{
                "participant_id": "P-1", "event_id": "PARK-1", "team_id": "T-1", "display_name": "Alex",
                "is_team_formation_captain": True, "is_leader": True,
            }]
        if path == "participant_sessions_v2":
            return [{"device_id": "device-1"}]
        if path == "team_access_sessions_v2":
            return [{"team_access_session_id": "CAPTAIN-SESSION"}]
        if path == "submissions_v2":
            return [{
                "submission_id": "S-1", "event_id": "PARK-1", "team_id": "T-1", "participant_id": "P-1",
                "activity_id": "A", "submission_status": "SUBMITTED", "submission_payload": {},
            }]
        if path == "teams_v2":
            return [{"team_id": "T-1", "team_name": "Alpha", "country": "", "team_flag": "", "is_active": True}]
        if path == "score_transactions_v2":
            return []
        return []


def test_adapter_rebuilds_captain_workspace_from_core_records_after_reconnect():
    adapter = StandardCoreV2Adapter(_ThemeParkRuntime())
    workspace = adapter.theme_park_race_participant_workspace("SESSION")
    assert workspace["EngineKind"] == "THEME_PARK_RACE"
    assert workspace["IsCaptain"] is True
    assert workspace["CaptainSessionActive"] is True
    assert workspace["CurrentMission"]["ActivityID"] == "B"
