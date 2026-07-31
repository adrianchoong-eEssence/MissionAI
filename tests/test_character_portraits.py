import unittest
from unittest.mock import patch

from data.google_sheets import GoogleSheetsDB, REQUIRED_WORKSHEETS
from data.mission_media import upload_character_portrait


class UploadedPortrait:
    name = "eva.png"
    type = "image/png"

    @staticmethod
    def getvalue():
        return b"eva-portrait-bytes"


class CharacterPortraitTests(unittest.TestCase):
    def test_character_fields_are_persisted_without_renaming_backend_records(self):
        self.assertIn("CharacterSource", REQUIRED_WORKSHEETS["Missions"])
        self.assertIn("CharacterPortraitURL", REQUIRED_WORKSHEETS["Missions"])
        self.assertIn("CharacterSource", REQUIRED_WORKSHEETS["MissionTemplates"])
        self.assertIn("CharacterPortraitURL", REQUIRED_WORKSHEETS["MissionTemplates"])
        self.assertIn("MissionID", REQUIRED_WORKSHEETS["Missions"])

    def test_eva_upload_reuses_one_deterministic_storage_object(self):
        class Runtime:
            def __init__(self):
                self.paths = []

            def upload_mission_media(
                self,
                storage_path,
                media_bytes,
                content_type,
            ):
                self.paths.append(storage_path)

        runtime = Runtime()
        with patch(
            "data.mission_media.get_runtime_database",
            return_value=runtime,
        ):
            first = upload_character_portrait(UploadedPortrait(), "EVA")
            second = upload_character_portrait(UploadedPortrait(), "EVA")

        self.assertEqual(first, second)
        self.assertEqual(
            first,
            "supabase://exos-mission-media/characters/eva/portrait",
        )
        self.assertEqual(
            runtime.paths,
            ["characters/eva/portrait", "characters/eva/portrait"],
        )

    def test_existing_eva_portrait_is_reused_across_experiences(self):
        db = GoogleSheetsDB.__new__(GoogleSheetsDB)
        records = {
            "Missions": [
                {
                    "EventID": "EVT-0004",
                    "MissionID": "M01",
                    "CharacterSource": "EVA",
                    "CharacterPortraitURL": (
                        "supabase://exos-mission-media/"
                        "characters/eva/portrait"
                    ),
                },
                {
                    "EventID": "EVT-0004",
                    "MissionID": "M02",
                    "CharacterSource": "None",
                    "CharacterPortraitURL": "",
                },
            ],
            "MissionTemplates": [],
        }
        with patch(
            "data.google_sheets.get_sheet_records",
            side_effect=lambda name: records[name],
        ):
            portrait = db.get_character_portrait("EVA")
            missing = db.get_character_portrait("Commander Orion")

        self.assertEqual(
            portrait,
            "supabase://exos-mission-media/characters/eva/portrait",
        )
        self.assertEqual(missing, "")

    def test_participant_runtime_mission_gets_latest_character_reference(self):
        class Runtime:
            is_configured = True

            @staticmethod
            def get_participant_current_mission(session_token):
                return {
                    "Mission": {
                        "MissionID": "M01",
                        "Title": "Experience 1",
                    },
                    "Stage": {},
                    "StateVersion": 1,
                }

        db = GoogleSheetsDB.__new__(GoogleSheetsDB)
        db.runtime = Runtime()
        db.get_mission = lambda event_id, mission_id: {
            "CharacterSource": "EVA",
            "CharacterPortraitURL": (
                "supabase://exos-mission-media/characters/eva/portrait"
            ),
        }

        mission = db.get_current_mission("EVT-0004", session_token="session")

        self.assertEqual(mission["CharacterSource"], "EVA")
        self.assertEqual(
            mission["CharacterPortraitURL"],
            "supabase://exos-mission-media/characters/eva/portrait",
        )


if __name__ == "__main__":
    unittest.main()
