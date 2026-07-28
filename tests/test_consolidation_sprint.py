import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from data.google_sheets import GoogleSheetsDB
from engines.stage_timer import (
    new_timer,
    remaining_seconds,
    transition_timer,
)
from screens.control_centre import stage_family
from screens.programme_builder import _save_event_module


class PersistentTimerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)

    def test_start_pause_resume_reset_and_end(self):
        timer = new_timer(600)
        running = transition_timer(timer, "START", now=self.now)
        self.assertEqual(running["Status"], "RUNNING")
        self.assertEqual(
            remaining_seconds(
                running,
                now=self.now + timedelta(seconds=75),
            ),
            525,
        )
        paused = transition_timer(
            running,
            "PAUSE",
            now=self.now + timedelta(seconds=75),
        )
        self.assertEqual(paused["RemainingSeconds"], 525)
        resumed = transition_timer(
            paused,
            "RESUME",
            now=self.now + timedelta(seconds=100),
        )
        self.assertEqual(
            remaining_seconds(
                resumed,
                now=self.now + timedelta(seconds=125),
            ),
            500,
        )
        reset = transition_timer(resumed, "RESET", 600, self.now)
        self.assertEqual(reset["RemainingSeconds"], 600)
        ended = transition_timer(reset, "END", now=self.now)
        self.assertEqual(ended["RemainingSeconds"], 0)
        self.assertEqual(ended["Status"], "ENDED")


class EventSafetyTests(unittest.TestCase):
    def test_archived_events_are_hidden_and_recoverable(self):
        db = GoogleSheetsDB.__new__(GoogleSheetsDB)
        rows = [
            {"EventID": "E1", "Status": "Draft"},
            {"EventID": "E2", "Status": "Archived"},
        ]
        with patch("data.google_sheets.get_sheet_records", return_value=rows):
            self.assertEqual([row["EventID"] for row in db.get_events()], ["E1"])
            self.assertEqual(len(db.get_events(include_archived=True)), 2)

    def test_event_metadata_preserves_existing_values(self):
        value = GoogleSheetsDB.event_metadata({
            "Notes": json.dumps({
                "LegacyValue": "keep",
                "ExpectedParticipants": 80,
            }),
        })
        self.assertEqual(value["LegacyValue"], "keep")
        self.assertEqual(value["ExpectedParticipants"], 80)


class ModuleIsolationTests(unittest.TestCase):
    class FakeDB:
        def __init__(self):
            self.master = {
                "TemplateID": "T1",
                "Title": "Master Name",
            }
            self.saved = None
            self.stages = [{
                "StageNo": 1,
                "StageName": "Master Name",
                "MissionID": "M1",
                "DurationMinutes": 30,
            }]

        def upsert_event_mission(self, record):
            self.saved = dict(record)

        def get_programme_stages(self, event_id):
            return self.stages

        def save_programme_stages(self, event_id, stages):
            self.stages = stages

    def test_event_copy_edit_does_not_change_master(self):
        db = self.FakeDB()
        event_copy = {
            "EventID": "E1",
            "MissionID": "M1",
            "TemplateID": "T1",
            "Title": "Master Name",
        }
        _save_event_module(
            db,
            "E1",
            event_copy,
            {
                "name": "Event-Specific Name",
                "participant_instructions": "Participant copy",
                "facilitator_instructions": "Facilitator copy",
                "rules": "Event rules",
                "answers": "Evaluation",
                "scoring": "Manual",
                "maximum_score": 100,
                "credit_value": 25,
                "mandatory": "Mandatory",
                "ai_required": False,
                "ai_prompt": "",
                "evidence_type": "TEXT",
                "evidence_required": True,
                "variants": "",
                "debrief": "Discuss",
                "image_url": "",
                "document_url": "",
                "qr_value": "",
                "checkpoint_name": "",
                "checkpoint_location": "",
                "latitude": 0,
                "longitude": 0,
                "geofence_radius": 0,
                "active": True,
                "time_limit": 45,
            },
            db.stages[0],
        )
        self.assertEqual(db.saved["Title"], "Event-Specific Name")
        self.assertEqual(db.master["Title"], "Master Name")
        self.assertEqual(db.stages[0]["DurationMinutes"], 45)

    def test_two_event_copies_can_diverge(self):
        master = {"TemplateID": "T1", "Title": "Master"}
        event_one = dict(master, EventID="E1", MissionID="M1", Points=10)
        event_two = dict(master, EventID="E2", MissionID="M1", Points=50)
        self.assertNotEqual(event_one["Points"], event_two["Points"])
        self.assertNotIn("EventID", master)


class StageWidgetTests(unittest.TestCase):
    def test_stage_families(self):
        self.assertEqual(
            stage_family({"StageType": "Registration"}),
            "registration",
        )
        self.assertEqual(
            stage_family({"StageName": "Mission AI"}),
            "mission",
        )
        self.assertEqual(
            stage_family({"StageName": "Closing"}),
            "closing",
        )


if __name__ == "__main__":
    unittest.main()
