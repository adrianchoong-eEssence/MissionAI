import importlib.util
from pathlib import Path

from scripts.rc2_mobile_matrix import BROWSERS, FIELDS, SCENARIOS, rows
from scripts.verify_runtime_compatibility import runtime_report


ROOT = Path(__file__).resolve().parents[1]


def test_mobile_matrix_is_exactly_52_unique_cells():
    matrix = rows()
    assert len(BROWSERS) == 4
    assert len(SCENARIOS) == 13
    assert len(matrix) == 52
    assert len({(row["Browser"], row["Scenario"]) for row in matrix}) == 52
    for required in ("ParticipantIDBefore", "ParticipantIDAfter", "TeamIDBefore",
                     "TeamIDAfter", "CreditsBefore", "CreditsAfter", "Result"):
        assert required in FIELDS


def test_runtime_pin_and_compatibility_contract_exist():
    assert (ROOT / ".python-version").read_text().strip() == "3.12.11"
    report = runtime_report()
    assert report["PythonMinimum"] == "3.11"
    assert report["OpenSSLMinimum"] == "1.1.1"


def test_audit_scripts_are_directly_importable():
    for name in ("programme_hierarchy_audit", "experience_migration_audit",
                 "transaction_migration_audit"):
        path = ROOT / "scripts" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert callable(module.run_audit)


def test_rc2_audit_orchestrator_is_select_only():
    source = (ROOT / "scripts" / "rc2_production_audits.py").read_text()
    assert '"Mode": "SELECT_ONLY"' in source
    assert '"ProductionRecordsChanged": False' in source
    for forbidden in ('"POST"', '"PATCH"', '"DELETE"'):
        assert forbidden not in source
