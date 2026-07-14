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


if __name__ == "__main__":
    unittest.main()
