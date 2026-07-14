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
                "admin": admin,
            })
            if path == "rpc/exos_participant_current_mission":
                return [{
                    "Mission": {"MissionID": "M01"},
                    "StateVersion": 4,
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


if __name__ == "__main__":
    unittest.main()
