from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _staging_env():
    original = os.getenv("EXOS_ENV")
    os.environ["EXOS_ENV"] = "staging"
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("EXOS_ENV", None)
        else:
            os.environ["EXOS_ENV"] = original


def _fake_runtime_factory(team_active: bool = True):
    class FakeRuntime:
        is_configured = True
        can_publish = True
        url = "https://staging.exos-core-v2.example.com"

        def __init__(self):
            self.rows = {
                "events_v2": [
                    {
                        "event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
                        "event_name": "L'OREAL FORMULA R.A.C.E. DEMO",
                        "join_code": "RACE4CF0CE",
                        "lifecycle_status": "READY",
                    },
                ],
                "teams_v2": [
                    {
                        "team_id": f"CORE-V2-RACE-UAT-T{index:02d}-4CF0CEAF5F",
                        "team_name": f"Team {index:02d}",
                        "country": f"Country {index:02d}",
                        "team_flag": f"FLAG-{index:02d}",
                        "is_active": bool(team_active),
                        "event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
                    }
                    for index in range(1, 11)
                ],
            }

        def _request(self, method, path, payload=None, query=None, admin=True):
            if method != "GET":
                raise RuntimeError("Unexpected non-GET call")
            table = path.replace("rpc/", "")
            candidates = self.rows.get(table, [])
            if table == "teams_v2":
                value = (query or {}).get("event_id", "").replace("eq.", "")
                active = (query or {}).get("is_active")
                candidates = [row for row in candidates if str(row.get("event_id", "")).strip() == value]
                if active == "eq.true":
                    candidates = [row for row in candidates if row.get("is_active") is True]
            if table == "events_v2":
                if "event_id" in (query or {}):
                    value = (query or {}).get("event_id", "").replace("eq.", "")
                    if value:
                        candidates = [row for row in candidates if str(row.get("event_id", "")).strip() == value]
                if "join_code" in (query or {}):
                    value = (query or {}).get("join_code", "").replace("eq.", "").strip().upper()
                    candidates = [row for row in candidates if str(row.get("join_code", "")).strip().upper() == value]
            select = (query or {}).get("select") if query else None
            if select == "1":
                candidates = candidates[:1]
            elif select == "eq.event_name":
                candidates = []
            return candidates

    return FakeRuntime()


def test_race_adapter_resolves_join_code_and_returns_ten_teams():
    with _staging_env():
        runtime = _fake_runtime_factory()
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)

    event = adapter.get_runtime_event("RACE4CF0CE")
    assert event["EventID"] == "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"
    assert event["JoinCode"] == "RACE4CF0CE"

    teams = adapter.get_runtime_teams("CORE-V2-RACE-UAT-EVT-4CF0CEAF5F")
    assert len(teams) == 10


def test_race_adapter_get_runtime_teams_falls_back_when_inactive_rows_exist():
    with _staging_env():
        runtime = _fake_runtime_factory(team_active=False)
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)

    teams = adapter.get_runtime_teams("RACE4CF0CE")
    assert len(teams) == 10
    assert {team["TeamName"] for team in teams} == {f"Team {idx:02d}" for idx in range(1, 11)}


def test_race_adapter_debug_get_runtime_teams_tracks_expected_filter():
    with _staging_env():
        runtime = _fake_runtime_factory()
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)

    result = adapter.debug_get_runtime_teams("RACE4CF0CE")
    assert result["event_found"] is True
    assert result["resolved_event_id"] == "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"
    assert result["query"]["event_id"] == "eq.CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"
    assert len(result["rows"]) == 10


def test_configuration_preparation_preview_reads_only_preserved_and_transactional_surfaces():
    with _staging_env():
        runtime = _fake_runtime_factory()
        runtime.rows.update(
            {
                "team_access_credentials_v2": [{"team_access_credential_id": f"PIN-{index}"} for index in range(10)],
                "submissions_v2": [{"event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"}],
                "marketplace_transactions_v2": [{"event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"}],
                "credit_transactions_v2": [{"event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"}],
                "build_status_v2": [{"event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"}],
                "judging_scores_v2": [{"event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"}],
                "race_results_v2": [{"event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"}],
            }
        )
        preview = FormulaRaceCoreV2StagingAdapter(runtime).get_formula_race_configuration_preparation_preview(
            "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"
        )

    assert preview["EventID"] == "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"
    assert preview["JoinCode"] == "RACE4CF0CE"
    assert preview["ActiveTeamCount"] == 10
    assert preview["CaptainPinCredentialCount"] == 10
    assert preview["CanonicalSubmissionCount"] == 1
    assert preview["RaceResultCount"] == 1


def test_race_adapter_exposes_submission_evidence_storage_reference():
    with _staging_env():
        runtime = _fake_runtime_factory()
        runtime.rows["submissions_v2"] = [{
            "submission_id": "SUBMISSION-1", "event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
            "team_id": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "activity_id": "CHECKPOINT-1",
            "submission_status": "SUBMITTED", "submission_payload": {
                "storage_reference": "supabase://exos-submissions/EVENT/TEAM/CHECKPOINT/photo.jpg"
            },
        }]
        runtime.rows["submission_evidence_v2"] = [{
            "submission_id": "SUBMISSION-1", "evidence_type": "PHOTO",
            "evidence_uri": "supabase://exos-submissions/EVENT/TEAM/CHECKPOINT/photo.jpg",
        }]
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)

    submission = adapter.get_canonical_submissions("CORE-V2-RACE-UAT-EVT-4CF0CEAF5F")[0]
    assert submission["StorageReference"] == "supabase://exos-submissions/EVENT/TEAM/CHECKPOINT/photo.jpg"
    assert submission["EvidenceType"] == "PHOTO"
    assert submission["EvidenceURI"] == submission["StorageReference"]


def test_race_result_save_uses_the_audited_pre_lock_correction_rpc():
    class Runtime:
        is_configured = True
        can_publish = True
        url = "https://staging.exos-core-v2.example.com"

        def __init__(self):
            self.calls = []

        def _request(self, method, path, payload=None, query=None, admin=True):
            self.calls.append((method, path, payload, admin))
            return {"RaceResultID": "RESULT-1", "Corrected": True}

    runtime = Runtime()
    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)
        adapter._get_checkpoint_activities = lambda _event_id: [{"activity_id": "CHECKPOINT-1"}]
        result = adapter.save_formula_race_result("EVENT-1", "TEAM-1", 10000, 1000, 0, True, "UAT correction", "Adrian")

    assert result["Corrected"] is True
    assert runtime.calls == [("POST", "rpc/exos_v2_formula_race_save_result", {
        "p_event_id": "EVENT-1", "p_team_id": "TEAM-1", "p_activity_id": "CHECKPOINT-1",
        "p_time_ms": 10000, "p_penalty_ms": 1000, "p_bonus": 0.0,
        "p_verified": True, "p_reason": "UAT correction", "p_actor": "Adrian",
    }, True)]


def test_captain_workspace_batches_runtime_and_reuses_marketplace_projection():
    source = Path("data/formula_race_core_v2_adapter.py").read_text()
    workspace = source.split("def formula_race_captain_workspace", 1)[1].split("def formula_race_captain_logout", 1)[0]
    assert workspace.count("self._marketplace_payload(event_id, team_id)") == 1
    assert '"activity_id": _in_filter(activity_ids)' in workspace
    assert '"Submissions": [' in workspace
    assert '"ImageReference": station["ImageReference"]' in source
    assert "get_formula_race_station_reference_image_url" not in workspace


def test_adapter_performance_report_has_safe_endpoint_timings_only():
    runtime = _fake_runtime_factory()
    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)
        adapter.get_runtime_event("RACE4CF0CE")
    report = adapter.get_performance_report()
    assert any(row["Operation"].startswith("GET events_v2") for row in report["Operations"])
    assert all(set(row) == {"Operation", "DurationMs", "BackendCallCount"} for row in report["Operations"])
    assert "payload" not in str(report).lower()


def test_race_review_and_gallery_share_the_private_evidence_resolver():
    source = Path("screens/formula_race.py").read_text()
    assert "def _resolve_race_private_evidence(runtime, storage_reference: str)" in source
    assert "reviews(snapshot,control,runtime)" in source
    assert "gallery(snapshot,runtime)" in source


def test_race_marketplace_uses_active_items_and_completed_purchase_stock():
    with _staging_env():
        runtime = _fake_runtime_factory()
        runtime.rows["marketplace_items_v2"] = [{
            "item_id": "ITEM-1", "event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
            "item_name": "Carbon Fibre Kit", "unit_cost_credits": 20,
            "stock_limit": 40, "is_active": True,
        }]
        runtime.rows["marketplace_transactions_v2"] = [{
            "marketplace_transaction_id": "PURCHASE-1", "event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
            "team_id": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "item_id": "ITEM-1",
            "quantity": 2, "amount_paid": 40, "status": "COMPLETED",
        }]
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)

    marketplace = adapter._marketplace_payload("CORE-V2-RACE-UAT-EVT-4CF0CEAF5F", "CORE-V2-RACE-UAT-T01-4CF0CEAF5F")
    assert marketplace["items"] == [{"ItemID": "ITEM-1", "ItemName": "Carbon Fibre Kit", "CreditCost": 20, "StockQuantity": 38, "Active": True}]
    assert marketplace["purchases"][0]["Amount"] == 40


def test_race_marketplace_control_uses_existing_item_activation_flag():
    source = Path("screens/formula_race.py").read_text()
    adapter = Path("data/formula_race_core_v2_adapter.py").read_text()
    assert "OPEN MARKETPLACE" in source
    assert "set_race_marketplace_runtime" in source
    assert "set_formula_race_marketplace_runtime" in adapter
    assert '"is_active": active' in adapter


def test_race_marketplace_open_verifies_persisted_active_rows():
    class Runtime:
        is_configured = True
        can_publish = True
        url = "https://staging.exos-core-v2.example.com"

        def __init__(self):
            self.items = [{"item_id": "ITEM-1", "event_id": "EVENT-1", "is_active": False}]

        def _request(self, method, path, payload=None, query=None, admin=True):
            if path != "marketplace_items_v2":
                return []
            if method == "GET":
                return list(self.items)
            if method == "PATCH":
                for item in self.items:
                    item.update(payload or {})
                return []
            raise RuntimeError("Unexpected request")

    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(Runtime())
        result = adapter.set_formula_race_marketplace_runtime("EVENT-1", "OPEN", "Facilitator")

    assert result["active_item_count"] == 1
    assert result["active"] is True


def test_race_manual_credit_adjustment_calls_the_race_ledger_rpc_once():
    class Runtime:
        is_configured = True
        can_publish = True
        url = "https://staging.exos-core-v2.example.com"

        def __init__(self):
            self.calls = []

        def _request(self, method, path, payload=None, query=None, admin=True):
            self.calls.append((method, path, payload, admin))
            return {"CreditTransactionID": "TX-1", "Duplicate": False, "Amount": 50}

    runtime = Runtime()
    with _staging_env():
        result = FormulaRaceCoreV2StagingAdapter(runtime).formula_race_manual_credit_adjustment(
            "EVENT-1", "TEAM-1", 50, "Facilitator correction", "Ari", "adjustment-1"
        )

    assert result["Amount"] == 50
    assert runtime.calls == [("POST", "rpc/exos_v2_formula_race_manual_credit_adjustment", {
        "p_event_id": "EVENT-1", "p_team_id": "TEAM-1", "p_amount": 50,
        "p_reason": "Facilitator correction", "p_actor": "Ari", "p_idempotency_key": "adjustment-1",
    }, True)]


def test_race_adapter_captain_workspace_returns_default_build_status_when_empty():
    with _staging_env():
        runtime = _fake_runtime_factory()
        runtime.rows["team_access_sessions_v2"] = [
            {
                "team_access_session_id": "SESSION-ONE",
                "event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
                "team_id": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F",
                "is_active": True,
                "device_id": "DEVICE-ONE",
                "session_token": "123e4567-e89b-12d3-a456-426614174000",
                "last_seen_at": "2026-08-10T00:00:00Z",
                "updated_at": "2026-08-10T00:00:00Z",
            }
        ]
        runtime.rows["credit_transactions_v2"] = [
            {"event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F", "team_id": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "amount": 52},
            {"event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F", "team_id": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "amount": 18},
            {"event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F", "team_id": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "amount": -20},
        ]
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)

    workspace = adapter.formula_race_captain_workspace(
        "123e4567-e89b-12d3-a456-426614174000", "DEVICE-ONE"
    )
    build_status = workspace.get("BuildStatus", {})
    assert build_status.get("status") == "NOT_STARTED"
    assert build_status.get("Status") == "NOT_STARTED"
    assert int(build_status.get("Progress", 0)) == 0
    assert workspace["Wallet"] == {"CreditsEarned": 70, "CreditsSpent": 20, "Balance": 50}


def test_race_build_status_preserves_the_race_phase_inside_core_v2_state():
    with _staging_env():
        runtime = _fake_runtime_factory()
        runtime.rows["build_status_v2"] = [{
            "event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
            "team_id": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F",
            "activity_id": "CHECKPOINT-1",
            "build_status": "IN_PROGRESS",
            "progress_pct": 60,
            "build_payload": {"race_build_status": "Painting"},
            "last_updated": "2026-08-13T00:00:00Z",
        }]
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)

    payload = adapter._build_status_payload("CORE-V2-RACE-UAT-EVT-4CF0CEAF5F", "CORE-V2-RACE-UAT-T01-4CF0CEAF5F")
    assert payload["status"] == "Painting"
    assert payload["Progress"] == 60
    assert adapter.get_formula_race_state("CORE-V2-RACE-UAT-EVT-4CF0CEAF5F")["BuildStatus"][0]["status"] == "Painting"


def test_formula_race_captain_login_returns_normalized_valid_token():
    class FakeRuntime:
        is_configured = True
        can_publish = True
        url = "https://staging.exos-core-v2.example.com"

        def __init__(self):
            self.payload = None

        def _request(self, method, path, payload=None, query=None, admin=True):
            self.payload = payload
            return {
                "Ambiguous": False,
                "EventID": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
                "RecoveryRequired": False,
                "SessionToken": "0e7f8f56-9f16-4dbf-a8bb-2d2f1f5d7f3c",
                "TeamID": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F",
            }

    runtime = FakeRuntime()
    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)
        payload = adapter.formula_race_captain_login("RACE4CF0CE", "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "PIN-01", "DEVICE-01")

    assert adapter.last_login_rpc_response is not None
    assert "SessionToken" in adapter.last_login_rpc_response
    assert payload["SessionToken"] == "0e7f8f56-9f16-4dbf-a8bb-2d2f1f5d7f3c"
    assert payload["EventID"] == "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"
    assert payload["TeamID"] == "CORE-V2-RACE-UAT-T01-4CF0CEAF5F"


def test_formula_race_captain_login_rejects_missing_session_token():
    class FakeRuntime:
        is_configured = True
        can_publish = True
        url = "https://staging.exos-core-v2.example.com"

        def _request(self, method, path, payload=None, query=None, admin=True):
            return {
                "Ambiguous": False,
                "EventID": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
                "RecoveryRequired": False,
                "SessionToken": None,
                "TeamID": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F",
            }

    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(FakeRuntime())
        try:
            adapter.formula_race_captain_login("RACE4CF0CE", "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "PIN-01", "DEVICE-01")
            assert False, "Expected missing token to raise"
        except Exception:
            pass


def test_formula_race_captain_workspace_rejects_invalid_session_token_before_runtime_call():
    class FakeRuntime:
        is_configured = True
        can_publish = True
        url = "https://staging.exos-core-v2.example.com"

        def __init__(self):
            self.calls = 0

        def _request(self, method, path, payload=None, query=None, admin=True):
            self.calls += 1
            return []

    runtime = FakeRuntime()
    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)
    try:
        adapter.formula_race_captain_workspace("None", "DEVICE-ONE")
        assert False
    except Exception:
        pass
    assert runtime.calls == 0


def test_formula_race_restore_captain_session_rejects_invalid_token_without_rpc():
    class FakeRuntime:
        is_configured = True
        can_publish = True
        url = "https://staging.exos-core-v2.example.com"
        def __init__(self):
            self.calls = 0
        def _request(self, method, path, payload=None, query=None, admin=True):
            self.calls += 1
            return {}

    runtime = FakeRuntime()
    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)
    for token in ("None", "null", "", "not-a-uuid", "123"):
        try:
            adapter.restore_formula_race_captain(token, "DEVICE-ONE")
            assert False
        except Exception:
            pass
    assert runtime.calls == 0
