from pathlib import Path

import pytest

from engines.formula_race_checkpoints import (
    checkpoint_progress, deterministic_checkpoint_order, is_formula_race_event,
    module_templates, parallel_runtime_payload,
)
from engines.programme_adapter import CanonicalProgrammeAdapter, ProgrammeIntegrityError


def checkpoints():
    return [{"ActivityID": f"CP-{number}", "Active": True, "Status": "AVAILABLE"} for number in range(1, 5)]


def test_formula_race_catalogue_is_product_specific_and_has_parallel_module():
    race = module_templates({"ProgrammeType": "Formula R.A.C.E."})
    assert [row[1] for row in race] == ["Launch EXOS", "RACE Checkpoints", "Marketplace / Spend Credits", "Build", "Team Photo", "Drag Race", "Judging", "Championship"]
    assert module_templates({"ProgrammeType": "Mission AI"}) is None
    assert is_formula_race_event({"EventName": "RACE"})
    assert is_formula_race_event({"EventName": "RACE", "ProgrammeType": "Team Building"})


def test_team_checkpoint_order_is_deterministic_across_refresh_and_reconnect():
    first = [row["ActivityID"] for row in deterministic_checkpoint_order(checkpoints(), "EVT-0006", "F1-01")]
    refreshed = [row["ActivityID"] for row in deterministic_checkpoint_order(checkpoints(), "EVT-0006", "F1-01")]
    reconnected = [row["ActivityID"] for row in deterministic_checkpoint_order(list(reversed(checkpoints())), "EVT-0006", "F1-01")]
    assert first == refreshed == reconnected


def test_different_teams_receive_different_checkpoint_order():
    orders = {tuple(row["ActivityID"] for row in deterministic_checkpoint_order(checkpoints(), "EVT-0006", f"F1-{n:02}")) for n in range(1, 11)}
    assert len(orders) > 1


def test_progress_moves_from_zero_to_four_and_completes():
    rows = checkpoints()
    assert checkpoint_progress(rows) == {"Approved": 0, "Total": 4, "Complete": False}
    for row in rows: row["Status"] = "APPROVED"
    assert checkpoint_progress(rows) == {"Approved": 4, "Total": 4, "Complete": True}


def test_parallel_runtime_payload_contains_all_four_activity_ids():
    payload = parallel_runtime_payload("EVT-0006", "RACE-MOD", checkpoints())
    assert payload["ModuleType"] == "RACE_CHECKPOINTS"
    assert payload["ParallelActivityIDs"] == ["CP-1", "CP-2", "CP-3", "CP-4"]


def _row(activity, order):
    return {"EventID": "E1", "ProgrammeID": "E1-PROGRAMME", "ModuleID": "RACE-MOD", "ActivityID": activity,
        "ModuleOrder": 1, "ActivityOrder": order, "StageNo": order, "StageName": activity,
        "ModuleName": "RACE Checkpoints", "ContentType": "RACE Checkpoints", "IsActive": "Yes"}


def test_projector_parallel_resolution_and_single_activity_regression():
    snapshot = CanonicalProgrammeAdapter("E1", [_row(f"CP-{n}", n) for n in range(1, 5)]).snapshot().require_valid()
    module, activities = snapshot.resolve_runtime_set({"ModuleID": "RACE-MOD", "ParallelActivityIDs": ["CP-1", "CP-2", "CP-3", "CP-4"]})
    assert module["ModuleID"] == "RACE-MOD" and len(activities) == 4
    _, single = snapshot.resolve_runtime({"ActivityID": "CP-2"})
    assert single["ActivityID"] == "CP-2"
    with pytest.raises(ProgrammeIntegrityError):
        snapshot.resolve_runtime_set({"ModuleID": "RACE-MOD", "ParallelActivityIDs": ["CP-1", "FOREIGN"]})


def test_migration_contract_reuses_canonical_pipeline_and_guards_isolation():
    sql = Path("supabase/019_formula_race_parallel_checkpoints.sql").read_text()
    for contract in ["canonical_submissions", "exos_decide_canonical_submission", "award_transactions",
                     "runtime_credit_transactions", "runtime_team_wallets", "event_id=a.event_id",
                     "team_id=a.team_id", "PENDING_REVIEW", "RETURNED_FOR_REVISION"]:
        assert contract in sql
    assert "Exactly four active RACE checkpoints are required" in sql
    assert "source_id=s.submission_id" in sql
