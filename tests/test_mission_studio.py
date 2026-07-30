import unittest
from unittest.mock import patch

from data.google_sheets import GoogleSheetsDB, REQUIRED_WORKSHEETS


class FakeWorksheet:
    def __init__(self, headers):
        self.headers = list(headers)
        self.appended = []
        self.updated = []
        self.batch_updated = []

    def row_values(self, row_number):
        return self.headers if row_number == 1 else []

    def append_row(self, values, **kwargs):
        self.appended.append(values)

    def append_rows(self, values, **kwargs):
        self.appended.extend(values)

    def update(self, **kwargs):
        self.updated.append(kwargs)

    def batch_update(self, payloads, **kwargs):
        self.batch_updated.extend(payloads)

    def delete_rows(self, row_number):
        self.updated.append({"deleted_row": row_number})


class FakeRuntime:
    def __init__(self, configured=False, publish_ready=False):
        self.is_configured = configured
        self.can_publish = publish_ready
        self.published_missions = []
        self.current_state = None

    def publish_programme(self, event_id, missions):
        self.published_missions = list(missions)
        return {"MissionsPublished": len(self.published_missions)}

    def get_participant_current_mission(self, session_token):
        return self.current_state


class MissionStudioDataTests(unittest.TestCase):
    def make_db(self):
        database = GoogleSheetsDB.__new__(GoogleSheetsDB)
        database.mission_templates = FakeWorksheet(
            REQUIRED_WORKSHEETS["MissionTemplates"]
        )
        database.missions = FakeWorksheet(REQUIRED_WORKSHEETS["Missions"])
        database.runtime = FakeRuntime()
        database.clear_cache = lambda: None
        return database

    def test_create_template_generates_id_and_preserves_media(self):
        database = self.make_db()
        with patch("data.google_sheets.get_sheet_records", return_value=[]):
            result = database.upsert_mission_template({
                "Title": "Signal Hunt",
                "ParticipantInstructions": "Find the signal.",
                "SubmissionType": "PHOTO",
                "VideoURL": "https://example.com/video",
            })

        self.assertEqual(result["Action"], "Created")
        self.assertEqual(result["TemplateID"], "MT-0001")
        headers = REQUIRED_WORKSHEETS["MissionTemplates"]
        row = dict(zip(headers, database.mission_templates.appended[0]))
        self.assertEqual(row["Title"], "Signal Hunt")
        self.assertEqual(row["VideoURL"], "https://example.com/video")

    def test_bulk_import_updates_and_creates_in_batches(self):
        database = self.make_db()
        existing = [{
            "TemplateID": "MT-0001",
            "Title": "Old Title",
            "Status": "ACTIVE",
            "Version": "1.0",
        }]
        records = [
            {
                "TemplateID": "MT-0001",
                "Title": "Updated Title",
                "ParticipantInstructions": "Updated instructions",
            },
            {
                "MissionID": "MT-0002",
                "MissionTitle": "Imported Mission",
                "Description": "Imported instructions",
            },
        ]

        with patch("data.google_sheets.get_sheet_records", return_value=existing):
            result = database.import_mission_templates(records)

        self.assertEqual(result["Updated"], 1)
        self.assertEqual(result["Created"], 1)
        self.assertEqual(result["Errors"], [])
        self.assertEqual(len(database.mission_templates.batch_updated), 1)
        self.assertEqual(len(database.mission_templates.appended), 1)

    def test_add_template_to_event_maps_instructions_and_media(self):
        database = self.make_db()
        template = {
            "TemplateID": "MT-0003",
            "Title": "Video Mission",
            "ParticipantInstructions": "Watch, then act.",
            "VideoURL": "https://example.com/mission-video",
            "Status": "ACTIVE",
        }
        captured = {}
        database.get_mission_template = lambda template_id: template

        def fake_upsert(record):
            captured.update(record)
            return {"MissionID": record["MissionID"], "Action": "Created"}

        database.upsert_event_mission = fake_upsert
        result = database.add_template_to_event(
            "MT-0003",
            "EVT-TEST",
            "M03",
        )

        self.assertEqual(result["MissionID"], "M03")
        self.assertEqual(captured["Description"], "Watch, then act.")
        self.assertEqual(captured["VideoURL"], "https://example.com/mission-video")
        self.assertEqual(captured["Status"], "DRAFT")

    def test_build_event_programme_creates_ordered_missions_and_stages(self):
        database = self.make_db()
        database.get_event = lambda event_id: {"EventID": event_id}
        database.get_mission_templates = lambda: [
            {
                "TemplateID": "MT-ONE",
                "Title": "First Mission",
                "ParticipantInstructions": "Do the first mission.",
                "FacilitatorInstructions": "Brief mission one.",
                "DebriefQuestions": "What happened?",
            },
            {
                "TemplateID": "MT-TWO",
                "Title": "Second Mission",
                "ParticipantInstructions": "Do the second mission.",
                "FacilitatorInstructions": "Brief mission two.",
            },
        ]
        captured_stages = []
        database.save_programme_stages = (
            lambda event_id, stages: captured_stages.extend(stages)
        )
        database.set_event_stage = lambda event_id, stage: True

        plan = [
            {
                "TemplateID": "MT-ONE",
                "MissionID": "M01",
                "DurationMinutes": 30,
                "IncludeDebrief": True,
            },
            {
                "TemplateID": "MT-TWO",
                "MissionID": "M02",
                "DurationMinutes": 45,
                "IncludeDebrief": False,
            },
        ]

        with patch("data.google_sheets.get_sheet_records", return_value=[]):
            result = database.build_event_programme(
                "EVT-TEST",
                plan,
                start_time="09:00",
                registration_minutes=15,
                team_discovery_minutes=15,
                debrief_minutes=10,
            )

        self.assertEqual(result["Missions"], 2)
        self.assertEqual(result["Stages"], 6)
        self.assertEqual(result["ProgrammeEndTime"], "11:05")
        self.assertEqual(captured_stages[0]["StageName"], "Registration")
        self.assertEqual(captured_stages[2]["MissionID"], "M01")
        self.assertEqual(captured_stages[3]["StageType"], "Debrief")
        self.assertEqual(captured_stages[4]["MissionID"], "M02")

    def test_build_event_programme_can_add_marketplace_stage(self):
        database = self.make_db()
        database.get_event = lambda event_id: {"EventID": event_id}
        database.get_mission_templates = lambda: [{
            "TemplateID": "MT-ONE",
            "Title": "Credit Mission",
            "ParticipantInstructions": "Earn credits.",
        }]
        captured_stages = []
        database.save_programme_stages = (
            lambda event_id, stages: captured_stages.extend(stages)
        )
        database.set_event_stage = lambda event_id, stage: True

        with patch("data.google_sheets.get_sheet_records", return_value=[]):
            result = database.build_event_programme(
                "EVT-TEST",
                [{
                    "TemplateID": "MT-ONE",
                    "MissionID": "M01",
                    "DurationMinutes": 20,
                    "IncludeDebrief": False,
                }],
                include_registration=False,
                include_team_discovery=False,
                include_marketplace=True,
                marketplace_minutes=30,
                include_closing=False,
            )

        self.assertEqual(result["Stages"], 2)
        self.assertEqual(captured_stages[1]["StageType"], "Marketplace")
        self.assertEqual(
            captured_stages[1]["DisplayMode"],
            "Credit Leaderboard",
        )

    def test_current_mission_uses_runtime_state_for_participant(self):
        database = self.make_db()
        database.runtime = FakeRuntime(configured=True)
        database.runtime.current_state = {
            "StateVersion": 9,
            "Stage": {
                "StageName": "Signal Hunt",
                "ParticipantMessage": "Find the signal.",
            },
            "Mission": {
                "EventID": "EVT-TEST",
                "MissionID": "M09",
                "Title": "Signal Hunt",
                "SubmissionType": "TEXT",
            },
        }

        mission = database.get_current_mission(
            "EVT-TEST",
            session_token="session-token",
        )

        self.assertEqual(mission["MissionID"], "M09")
        self.assertEqual(mission["_RuntimeStateVersion"], 9)
        self.assertEqual(
            mission["_RuntimeStage"]["ParticipantMessage"],
            "Find the signal.",
        )

    def test_event_mission_edit_persists_without_changing_master(self):
        database = self.make_db()
        master = {"TemplateID": "MT-ONE", "Title": "Master", "Clue": "Master clue"}
        event = {
            "EventID": "EVT-0004", "MissionID": "M01", "Title": "Event copy",
            "TemplateID": "MT-ONE", "Clue": "Old event clue",
        }
        with patch("data.google_sheets.get_sheet_records", return_value=[event]):
            database.upsert_event_mission({**event, "Clue": "Edited event clue"})
        headers = REQUIRED_WORKSHEETS["Missions"]
        saved = dict(zip(headers, database.missions.updated[0]["values"][0]))
        self.assertEqual(saved["Clue"], "Edited event clue")
        self.assertEqual(master["Clue"], "Master clue")

    def test_two_events_can_have_different_m01_versions(self):
        database = self.make_db()
        rows = [
            {"EventID": "EVT-A", "MissionID": "M01", "Title": "A", "Version": "A"},
            {"EventID": "EVT-B", "MissionID": "M01", "Title": "B", "Version": "B"},
        ]
        with patch("data.google_sheets.get_sheet_records", return_value=rows):
            self.assertEqual(database.get_event_missions("EVT-A")[0]["Version"], "A")
            self.assertEqual(database.get_event_missions("EVT-B")[0]["Version"], "B")

    def test_mission_order_is_event_specific(self):
        database = self.make_db()
        rows = [
            {"EventID": "EVT-A", "MissionID": "M01"},
            {"EventID": "EVT-A", "MissionID": "M02"},
            {"EventID": "EVT-B", "MissionID": "M01"},
        ]
        with patch("data.google_sheets.get_sheet_records", return_value=rows):
            result = database.reorder_event_missions("EVT-A", ["M02", "M01"])
        self.assertEqual(result["Updated"], 2)
        self.assertEqual(len(database.missions.batch_updated), 2)

    def test_duplication_creates_event_copy_only(self):
        database = self.make_db()
        source = {
            "EventID": "EVT-0004", "MissionID": "M01", "Title": "Signal",
            "TemplateID": "MT-SIGNAL", "Clue": "Find it",
        }
        database.get_mission = lambda event_id, mission_id: dict(source)
        database.get_event_missions = lambda event_id: [source]
        captured = {}
        database.upsert_event_mission = lambda record: (
            captured.update(record) or {"MissionID": record["MissionID"], "Action": "Created"}
        )
        result = database.duplicate_event_mission("EVT-0004", "M01", "M05")
        self.assertEqual(result["MissionID"], "M05")
        self.assertEqual(captured["EventID"], "EVT-0004")
        self.assertEqual(captured["TemplateID"], "MT-SIGNAL")
        self.assertEqual(source["MissionID"], "M01")

    def test_evt0004_backfill_preserves_existing_content(self):
        database = self.make_db()
        source = {
            "EventID": "EVT-0004", "MissionID": "M01",
            "Title": "Existing title", "Clue": "Existing clue",
            "ParticipantInstructions": "Existing question", "Points": 75,
            "SubmissionType": "TEXT",
        }
        database.get_event_missions = lambda event_id: [dict(source)]
        captured = []
        database.upsert_event_mission = lambda record: (
            captured.append(dict(record))
            or {"MissionID": record["MissionID"], "Action": "Updated"}
        )
        result = database.backfill_event_mission_editor_fields(
            "EVT-0004", ["M01", "M02", "M03", "M04"],
        )
        self.assertEqual(result["Updated"], ["M01"])
        self.assertEqual(captured[0]["Clue"], "Existing clue")
        self.assertEqual(captured[0]["MainQuestion"], "Existing question")
        self.assertEqual(captured[0]["CreditValue"], 75)


if __name__ == "__main__":
    unittest.main()
