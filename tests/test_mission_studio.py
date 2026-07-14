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


class MissionStudioDataTests(unittest.TestCase):
    def make_db(self):
        database = GoogleSheetsDB.__new__(GoogleSheetsDB)
        database.mission_templates = FakeWorksheet(
            REQUIRED_WORKSHEETS["MissionTemplates"]
        )
        database.missions = FakeWorksheet(REQUIRED_WORKSHEETS["Missions"])
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


if __name__ == "__main__":
    unittest.main()
