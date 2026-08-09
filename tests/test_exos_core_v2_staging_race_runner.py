import ast
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "exos_core_v2_staging_race_vertical_slice.py"

spec = importlib.util.spec_from_file_location("exos_core_v2_staging_race_vertical_slice", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)  # type: ignore[arg-type]
CoreV2RaceStagingRunner = module.CoreV2RaceStagingRunner


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
