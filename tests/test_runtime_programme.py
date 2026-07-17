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
            if path == "runtime_missions":
                return [{"mission_id": "M01"}]
            if path == "rpc/exos_ai_conversation":
                return [{
                    "EventID": "EVT-TEST",
                    "TeamName": "Team Alpha",
                    "MissionID": "M01",
                    "HintLevel": 1,
                    "Messages": [{
                        "Role": "Assistant",
                        "Message": "Start with what you can observe.",
                    }],
                }]
            if path == "rpc/exos_ai_add_message":
                return [{
                    "MessageID": "MSG-1",
                    "Role": "User",
                    "Message": payload["p_message"],
                    "HintLevel": payload["p_hint_level"],
                }]
            if path == "rpc/exos_ai_advance_hint":
                return [{
                    "Enabled": True,
                    "Level": 2,
                    "Label": "Stronger Hint",
                    "HintText": "Divide the evidence into categories.",
                    "Remaining": 1,
                }]
            if path == "rpc/exos_road_hunt_missions":
                return [{
                    "EventID": "EVT-TEST",
                    "TeamName": "Team Alpha",
                    "Enabled": True,
                    "TotalMissions": 2,
                    "UnlockedMissions": 1,
                    "SubmittedMissions": 0,
                    "AvailableMissions": [{
                        "StopID": "IPOH-01",
                        "MissionID": "M01",
                        "Mission": {"MissionID": "M01"},
                        "Submitted": False,
                    }],
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

    def test_ai_conversation_uses_participant_session_rpc(self):
        runtime = self.make_runtime()
        result = runtime.get_ai_conversation("token-123", "M01")

        self.assertEqual(result["HintLevel"], 1)
        self.assertEqual(result["Messages"][0]["Role"], "Assistant")
        call = runtime.calls[0]
        self.assertEqual(call["path"], "rpc/exos_ai_conversation")
        self.assertEqual(call["payload"]["p_session_token"], "token-123")
        self.assertFalse(call["admin"])

    def test_ai_message_write_uses_service_role_rpc(self):
        runtime = self.make_runtime()
        result = runtime.save_ai_message(
            "token-123",
            "M01",
            "Atlas",
            "User",
            "What should we inspect?",
            hint_level=1,
        )

        self.assertEqual(result["MessageID"], "MSG-1")
        call = runtime.calls[0]
        self.assertEqual(call["path"], "rpc/exos_ai_add_message")
        self.assertTrue(call["admin"])
        self.assertEqual(call["payload"]["p_role"], "user")
        self.assertEqual(call["payload"]["p_hint_level"], 1)

    def test_ai_hint_advance_uses_service_role_rpc(self):
        runtime = self.make_runtime()
        result = runtime.advance_ai_hint("token-123", "M01")

        self.assertEqual(result["Level"], 2)
        self.assertEqual(result["Remaining"], 1)
        call = runtime.calls[0]
        self.assertEqual(call["path"], "rpc/exos_ai_advance_hint")
        self.assertTrue(call["admin"])

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

    def test_has_event_mission_checks_runtime_payload(self):
        runtime = self.make_runtime()

        self.assertTrue(runtime.has_event_mission("EVT-TEST", "M01"))
        call = runtime.calls[0]
        self.assertEqual(call["path"], "runtime_missions")
        self.assertEqual(call["query"]["mission_id"], "eq.M01")
        self.assertTrue(call["admin"])

    def test_submission_image_uses_private_storage_endpoint(self):
        runtime = self.make_runtime()
        storage_calls = []

        def fake_storage_request(
            method,
            path,
            payload=None,
            binary_body=None,
            content_type="application/json",
            extra_headers=None,
            return_bytes=False,
            retries=4,
        ):
            storage_calls.append({
                "method": method,
                "path": path,
                "payload": payload,
                "binary_body": binary_body,
                "content_type": content_type,
                "return_bytes": return_bytes,
            })
            if return_bytes:
                return b"downloaded-image-bytes"
            if "/sign/" in path:
                return {"signedURL": "/object/sign/exos-submissions/test.jpg?token=x"}
            if method == "DELETE":
                return [{"name": "EVT/M01/Team/test.jpg"}]
            return {"Id": "storage-object-id"}

        runtime._storage_request = fake_storage_request
        uploaded = runtime.upload_submission_image(
            "EVT/M01/Team/test.jpg",
            b"image-bytes",
        )
        signed_url = runtime.create_submission_image_url(
            "EVT/M01/Team/test.jpg"
        )
        downloaded = runtime.download_submission_image(
            "EVT/M01/Team/test.jpg"
        )
        deleted = runtime.delete_submission_images([
            "EVT/M01/Team/test.jpg"
        ])

        self.assertEqual(uploaded["Bucket"], "exos-submissions")
        self.assertEqual(
            storage_calls[0]["path"],
            "object/exos-submissions/EVT/M01/Team/test.jpg",
        )
        self.assertEqual(storage_calls[0]["binary_body"], b"image-bytes")
        self.assertEqual(
            signed_url,
            "https://example.supabase.co/storage/v1/object/sign/"
            "exos-submissions/test.jpg?token=x",
        )
        self.assertEqual(downloaded, b"downloaded-image-bytes")
        self.assertEqual(deleted[0]["name"], "EVT/M01/Team/test.jpg")
        self.assertEqual(
            storage_calls[2]["path"],
            "object/authenticated/exos-submissions/EVT/M01/Team/test.jpg",
        )
        self.assertEqual(
            storage_calls[3]["payload"],
            {"prefixes": ["EVT/M01/Team/test.jpg"]},
        )

    def test_mission_media_uses_private_storage_and_signed_url(self):
        runtime = self.make_runtime()
        storage_calls = []

        def fake_storage_request(
            method,
            path,
            payload=None,
            binary_body=None,
            content_type="application/json",
            extra_headers=None,
            return_bytes=False,
            retries=4,
        ):
            storage_calls.append({
                "method": method,
                "path": path,
                "payload": payload,
                "binary_body": binary_body,
                "content_type": content_type,
            })
            if "/sign/" in path:
                return {
                    "signedURL": (
                        "/object/sign/exos-mission-media/templates/"
                        "MT-01/video.mp4?token=x"
                    )
                }
            return {"Id": "mission-media-id"}

        runtime._storage_request = fake_storage_request
        uploaded = runtime.upload_mission_media(
            "templates/MT-01/video.mp4",
            b"video-bytes",
            "video/mp4",
        )
        signed_url = runtime.create_mission_media_url(
            "templates/MT-01/video.mp4"
        )

        self.assertEqual(uploaded["Bucket"], "exos-mission-media")
        self.assertEqual(
            storage_calls[0]["path"],
            "object/exos-mission-media/templates/MT-01/video.mp4",
        )
        self.assertEqual(storage_calls[0]["binary_body"], b"video-bytes")
        self.assertIn("token=x", signed_url)

    def test_credit_wallet_and_marketplace_use_expected_rpcs(self):
        runtime = self.make_runtime()
        runtime.configure_credit_wallet("EVT-TEST", enabled=True)
        runtime.publish_marketplace(
            "EVT-TEST",
            [{
                "ItemID": "UPGRADE-01",
                "ItemName": "Wheel Upgrade",
                "CreditCost": 100,
                "StockQuantity": 10,
                "Active": True,
            }],
        )
        runtime.purchase_marketplace_item(
            "session-token",
            "UPGRADE-01",
            2,
        )

        self.assertEqual(
            runtime.calls[0]["path"],
            "rpc/exos_configure_credit_wallet",
        )
        self.assertTrue(runtime.calls[0]["admin"])
        self.assertEqual(
            runtime.calls[1]["payload"]["p_items"][0]["credit_cost"],
            100.0,
        )
        self.assertEqual(
            runtime.calls[2]["path"],
            "rpc/exos_purchase_marketplace_item",
        )
        self.assertFalse(runtime.calls[2]["admin"])

    def test_road_hunt_route_and_location_use_expected_rpcs(self):
        runtime = self.make_runtime()
        runtime.configure_road_hunt(
            "EVT-TEST",
            enabled=True,
            location_interval_seconds=15,
        )
        runtime.publish_road_hunt_route(
            "EVT-TEST",
            [{
                "StopID": "ipoh-01",
                "StopName": "Mirror Lake",
                "Latitude": 4.5593,
                "Longitude": 101.1197,
                "RadiusMeters": 120,
                "MissionIDs": "IPOH-01, IPOH-02",
            }],
        )
        runtime.get_road_hunt_participant_state("session-token")
        runtime.claim_team_tracker("session-token")
        runtime.submit_team_location(
            "session-token",
            4.5593,
            101.1197,
            accuracy_meters=8.5,
            captured_at="2026-07-17T02:00:00Z",
        )
        runtime.get_road_hunt_status("EVT-TEST")

        self.assertEqual(
            runtime.calls[0]["path"],
            "rpc/exos_configure_road_hunt",
        )
        self.assertTrue(runtime.calls[0]["admin"])
        route_call = runtime.calls[1]
        self.assertEqual(route_call["path"], "rpc/exos_publish_route")
        self.assertEqual(
            route_call["payload"]["p_stops"][0]["mission_ids"],
            ["IPOH-01", "IPOH-02"],
        )
        self.assertTrue(route_call["admin"])
        self.assertFalse(runtime.calls[2]["admin"])
        self.assertFalse(runtime.calls[3]["admin"])
        self.assertFalse(runtime.calls[4]["admin"])
        self.assertEqual(
            runtime.calls[4]["payload"]["p_accuracy_meters"],
            8.5,
        )
        self.assertTrue(runtime.calls[5]["admin"])

    def test_road_hunt_team_missions_use_participant_session(self):
        runtime = self.make_runtime()

        result = runtime.get_road_hunt_unlocked_missions("session-token")

        self.assertTrue(result["Enabled"])
        self.assertEqual(result["UnlockedMissions"], 1)
        self.assertEqual(
            result["AvailableMissions"][0]["MissionID"],
            "M01",
        )
        call = runtime.calls[0]
        self.assertEqual(call["path"], "rpc/exos_road_hunt_missions")
        self.assertEqual(
            call["payload"]["p_session_token"],
            "session-token",
        )
        self.assertFalse(call["admin"])

    def test_individual_submission_uses_session_identity_rpc(self):
        runtime = self.make_runtime()
        runtime.save_submission({
            "SubmissionID": "SUB-1",
            "EventID": "EVT-TEST",
            "MissionID": "M01",
            "TeamName": "Team Alpha",
            "ParticipantName": "Adrian Choong",
            "SessionToken": "session-token-1",
            "SubmissionType": "NASI",
        })

        call = runtime.calls[0]
        self.assertEqual(call["path"], "rpc/exos_save_submission_v2")
        self.assertEqual(
            call["payload"]["p_session_token"],
            "session-token-1",
        )

    def test_individual_submission_lookup_uses_session_identity(self):
        runtime = self.make_runtime()
        runtime.get_submission(
            "EVT-TEST",
            "M01",
            "PARTICIPANT",
            "Adrian Choong",
            session_token="session-token-1",
        )

        call = runtime.calls[0]
        self.assertEqual(call["path"], "rpc/exos_get_submission_v2")
        self.assertEqual(
            call["payload"]["p_session_token"],
            "session-token-1",
        )

    def test_submission_load_test_checks_concurrency_photos_and_cleanup(self):
        runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
        runtime.url = "https://example.supabase.co"
        runtime.anon_key = "publishable-key"
        runtime.service_key = "secret-key"
        saved = []
        uploaded = {}
        deleted = []
        cleanup_calls = []
        teams = [f"Team {number}" for number in range(1, 7)]

        def fake_request(
            method,
            path,
            payload=None,
            query=None,
            admin=False,
            retries=4,
        ):
            if method == "GET" and path == "runtime_events":
                return [{"event_id": "EVT-TEST", "next_team_index": 2}]
            cleanup_calls.append((method, path, payload, query, admin))
            return []

        def fake_join(join_code, name):
            number = int(name.split("-")[-1].split()[0])
            return {
                "Name": name,
                "Team": teams[(number - 1) % len(teams)],
                "SessionToken": f"token-{number}",
            }

        def fake_save(record):
            saved.append(dict(record))
            return dict(record)

        runtime._request = fake_request
        runtime.join_player = fake_join
        runtime.save_submission = fake_save
        runtime.upload_submission_image = (
            lambda path, image_bytes, content_type="image/jpeg": uploaded.__setitem__(
                path,
                image_bytes,
            )
        )
        runtime.download_submission_image = lambda path: uploaded[path]
        runtime.delete_submission_images = lambda paths: deleted.extend(paths)
        runtime.get_submissions = lambda event_id: [
            {"MissionID": record["MissionID"]}
            for record in saved
        ]

        result = runtime.run_submission_load_test(
            "EVT-TEST",
            "TEST01",
            total_participants=12,
            max_workers=6,
        )

        self.assertTrue(result["Passed"])
        self.assertTrue(result["CleanupPassed"])
        self.assertEqual(result["IndividualSubmissions"], 12)
        self.assertEqual(result["TeamPhotoSubmissions"], 6)
        self.assertEqual(len(uploaded), 6)
        self.assertEqual(sorted(uploaded.keys()), sorted(deleted))
        self.assertIn(
            ("PATCH", "runtime_events"),
            [(method, path) for method, path, _, _, _ in cleanup_calls],
        )

    def test_dual_event_load_test_keeps_runs_separate(self):
        runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
        calls = []

        def fake_submission_test(
            event_id,
            join_code,
            total_participants=100,
            max_workers=40,
        ):
            calls.append((event_id, join_code, total_participants))
            return {
                "RunID": f"RUN-{event_id}",
                "Requested": total_participants,
                "Joined": total_participants,
                "IndividualSubmissions": total_participants,
                "TeamPhotoSubmissions": 6,
                "Failed": 0,
                "Passed": True,
                "CleanupPassed": True,
                "Errors": [],
            }

        runtime.run_submission_load_test = fake_submission_test
        result = runtime.run_dual_event_load_test(
            [
                {
                    "EventID": "EVT-A",
                    "EventName": "Test A",
                    "JoinCode": "TESTA",
                },
                {
                    "EventID": "EVT-B",
                    "EventName": "Test B",
                    "JoinCode": "TESTB",
                },
            ],
            total_participants_each=50,
        )

        self.assertTrue(result["Passed"])
        self.assertTrue(result["IsolatedRuns"])
        self.assertEqual(result["RequestedTotal"], 100)
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            {event_id for event_id, _, _ in calls},
            {"EVT-A", "EVT-B"},
        )


if __name__ == "__main__":
    unittest.main()
