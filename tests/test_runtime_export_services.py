from data.runtime_database import SupabaseRuntimeDB


class TestRuntimeExportServices:
    def test_export_event_csv_bundle_includes_minimum_surfaces(self):
        runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)

        def fake_request(method, path, payload=None, query=None, admin=False, retries=4):
            self = runtime
            self.calls.append((path, query))
            if path == "runtime_participants":
                return [{"ParticipantID": "P-1", "TeamID": "T-1", "EventID": "EVT-TEST"}]
            if path == "runtime_teams":
                return [{"TeamID": "T-1", "TeamName": "Team One", "EventID": "EVT-TEST"}]
            if path == "runtime_submissions":
                return [
                    {"SubmissionID": "S-1", "EventID": "EVT-TEST", "SubmissionType": "GPS", "Metric1": "1.1", "Metric2": "2.2", "Metric3": "3.3", "TeamID": "T-1", "ActivityID": "A1", "CanonicalContext": {"accuracy_meters": 1.4, "timestamp": "2026-01-01T00:00:00Z", "radius_meters": 50, "distance_meters": 12.3}},
                    {"SubmissionID": "S-2", "EventID": "EVT-TEST", "SubmissionType": "NASI", "Metric1": "", "Metric2": "", "Metric3": "", "TeamID": "T-1", "ActivityID": "A2", "Remarks": "New ideas"},
                ]
            if path == "runtime_credit_transactions":
                return []
            if path == "runtime_marketplace_items":
                return [{"ItemID": "I-1", "EventID": "EVT-TEST", "ItemName": "Shield"}]
            if path == "runtime_marketplace_purchases":
                return []
            if path == "judge_scores":
                return []
            if path == "formula_race_judging":
                return []
            if path == "formula_race_results":
                return []
            raise AssertionError(f"unexpected runtime read: {path}")

        runtime.calls = []
        runtime._request = fake_request
        runtime.get_programme_hierarchy = lambda event_id: [
            {
                "ProgrammeID": "EVT-TEST-PROG",
                "ProgrammeName": "Demo",
                "ModuleID": "M-1",
                "ModuleName": "Mission",
                "Activities": [{
                    "ActivityID": "A1",
                    "ActivityName": "Track",
                    "Title": "Track",
                    "ActivityType": "STANDARD",
                    "ScoringMode": "TEAM_COMPETITIVE",
                    "DisplayOrder": 1,
                    "Duration": 300,
                }],
            },
        ]

        export = runtime.export_event_csv_bundle("EVT-TEST")

        expected_keys = {
            "participants.csv", "teams.csv", "programme.csv", "submissions.csv",
            "nasi.csv", "scores.csv", "credits.csv", "marketplace_items.csv",
            "marketplace.csv", "judging.csv", "race_results.csv", "gps_evidence.csv",
        }
        assert set(export) == expected_keys
        for key, payload in export.items():
            assert isinstance(payload, (bytes, bytearray))
            assert payload.startswith(b"SubmissionID") or b"," in payload

        gps_payload = export["gps_evidence.csv"].decode("utf-8")
        assert "S-1" in gps_payload
        assert "1.1" in gps_payload
