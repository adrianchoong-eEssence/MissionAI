import unittest

from scripts.exos_core_v2_staging_journey import CoreV2JourneyRunner


class StagingJourneyCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CoreV2JourneyRunner()

    def test_empty_id_list_skips_cleanup_step_without_request(self):
        counts_called = []
        delete_called = []

        self.runner._count = lambda table, query: counts_called.append((table, query)) or 0
        self.runner._rest_request_with_status = lambda *args, **kwargs: (
            delete_called.append((args, kwargs)),
            (500, {"error": {"body": "should not happen"}}),
        )[1]

        result, failed = self.runner._delete_step("ai_results_v2", None, "ai_results_v2")

        self.assertFalse(failed)
        self.assertEqual(counts_called, [])
        self.assertEqual(delete_called, [])
        self.assertEqual(result["filter"], "SKIPPED — NO IDS")
        self.assertEqual(result["delete_result"], "SKIPPED — NO IDS")

    def test_ids_filter_generates_in_list_for_non_empty_uuid_collection(self):
        result = self.runner._ids_filter(["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"], "submission_id")

        self.assertEqual(
            result,
            {
                "submission_id": 'in.("11111111-1111-1111-1111-111111111111","22222222-2222-2222-2222-222222222222")'
            },
        )

    def test_cleanup_filters_do_not_use_fake_uuid_sentinels(self):
        plucks = {
            "programmes_v2": [],
            "participants_v2": [],
            "participant_sessions_v2": [],
            "submissions_v2": [],
            "ai_jobs_v2": [],
        }
        counts = []
        delete_steps = []

        self.runner._pluck = lambda table, column, query: plucks.get(table, [])
        self.runner._rest_request_with_status = lambda method, path, payload=None, query=None, admin=True: (
            delete_steps.append((method, path, query)),
            (200, []),
        )[1]
        self.runner._count = lambda table, query: (
            self.assertNotIn("eq.none", [str(v) for v in query.values()]),
            counts.append((table, query)),
            0,
        )[2]

        self.runner.verify_cleanup = lambda: {"events_v2_event": 0}

        # run cleanup and verify every cleanup step is reached even when optional collections are empty
        self.runner.cleanup()

        called_labels = [step["label"] for step in self.runner._cleanup_steps]
        self.assertIn("ai_results_v2", called_labels)
        self.assertIn("submissions_v2", called_labels)
        self.assertIn("programmes_v2", called_labels)
        # Ensure at least the expected ai_results step was skipped with no request
        skipped = [step for step in self.runner._cleanup_steps if step["label"] == "ai_results_v2"]
        self.assertTrue(skipped and skipped[0]["filter"] == "SKIPPED — NO IDS")
        # Ensure skipped step does not issue a delete request
        ai_step_requests = [call for call in delete_steps if call[0] == "DELETE" and call[1] == "ai_results_v2"]
        self.assertEqual(ai_step_requests, [])
        # Ensure no fake uuid sentinels were produced in mocked count paths
        self.assertTrue(all(query.get(column) != "eq.none" for table, query in counts for column in query if isinstance(query, dict)))


if __name__ == "__main__":
    unittest.main()
