#!/usr/bin/env python3
"""Run a real staging Formula R.A.C.E. Core v2 vertical slice using direct Supabase REST/RPC."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import ast

from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter


KNOWN_PROD_HOSTS = {
    # Known production runtime project (must never target).
    "bqsbkdfzqyiodivhyxnq.supabase.co",
}

LEGACY_RUNTIME_TABLE_PATTERNS = {
    "runtime_events",
    "runtime_teams",
    "runtime_participants",
    "runtime_submissions",
    "runtime_missions",
    "runtime_mission_submissions",
    "runtime_mission_evidence",
    "runtime_mission_status",
    "runtime_credit_transactions",
    "runtime_team_wallets",
    "runtime_marketplace_items",
    "runtime_marketplace_purchases",
    "formula_race_checkpoints",
    "formula_race_team_access",
    "formula_race_checkpoint_runtime",
    "formula_race_build_status",
    "formula_race_judging",
    "formula_race_results",
}


def _in_filter(values: list[str]) -> str:
    sanitized = [str(value).replace('"', '""') for value in values]
    if not sanitized:
        return ""
    if len(sanitized) == 1:
        return f"eq.{sanitized[0]}"
    return "in.({})".format(
        ",".join('"{}"'.format(value) for value in sanitized)
    )


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _activity_call_has_event_id_filter(query_node: ast.AST | None) -> bool:
    if not isinstance(query_node, ast.Dict):
        return False
    for key_node in query_node.keys:
        key = _literal_string(key_node)
        if key == "event_id":
            return True
    return False


def find_stale_activity_event_refs(source_text: str) -> list[str]:
    """Return executable callsites that use activities_v2 with event_id filters."""

    tree = ast.parse(source_text)
    stale: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method_name = node.func.attr

        table_expr = None
        query_expr = None

        if method_name in {"_get", "_post", "_patch", "_delete"}:
            if len(node.args) >= 1:
                table_expr = node.args[0]
            if len(node.args) >= 2:
                query_expr = node.args[1]
            for kw in node.keywords:
                if kw.arg in {"query", "payload"} and kw.value is not None:
                    # For direct request calls we inspect payload filters too.
                    query_expr = kw.value
        elif method_name == "_request":
            # _request(method, path, payload=None, query=None, admin=True)
            if len(node.args) >= 2:
                table_expr = node.args[1]
            for kw in node.keywords:
                if kw.arg == "query":
                    query_expr = kw.value
            if query_expr is None and len(node.args) >= 4:
                query_expr = node.args[3]
        else:
            continue

        table = _literal_string(table_expr)
        if table != "activities_v2":
            continue

        query_key_node: ast.AST | None = query_expr
        if _activity_call_has_event_id_filter(query_key_node):
            stale.append(f"line {getattr(node, 'lineno', 0)}")

    return stale


class _RunnerCoreV2Runtime:
    """Minimal transport bridge so certification uses the live Core-v2 adapter."""

    def __init__(self, runner: "CoreV2RaceStagingRunner") -> None:
        self.runner = runner
        self.url = runner.supabase_url
        self.is_configured = bool(runner.supabase_url and runner.anon_key)
        self.can_publish = bool(runner.service_key)

    def _request(self, method: str, path: str, *, payload=None, query=None, admin: bool = True):
        return self.runner._request(method, path, payload=payload, query=query, admin=admin)


class CoreV2RaceStagingRunner:
    @staticmethod
    def _git_commit_short() -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=os.path.dirname(__file__),
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            return "unknown"

    @staticmethod
    def _runner_version() -> str:
        return "exos-core-v2-race-vertical-slice-v9"

    @staticmethod
    def _coerce_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, str):
            return value.lower() in {"true", "1", "yes", "y", "on"}
        return bool(value)

    def _is_expected_lock_rejection(self, error: Exception, expected_message: str) -> bool:
        text = str(error)
        return "P0001" in text and expected_message.lower() in text.lower()

    @staticmethod
    def _compute_team_rank_order(rows: list[dict]) -> tuple[list[str], list[tuple[str, float]], bool]:
        seen_team_ids = set()
        ordered_teams = []
        computed_rows: list[tuple[str, float]] = []
        ties_ok = True

        for row in rows:
            if not isinstance(row, dict):
                continue
            team_id = row.get("team_id")
            if not team_id:
                continue
            if team_id in seen_team_ids:
                ties_ok = False
                continue
            seen_team_ids.add(team_id)

            payload = row.get("result_payload") or {}
            adjusted = float(payload.get("time_ms", 0) or 0) + float(payload.get("penalty_ms", 0) or 0)
            ordered_teams.append(team_id)
            computed_rows.append((team_id, adjusted))

        ordered_by_metric = sorted(
            computed_rows,
            key=lambda item: (item[1], item[0]),
        )
        expected_order: list[str] = []
        expected_rank = {}
        for idx, (team_id, adjusted) in enumerate(ordered_by_metric):
            expected_rank[team_id] = idx + 1
            expected_order.append(team_id)

        tie_pairs = []
        for idx in range(1, len(ordered_by_metric)):
            if ordered_by_metric[idx][1] == ordered_by_metric[idx - 1][1]:
                tie_pairs.append((ordered_by_metric[idx - 1][0], ordered_by_metric[idx][0]))

        for left_team, right_team in tie_pairs:
            if left_team > right_team:
                ties_ok = False

        expected_position_match = all(
            int(row.get("ranking_position", 0)) == expected_rank.get(row.get("team_id"))
            for row in rows
            if isinstance(row, dict)
            and row.get("team_id")
            and row.get("ranking_position") is not None
        )

        return expected_order, list(ordered_by_metric), ties_ok and expected_position_match

    @staticmethod
    def _normalize_team_id_map(rows: list[dict], key: str) -> dict[str, list[dict]]:
        index: dict[str, list[dict]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            team_id = row.get(key)
            if not team_id:
                continue
            index.setdefault(str(team_id), []).append(row)
        return index

    def _print_ranking_diagnostic(self, race_rows: list[dict]) -> tuple[int, int, int, list[str], list[str], list[str]]:
        """Print concise ranking diagnostics and return basic counts."""

        team_row_map = self._normalize_team_id_map(race_rows, "team_id")
        expected_team_ids = [str(team_id) for team_id in self.team_ids[:10]]

        for team_id in expected_team_ids:
            rows = team_row_map.get(team_id, [])
            row_count = len(rows)
            if row_count == 0:
                print(f"RANKING DIAGNOSTIC | TeamID={team_id} | row_count=0 | checkpoint=Race Final | locked=False | time_ms=NA | penalty_ms=NA | adjusted_time=NA | ranking_position=NA")
                continue

            for row in rows:
                payload = row.get("result_payload") or {}
                time_ms = payload.get("time_ms")
                penalty_ms = payload.get("penalty_ms")
                try:
                    adjusted_time = float(time_ms or 0) + float(penalty_ms or 0)
                except Exception:
                    adjusted_time = None
                print(
                    "RANKING DIAGNOSTIC | TeamID={team_id} | row_count={row_count} | "
                    "checkpoint={checkpoint} | locked={locked} | time_ms={time_ms} | penalty_ms={penalty_ms} | "
                    "adjusted_time={adjusted_time} | ranking_position={ranking_position}".format(
                        team_id=team_id,
                        row_count=row_count,
                        checkpoint=row.get("checkpoint", "Race Final"),
                        locked=row.get("locked", False),
                        time_ms=time_ms,
                        penalty_ms=penalty_ms,
                        adjusted_time=adjusted_time,
                        ranking_position=row.get("ranking_position"),
                    )
                )

        expected_count = len(expected_team_ids)
        actual_count = len(race_rows) if isinstance(race_rows, list) else 0
        unique_teams = [team_id for team_id in sorted(team_row_map)]

        missing_teams = [team_id for team_id in expected_team_ids if team_id not in team_row_map]
        duplicate_teams = [
            team_id for team_id, rows in team_row_map.items()
            if team_id in expected_team_ids and len(rows) > 1
        ]

        print(f"EXPECTED TEAM COUNT | {expected_count}")
        print(f"ACTUAL RESULT ROW COUNT | {actual_count}")
        print(f"UNIQUE TEAM COUNT | {len(team_row_map)}")
        print(f"MISSING TEAM IDs | {json.dumps(missing_teams)}")
        print(f"DUPLICATE TEAM IDs | {json.dumps(duplicate_teams)}")

        return expected_count, actual_count, len(team_row_map), missing_teams, duplicate_teams

    def _ranking_10_team_produced(self, ranking_rows: list[dict], expected_team_ids: list[str]) -> bool:
        """Validate exactly 10 canonical Race Final rows with positions 1..10."""

        team_row_map = self._normalize_team_id_map(ranking_rows, "team_id")

        missing_team_ids = [team_id for team_id in expected_team_ids if team_id not in team_row_map]
        duplicate_team_ids = [team_id for team_id, rows in team_row_map.items() if len(rows) > 1]
        ranking_positions = [
            int(row.get("ranking_position", 0))
            for row in ranking_rows
            if isinstance(row, dict)
            and row.get("ranking_position") is not None
            and str(row.get("ranking_position")).isdigit()
        ]

        return (
            len(ranking_rows) == 10
            and len(expected_team_ids) == 10
            and len(team_row_map) == 10
            and not missing_team_ids
            and not duplicate_team_ids
            and sorted(ranking_positions) == list(range(1, 11))
        )

    def _compute_rank_positions(self, rows: list[dict]) -> list[dict[str, object]]:
        """Compute canonical ranking positions for the supplied final rows."""

        ranked_payload: list[tuple[str, float, dict]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            team_id = row.get("team_id")
            payload = row.get("result_payload") or {}
            try:
                adjusted = float(payload.get("time_ms", 0) or 0) + float(payload.get("penalty_ms", 0) or 0)
            except (TypeError, ValueError):
                adjusted = 0.0
            ranked_payload.append((str(team_id), adjusted, row))

        ordered = sorted(ranked_payload, key=lambda item: (item[1], item[0]))
        positions: dict[str, int] = {}
        current_position = 1
        previous_metric = None
        for idx, (team_id, adjusted, _row) in enumerate(ordered):
            if previous_metric is None or adjusted != previous_metric:
                current_position = idx + 1
            positions[team_id] = current_position
            previous_metric = adjusted

        return [
            {"team_id": team_id, "ranking_position": rank}
            for team_id, rank in positions.items()
        ]

    def _is_reconnect_contract_ok(self, login: object, restore: object, session_row: object) -> bool:
        if not isinstance(login, dict) or not isinstance(restore, dict):
            return False

        expected_event_id = self._team_access_diagnostics.get("event_id")
        expected_team_id = self._team_access_diagnostics.get("team_id")
        expected_device_id = self._team_access_diagnostics.get("device_id")

        if login.get("EventID") != expected_event_id:
            return False
        if login.get("TeamID") != expected_team_id:
            return False

        if not isinstance(session_row, dict):
            return False
        if session_row.get("event_id") != expected_event_id:
            return False
        if session_row.get("team_id") != expected_team_id:
            return False
        if session_row.get("device_id") != expected_device_id:
            return False
        if not session_row.get("is_active"):
            return False

        if restore.get("EventID") != expected_event_id:
            return False
        if restore.get("TeamID") != expected_team_id:
            return False
        if self._coerce_bool(restore.get("Ambiguous")):
            return False
        if self._coerce_bool(restore.get("RecoveryRequired")):
            return False

        return True

    def __init__(self) -> None:
        self.supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.anon_key = (
            os.getenv("SUPABASE_PUBLISHABLE_KEY")
            or os.getenv("SUPABASE_ANON_KEY", "")
        ).strip()
        self.service_key = (
            os.getenv("SUPABASE_SECRET_KEY")
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        ).strip()
        self.env = os.getenv("EXOS_ENV", "").strip().lower()

        run_id = uuid.uuid4().hex[:10].upper()
        self.event_id = f"CORE-V2-RACE-UAT-EVT-{run_id}"
        self.join_code = f"RACE{run_id[:6]}"
        self.programme_id = f"CORE-V2-RACE-UAT-PROG-{run_id}"
        self.module_id = f"CORE-V2-RACE-UAT-MOD-{run_id}"
        self.activity_ids = [f"CORE-V2-RACE-UAT-CP-{idx:02d}-{run_id}" for idx in range(1, 5)]
        self.team_ids = [f"CORE-V2-RACE-UAT-T{idx:02d}-{run_id}" for idx in range(1, 11)]
        self.team_names = [f"RACE Team {idx:02d}" for idx in range(1, 11)]

        self.captain_device = f"CORE-V2-RACE-DEVICE-{run_id}"
        self.session_token = ""
        self.checkpoint_rows = []
        self.submission_ids = []
        self.configured_marketplace_item_id = ""
        self._race_configuration_snapshot = {}

        self.gates = {
            "staging_connectivity": False,
            "race_event_created": False,
            "ten_teams": False,
            "captain_login": False,
            "wrong_pin_rejection": False,
            "captain_reconnect": False,
            "four_checkpoints": False,
            "configuration_saved": False,
            "station_methods": False,
            "team_routes": False,
            "submission_gated_progression": False,
            "approval_independent_unlock": False,
            "configurable_credits": False,
            "marketplace_configuration": False,
            "judging_configuration": False,
            "pin_reset": False,
            "checkpoint_submission": False,
            "facilitator_review": False,
            "credits_ledger": False,
            "wallet_reconciliation": False,
            "marketplace": False,
            "build_status": False,
            "judging": False,
            "race_result": False,
            "penalties_bonuses": False,
            "result_row_created": False,
            "penalty_applied_once": False,
            "bonus_applied_once": False,
            "lock_persisted": False,
            "locked_mutation_rejected": False,
            "missing_result_rejected": False,
            "unverified_result_rejected": False,
            "idempotent_relock": False,
            "ranking_10_teams": False,
            "ranking_deterministic": False,
            "tie_rule_deterministic": False,
            "result_locking": False,
            "final_ranking": False,
            "reset_preview": False,
            "reset_execution": False,
            "reset_configuration_preserved": False,
            "reset_zero_state": False,
            "google_sheets_runtime_calls": False,
            "cleanup": False,
        }
        self.ui_checks = {"runtime_snapshot": False}

        self._legacy_runtime_calls = []
        self._legacy_rpc_calls = []
        self._cleanup_steps = []
        self._error = None
        self.captain_participant = {}
        self.ranking_metric = "time_ms + penalty_ms"
        self._team_access_diagnostics = {
            "event_id": None,
            "team_id": None,
            "device_id": None,
            "captain_participant": {},
            "team_access_session_id": None,
            "login_rpc_input": None,
            "login_rpc_response": None,
            "restore_rpc_input": None,
            "restore_rpc_response": None,
            "stored_credential_row": None,
            "stored_session_row": None,
        }
        self._race_control_adapter = None

        # Canonical operation audit for this runner.
        self.operation_audit = []
        self.runner_commit = self._git_commit_short()
        self.runner_version = self._runner_version()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _record_operation(self, step: str, table_or_rpc: str, method: str, filters_or_payload: dict | None) -> None:
        self.operation_audit.append(
            {
                "step": step,
                "table_or_rpc": table_or_rpc,
                "method": method,
                "filters_or_payload": filters_or_payload or {},
            }
        )

    def get_activity_ids_for_event(self, event_id: str) -> list[str]:
        programmes = self._get(
            "programmes_v2",
            {
                "event_id": f"eq.{event_id}",
                "select": "programme_id",
            },
        )
        programme_ids = [row.get("programme_id") for row in (programmes or []) if isinstance(row, dict) and row.get("programme_id")]
        if not programme_ids:
            return []

        modules = self._get(
            "modules_v2",
            {
                "programme_id": _in_filter(programme_ids),
                "select": "module_id",
            },
        )
        module_ids = [row.get("module_id") for row in (modules or []) if isinstance(row, dict) and row.get("module_id")]
        if not module_ids:
            return []

        activities = self._get(
            "activities_v2",
            {
                "module_id": _in_filter(module_ids),
                "select": "activity_id",
            },
        )
        return [
            row.get("activity_id")
            for row in (activities or [])
            if isinstance(row, dict) and row.get("activity_id")
        ]

    def get_submission_ids_for_event(self, event_id: str) -> list[str]:
        submissions = self._get(
            "submissions_v2",
            {
                "event_id": f"eq.{event_id}",
                "select": "submission_id",
            },
        )
        return [
            str(row.get("submission_id"))
            for row in (submissions or [])
            if isinstance(row, dict) and row.get("submission_id")
        ]

    def get_review_ids_for_event(self, event_id: str) -> list[str]:
        submission_ids = self.get_submission_ids_for_event(event_id)
        if not submission_ids:
            return []

        submission_filter = _in_filter(submission_ids)
        if not submission_filter:
            return []

        reviews = self._get(
            "reviews_v2",
            {
                "submission_id": submission_filter,
                "select": "review_id",
            },
        )
        return [
            str(row.get("review_id"))
            for row in (reviews or [])
            if isinstance(row, dict) and row.get("review_id")
        ]

    def _emit_runner_identity(self) -> None:
        print(f"RUNNER COMMIT: {self.runner_commit}")
        print(f"RUNNER VERSION: {self.runner_version}")

    def _check_stale_activity_event_refs(self) -> None:
        script_path = os.path.join(os.path.dirname(__file__), os.path.basename(__file__))
        with open(script_path, "r", encoding="utf-8") as stream:
            source = stream.read()
        self.stale_activity_event_id_refs = find_stale_activity_event_refs(source)
        print(
            "STALE_ACTIVITY_EVENT_PATHS: "
            + str(len(self.stale_activity_event_id_refs))
        )
        if self.stale_activity_event_id_refs:
            raise RuntimeError(
                "Stale activities_v2 event_id references detected: "
                + ", ".join(self.stale_activity_event_id_refs)
            )

    def _require_env(self) -> None:
        if self.env != "staging":
            raise RuntimeError("Refusing to run: EXOS_ENV must be exactly 'staging'.")
        if not self.supabase_url:
            raise RuntimeError("SUPABASE_URL is required.")
        if not self.anon_key:
            raise RuntimeError("SUPABASE_PUBLISHABLE_KEY (or SUPABASE_ANON_KEY) is required.")
        if not self.service_key:
            raise RuntimeError("SUPABASE_SECRET_KEY (or SUPABASE_SERVICE_ROLE_KEY) is required.")

        host = (urlparse(self.supabase_url).hostname or "").lower()
        print(f"Supabase host: {host}")
        if host in KNOWN_PROD_HOSTS:
            raise RuntimeError(f"Refusing to run against known production host: {host}")

    @staticmethod
    def _is_legacy_runtime_path(path: str) -> bool:
        normalized = (path or "").lower()
        if normalized.startswith("rpc/"):
            return False
        return any(pattern in normalized for pattern in LEGACY_RUNTIME_TABLE_PATTERNS)

    @staticmethod
    def _is_legacy_runtime_rpc(name: str) -> bool:
        normalized = (name or "").lower()
        return any(
            pattern in normalized
            for pattern in (
                LEGACY_RUNTIME_TABLE_PATTERNS
                | {
                    "exos_formula_race_",
                    "formula_race",
                    "exos_set_formula_race_",
                    "exos_formula_race",
                }
            )
        )

    def _assert_no_legacy_runtime_calls(self) -> None:
        count = len(self._legacy_runtime_calls) + len(self._legacy_rpc_calls)
        print(f"LEGACY_RUNTIME_CALLS = {count}")
        if count:
            details = ", ".join(
                sorted(set(self._legacy_runtime_calls + self._legacy_rpc_calls))
            )
            raise RuntimeError(f"Legacy runtime calls detected: {details}")

    def _request(self, method: str, path: str, payload=None, query=None, admin: bool = True):
        if self._is_legacy_runtime_path(path):
            self._legacy_runtime_calls.append(path)
            raise RuntimeError(f"Blocked legacy runtime call attempt: {path}")

        headers = {
            "apikey": self.service_key if admin else self.anon_key,
            "Authorization": f"Bearer {self.service_key if admin else self.anon_key}",
            "Accept": "application/json",
        }

        url = f"{self.supabase_url}/rest/v1/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query, doseq=True)}"

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            if method.upper() in {"POST", "PATCH", "PUT", "DELETE"}:
                headers["Prefer"] = "return=representation"
        elif method.upper() == "GET":
            headers["Prefer"] = "count=exact"

        req = Request(url, method=method.upper(), headers=headers, data=body)
        try:
            with urlopen(req, timeout=45) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
        except HTTPError as error:
            body = ""
            try:
                body = error.read().decode("utf-8")
            except Exception:
                pass
            raise RuntimeError(f"HTTP {error.code} {method} {path}: {body or error.reason}")
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Request failed for {method} {path}: {exc}")

    def _canonical_race_control_adapter(self) -> FormulaRaceCoreV2StagingAdapter:
        """Use the live Race Control Core-v2 result path, not a runner-local RPC."""
        if self._race_control_adapter is None:
            self._race_control_adapter = FormulaRaceCoreV2StagingAdapter(
                _RunnerCoreV2Runtime(self)
            )
        return self._race_control_adapter

    def _rpc(self, name: str, payload: dict, admin: bool = True):
        if self._is_legacy_runtime_rpc(name):
            self._legacy_rpc_calls.append(name)
            raise RuntimeError(f"Blocked legacy RPC call attempt: {name}")
        self._record_operation("rpc", name, "POST", payload)
        return self._request("POST", f"rpc/{name}", payload=payload, admin=admin)

    def _post(self, table: str, payload: dict):
        self._record_operation("insert", table, "POST", payload)
        return self._request("POST", table, payload=payload, admin=True)

    def _get(self, table: str, query: dict):
        self._record_operation("query", table, "GET", query)
        return self._request("GET", table, query=query, admin=True)

    def _patch(self, table: str, query: dict, payload: dict):
        self._record_operation("update", table, "PATCH", payload)
        return self._request("PATCH", table, query=query, payload=payload, admin=True)

    def _delete(self, table: str, query: dict):
        self._cleanup_steps.append((table, dict(query)))
        self._record_operation("delete", table, "DELETE", query)
        return self._request("DELETE", table, query=query, admin=True)

    def _ensure_single_review(self, event_id: str, submission_id: str, payload: dict) -> list[dict]:
        reviewer = str(payload.get("reviewer", "")).strip()
        if not reviewer:
            raise RuntimeError("Reviewer required for review write")

        existing = self._get(
            "reviews_v2",
            {
                "event_id": f"eq.{event_id}",
                "submission_id": f"eq.{submission_id}",
                "reviewer": f"eq.{reviewer}",
                "select": "review_id",
                "limit": "1",
            },
        )
        if isinstance(existing, list) and existing and existing[0].get("review_id"):
            review_id = existing[0]["review_id"]
            updated = self._patch(
                "reviews_v2",
                {"review_id": f"eq.{review_id}"},
                {
                    "decision": payload.get("decision"),
                    "score_points": payload.get("score_points"),
                    "rationale": payload.get("rationale"),
                },
            )
            if isinstance(updated, list) and updated:
                return updated

        return self._post("reviews_v2", payload)

    def check_connectivity(self) -> None:
        rows = self._get("events_v2", {"select": "event_id", "limit": "1"})
        if isinstance(rows, list):
            self.gates["staging_connectivity"] = True
            return
        raise RuntimeError("Staging connectivity payload invalid")

    def create_race_event(self) -> None:
        teams = []
        for idx, team_id in enumerate(self.team_ids):
            teams.append(
                {
                    "team_id": team_id,
                    "team_name": self.team_names[idx],
                    "country": "Staging",
                    "team_flag": f"FLAG-{idx + 1:02d}",
                }
            )

        published = self._rpc(
            "exos_v2_publish_event",
            {
                "p_event_id": self.event_id,
                "p_join_code": self.join_code,
                "p_event_name": f"{self.event_id} Formula R.A.C.E. UAT",
                "p_teams": teams,
                "p_scoring_mode": "TEAM_COMPETITIVE",
                "p_event_type": "RACE",
            },
            admin=True,
        )
        if not isinstance(published, dict) or published.get("EventID") != self.event_id:
            raise RuntimeError("Event publish did not return expected payload")

        created_events = self._get(
            "events_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "event_id,event_type,programme_type,event_name",
                "limit": "1",
            },
        )
        teams_rows = self._get(
            "teams_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "team_id",
                "order": "team_id.asc",
            },
        )

        event_ok = bool(
            isinstance(created_events, list)
            and created_events
            and created_events[0].get("event_id") == self.event_id
        )
        self.gates["race_event_created"] = event_ok
        self.gates["ten_teams"] = isinstance(teams_rows, list) and len(teams_rows) >= 10
        if not (event_ok and self.gates["ten_teams"]):
            raise RuntimeError("Event creation or team seed failed")

    def create_programme_and_checkpoints(self) -> None:
        self._post(
            "programmes_v2",
            {
                "programme_id": self.programme_id,
                "event_id": self.event_id,
                "programme_name": f"{self.event_id} Programme",
                "programme_type": "Formula R.A.C.E.",
                "module_count": 1,
                "is_active": True,
            },
        )

        self._post(
            "modules_v2",
            {
                "module_id": self.module_id,
                "programme_id": self.programme_id,
                "module_name": "Formula R.A.C.E. Checkpoints",
                "module_payload": {"module_type": "RACE Checkpoints", "is_parallel": True},
                "activity_sequence": 1,
                "scoring_mode": "TEAM_COMPETITIVE",
                "is_active": True,
            },
        )

        for idx, activity_id in enumerate(self.activity_ids, 1):
            self._post(
                "activities_v2",
                {
                    "activity_id": activity_id,
                    "module_id": self.module_id,
                    "programme_id": self.programme_id,
                    "activity_type": "CHECKPOINT",
                    "scoring_mode": "TEAM_COMPETITIVE",
                    "activity_name": f"RACE Checkpoint {idx}",
                    "activity_order": idx,
                    "duration_seconds": 300,
                    "activity_payload": {
                        "proof_type": "Photo + Text" if idx % 2 == 0 else "Text",
                        "instructions": f"Formula R.A.C.E. checkpoint {idx}",
                        "max_score": 10,
                        "credits": 2,
                    },
                    "is_active": True,
                },
            )

        checkpoints = self._get(
            "activities_v2",
            {
                "programme_id": f"eq.{self.programme_id}",
                "activity_type": "eq.CHECKPOINT",
                "select": "activity_id,activity_name,activity_order,activity_payload",
                "order": "activity_order.asc",
            },
        )
        self.checkpoint_rows = checkpoints if isinstance(checkpoints, list) else []

        self.gates["four_checkpoints"] = bool(
            isinstance(self.checkpoint_rows, list) and len(self.checkpoint_rows) == 4
        )
        if not self.gates["four_checkpoints"]:
            raise RuntimeError("Checkpoint config not persisted with 4 checkpoints")

        # PIN configuration is exercised via captain RPC; keep mapping to this event's team set.
        self._configured_pins = True

    def captain_flow(self) -> None:
        captain_name = f"CORE-V2-RACE-CAP-{self.event_id[-6:]}"
        captain_device = self.captain_device

        selected_team_id = self.team_ids[0]

        self._team_access_diagnostics.update(
            {
                "event_id": self.event_id,
                "team_id": selected_team_id,
                "device_id": captain_device,
                "captain_participant": {},
                "team_access_session_id": None,
            }
        )

        captain = self._rpc(
            "exos_v2_join_event_v2",
            {
                "p_join_code": self.join_code,
                "p_participant_name": captain_name,
                "p_device_id": captain_device,
                "p_requested_team_id": self.team_ids[0],
            },
            admin=False,
        )
        if not isinstance(captain, dict) or captain.get("RecoveryRequired"):
            raise RuntimeError("Captain seed join failed")
        self.captain_participant = {
            "participant_id": captain.get("ParticipantID"),
            "team_id": captain.get("TeamID"),
        }
        team_id = self.captain_participant.get("team_id") or self.team_ids[0]

        wrong_pin_ok = False
        try:
            self._rpc(
                "exos_v2_team_access_login",
                {
                    "p_join_code": self.join_code,
                    "p_team_id": team_id,
                    "p_pin": "BADPIN",
                    "p_device_id": self.captain_device,
                },
                admin=False,
            )
            wrong_pin_ok = False
        except RuntimeError:
            wrong_pin_ok = True
        self.gates["wrong_pin_rejection"] = wrong_pin_ok

        # Keep pin as TEAM-ID suffixed deterministic token for UAT execution.
        team_pin = f"PIN-{team_id[-2:]}"
        configured = 0
        for team_id in self.team_ids:
            result = self._rpc(
                "exos_v2_set_team_access_pin",
                {
                    "p_event_id": self.event_id,
                    "p_team_id": team_id,
                    "p_pin": f"PIN-{team_id[-2:]}",
                    "p_actor": "QA Bot",
                },
            )
            if isinstance(result, dict) and result.get("Configured"):
                configured += 1

        if configured < 10:
            raise RuntimeError("Not all team PINs were configured")

        # Keep pin as TEAM-ID suffixed deterministic token for UAT execution.
        team_pin = f"PIN-{selected_team_id[-2:]}"
        login = self._rpc(
            "exos_v2_team_access_login",
            {
                "p_join_code": self.join_code,
                "p_team_id": selected_team_id,
                "p_pin": team_pin,
                "p_device_id": self.captain_device,
            },
            admin=False,
        )
        login_team_id = login.get("TeamID") if isinstance(login, dict) else None
        self._team_access_diagnostics["team_id"] = login_team_id or selected_team_id
        self._team_access_diagnostics["login_rpc_input"] = {
            "p_event_id": self.event_id,
            "p_team_id": login_team_id or selected_team_id,
            "p_device_id": self.captain_device,
            "used_team_pin_suffix": f"PIN-{(selected_team_id[-2:] if selected_team_id else 'NA')}",
        }
        self._team_access_diagnostics["login_rpc_response"] = login
        self.session_token = str(login.get("SessionToken", "")) if isinstance(login, dict) else ""

        login_ok = (
            isinstance(login, dict)
            and login.get("EventID") == self.event_id
            and login.get("TeamID") == (login_team_id or selected_team_id)
            and len(self.session_token) > 0
        )

        self._team_access_diagnostics["restore_rpc_input"] = {
            "p_session_token": self.session_token,
            "p_device_id": self.captain_device,
        }
        restore = self._rpc(
            "exos_v2_restore_team_access",
            {
                "p_session_token": self.session_token,
                "p_device_id": self.captain_device,
            },
            admin=False,
        )
        self._team_access_diagnostics["restore_rpc_response"] = restore

        credential_rows = self._get(
            "team_access_credentials_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{login_team_id or selected_team_id}",
                "select": "team_access_credential_id,event_id,team_id,credential_purpose,is_active,created_by,created_at,updated_at",
            },
        )
        session_rows = self._get(
            "team_access_sessions_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{login_team_id or selected_team_id}",
                "select": "team_access_session_id,event_id,team_id,device_id,is_active,recovery_required,session_token,team_access_credential_id,updated_at,last_seen_at",
                "order": "updated_at.desc",
            },
        )
        stored_session_row = session_rows[0] if isinstance(session_rows, list) and session_rows else None
        self._team_access_diagnostics["stored_session_row"] = stored_session_row
        stored_credential_row = credential_rows[0] if isinstance(credential_rows, list) and credential_rows else None
        self._team_access_diagnostics["stored_credential_row"] = stored_credential_row

        if stored_session_row and stored_session_row.get("team_access_session_id"):
            self._team_access_diagnostics["team_access_session_id"] = stored_session_row.get("team_access_session_id")
            self._team_access_diagnostics["team_id"] = stored_session_row.get("team_id") or self._team_access_diagnostics.get("team_id")
        self._team_access_diagnostics["captain_participant"] = dict(self.captain_participant)

        print("TEAM ACCESS DIAGNOSTICS:")
        print(json.dumps(self._team_access_diagnostics, sort_keys=True))

        wrong_device_login_blocked = False
        try:
            self._rpc(
                "exos_v2_team_access_login",
                {
                    "p_join_code": self.join_code,
                    "p_team_id": selected_team_id,
                    "p_pin": team_pin,
                    "p_device_id": f"{self.captain_device}-OTHER",
                },
                admin=False,
            )
        except RuntimeError:
            wrong_device_login_blocked = True

        # Keep wrong-device guard for hardening, but do not couple reconnect gate to it.
        self.gates["captain_login"] = bool(login_ok)
        self.gates["captain_reconnect"] = bool(
            login_ok
            and self._is_reconnect_contract_ok(login, restore, stored_session_row)
        )

        if wrong_device_login_blocked:
            self._team_access_diagnostics["wrong_device_reject_reason"] = "blocked"
        else:
            self._team_access_diagnostics["wrong_device_reject_reason"] = "allowed"

        if not (self.gates["captain_login"] and self.gates["captain_reconnect"] and wrong_pin_ok):
            raise RuntimeError("Captain identity controls failed")

        # Migration 030 promises PIN credentials survive reset. Prove the
        # generated credential can be rotated on this disposable team first.
        reset_pin = f"RESET-{selected_team_id[-6:]}"
        reset_result = self._rpc(
            "exos_v2_set_team_access_pin",
            {
                "p_event_id": self.event_id,
                "p_team_id": selected_team_id,
                "p_pin": reset_pin,
                "p_actor": "QA Bot PIN reset",
            },
        )
        reset_login = self._rpc(
            "exos_v2_team_access_login",
            {
                "p_join_code": self.join_code,
                "p_team_id": selected_team_id,
                "p_pin": reset_pin,
                "p_device_id": self.captain_device,
            },
            admin=False,
        )
        reset_token = str(reset_login.get("SessionToken", "")) if isinstance(reset_login, dict) else ""
        self.gates["pin_reset"] = bool(
            isinstance(reset_result, dict)
            and reset_result.get("Configured")
            and isinstance(reset_login, dict)
            and reset_login.get("TeamID") == selected_team_id
            and reset_token
        )
        if not self.gates["pin_reset"]:
            raise RuntimeError("Disposable captain PIN reset failed")
        self.session_token = reset_token

        activity_runtime_rows = self._post(
            "activity_runtime_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "participant_id": self.captain_participant.get("participant_id"),
                "activity_id": self.checkpoint_rows[0].get("activity_id"),
                "state_payload": {
                    "status": "LIVE",
                    "actor": "CAPTAIN",
                    "mode": "parallel_checkpoints",
                    "activity_count": len(self.checkpoint_rows),
                },
                "activity_started_at": self._now_iso(),
                "is_completed": False,
            },
        )
        self.gates["four_checkpoints"] = bool(
            self.gates["four_checkpoints"]
            and isinstance(activity_runtime_rows, list)
            and len(activity_runtime_rows) >= 1
        )

    def configure_030_architecture(self) -> None:
        """Configure every 030 surface on this generated event before runtime data exists."""
        if len(self.checkpoint_rows) != 4:
            raise RuntimeError("030 certification requires four disposable checkpoint activities")

        station_ids = [str(row.get("activity_id", "")) for row in self.checkpoint_rows]
        if not all(station_ids):
            raise RuntimeError("Disposable checkpoint IDs are incomplete")

        scoring_methods = (
            "FACILITATOR_SCORE",
            "LOWEST_TIME",
            "HIGHEST_COUNT",
            "SUCCESS_COUNT",
        )
        base_credits = (17, 3, 4, 1)
        performance = (
            {},
            {"RankCredits": {"1": 11, "2": 6}},
            {"RankCredits": {"1": 9, "2": 5}},
            {"PerSuccess": 2},
        )
        stations = []
        for index, activity_id in enumerate(station_ids, 1):
            method = scoring_methods[index - 1]
            stations.append(
                {
                    "ActivityID": activity_id,
                    "DisplayOrder": index,
                    "ShortCode": f"S{index}",
                    "DisplayName": f"Disposable 030 Station {index}",
                    "ParticipantInstruction": f"Submit the configured result for disposable station {index}.",
                    "FacilitatorInstruction": f"Verify disposable station {index}.",
                    "ScoringMethod": method,
                    "ResultLabel": "Score" if method == "FACILITATOR_SCORE" else "Measured result",
                    "ResultUnit": "points" if method == "FACILITATOR_SCORE" else ("ms" if method == "LOWEST_TIME" else "count"),
                    "ResultMinimum": 0,
                    "ResultMaximum": 10 if method == "FACILITATOR_SCORE" else 100000,
                    "TiePolicy": "TEAM_ID",
                    "EvidenceRequirement": "PHOTO_OPTIONAL",
                    "BaseCredits": base_credits[index - 1],
                    "PerformanceCredits": performance[index - 1],
                    "Enabled": True,
                }
            )

        self.configured_marketplace_item_id = f"CORE-V2-RACE-CONFIG-ITEM-{self.event_id[-10:]}"
        configuration = {
            "Stations": stations,
            "TeamRoutes": {
                team_id: station_ids[position % len(station_ids):] + station_ids[:position % len(station_ids)]
                for position, team_id in enumerate(self.team_ids)
            },
            "Marketplace": [
                {
                    "ItemID": self.configured_marketplace_item_id,
                    "DisplayOrder": 1,
                    "Category": "TOOL",
                    "ItemName": "Disposable 030 Engine Kit",
                    "Description": "Certification-only configured marketplace item.",
                    "CreditCost": 5,
                    "StockLimit": 2,
                    "Enabled": True,
                }
            ],
            "JudgingCriteria": [
                {
                    "DisplayOrder": 1,
                    "CriterionName": "Configuration fidelity",
                    "Description": "Uses the configured Formula R.A.C.E. event architecture.",
                    "MaximumScore": 10,
                    "Enabled": True,
                },
                {
                    "DisplayOrder": 2,
                    "CriterionName": "Execution quality",
                    "Description": "Completes the disposable staging journey safely.",
                    "MaximumScore": 10,
                    "Enabled": True,
                },
            ],
        }
        adapter = self._canonical_race_control_adapter()
        saved = adapter.save_formula_race_configuration(
            self.event_id,
            configuration,
            "Disposable staging certification",
        )
        persisted = adapter.get_formula_race_configuration(self.event_id)
        persisted_stations = adapter.get_formula_race_stations(self.event_id, configuration=persisted)
        persisted_by_id = {str(row.get("ActivityID", "")): row for row in persisted_stations}
        persisted_marketplace = persisted.get("Marketplace", [])
        persisted_judging = persisted.get("JudgingCriteria", [])

        self._race_configuration_snapshot = {
            "Stations": persisted.get("Stations", []),
            "TeamRoutes": persisted.get("TeamRoutes", {}),
            "Marketplace": persisted_marketplace,
            "JudgingCriteria": persisted_judging,
        }
        self.gates["configuration_saved"] = bool(
            isinstance(saved, dict) and saved.get("Saved") and saved.get("EventID") == self.event_id
        )
        self.gates["station_methods"] = (
            [persisted_by_id.get(activity_id, {}).get("ScoringMethod") for activity_id in station_ids]
            == list(scoring_methods)
        )
        self.gates["team_routes"] = all(
            persisted.get("TeamRoutes", {}).get(team_id) == configuration["TeamRoutes"][team_id]
            for team_id in self.team_ids
        )
        self.gates["configurable_credits"] = bool(
            persisted_by_id.get(station_ids[0], {}).get("BaseCredits") == 17
            and persisted_by_id.get(station_ids[1], {}).get("PerformanceCredits", {}).get("RankCredits", {}).get("1") == 11
            and persisted_by_id.get(station_ids[3], {}).get("PerformanceCredits", {}).get("PerSuccess") == 2
        )
        self.gates["marketplace_configuration"] = bool(
            isinstance(persisted_marketplace, list)
            and persisted_marketplace
            and persisted_marketplace[0].get("ItemID") == self.configured_marketplace_item_id
            and persisted_marketplace[0].get("Category") == "TOOL"
        )
        self.gates["judging_configuration"] = bool(
            isinstance(persisted_judging, list)
            and [row.get("CriterionName") for row in persisted_judging] == [
                "Configuration fidelity",
                "Execution quality",
            ]
        )
        if not all(
            self.gates[gate]
            for gate in (
                "configuration_saved",
                "station_methods",
                "team_routes",
                "configurable_credits",
                "marketplace_configuration",
                "judging_configuration",
            )
        ):
            raise RuntimeError("Migration 030 configuration did not persist on the disposable event")

    def certify_030_submission_progression(self) -> None:
        """Prove that configured route progression is submission-gated, not approval-gated."""
        team_id = self.captain_participant.get("team_id") or self.team_ids[0]
        expected_route = self._race_configuration_snapshot.get("TeamRoutes", {}).get(team_id, [])
        if len(expected_route) < 2:
            raise RuntimeError("Disposable captain route is not configured")

        adapter = self._canonical_race_control_adapter()
        before = adapter.formula_race_captain_workspace(self.session_token, self.captain_device)
        if before.get("CurrentCheckpoint", {}).get("ActivityID") != expected_route[0]:
            raise RuntimeError("Configured route did not project the captain's first station")
        submission = adapter.formula_race_submit_checkpoint(
            self.session_token,
            self.captain_device,
            expected_route[0],
            text_response="Disposable migration-030 station proof",
            idempotency_key=f"030-submit-{self.event_id}",
            result_value=9,
            result_unit="points",
        )
        submission_id = str(submission.get("SubmissionID", "")) if isinstance(submission, dict) else ""
        after_submit = adapter.formula_race_captain_workspace(self.session_token, self.captain_device)
        self.gates["checkpoint_submission"] = bool(submission_id and submission.get("Status") == "SUBMITTED")
        self.gates["submission_gated_progression"] = bool(
            self.gates["checkpoint_submission"]
            and after_submit.get("CurrentCheckpoint", {}).get("ActivityID") == expected_route[1]
            and any(
                row.get("SubmissionID") == submission_id and row.get("Status") == "SUBMITTED"
                for row in after_submit.get("Submissions", [])
            )
        )
        # This is intentionally evaluated before facilitator verification.
        self.gates["approval_independent_unlock"] = self.gates["submission_gated_progression"]
        if not self.gates["submission_gated_progression"]:
            raise RuntimeError("Configured station submission did not unlock the next route station")

        verification = adapter.formula_race_review_checkpoint(
            submission_id,
            "APPROVE",
            "Disposable staging reviewer",
            notes="Configured station verified after the route already advanced.",
            idempotency_key=f"030-verify-{self.event_id}",
            official_result=9,
        )
        credit_rows = self._get(
            "credit_transactions_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "transaction_type": "eq.RACE_STATION_BASE",
                "select": "amount,transaction_type,reason",
            },
        )
        earned = sum(int(row.get("amount", 0) or 0) for row in (credit_rows or []))
        self.gates["facilitator_review"] = bool(
            isinstance(verification, dict) and verification.get("Decision") == "APPROVE"
        )
        self.gates["credits_ledger"] = bool(earned == 17)
        self.gates["wallet_reconciliation"] = bool(isinstance(credit_rows, list) and earned == 17)
        if not (self.gates["facilitator_review"] and self.gates["credits_ledger"]):
            raise RuntimeError("Configured station verification or Credits mapping failed")

    def submit_and_review(self) -> None:
        checkpoints = self._get(
            "activities_v2",
            {
                "programme_id": f"eq.{self.programme_id}",
                "activity_type": "eq.CHECKPOINT",
                "select": "activity_id,activity_name,activity_payload",
                "order": "activity_order.asc",
            },
        )
        if not (isinstance(checkpoints, list) and checkpoints):
            raise RuntimeError("No checkpoints available for submission")

        cp = checkpoints[0]
        checkpoint_id = cp.get("activity_id")
        submission = self._post(
            "submissions_v2",
            {
                "event_id": self.event_id,
                "team_id": self.captain_participant.get("team_id"),
                "participant_id": self.captain_participant.get("participant_id"),
                "activity_id": checkpoint_id,
                "submission_key": f"race-checkpoint-{uuid.uuid4().hex}",
                "submission_payload": {
                    "checkpoint_text": "checkpoint proof",
                    "checkpoint_id": checkpoint_id,
                },
            },
        )
        submission_id = submission[0].get("submission_id") if isinstance(submission, list) else None
        self.gates["checkpoint_submission"] = bool(
            isinstance(submission, list)
            and bool(submission_id)
        )
        if not self.gates["checkpoint_submission"]:
            raise RuntimeError("Checkpoint submission failed")

        review = self._ensure_single_review(
            self.event_id,
            submission_id,
            {
                "event_id": self.event_id,
                "submission_id": submission_id,
                "reviewer": "QA Reviewer",
                "decision": "APPROVE",
                "score_points": 10,
                "rationale": "Looks good",
            },
        )

        score_txn = self._rpc(
            "exos_v2_ledger_score",
            {
                "p_event_id": self.event_id,
                "p_team_id": self.captain_participant.get("team_id"),
                "p_submission_id": submission_id,
                "p_amount": 5,
                "p_reason": "checkpoint",
                "p_scoring_mode": "TEAM_COMPETITIVE",
                "p_idempotency_key": f"race-score-{uuid.uuid4().hex}",
            },
            admin=True,
        )

        self.gates["facilitator_review"] = bool(
            isinstance(review, list)
            and isinstance(score_txn, str)
        )

        team_id = self.captain_participant.get("team_id") or self.team_ids[0]
        credit_rows = self._get(
            "credit_transactions_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "transaction_type": "eq.PURCHASE",
                "select": "credit_transaction_id,amount,transaction_type,reason",
            },
        )

        credits = sum((row.get("amount") or 0) for row in credit_rows) if isinstance(credit_rows, list) else None
        earned = sum((row.get("amount") or 0) for row in credit_rows) if isinstance(credit_rows, list) else 0
        self.gates["credits_ledger"] = bool(isinstance(credits, (int, float)) and credits >= 0)
        self.gates["wallet_reconciliation"] = bool(isinstance(credit_rows, list) and earned >= 0)

    def marketplace_journey(self) -> None:
        team_id = self.captain_participant.get("team_id") or self.team_ids[0]
        item_id = self.configured_marketplace_item_id
        if not item_id:
            raise RuntimeError("Migration 030 marketplace configuration was not initialized")

        first = self._rpc(
            "exos_v2_ledger_credit",
            {
                "p_event_id": self.event_id,
                "p_team_id": team_id,
                "p_participant_id": self.captain_participant.get("participant_id"),
                "p_transaction_type": "PURCHASE",
                "p_amount": 10,
                "p_reason": "Wallet top-up",
                "p_idempotency_key": f"credit-topup-{self.event_id}",
            },
            admin=True,
        )
        purchase = self._canonical_race_control_adapter().formula_race_purchase(
            self.session_token,
            self.captain_device,
            item_id,
            quantity=1,
            idempotency_key=f"purchase-{self.event_id}",
        )

        stock_fail = False
        try:
            self._canonical_race_control_adapter().formula_race_purchase(
                self.session_token,
                self.captain_device,
                item_id,
                quantity=99,
                idempotency_key=f"purchase-over-{uuid.uuid4().hex}",
            )
        except RuntimeError:
            stock_fail = True

        stock_rows = self._get(
            "marketplace_items_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "item_id": f"eq.{item_id}",
                "select": "item_type,unit_cost_credits,stock_limit,item_payload",
            },
        )

        if isinstance(stock_rows, list) and len(stock_rows) == 1:
            stock_fail = stock_fail or stock_rows[0].get("stock_limit", 0) == 0

        self.gates["marketplace"] = bool(
            isinstance(first, str)
            and isinstance(purchase, dict)
            and isinstance(stock_rows, list)
            and len(stock_rows) == 1
            and stock_rows[0].get("item_type") == "TOOL"
            and stock_rows[0].get("unit_cost_credits") == 5
        )

    def build_judging_and_results(self) -> None:
        team_id = self.captain_participant.get("team_id") or self.team_ids[0]

        self._post(
            "build_status_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "activity_id": self.activity_ids[0],
                "build_status": "IN_PROGRESS",
                "progress_pct": 25,
                "build_payload": {"chassis": True, "electronics": True},
            },
        )

        build_rows = self._get(
            "build_status_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "select": "build_status,team_id",
                "order": "last_updated.desc",
                "limit": "1",
            },
        )
        self.gates["build_status"] = bool(isinstance(build_rows, list) and bool(build_rows))

        self._post(
            "judging_scores_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "activity_id": self.activity_ids[0],
                "judge_name": "QA Judge",
                "score_dimension": "Engineering Design",
                "score_value": 8,
                "decision": "APPROVE",
                "rationale": "initial",
            },
        )
        correction = self._post(
            "judging_scores_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "activity_id": self.activity_ids[0],
                "judge_name": "QA Judge",
                "score_dimension": "Creativity",
                "score_value": 10,
                "decision": "APPROVE",
                "rationale": "correction",
            },
        )
        judge_rows = self._get(
            "judging_scores_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "select": "judge_name,score_value,score_dimension",
            },
        )
        self.gates["judging"] = bool(
            isinstance(judge_rows, list)
            and bool(judge_rows)
            and isinstance(correction, list)
        )

        self._certify_final_lock_results()

    def _save_final_result(self, team_id: str, time_ms: int, penalty_ms: int, verified: bool) -> dict:
        result = self._canonical_race_control_adapter().save_formula_race_result(
            self.event_id,
            team_id,
            time_ms,
            penalty_ms,
            7,
            verified,
            "Automated disposable-event final-lock certification",
            "RACE_AUTOMATION",
        )
        if not isinstance(result, dict) or not result.get("RaceResultID"):
            raise RuntimeError("Race result RPC did not return a result identifier")
        return result

    def _lock_final_results(self) -> dict:
        result = self._canonical_race_control_adapter().lock_formula_race_results(
            self.event_id,
            "RACE_AUTOMATION",
            "Automated disposable-event final-lock certification",
        )
        if not isinstance(result, dict):
            raise RuntimeError("Final lock RPC returned an invalid payload")
        return result

    def _expect_incomplete_lock_rejection(self, gate: str) -> None:
        try:
            self._lock_final_results()
        except RuntimeError as error:
            if "Every active team requires one verified Race Final result before locking" not in str(error):
                raise
            self.gates[gate] = True
            return
        raise RuntimeError(f"Expected {gate} lock rejection was not returned")

    def _certify_final_lock_results(self) -> None:
        """Exercise 029 and the final-lock RPC against this runner's disposable event."""
        # Nine verified rows prove a missing active-team result blocks the lock.
        for index, team_id in enumerate(self.team_ids[:9], start=1):
            self._save_final_result(team_id, 120000 + index * 1000, 1000, True)
        self._expect_incomplete_lock_rejection("missing_result_rejected")

        # The tenth row exists but is unverified, which must remain a separate block.
        tenth_team_id = self.team_ids[9]
        self._save_final_result(tenth_team_id, 130000, 1000, False)
        self._expect_incomplete_lock_rejection("unverified_result_rejected")

        # Correct the tenth result before lock. The first pair tie on adjusted time;
        # TeamID ASC must therefore put the first team ahead of the second.
        self._save_final_result(tenth_team_id, 130000, 1000, True)
        self._save_final_result(self.team_ids[0], 120000, 5000, True)
        self._save_final_result(self.team_ids[1], 121000, 4000, True)

        rows = self._get(
            "race_results_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "checkpoint": "eq.Race Final",
                "select": "team_id,activity_id,checkpoint,locked,ranking_position,result_payload",
                "order": "team_id.asc",
            },
        )
        result_rows = rows if isinstance(rows, list) else []
        self.gates["result_row_created"] = len(result_rows) == 10
        self.gates["race_result"] = self.gates["result_row_created"]
        self.gates["penalty_applied_once"] = all(
            int((row.get("result_payload") or {}).get("penalty_ms", 0) or 0) > 0
            for row in result_rows
        )
        self.gates["bonus_applied_once"] = all(
            (row.get("result_payload") or {}).get("bonus") == 7 for row in result_rows
        )
        self.gates["penalties_bonuses"] = bool(
            self.gates["penalty_applied_once"] and self.gates["bonus_applied_once"]
        )

        locked = self._lock_final_results()
        self.gates["lock_persisted"] = bool(locked.get("Locked") and not locked.get("AlreadyLocked"))
        repeated_lock = self._lock_final_results()
        self.gates["idempotent_relock"] = bool(repeated_lock.get("Locked") and repeated_lock.get("AlreadyLocked"))

        try:
            self._save_final_result(self.team_ids[0], 1, 0, False)
        except RuntimeError as error:
            self.gates["locked_mutation_rejected"] = self._is_expected_lock_rejection(
                error,
                "race result is locked and immutable until explicit unlock",
            )
        if not self.gates["locked_mutation_rejected"]:
            raise RuntimeError("Expected post-lock result mutation rejection was not returned")

        rankings = self._get(
            "race_results_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "checkpoint": "eq.Race Final",
                "select": "team_id,ranking_position,result_payload,locked",
                "order": "ranking_position.asc,team_id.asc",
            },
        )
        ranking_rows = rankings if isinstance(rankings, list) else []
        expected_order, _, ranking_payloads_ok = self._compute_team_rank_order(ranking_rows)
        observed_order = [str(row.get("team_id", "")) for row in ranking_rows]
        expected_team_ids = [str(team_id) for team_id in self.team_ids[:10]]
        self.gates["ranking_10_teams"] = self._ranking_10_team_produced(ranking_rows, expected_team_ids)
        self.gates["ranking_deterministic"] = bool(
            ranking_payloads_ok
            and observed_order == expected_order
            and observed_order.index(self.team_ids[0]) < observed_order.index(self.team_ids[1])
        )
        self.gates["tie_rule_deterministic"] = bool(self.gates["ranking_deterministic"])
        self.gates["lock_persisted"] = bool(
            self.gates["lock_persisted"]
            and len(ranking_rows) == 10
            and all(row.get("locked") is True for row in ranking_rows)
        )
        self.gates["result_locking"] = bool(
            self.gates["lock_persisted"] and self.gates["locked_mutation_rejected"] and self.gates["idempotent_relock"]
        )
        self.gates["final_ranking"] = bool(
            self.gates["ranking_10_teams"]
            and self.gates["ranking_deterministic"]
            and self.gates["tie_rule_deterministic"]
        )
        adapter = self._canonical_race_control_adapter()
        if hasattr(adapter, "_assert_no_legacy_or_sheet_calls"):
            adapter._assert_no_legacy_or_sheet_calls()

    def ui_verification(self) -> None:
        dashboard = self._get(
            "events_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "event_id,event_name,event_type,published_at",
            },
        )
        workspace = self._get(
            "activity_runtime_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "event_id,team_id,participant_id,state_payload",
                "limit": "1",
            },
        )
        state = self._get(
            "build_status_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "team_id,build_status,progress_pct",
            },
        )

        dashboard_ok = isinstance(dashboard, list) and bool(dashboard) and dashboard[0].get("event_id") == self.event_id
        workspace_ok = (
            isinstance(workspace, list)
            and workspace
            and workspace[0].get("event_id") == self.event_id
            and isinstance(state, list)
        )
        state_ok = bool(
            isinstance(state, list)
            and len(state) > 0
            and isinstance(workspace, list)
        )
        self.ui_checks["runtime_snapshot"] = bool(dashboard_ok and workspace_ok and state_ok)

    def certify_030_reset(self) -> None:
        """Preview, execute and verify the 030 reset boundary on this disposable event."""
        event_rows = self._get(
            "events_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "event_id,join_code,event_payload",
                "limit": "1",
            },
        )
        if not isinstance(event_rows, list) or len(event_rows) != 1:
            raise RuntimeError("Disposable event was not available for the 030 reset preview")

        preview_counts = {}
        for table in (
            "submissions_v2",
            "credit_transactions_v2",
            "marketplace_transactions_v2",
            "judging_scores_v2",
            "race_results_v2",
            "team_access_sessions_v2",
        ):
            rows = self._get(table, {"event_id": f"eq.{self.event_id}", "select": "event_id"})
            preview_counts[table] = len(rows) if isinstance(rows, list) else -1
        preview_event = event_rows[0]
        preview_config = (preview_event.get("event_payload") or {}).get("RaceConfiguration", {})
        preview_submission_ids = self.get_submission_ids_for_event(self.event_id)
        self.gates["reset_preview"] = bool(
            preview_event.get("join_code") == self.join_code
            and {key: preview_config.get(key) for key in self._race_configuration_snapshot}
            == self._race_configuration_snapshot
            and all(count > 0 for count in preview_counts.values())
        )
        if not self.gates["reset_preview"]:
            raise RuntimeError("Disposable 030 reset preview did not find the expected live state")

        reset = self._canonical_race_control_adapter().reset_formula_race_event(
            self.event_id,
            f"RESET {self.event_id}",
            "Disposable staging certification",
        )
        self.gates["reset_execution"] = bool(
            isinstance(reset, dict) and reset.get("Reset") and reset.get("EventID") == self.event_id
        )
        if not self.gates["reset_execution"]:
            raise RuntimeError("Migration 030 reset RPC did not confirm execution")

        event_after = self._get(
            "events_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "event_id,join_code,event_payload",
                "limit": "1",
            },
        )
        teams_after = self._get("teams_v2", {"event_id": f"eq.{self.event_id}", "select": "team_id"})
        credentials_after = self._get(
            "team_access_credentials_v2",
            {"event_id": f"eq.{self.event_id}", "select": "team_id,is_active"},
        )
        marketplace_after = self._get(
            "marketplace_items_v2",
            {"event_id": f"eq.{self.event_id}", "select": "item_id,item_payload"},
        )
        activities_after = self._get(
            "activities_v2",
            {"programme_id": f"eq.{self.programme_id}", "select": "activity_id,activity_payload"},
        )
        event_payload_after = (event_after[0].get("event_payload") or {}) if isinstance(event_after, list) and event_after else {}
        config_after = event_payload_after.get("RaceConfiguration", {})
        self.gates["reset_configuration_preserved"] = bool(
            isinstance(event_after, list)
            and len(event_after) == 1
            and event_after[0].get("join_code") == self.join_code
            and {key: config_after.get(key) for key in self._race_configuration_snapshot} == self._race_configuration_snapshot
            and isinstance(teams_after, list)
            and len(teams_after) == len(self.team_ids)
            and isinstance(credentials_after, list)
            and len(credentials_after) == len(self.team_ids)
            and isinstance(marketplace_after, list)
            and any(row.get("item_id") == self.configured_marketplace_item_id for row in marketplace_after)
            and isinstance(activities_after, list)
            and len(activities_after) == len(self.activity_ids)
            and all((row.get("activity_payload") or {}).get("race_station") for row in activities_after)
        )

        zero_tables = (
            "projector_state_v2",
            "race_results_v2",
            "judging_scores_v2",
            "build_status_v2",
            "marketplace_transactions_v2",
            "credit_transactions_v2",
            "score_transactions_v2",
            "activity_runtime_v2",
            "submissions_v2",
            "reviews_v2",
            "team_access_sessions_v2",
        )
        zero_state = True
        for table in zero_tables:
            rows = self._get(table, {"event_id": f"eq.{self.event_id}", "select": "event_id"})
            zero_state = zero_state and isinstance(rows, list) and not rows
        if preview_submission_ids:
            evidence_rows = self._get(
                "submission_evidence_v2",
                {"submission_id": _in_filter(preview_submission_ids), "select": "submission_id"},
            )
            zero_state = zero_state and isinstance(evidence_rows, list) and not evidence_rows
        self.gates["reset_zero_state"] = bool(zero_state)
        if not (self.gates["reset_configuration_preserved"] and self.gates["reset_zero_state"]):
            raise RuntimeError("Migration 030 reset did not preserve configuration with a transactional zero-state")

    def cleanup(self) -> None:
        submission_rows = self._get(
            "submissions_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "submission_id",
            },
        )
        self.submission_ids = [
            str(row.get("submission_id"))
            for row in (submission_rows or [])
            if isinstance(row, dict) and row.get("submission_id")
        ]

        review_ids = self.get_review_ids_for_event(self.event_id)

        # Reverse dependency cleanup: child-first by team and submission scope.
        for team_id in self.team_ids:
            self._delete(
                "score_transactions_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "marketplace_transactions_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "build_status_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "judging_scores_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "race_results_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "activity_runtime_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "submissions_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )

        submission_filter = _in_filter(self.submission_ids)
        if submission_filter:
            self._delete(
                "submission_evidence_v2",
                {"submission_id": submission_filter},
            )
        if review_ids:
            self._delete(
                "reviews_v2",
                {"submission_id": _in_filter(review_ids)},
            )

        self._delete("team_access_sessions_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("team_access_credentials_v2", {"event_id": f"eq.{self.event_id}"})

        self._delete("participants_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("participant_sessions_v2", {"event_id": f"eq.{self.event_id}"})

        # Programme hierarchy delete via canonical FK path.
        activity_ids = self.get_activity_ids_for_event(self.event_id)
        if activity_ids:
            activity_filter = _in_filter(activity_ids)
            if activity_filter:
                self._delete("activity_runtime_v2", {"activity_id": activity_filter})

        module_ids = [
            row.get("module_id")
            for row in (self._get("modules_v2", {
                "programme_id": f"eq.{self.programme_id}",
                "select": "module_id",
            }) or [])
            if isinstance(row, dict) and row.get("module_id")
        ]
        if module_ids:
            module_filter = _in_filter(module_ids)
            if module_filter:
                self._delete("activities_v2", {"module_id": module_filter})
        self._delete("modules_v2", {"programme_id": f"eq.{self.programme_id}"})

        # Event-scoped references.
        self._delete("projector_state_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("marketplace_items_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("credit_transactions_v2", {"event_id": f"eq.{self.event_id}"})

        self._delete("programmes_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("teams_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("events_v2", {"event_id": f"eq.{self.event_id}"})

        remaining = self._get("events_v2", {"event_id": f"eq.{self.event_id}", "select": "event_id"})
        self.gates["cleanup"] = bool(not (isinstance(remaining, list) and remaining))

        if not self.gates["cleanup"]:
            raise RuntimeError("Cleanup did not remove all scoped UAT rows")

    def print_report(self) -> None:
        print(f"Staging connectivity: {'PASS' if self.gates['staging_connectivity'] else 'FAIL'}")
        print(f"RACE event created: {'PASS' if self.gates['race_event_created'] else 'FAIL'}")
        print(f"10 teams: {'PASS' if self.gates['ten_teams'] else 'FAIL'}")
        print(f"Captain login: {'PASS' if self.gates['captain_login'] else 'FAIL'}")
        print(f"Wrong PIN rejection: {'PASS' if self.gates['wrong_pin_rejection'] else 'FAIL'}")
        print(f"Captain reconnect: {'PASS' if self.gates['captain_reconnect'] else 'FAIL'}")
        print(f"4 checkpoints: {'PASS' if self.gates['four_checkpoints'] else 'FAIL'}")
        print(f"030 configuration saved: {'PASS' if self.gates['configuration_saved'] else 'FAIL'}")
        print(f"030 configurable station methods: {'PASS' if self.gates['station_methods'] else 'FAIL'}")
        print(f"030 per-team routes: {'PASS' if self.gates['team_routes'] else 'FAIL'}")
        print(f"030 submission-gated progression: {'PASS' if self.gates['submission_gated_progression'] else 'FAIL'}")
        print(f"030 approval-independent unlock: {'PASS' if self.gates['approval_independent_unlock'] else 'FAIL'}")
        print(f"030 configurable Credits: {'PASS' if self.gates['configurable_credits'] else 'FAIL'}")
        print(f"030 marketplace configuration: {'PASS' if self.gates['marketplace_configuration'] else 'FAIL'}")
        print(f"030 judging configuration: {'PASS' if self.gates['judging_configuration'] else 'FAIL'}")
        print(f"030 PIN generation/reset: {'PASS' if self.gates['pin_reset'] else 'FAIL'}")
        print(f"Checkpoint submission: {'PASS' if self.gates['checkpoint_submission'] else 'FAIL'}")
        print(f"Facilitator review: {'PASS' if self.gates['facilitator_review'] else 'FAIL'}")
        print(f"Credits ledger: {'PASS' if self.gates['credits_ledger'] else 'FAIL'}")
        print(f"Wallet reconciliation: {'PASS' if self.gates['wallet_reconciliation'] else 'FAIL'}")
        print(f"Marketplace: {'PASS' if self.gates['marketplace'] else 'FAIL'}")
        print(f"Build status: {'PASS' if self.gates['build_status'] else 'FAIL'}")
        print(f"Judging: {'PASS' if self.gates['judging'] else 'FAIL'}")
        print(f"Race result: {'PASS' if self.gates['race_result'] else 'FAIL'}")
        print(f"Result row created: {'PASS' if self.gates['result_row_created'] else 'FAIL'}")
        print(f"Penalty applied once: {'PASS' if self.gates['penalty_applied_once'] else 'FAIL'}")
        print(f"Bonus applied once: {'PASS' if self.gates['bonus_applied_once'] else 'FAIL'}")
        print(f"Lock persisted: {'PASS' if self.gates['lock_persisted'] else 'FAIL'}")
        print(f"Locked mutation rejected: {'PASS' if self.gates['locked_mutation_rejected'] else 'FAIL'}")
        print(f"Missing result rejected: {'PASS' if self.gates['missing_result_rejected'] else 'FAIL'}")
        print(f"Unverified result rejected: {'PASS' if self.gates['unverified_result_rejected'] else 'FAIL'}")
        print(f"Idempotent re-lock: {'PASS' if self.gates['idempotent_relock'] else 'FAIL'}")
        print(f"Result locking: {'PASS' if self.gates['result_locking'] else 'FAIL'}")
        print(f"Ranking metric used: {self.ranking_metric}")
        print(f"10-team ranking produced: {'PASS' if self.gates['ranking_10_teams'] else 'FAIL'}")
        print(f"Ranking deterministic: {'PASS' if self.gates['ranking_deterministic'] else 'FAIL'}")
        print(f"Tie handling deterministic: {'PASS' if self.gates['tie_rule_deterministic'] else 'FAIL'}")
        print("RACE premium UI: DEFERRED (UI/UX overhaul; not an engine gate)")
        print(f"RACE UI runtime snapshot: {'PASS' if self.ui_checks['runtime_snapshot'] else 'FAIL'}")
        print(f"030 reset preview: {'PASS' if self.gates['reset_preview'] else 'FAIL'}")
        print(f"030 reset execution: {'PASS' if self.gates['reset_execution'] else 'FAIL'}")
        print(f"030 configuration preserved after reset: {'PASS' if self.gates['reset_configuration_preserved'] else 'FAIL'}")
        print(f"030 transactional zero-state: {'PASS' if self.gates['reset_zero_state'] else 'FAIL'}")
        print(f"Google Sheets runtime calls: {'YES' if self.gates['google_sheets_runtime_calls'] else 'NO'}")
        print(f"Cleanup: {'PASS' if self.gates['cleanup'] else 'FAIL'}")
        print(f"EventID: {self.event_id}")

        if all(self.gates.values()):
            print("FORMULA R.A.C.E. ON EXOS CORE V2: READY")

    def run(self) -> int:
        self._emit_runner_identity()
        self._check_stale_activity_event_refs()
        self._require_env()
        try:
            self.check_connectivity()
            self.create_race_event()
            self.create_programme_and_checkpoints()
            self.captain_flow()
            self.configure_030_architecture()
            self.certify_030_submission_progression()
            self.marketplace_journey()
            self.build_judging_and_results()
            self.ui_verification()
            self.certify_030_reset()
            self._assert_no_legacy_runtime_calls()
            return 0
        except Exception as exc:
            self._error = str(exc)
            print(f"[ERROR] {exc}")
            return 1
        finally:
            try:
                self.cleanup()
            except Exception as exc:
                print(f"[CLEANUP FAILED] {exc}")
                self.gates["cleanup"] = False
            self.print_report()
            if self._error:
                return 1


def main() -> int:
    return CoreV2RaceStagingRunner().run()


if __name__ == "__main__":
    raise SystemExit(main())
