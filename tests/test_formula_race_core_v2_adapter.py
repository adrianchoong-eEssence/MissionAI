from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
import os
from contextlib import contextmanager


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
                "session_token": "TOKEN-ONE",
                "last_seen_at": "2026-08-10T00:00:00Z",
                "updated_at": "2026-08-10T00:00:00Z",
            }
        ]
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)

    workspace = adapter.formula_race_captain_workspace("TOKEN-ONE", "DEVICE-ONE")
    build_status = workspace.get("BuildStatus", {})
    assert build_status.get("status") == "NOT_STARTED"
    assert build_status.get("Status") == "NOT_STARTED"
    assert int(build_status.get("Progress", 0)) == 0


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
