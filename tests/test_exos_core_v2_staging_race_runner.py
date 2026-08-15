import ast
import importlib.util
from typing import Any
from pathlib import Path
import textwrap


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "exos_core_v2_staging_race_vertical_slice.py"

spec = importlib.util.spec_from_file_location("exos_core_v2_staging_race_vertical_slice", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)  # type: ignore[arg-type]
CoreV2RaceStagingRunner = module.CoreV2RaceStagingRunner
find_stale_activity_event_refs = module.find_stale_activity_event_refs


def test_captain_reconnect_contract_with_no_session_token_in_restore_shape() -> None:
    runner = CoreV2RaceStagingRunner()
    runner._team_access_diagnostics.update(
        {
            "event_id": "CORE-V2-RACE-UAT-EVT-54B12826FF",
            "team_id": "CORE-V2-RACE-UAT-T01-54B12826FF",
            "device_id": "CORE-V2-RACE-DEVICE-54B12826FF",
        }
    )

    login = {
        "EventID": "CORE-V2-RACE-UAT-EVT-54B12826FF",
        "TeamID": "CORE-V2-RACE-UAT-T01-54B12826FF",
    }
    restore = {
        "EventID": "CORE-V2-RACE-UAT-EVT-54B12826FF",
        "TeamID": "CORE-V2-RACE-UAT-T01-54B12826FF",
        "Ambiguous": False,
        "RecoveryRequired": False,
    }
    session_row = {
        "event_id": "CORE-V2-RACE-UAT-EVT-54B12826FF",
        "team_id": "CORE-V2-RACE-UAT-T01-54B12826FF",
        "device_id": "CORE-V2-RACE-DEVICE-54B12826FF",
        "is_active": True,
    }

    assert "SessionToken" not in restore
    assert runner._is_reconnect_contract_ok(login, restore, session_row) is True


def test_race_cleanup_does_not_filter_reviews_by_team_id() -> None:
    source = (ROOT / "scripts" / "exos_core_v2_staging_race_vertical_slice.py").read_text()
    ast_tree = ast.parse(source)

    cleanup_calls = [
        call
        for call in ast.walk(ast_tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "_delete"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == "reviews_v2"
    ]

    assert cleanup_calls, "Expected reviews_v2 cleanup call"

    for call in cleanup_calls:
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Dict):
            keys = {
                key.value
                for key in call.args[1].keys
                if isinstance(key, ast.Constant)
            }
            assert "submission_id" in keys
            assert "team_id" not in keys


def test_submit_and_review_uses_single_review_upsert() -> None:
    source = (ROOT / "scripts" / "exos_core_v2_staging_race_vertical_slice.py").read_text()
    ast_tree = ast.parse(source)

    submit = next(
        node
        for node in ast.walk(ast_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "submit_and_review"
    )

    submit_calls = [node for node in ast.walk(submit) if isinstance(node, ast.Call)]
    has_review_upsert = False
    has_direct_reviews_insert = False

    for call in submit_calls:
        if isinstance(call.func, ast.Attribute) and call.func.attr == "_ensure_single_review":
            has_review_upsert = True
        if isinstance(call.func, ast.Attribute) and call.func.attr == "_post":
            if (
                len(call.args) >= 1
                and isinstance(call.args[0], ast.Constant)
                and call.args[0].value == "reviews_v2"
            ):
                has_direct_reviews_insert = True

    assert has_review_upsert is True
    assert has_direct_reviews_insert is False


def test_review_upsert_is_idempotent_in_submit_and_review_path() -> None:
    runner = CoreV2RaceStagingRunner()
    runner.checkpoint_rows = [{"activity_id": "CORE-V2-RACE-CP-01"}]
    runner.captain_participant = {"team_id": "CORE-V2-RACE-T01"}

    calls: list[tuple[str, str, dict[str, Any]]] = []

    def fake_get(table: str, query: dict):
        if table == "activities_v2":
            return [{"activity_id": "CORE-V2-RACE-CP-01"}]
        if table == "reviews_v2":
            calls.append((table, "GET", dict(query)))
            return [{"review_id": "REV-1"}]
        if table == "credit_transactions_v2":
            calls.append((table, "GET", dict(query)))
            return []
        return []

    def fake_post(table: str, payload: dict) -> list[dict]:
        calls.append((table, "POST", dict(payload)))
        if table == "submissions_v2":
            return [{"submission_id": "SUB-1"}]
        if table == "reviews_v2":
            return [{"review_id": "REV-1"}]
        return []

    def fake_patch(table: str, query: dict, payload: dict) -> list[dict]:
        calls.append((table, "PATCH", dict(payload)))
        return [{"review_id": "REV-1"}]

    def fake_rpc(name: str, payload: dict, admin: bool = True) -> str:
        calls.append((name, "RPC", dict(payload)))
        return "txn-1"

    runner._get = fake_get  # type: ignore[method-assign]
    runner._post = fake_post  # type: ignore[method-assign]
    runner._patch = fake_patch  # type: ignore[method-assign]
    runner._rpc = fake_rpc  # type: ignore[method-assign]

    runner.submit_and_review()

    review_post_calls = [call for call in calls if call[:2] == ("reviews_v2", "POST")]
    review_patch_calls = [call for call in calls if call[:2] == ("reviews_v2", "PATCH")]
    score_calls = [call for call in calls if call[0] == "exos_v2_ledger_score"]

    assert len(review_post_calls) == 0
    assert len(review_patch_calls) == 1
    assert len(score_calls) == 1


def test_stale_activity_event_detector_ignores_detector_source() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    findings = find_stale_activity_event_refs(source)
    assert findings == []


def test_stale_activity_event_detector_ignores_comments_and_strings() -> None:
    source = textwrap.dedent(
        """
        class Demo:
            def check(self):
                # activities_v2.event_id should not trigger stale detector
                msg = "activities_v2.event_id"
                print("STALE_ACTIVITY_EVENT_PATHS:")
                return msg
        """
    ).strip()
    findings = find_stale_activity_event_refs(source)
    assert findings == []


def test_stale_activity_event_detector_detects_invalid_query() -> None:
    source = textwrap.dedent(
        """
        class Demo:
            def run(self):
                rows = self._get(
                    \"activities_v2\",
                    {
                        \"event_id\": \"eq.abc-123\",
                        \"select\": \"activity_id\"
                    },
                )
        """
    ).strip()
    findings = find_stale_activity_event_refs(source)
    assert len(findings) == 1
    assert findings[0].startswith("line ")


def test_stale_activity_event_detector_allows_canonical_hierarchy_query() -> None:
    source = textwrap.dedent(
        """
        class Demo:
            def run(self):
                rows = self._get(
                    \"activities_v2\",
                    {
                        \"module_id\": \"eq.mod-001\",
                        \"select\": \"activity_id\",
                    },
                )
        """
    ).strip()
    findings = find_stale_activity_event_refs(source)
    assert findings == []


def test_stale_activity_event_detector_detects_no_false_positive_from_rest_like_query() -> None:
    source = textwrap.dedent(
        """
        class Demo:
            def run(self):
                rows = self._request(
                    \"GET\",
                    \"activities_v2\",
                    query={\"event_id\": \"eq.abc\"},
                )
        """
    ).strip()
    findings = find_stale_activity_event_refs(source)
    assert len(findings) == 1


def test_expected_lock_rejection_message_is_recognized() -> None:
    runner = CoreV2RaceStagingRunner()
    err = RuntimeError('HTTP 400 PATCH race_results_v2: {"code":"P0001","message":"Race result is locked and immutable until explicit unlock."}')
    assert runner._is_expected_lock_rejection(err, "race result is locked and immutable until explicit unlock") is True


def test_non_lock_error_is_not_treated_as_expected() -> None:
    runner = CoreV2RaceStagingRunner()
    err = RuntimeError('HTTP 400 PATCH race_results_v2: {"code":"23505","message":"duplicate key value violates unique constraint"}')
    assert runner._is_expected_lock_rejection(err, "race result is locked and immutable until explicit unlock") is False


def test_runner_legacy_guard_still_blocks_pre_core_v2_result_rpc() -> None:
    runner = CoreV2RaceStagingRunner()
    assert runner._is_legacy_runtime_rpc("exos_save_formula_race_result") is True


def test_final_lock_certification_uses_only_the_disposable_event_and_lock_rpcs() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    certification = source.split("def _certify_final_lock_results", 1)[1].split("def ui_verification", 1)[0]
    assert "self._save_final_result(" in certification
    assert "self._lock_final_results(" in certification
    save_result = source.split("def _save_final_result", 1)[1].split("def _lock_final_results", 1)[0]
    lock_result = source.split("def _lock_final_results", 1)[1].split("def _expect_incomplete_lock_rejection", 1)[0]
    assert "_canonical_race_control_adapter().save_formula_race_result(" in save_result
    assert "_canonical_race_control_adapter().lock_formula_race_results(" in lock_result
    assert "missing_result_rejected" in certification
    assert "unverified_result_rejected" in certification
    assert "idempotent_relock" in certification
    assert "self.event_id" in certification


def test_premium_ui_is_deferred_and_not_an_engine_gate() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'self.ui_checks = {"runtime_snapshot": False}' in source
    assert "RACE premium UI: DEFERRED (UI/UX overhaul; not an engine gate)" in source
    gates = source.split("self.gates = {", 1)[1].split("}\n        self.ui_checks", 1)[0]
    assert '"race_premium_ui"' not in gates


def test_final_lock_certification_exercises_missing_unverified_tie_and_relock_gates() -> None:
    runner = CoreV2RaceStagingRunner()
    runner.team_ids = [f"TEAM-{idx:02d}" for idx in range(1, 11)]
    runner.activity_ids = ["ACTIVITY-1"]
    rows: dict[str, dict[str, object]] = {}

    def fake_rpc(name: str, payload: dict, admin: bool = True):
        if name == "exos_v2_formula_race_save_result":
            team_id = str(payload["p_team_id"])
            row = rows.get(team_id)
            if row and row["locked"]:
                raise RuntimeError('HTTP 400 POST rpc: {"code":"P0001","message":"Race result is locked and immutable until explicit unlock."}')
            rows[team_id] = {
                "team_id": team_id,
                "ranking_position": row.get("ranking_position") if row else None,
                "locked": False,
                "result_payload": {
                    "time_ms": payload["p_time_ms"],
                    "penalty_ms": payload["p_penalty_ms"],
                    "bonus": payload["p_bonus"],
                    "verified": payload["p_verified"],
                },
            }
            return {"RaceResultID": f"RESULT-{team_id}"}
        if name == "exos_v2_formula_race_lock_final_results":
            verified = [row for row in rows.values() if row["result_payload"]["verified"]]
            if len(verified) != 10:
                raise RuntimeError("Every active team requires one verified Race Final result before locking")
            if all(row["locked"] for row in verified):
                return {"Locked": True, "AlreadyLocked": True}
            if any(row["locked"] for row in verified):
                raise RuntimeError("Race Final has a partial lock state and requires controlled reconciliation")
            for position, row in enumerate(
                sorted(verified, key=lambda row: (row["result_payload"]["time_ms"] + row["result_payload"]["penalty_ms"], row["team_id"])),
                start=1,
            ):
                row["ranking_position"] = position
                row["locked"] = True
            return {"Locked": True, "AlreadyLocked": False}
        raise AssertionError(f"Unexpected RPC: {name}")

    def fake_get(table: str, query: dict):
        assert table == "race_results_v2"
        result = [dict(row) for row in rows.values()]
        if query.get("order") == "ranking_position.asc,team_id.asc":
            return sorted(result, key=lambda row: (row["ranking_position"] or 999, row["team_id"]))
        return sorted(result, key=lambda row: row["team_id"])

    class FakeRaceControlAdapter:
        def save_formula_race_result(self, event_id, team_id, time_ms, penalty_ms, bonus, verified, reason, actor):
            return fake_rpc("exos_v2_formula_race_save_result", {
                "p_event_id": event_id, "p_team_id": team_id, "p_time_ms": time_ms,
                "p_penalty_ms": penalty_ms, "p_bonus": bonus, "p_verified": verified,
            })

        def lock_formula_race_results(self, event_id, actor, reason):
            return fake_rpc("exos_v2_formula_race_lock_final_results", {"p_event_id": event_id})

    runner._rpc = fake_rpc  # type: ignore[method-assign]
    runner._get = fake_get  # type: ignore[method-assign]
    runner._race_control_adapter = FakeRaceControlAdapter()
    runner._certify_final_lock_results()

    for gate in (
        "missing_result_rejected", "unverified_result_rejected", "idempotent_relock",
        "penalty_applied_once", "lock_persisted", "locked_mutation_rejected",
        "ranking_10_teams", "ranking_deterministic", "tie_rule_deterministic",
    ):
        assert runner.gates[gate] is True, gate


def test_ranking_10_team_produced_contract_with_exact_staging_dataset() -> None:
    runner = CoreV2RaceStagingRunner()
    runner.team_ids = [f"CORE-V2-RACE-UAT-T{idx:02d}-ABCDEF1234" for idx in range(1, 11)]

    ranking_rows = []
    for idx, team_id in enumerate(runner.team_ids, start=1):
        ranking_rows.append(
            {
                "team_id": team_id,
                "ranking_position": idx,
                "result_payload": {
                    "time_ms": 120000 + idx * 500,
                    "penalty_ms": 5000 if idx in {1, 2} else 2000,
                    "bonus_credits": 0,
                },
                "checkpoint": "Race Final",
                "activity_id": runner.activity_ids[0],
            }
        )

    assert runner._ranking_10_team_produced(ranking_rows, runner.team_ids[:10]) is True


def test_ranking_10_team_produced_contract_rejects_partial_dataset() -> None:
    runner = CoreV2RaceStagingRunner()
    runner.team_ids = [f"CORE-V2-RACE-UAT-T{idx:02d}-ABCDEF1234" for idx in range(1, 11)]

    ranking_rows = [
        {"team_id": runner.team_ids[0], "ranking_position": 1, "result_payload": {"time_ms": 1, "penalty_ms": 0}},
        {"team_id": runner.team_ids[0], "ranking_position": 1, "result_payload": {"time_ms": 2, "penalty_ms": 0}},
    ]
    assert runner._ranking_10_team_produced(ranking_rows, runner.team_ids[:10]) is False
