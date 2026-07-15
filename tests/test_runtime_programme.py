import unittest

from data.runtime_database import SupabaseRuntimeDB


class RuntimeProgrammeTests(unittest.TestCase):
    def make_runtime(self):
        runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
        runtime.url = "https://example.supabase.co"
        runtime.anon_key = "publishable-key"
        runtime.service_key = "secret-key"
        runtime.calls = []

        def fake_request(method, path, payload=None, query=None, admin=False, retries=4):
            runtime.calls.append({
                "method": method,
                "path": path,
                "payload": payload,
                "query": query,
                "admin": admin,
            })
            if path == "rpc/exos_participant_current_mission":
                return [{
                    "Mission": {"MissionID": "M01"},
                    "StateVersion": 4,
                }]
            if path == "runtime_events":
                return [{
                    "event_id": "EVT-TEST",
                    "current_stage_no": 4,
                    "stage_state": "MissionActive",
                    "stage_name": "Mission One",
                    "current_mission_id": "M01",
                    "display_mode": "Current Mission",
                    "state_version": 7,
                    "state_updated_at": "2026-07-15T01:00:00Z",
                }]
            return [{"MissionsPublished": 1}]

        runtime._request = fake_request
        return runtime

    def test_publish_programme_uses_admin_rpc(self):
        runtime = self.make_runtime()
        result = runtime.publish_programme(
            "EVT-TEST",
            [{"MissionID": "M01", "Title": "Mission One"}],
        )

        self.assertEqual(result["MissionsPublished"], 1)
        call = runtime.calls[0]
        self.assertEqual(call["path"], "rpc/exos_publish_programme")
        self.assertTrue(call["admin"])
        self.assertEqual(
            call["payload"]["p_missions"][0]["mission_id"],
            "M01",
        )

    def test_participant_current_mission_uses_public_rpc(self):
        runtime = self.make_runtime()
        result = runtime.get_participant_current_mission("token-123")

        self.assertEqual(result["Mission"]["MissionID"], "M01")
        call = runtime.calls[0]
        self.assertEqual(
            call["path"],
            "rpc/exos_participant_current_mission",
        )
        self.assertFalse(call["admin"])

    def test_get_event_stage_reads_authoritative_runtime_state(self):
        runtime = self.make_runtime()
        result = runtime.get_event_stage("EVT-TEST")

        self.assertEqual(result["CurrentStageNo"], 4)
        self.assertEqual(result["MissionID"], "M01")
        self.assertEqual(result["StateVersion"], 7)
        call = runtime.calls[0]
        self.assertEqual(call["path"], "runtime_events")
        self.assertEqual(call["query"]["event_id"], "eq.EVT-TEST")
        self.assertTrue(call["admin"])


if __name__ == "__main__":
    unittest.main()
