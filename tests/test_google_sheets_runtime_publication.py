import unittest

from data.google_sheets import GoogleSheetsDB, RuntimeDatabaseError


class FakeRuntime:
    def __init__(self, join_code_map=None, runtime_events=None):
        self.join_code_map = dict(join_code_map or {})
        self.runtime_events = dict(runtime_events or {})
        self.is_configured = True
        self.can_publish = True
        self.publish_calls = []
        self.programme_calls = []

    def publish_event(self, event, teams, reset_registration=False):
        self.publish_calls.append({
            "event": dict(event),
            "team_count": len(teams),
            "reset": bool(reset_registration),
        })
        return {
            "JoinCode": str(event.get("JoinCode", "")).strip().upper(),
            "TeamsPublished": len(teams),
        }

    def publish_programme(self, event_id, missions):
        self.programme_calls.append({
            "event_id": str(event_id).strip(),
            "mission_count": len(missions),
        })
        return {"MissionsPublished": len(missions)}

    def set_event_stage(self, event_id, stage):
        return {"StageSet": str(event_id).strip()}

    def get_event_by_join_code(self, join_code):
        return self.join_code_map.get(str(join_code).strip().upper())

    def get_runtime_event(self, event_id):
        return self.runtime_events.get(str(event_id).strip())


class GoogleSheetsPublishRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.event = {
            "EventID": "EVT-0016",
            "EventName": "AIA",
            "JoinCode": "A4FQYV",
        }
        self.teams = [{"TeamID": "TEAM-01", "TeamName": "Team 1"}]
        self.event_missions = [{"MissionID": "M1"}]
        self.event_state = {
            "CurrentStageNo": 0,
            "State": "",
            "StageName": "",
            "MissionID": "",
            "DisplayMode": "Hybrid",
        }

    def make_database(self, runtime):
        database = GoogleSheetsDB.__new__(GoogleSheetsDB)
        database.runtime = runtime
        database.get_event = lambda event_id: self.event if event_id == "EVT-0016" else None
        database.get_teams = lambda event_id: list(self.teams)
        database.get_event_missions = lambda event_id: list(self.event_missions)
        database.get_event_state = lambda event_id: dict(self.event_state)
        database.get_programme_stages = (
            lambda event_id: [{"StageNo": 1, "StageType": "Registration"}]
        )
        return database

    def test_publish_event_to_runtime_verifies_join_code_resolution(self):
        runtime = FakeRuntime(
            join_code_map={"A4FQYV": {
                "EventID": "EVT-0016",
                "JoinCode": "A4FQYV",
            }},
            runtime_events={"EVT-0016": {"EventID": "EVT-0016", "JoinCode": "A4FQYV"}},
        )
        database = self.make_database(runtime)

        result = database.publish_event_to_runtime("EVT-0016", reset_registration=True)

        self.assertEqual(runtime.publish_calls[0]["event"]["EventID"], "EVT-0016")
        self.assertTrue(result["RuntimePublished"])
        self.assertTrue(result["RuntimeVerified"])
        self.assertEqual(result["VerifiedEventID"], "EVT-0016")
        self.assertEqual(result["VerifiedJoinCode"], "A4FQYV")

    def test_publish_event_to_runtime_fails_without_join_code_mapping(self):
        runtime = FakeRuntime(
            join_code_map={},
            runtime_events={},
        )
        database = self.make_database(runtime)

        with self.assertRaises(RuntimeDatabaseError):
            database.publish_event_to_runtime("EVT-0016")

    def test_publish_event_to_runtime_recovers_after_retry(self):
        runtime = FakeRuntime(
            join_code_map={},
            runtime_events={},
        )
        database = self.make_database(runtime)

        with self.assertRaises(RuntimeDatabaseError):
            database.publish_event_to_runtime("EVT-0016")

        runtime.join_code_map["A4FQYV"] = {
            "EventID": "EVT-0016",
            "JoinCode": "A4FQYV",
        }
        runtime.runtime_events["EVT-0016"] = {
            "EventID": "EVT-0016",
            "JoinCode": "A4FQYV",
        }
        result = database.publish_event_to_runtime("EVT-0016")

        self.assertTrue(result["RuntimeVerified"])
        self.assertEqual(result["VerifiedJoinCode"], "A4FQYV")

    def test_publish_event_id_isolation_by_event_id(self):
        runtime = FakeRuntime(
            join_code_map={"A4FQYV": {
                "EventID": "EVT-9999",
                "JoinCode": "A4FQYV",
            }},
            runtime_events={"EVT-0016": {"EventID": "EVT-0016", "JoinCode": "ABC123"}},
        )
        database = self.make_database(runtime)

        with self.assertRaises(RuntimeDatabaseError):
            database.publish_event_to_runtime("EVT-0016")

    def test_join_code_duplicate_lookup_prefers_runtime(self):
        runtime = FakeRuntime(
            join_code_map={"A4FQYV": {
                "EventID": "EVT-0016",
                "JoinCode": "A4FQYV",
            }},
            runtime_events={"EVT-0016": {"EventID": "EVT-0016", "JoinCode": "A4FQYV"}},
        )
        database = self.make_database(runtime)
        database.get_events = lambda: [{"EventID": "EVT-9999", "JoinCode": "A4FQYV"}]

        result = database.get_event_by_join_code("A4FQYV")

        self.assertEqual(result["EventID"], "EVT-0016")
