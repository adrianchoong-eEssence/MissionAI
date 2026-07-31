import json
from unittest.mock import patch

from data.google_sheets import GoogleSheetsDB
from data.runtime_database import SupabaseRuntimeDB
from screens.administration import reset_confirmation_matches


class Worksheet:
    def __init__(self, headers):
        self.headers = list(headers)
        self.deleted_rows = []
        self.batch_updates = []
        self.updated_rows = []

    def row_values(self, row_number):
        return list(self.headers)

    def delete_rows(self, row_number):
        self.deleted_rows.append(row_number)

    def batch_update(self, updates):
        self.batch_updates.extend(updates)

    def update(self, values, range_name):
        self.updated_rows.append((range_name, values))


class Runtime:
    is_configured = True
    can_publish = True

    def __init__(self):
        self.reset_calls = []
        self.deleted_images = []

    def get_submissions(self, event_id):
        return [{
            "EventID": event_id,
            "ImageURL": (
                f"supabase://exos-submissions/{event_id}/runtime-photo.jpg"
            ),
        }]

    def delete_submission_images(self, paths):
        self.deleted_images.extend(paths)

    def reset_event_data(self, event_id, reset_type):
        self.reset_calls.append((event_id, reset_type))
        return {"EventID": event_id, "ResetType": reset_type}


def make_database():
    db = GoogleSheetsDB.__new__(GoogleSheetsDB)
    db.runtime = Runtime()
    db.clear_cache = lambda: None
    db.get_event = lambda event_id: {
        "EventID": event_id,
        "Notes": json.dumps({
            "StageTimers": {"1": {"Status": "RUNNING"}},
            "ProjectorBroadcast": {"Mode": "Announcement"},
            "CurrentStageStatus": "RUNNING",
            "ProtectedNote": "keep",
        }),
    }
    sheets = {
        "Participants": Worksheet(
            ["EventID", "Name", "Team", "Points", "Status"],
        ),
        "Teams": Worksheet(
            ["EventID", "TeamID", "TeamName", "Score", "Status"],
        ),
        "Submissions": Worksheet(
            ["SubmissionID", "EventID", "ImageURL"],
        ),
        "Conversations": Worksheet(
            ["EventID", "Team", "Message"],
        ),
        "EventState": Worksheet(
            ["EventID", "CurrentStageNo", "State"],
        ),
        "Events": Worksheet(
            [
                "EventID",
                "EventName",
                "Notes",
                "NumberOfTeams",
                "NextTeamIndex",
            ],
        ),
    }
    db.participants = sheets["Participants"]
    db.teams = sheets["Teams"]
    db.submissions = sheets["Submissions"]
    db.conversations = sheets["Conversations"]
    db.event_state = sheets["EventState"]
    db.events = sheets["Events"]
    records = {
        "Participants": [
            {
                "EventID": "EVT-RESET",
                "Name": "Reset",
                "Points": 50,
                "Status": "Active",
            },
            {"EventID": "EVT-KEEP", "Name": "Keep", "Points": 80},
        ],
        "Teams": [
            {"EventID": "EVT-RESET", "TeamName": "Reset", "Score": 70},
            {"EventID": "EVT-KEEP", "TeamName": "Keep", "Score": 90},
        ],
        "Submissions": [
            {
                "EventID": "EVT-RESET",
                "ImageURL": (
                    "supabase://exos-submissions/EVT-RESET/sheet-photo.jpg"
                ),
            },
            {"EventID": "EVT-KEEP", "ImageURL": "keep.jpg"},
        ],
        "Conversations": [
            {"EventID": "EVT-RESET", "Message": "reset"},
            {"EventID": "EVT-KEEP", "Message": "keep"},
        ],
        "EventState": [
            {"EventID": "EVT-RESET", "State": "LIVE"},
            {"EventID": "EVT-KEEP", "State": "LIVE"},
        ],
        "Events": [{
            "EventID": "EVT-RESET",
            "EventName": "Reset Event",
            "Notes": json.dumps({
                "StageTimers": {"1": {"Status": "RUNNING"}},
                "ProjectorBroadcast": {"Mode": "Announcement"},
                "CurrentStageStatus": "RUNNING",
                "ProtectedNote": "keep",
            }),
            "NumberOfTeams": 2,
            "NextTeamIndex": 1,
        }],
    }
    return db, sheets, records


def test_reset_confirmation_requires_exact_event_phrase():
    assert reset_confirmation_matches("EVT-0004", "RESET EVT-0004")
    assert not reset_confirmation_matches("EVT-0004", "RESET")
    assert not reset_confirmation_matches("EVT-0004", "reset EVT-0004")


def test_reset_participants_only_removes_participants():
    db, sheets, records = make_database()
    with patch(
        "data.google_sheets.get_sheet_records",
        side_effect=lambda name: records[name],
    ):
        result = db.reset_event("EVT-RESET", "PARTICIPANTS")

    assert sheets["Participants"].deleted_rows == [2]
    for name in ("Teams", "Submissions", "Conversations", "EventState"):
        assert sheets[name].deleted_rows == []
    assert db.runtime.reset_calls == [("EVT-RESET", "PARTICIPANTS")]
    assert result["Preserved"] == [
        "Events",
        "ProgrammeStages",
        "Missions",
        "Assets",
    ]


def test_reset_runtime_preserves_participants_and_clears_live_data():
    db, sheets, records = make_database()
    with patch(
        "data.google_sheets.get_sheet_records",
        side_effect=lambda name: records[name],
    ):
        result = db.reset_event("EVT-RESET", "RUNTIME")

    assert sheets["Participants"].deleted_rows == []
    assert sheets["Teams"].deleted_rows == []
    assert sheets["Submissions"].deleted_rows == [2]
    assert sheets["EventState"].deleted_rows == [2]
    assert sheets["Participants"].batch_updates
    assert sheets["Teams"].batch_updates
    assert db.runtime.deleted_images == [
        "EVT-RESET/sheet-photo.jpg",
        "EVT-RESET/runtime-photo.jpg",
    ]
    assert result["SubmissionPhotosRemoved"] == 2


def test_factory_reset_keeps_event_programme_experiences_and_media():
    db, sheets, records = make_database()
    with patch(
        "data.google_sheets.get_sheet_records",
        side_effect=lambda name: records[name],
    ):
        result = db.reset_event("EVT-RESET", "FACTORY")

    for name in (
        "Participants",
        "Teams",
        "Submissions",
        "Conversations",
        "EventState",
    ):
        assert sheets[name].deleted_rows == [2]
    assert result["Preserved"] == [
        "Events",
        "ProgrammeStages",
        "Missions",
        "Assets",
    ]


def test_uat_reset_clears_progress_and_preserves_event_configuration():
    db, sheets, records = make_database()
    with patch(
        "data.google_sheets.get_sheet_records",
        side_effect=lambda name: records[name],
    ):
        result = db.reset_event("EVT-RESET", "UAT")

    for name in ("Participants", "Submissions", "Conversations", "EventState"):
        assert sheets[name].deleted_rows == [2]
    assert sheets["Teams"].deleted_rows == []
    assert sheets["Teams"].batch_updates
    assert db.runtime.reset_calls == [("EVT-RESET", "UAT")]
    assert result["Preserved"] == [
        "Events", "ProgrammeStages", "Missions", "Assets",
    ]
    updated_notes = json.loads(sheets["Events"].updated_rows[-1][1][0][2])
    assert "StageTimers" not in updated_notes
    assert "ProjectorBroadcast" not in updated_notes
    assert "CurrentStageStatus" not in updated_notes
    assert updated_notes["ProtectedNote"] == "keep"


def test_runtime_uat_reset_returns_to_welcome_without_deleting_content():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return []

    runtime._request = request
    runtime.reset_event_data("EVT-RESET", "UAT")

    deleted = {path for method, path, _ in calls if method == "DELETE"}
    assert "runtime_participants" in deleted
    assert "runtime_teams" in deleted
    assert "runtime_submissions" in deleted
    assert "runtime_team_wallets" in deleted
    assert "runtime_marketplace_purchases" in deleted
    assert "runtime_events" not in deleted
    assert "runtime_missions" not in deleted
    assert "runtime_marketplace_items" not in deleted
    event_patch = next(
        kwargs["payload"] for method, path, kwargs in calls
        if method == "PATCH" and path == "runtime_events"
    )
    assert event_patch["display_mode"] == "Welcome"
    assert event_patch["current_stage_no"] == 0
    assert event_patch["current_mission_id"] == ""


def test_runtime_factory_reset_never_deletes_event_or_experiences():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return []

    runtime._request = request
    runtime.reset_event_data("EVT-RESET", "FACTORY")

    deleted_tables = {
        path for method, path, _ in calls if method == "DELETE"
    }
    assert "runtime_participants" in deleted_tables
    assert "runtime_teams" in deleted_tables
    assert "runtime_events" not in deleted_tables
    assert "runtime_missions" not in deleted_tables
    assert "runtime_route_stops" not in deleted_tables
