from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "exos_core_v2_staging_race_vertical_slice.py"

SCHEMA_COLUMNS = {
    "events_v2": {
        "event_id",
        "event_name",
        "join_code",
        "event_type",
        "programme_type",
        "scoring_mode",
        "lifecycle_status",
        "event_payload",
        "published_at",
        "created_at",
        "updated_at",
    },
    "programmes_v2": {
        "programme_id",
        "event_id",
        "programme_name",
        "programme_type",
        "programme_schema_version",
        "module_count",
        "is_active",
        "published_at",
        "created_at",
        "updated_at",
    },
    "modules_v2": {
        "module_id",
        "programme_id",
        "module_name",
        "activity_sequence",
        "module_payload",
        "scoring_mode",
        "is_active",
        "created_at",
        "updated_at",
    },
    "activities_v2": {
        "activity_id",
        "module_id",
        "programme_id",
        "activity_type",
        "scoring_mode",
        "activity_name",
        "activity_order",
        "duration_seconds",
        "activity_payload",
        "is_active",
        "created_at",
        "updated_at",
    },
    "teams_v2": {
        "team_id",
        "event_id",
        "team_name",
        "country",
        "team_flag",
        "is_active",
        "created_at",
    },
    "team_access_credentials_v2": {
        "team_access_credential_id",
        "event_id",
        "team_id",
        "credential_hash",
        "credential_purpose",
        "is_active",
        "created_by",
        "created_at",
        "updated_at",
    },
    "team_access_sessions_v2": {
        "team_access_session_id",
        "event_id",
        "team_access_credential_id",
        "team_id",
        "device_id",
        "session_token",
        "is_active",
        "recovery_required",
        "takeover_by_session_id",
        "created_by",
        "last_seen_at",
        "created_at",
        "updated_at",
    },
    "submissions_v2": {
        "submission_id",
        "event_id",
        "team_id",
        "participant_id",
        "activity_id",
        "runtime_id",
        "submission_key",
        "submission_status",
        "submission_payload",
        "submitted_at",
        "reviewed_at",
        "reviewed_by",
        "score",
        "created_at",
        "updated_at",
    },
    "submission_evidence_v2": {
        "evidence_id",
        "submission_id",
        "evidence_type",
        "evidence_uri",
        "evidence_payload",
        "captured_by",
        "captured_at",
    },
    "reviews_v2": {
        "review_id",
        "event_id",
        "submission_id",
        "reviewer",
        "decision",
        "score_points",
        "rationale",
        "reviewed_at",
        "created_at",
    },
    "score_transactions_v2": {
        "score_transaction_id",
        "event_id",
        "team_id",
        "submission_id",
        "scoring_mode",
        "score_delta",
        "reason",
        "idempotency_key",
        "source_reference",
        "created_at",
        "created_by",
    },
    "credit_transactions_v2": {
        "credit_transaction_id",
        "event_id",
        "team_id",
        "participant_id",
        "transaction_type",
        "amount",
        "idempotency_key",
        "reason",
        "created_at",
        "created_by",
    },
    "marketplace_items_v2": {
        "item_id",
        "event_id",
        "item_name",
        "item_type",
        "unit_cost_credits",
        "stock_limit",
        "is_active",
        "item_payload",
        "created_at",
    },
    "marketplace_transactions_v2": {
        "marketplace_transaction_id",
        "event_id",
        "team_id",
        "item_id",
        "credit_transaction_id",
        "quantity",
        "amount_paid",
        "status",
        "idempotency_key",
        "purchased_at",
    },
    "activity_runtime_v2": {
        "runtime_id",
        "event_id",
        "team_id",
        "participant_id",
        "activity_id",
        "session_id",
        "state_payload",
        "activity_started_at",
        "activity_ended_at",
        "checkpoint_count",
        "completion_ratio",
        "is_completed",
        "updated_at",
    },
    "build_status_v2": {
        "event_id",
        "team_id",
        "activity_id",
        "build_status",
        "progress_pct",
        "build_payload",
        "started_at",
        "completed_at",
        "last_updated",
    },
    "judging_scores_v2": {
        "judging_score_id",
        "event_id",
        "team_id",
        "activity_id",
        "judge_name",
        "score_dimension",
        "score_value",
        "decision",
        "rationale",
        "recorded_at",
    },
    "race_results_v2": {
        "race_result_id",
        "event_id",
        "team_id",
        "activity_id",
        "checkpoint",
        "ranking_position",
        "result_payload",
        "locked",
        "recorded_at",
        "updated_at",
    },
    "projector_state_v2": {
        "event_id",
        "team_id",
        "projection_stage",
        "state_payload",
        "visible_to_event",
        "updated_at",
    },
    "participants_v2": {
        "participant_id",
        "event_id",
        "team_id",
        "normalized_name",
        "display_name",
        "participant_payload",
        "country",
        "flag",
        "participant_status",
        "is_leader",
        "team_leader_at",
        "intelligence_credits",
        "merged_into_participant_id",
        "is_archived",
        "created_at",
        "last_seen_at",
    },
    "participant_sessions_v2": {
        "participant_session_id",
        "event_id",
        "participant_id",
        "device_id",
        "session_token",
        "idempotency_key",
        "joined_from_client",
        "last_seen_at",
        "created_at",
        "is_active",
    },
}

RESERVED_QUERY_KEYS = {"order", "select", "limit", "on_conflict"}


def _iter_table_ops() -> list[tuple[str, str, set[str], int]]:
    source = SCRIPT.read_text()
    tree = ast.parse(source)
    ops: list[tuple[str, str, set[str], int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute):
            continue
        if fn.attr not in {"_get", "_post", "_patch", "_delete"}:
            continue

        if len(node.args) < 2:
            continue
        table_node = node.args[0]
        if not isinstance(table_node, ast.Constant) or not isinstance(table_node.value, str):
            continue
        table = table_node.value

        query_node = node.args[1]
        if not isinstance(query_node, ast.Dict):
            continue
        keys: set[str] = set()
        for key in query_node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value not in RESERVED_QUERY_KEYS:
                    keys.add(key.value)

        # Column usage in explicit select/order clauses should be validated too.
        keys.update(_collect_columns_from_select(query_node))
        keys.update(_collect_columns_from_order(query_node))
        ops.append((fn.attr, table, keys, node.lineno))
    return ops


def _iter_order_and_select_literals(query_node: ast.Dict) -> list[ast.expr]:
    for key_node, value_node in zip(query_node.keys, query_node.values):
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            continue
        if key_node.value in {"order", "select"}:
            yield value_node


def _collect_columns_from_select(query_node: ast.Dict) -> set[str]:
    columns: set[str] = set()
    for value_node in _iter_order_and_select_literals(query_node):
        if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
            raw = value_node.value
            # Examples: "event_id,team_id" or "event_id, created_at:desc"
            for raw_token in raw.split(","):
                token = raw_token.strip()
                if not token:
                    continue
                # strip aliases/functions
                token = token.split(":")[0].split(" as ")[0].split("(")[0].strip()
                columns.add(token)
    return columns


def _collect_columns_from_order(query_node: ast.Dict) -> set[str]:
    columns: set[str] = set()
    for value_node in _iter_order_and_select_literals(query_node):
        if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
            raw = value_node.value
            for raw_token in raw.split(","):
                token = raw_token.strip()
                if not token:
                    continue
                token = token.split(":")[0].split(" ")[0]
                token = token.split(".")[0]
                columns.add(token)
    return columns


def _normalize_column(token: str) -> str:
    return token.strip().split(":")[0].split(".")[0].split(" ")[0]


def test_runner_core_v2_schema_column_contract() -> None:
    violations: list[str] = []
    for method, table, columns, lineno in _iter_table_ops():
        known = SCHEMA_COLUMNS.get(table)
        if not known:
            continue
        invalid = sorted({
            _normalize_column(col)
            for col in columns
            if _normalize_column(col) not in known
        })
        if invalid:
            violations.append(f"{table} {method} at line {lineno}: invalid columns {invalid}")

    assert not violations, f"Runner has invalid table-column assumptions: {violations}"


def test_runner_disallow_core_mapped_invalid_shortcuts() -> None:
    source = SCRIPT.read_text()
    assert '"activities_v2",\n                {\n                "event_id"' not in source
    assert '"reviews_v2",\n                {\n                "team_id"' not in source
    assert '"submission_evidence_v2",\n                {\n                "event_id"' not in source
