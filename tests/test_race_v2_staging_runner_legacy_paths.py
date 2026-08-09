from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
RACE_RUNNER = ROOT / "scripts" / "exos_core_v2_staging_race_vertical_slice.py"

FORBIDDEN_LEGACY_RUNTIME_PATH_FRAGMENTS = {
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


class _LegacyRequestCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.legacy_calls = []

    def visit_Call(self, node: ast.Call) -> None:
        fn = node.func
        fn_name = fn.attr if isinstance(fn, ast.Attribute) and isinstance(fn.attr, str) else ""

        if fn_name in {"_request", "_get", "_post", "_delete"}:
            if fn_name == "_request":
                first_arg = node.args[1] if len(node.args) > 1 else None
            else:
                first_arg = node.args[0] if node.args else None

            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                path = first_arg.value.lower()
                if any(fragment in path for fragment in FORBIDDEN_LEGACY_RUNTIME_PATH_FRAGMENTS):
                    self.legacy_calls.append((path, node.lineno))

        self.generic_visit(node)


def test_staging_race_runner_has_legacy_guard_counter():
    source = RACE_RUNNER.read_text()
    assert "LEGACY_RUNTIME_TABLE_PATTERNS" in source
    assert "_assert_no_legacy_runtime_calls" in source


def test_staging_race_runner_no_direct_legacy_runtime_table_paths():
    tree = ast.parse(RACE_RUNNER.read_text())
    collector = _LegacyRequestCollector()
    collector.visit(tree)
    assert not collector.legacy_calls, f"Legacy runtime paths used in runner requests: {collector.legacy_calls}"
