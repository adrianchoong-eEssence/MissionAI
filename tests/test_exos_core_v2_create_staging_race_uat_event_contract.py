from __future__ import annotations

import ast
from pathlib import Path

from test_race_v2_staging_runner_schema_contract import SCHEMA_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "exos_core_v2_create_staging_race_uat_event.py"

EXPECTED_TABLE_PAYLOADS = {
    "programmes_v2": {"programme_id", "event_id", "programme_name", "programme_type", "module_count", "is_active"},
    "modules_v2": {
        "module_id",
        "programme_id",
        "module_name",
        "activity_sequence",
        "module_payload",
        "scoring_mode",
        "is_active",
    },
    "activities_v2": {
        "activity_id",
        "programme_id",
        "module_id",
        "activity_name",
        "activity_type",
        "scoring_mode",
        "activity_order",
        "duration_seconds",
        "activity_payload",
        "is_active",
    },
    "marketplace_items_v2": {
        "event_id",
        "item_id",
        "item_name",
        "item_type",
        "unit_cost_credits",
        "stock_limit",
        "is_active",
    },
    "events_v2": {
        "event_payload",
    },
}

EXPECTED_RPC_PARAMS = {
    "exos_v2_publish_event": {"p_event_id", "p_join_code", "p_event_name", "p_teams", "p_scoring_mode", "p_event_type"},
    "exos_v2_set_team_access_pin": {"p_event_id", "p_team_id", "p_pin", "p_actor"},
}


def _iter_payload_calls() -> list[tuple[str, dict[str, object], int]]:
    tree = ast.parse(SCRIPT.read_text())
    rows: list[tuple[str, dict[str, object], int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or fn.attr not in {"post", "patch", "rpc"}:
            continue

        if len(node.args) < 2:
            continue
        table_node = node.args[0]
        payload_node = node.args[1]

        if not isinstance(table_node, ast.Constant) or not isinstance(table_node.value, str):
            continue
        table = table_node.value

        if not isinstance(payload_node, ast.Dict):
            continue

        keys: dict[str, object] = {}
        for k_node, v_node in zip(payload_node.keys, payload_node.values):
            if not isinstance(k_node, ast.Constant) or not isinstance(k_node.value, str):
                continue
            keys[k_node.value] = v_node
        rows.append((table if fn.attr in {"post", "patch"} else table, keys, getattr(node, "lineno", 0)))
    return rows


def test_uat_creator_schema_contract() -> None:
    rows = _iter_payload_calls()
    violations: list[str] = []

    for table, payload, lineno in rows:
        schema = SCHEMA_COLUMNS.get(table)
        if not schema:
            continue
        unknown = sorted(set(payload.keys()) - schema)
        if unknown:
            violations.append(f"{table} payload at line {lineno} has unknown fields: {unknown}")

    for table in ("modules_v2", "activities_v2", "programmes_v2", "marketplace_items_v2"):
        assert table in {row[0] for row in rows}, f"Creator must create {table} rows."

    assert not violations, f"Creator payload keys do not match Core v2 schema: {violations}"


def _iter_rpc_payloads() -> list[tuple[str, dict[str, object], int]]:
    tree = ast.parse(SCRIPT.read_text())
    rows: list[tuple[str, dict[str, object], int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or fn.attr != "rpc":
            continue
        if len(node.args) < 2:
            continue
        rpc_node = node.args[0]
        payload_node = node.args[1]
        if not isinstance(rpc_node, ast.Constant) or not isinstance(rpc_node.value, str):
            continue
        if not isinstance(payload_node, ast.Dict):
            continue
        keys: dict[str, object] = {}
        for k_node, v_node in zip(payload_node.keys, payload_node.values):
            if not isinstance(k_node, ast.Constant) or not isinstance(k_node.value, str):
                continue
            keys[k_node.value] = v_node
        rows.append((rpc_node.value, keys, getattr(node, "lineno", 0)))
    return rows


def test_uat_creator_rpc_payload_contract() -> None:
    rows = _iter_rpc_payloads()
    violations: list[str] = []

    for rpc, payload, lineno in rows:
        expected = EXPECTED_RPC_PARAMS.get(rpc)
        if not expected:
            continue
        unknown = sorted(set(payload.keys()) - expected)
        if unknown:
            violations.append(f"{rpc} payload at line {lineno} has unexpected keys: {unknown}")

    assert not violations, f"Creator RPC payload keys do not match known contracts: {violations}"
