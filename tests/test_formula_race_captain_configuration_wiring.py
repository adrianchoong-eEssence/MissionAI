"""Disposable-only regression coverage for Captain's migration-030 wiring."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
from engines.formula_race_configuration import generate_balanced_routes


@contextmanager
def _staging_env():
    original = os.getenv("EXOS_ENV")
    os.environ["EXOS_ENV"] = "staging"
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("EXOS_ENV", None)
        else:
            os.environ["EXOS_ENV"] = original


class _DisposableRuntime:
    is_configured = True
    can_publish = True
    url = "https://staging.disposable.example.test"

    def _request(self, *_args, **_kwargs):
        return []


def _adapter() -> FormulaRaceCoreV2StagingAdapter:
    with _staging_env():
        return FormulaRaceCoreV2StagingAdapter(_DisposableRuntime())


def _stations():
    return [
        {
            "ActivityID": activity_id,
            "DisplayOrder": index,
            "ShortCode": short_code,
            "DisplayName": name,
            "ParticipantInstruction": instruction,
            "FacilitatorInstruction": "Facilitator records the official result.",
            "ScoringMethod": method,
            "EvidenceRequirement": evidence,
            "BaseCredits": 15,
            "Enabled": True,
        }
        for index, (activity_id, short_code, name, instruction, method, evidence) in enumerate([
            ("CURRENT-R", "R", "RESULT — Sponsor Pitch", "Pitch your sponsor result.", "FACILITATOR_SCORE", "NO_PHOTO"),
            ("CURRENT-A", "A", "ACCELERATE — Pit Lane Relay", "Complete the pit lane relay.", "LOWEST_TIME", "PHOTO_REQUIRED"),
            ("CURRENT-C", "C", "COLLABORATION — Tyre Management Challenge", "Manage the tyres together.", "HIGHEST_COUNT", "PHOTO_OPTIONAL"),
            ("CURRENT-E", "E", "EFFICIENCY — Driver Reflex Academy", "Complete the driver reflex successes.", "SUCCESS_COUNT", "PHOTO_REQUIRED"),
        ], 1)
    ]


def _activities(stations):
    # These rows deliberately retain obsolete UAT labels/payloads.  Migration
    # 030 stores its real station payload beneath race_station.
    return [
        {
            "activity_id": station["ActivityID"],
            "activity_name": f"RACE CHECKPOINT {index}",
            "activity_order": index,
            "activity_payload": {
                "Instructions": f"Checkpoint {index} proof + notes.",
                "Credits": index,
                "race_station": station,
            },
        }
        for index, station in enumerate(stations, 1)
    ]


def test_captain_workspace_reads_the_same_canonical_station_fields_as_race_control():
    adapter = _adapter()
    stations = _stations()
    activities = _activities(stations)
    team_ids = [f"DISPOSABLE-TEAM-{number:02d}" for number in range(1, 11)]
    teams = [{"TeamID": team_id, "TeamName": f"Disposable Team {number:02d}", "IsActive": True} for number, team_id in enumerate(team_ids, 1)]
    routes = generate_balanced_routes(team_ids, [station["ActivityID"] for station in stations])
    configuration = {"Stations": stations, "TeamRoutes": routes}
    active_team = {"team_id": team_ids[0]}

    adapter._get_checkpoint_activities = lambda _event_id: activities
    adapter.get_formula_race_configuration = lambda _event_id: configuration
    adapter.get_runtime_teams = lambda _event_id: teams
    adapter.get_canonical_transaction_report = lambda *_args, **_kwargs: {"Leaderboard": []}
    adapter._marketplace_payload = lambda *_args, **_kwargs: {"items": [], "purchases": []}
    adapter._build_status_payload = lambda *_args, **_kwargs: {}

    def fake_get(table, _query=None, _admin=True):
        if table == "team_access_sessions_v2":
            return [{
                "team_access_session_id": "SESSION", "event_id": "DISPOSABLE-EVENT",
                "team_id": active_team["team_id"], "is_active": True,
            }]
        return []

    adapter._get = fake_get
    first = adapter.formula_race_captain_workspace("00000000-0000-0000-0000-000000000001", "disposable-device")

    assert first["EventID"] == "DISPOSABLE-EVENT"
    assert first["TeamID"] == team_ids[0]
    assert first["Route"] == routes[team_ids[0]]
    current = first["CurrentCheckpoint"]
    assert current["ActivityID"] == "CURRENT-R"
    assert current["Name"] == "RESULT — Sponsor Pitch"
    assert current["Instructions"] == "Pitch your sponsor result."
    assert current["Credits"] == 15
    assert current["ScoringMethod"] == "FACILITATOR_SCORE"
    assert current["EvidenceRequirement"] == "NO_PHOTO"
    assert "RouteConfigurationIssue" not in first or not first["RouteConfigurationIssue"]

    # A canonical submission advances without facilitator approval, and a
    # reconnect rehydrates the same team-specific canonical route.
    def submitted_get(table, _query=None, _admin=True):
        if table == "team_access_sessions_v2":
            return [{"team_access_session_id": "SESSION", "event_id": "DISPOSABLE-EVENT", "team_id": team_ids[0], "is_active": True}]
        if table == "submissions_v2":
            return [{"activity_id": "CURRENT-R", "submission_status": "SUBMITTED"}]
        return []

    adapter._get = submitted_get
    reconnected = adapter.formula_race_captain_workspace("00000000-0000-0000-0000-000000000001", "disposable-device")
    assert reconnected["Route"] == routes[team_ids[0]]
    assert reconnected["CurrentCheckpoint"]["ActivityID"] == "CURRENT-A"
    assert reconnected["CurrentCheckpoint"]["Name"] == "ACCELERATE — Pit Lane Relay"

    # Each saved route remains isolated to its canonical TeamID.
    assert len(routes) == 10
    assert all(set(route) == {"CURRENT-R", "CURRENT-A", "CURRENT-C", "CURRENT-E"} for route in routes.values())


def test_rotated_cp2_first_route_renders_and_advances_in_team_route_order():
    """A Captain route is ordered by TeamRoutes, never global CP numbering."""
    adapter = _adapter()
    stations = _stations()
    replacement_ids = ["CP3", "CP1", "CP2", "CP4"]
    for station, activity_id in zip(stations, replacement_ids):
        station["ActivityID"] = activity_id
    activities = _activities(stations)
    team_id = "ROTATED-TEAM"
    configuration = {
        "Stations": stations,
        "TeamRoutes": {team_id: ["CP2", "CP1", "CP3", "CP4"]},
    }
    adapter._get_checkpoint_activities = lambda _event_id: activities
    adapter.get_formula_race_configuration = lambda _event_id: configuration
    adapter.get_runtime_teams = lambda _event_id: [{"TeamID": team_id, "TeamName": "Disposable", "IsActive": True}]
    adapter.get_canonical_transaction_report = lambda *_args, **_kwargs: {"Leaderboard": []}
    adapter._marketplace_payload = lambda *_args, **_kwargs: {"items": [], "purchases": []}
    adapter._build_status_payload = lambda *_args, **_kwargs: {}

    def workspace_get(submissions):
        def fake_get(table, _query=None, _admin=True):
            if table == "team_access_sessions_v2":
                return [{"team_access_session_id": "SESSION", "event_id": "DISPOSABLE-EVENT", "team_id": team_id, "is_active": True}]
            if table == "submissions_v2":
                return submissions
            return []
        return fake_get

    adapter._get = workspace_get([])
    before = adapter.formula_race_captain_workspace("00000000-0000-0000-0000-000000000001", "disposable-device")
    assert before["CurrentCheckpoint"]["ActivityID"] == "CP2"
    assert [row["ActivityID"] for row in before["Checkpoints"]] == ["CP2"]

    # The only persisted submission is CP2.  It immediately advances to the
    # configured second route entry; CP1 is not synthesised by the workspace.
    adapter._get = workspace_get([{"activity_id": "CP2", "submission_status": "SUBMITTED"}])
    after = adapter.formula_race_captain_workspace("00000000-0000-0000-0000-000000000001", "disposable-device")
    assert after["CurrentCheckpoint"]["ActivityID"] == "CP1"
    assert [row["ActivityID"] for row in after["Checkpoints"]] == ["CP2", "CP1"]
    assert after["NextCheckpoint"]["ActivityID"] == "CP3"

    captain_source = (Path(__file__).resolve().parents[1] / "screens" / "formula_race_captain.py").read_text()
    assert captain_source.count('st.session_state.pop("race_captain_selected_checkpoint", None)') >= 3
    assert 'storage_path=f"{event_id}/{team_id}/{current.get(\'ActivityID\')}' in captain_source


def test_station_projection_excludes_retired_cp_rows_and_route_preview_is_read_only():
    adapter = _adapter()
    stations = _stations()
    activities = [
        *(_activities(stations)),
        {"activity_id": "RETIRED-CP1", "activity_name": "RACE CHECKPOINT 1", "activity_order": 99, "activity_payload": {"Credits": 2}},
    ]
    teams = [{"TeamID": "TEAM-1", "TeamName": "Disposable Team", "IsActive": True}]
    configuration = {"Stations": stations, "TeamRoutes": {"TEAM-1": ["RETIRED-CP1", "CURRENT-R", "CURRENT-A", "CURRENT-C"]}}
    adapter._get_checkpoint_activities = lambda _event_id: activities
    adapter.get_formula_race_configuration = lambda _event_id: configuration
    adapter.get_runtime_teams = lambda _event_id: teams

    projected = adapter.get_formula_race_stations("DISPOSABLE-EVENT")
    preview = adapter.get_formula_race_route_reconciliation_preview("DISPOSABLE-EVENT")

    assert [station["ActivityID"] for station in projected] == ["CURRENT-R", "CURRENT-A", "CURRENT-C", "CURRENT-E"]
    assert preview["NeedsReconciliation"] is True
    row = preview["Teams"][0]
    assert row["CurrentRouteActivityIDs"][0] == "RETIRED-CP1"
    assert row["ResolvedStationNames"][0] == "RACE CHECKPOINT 1"
    assert row["StaleActivityIDs"] == ["RETIRED-CP1"]
    assert row["ProposedReplacementActivityIDs"] == ["CURRENT-R", "CURRENT-A", "CURRENT-C", "CURRENT-E"]
