"""Local contract tests for the staging-only Team Formation V1 harness."""

import importlib.util
from pathlib import Path
import sys
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "certify_team_formation_v1.py"


def load_module():
    spec = importlib.util.spec_from_file_location("certify_team_formation_v1", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_harness_is_inert_without_execute_and_documents_real_concurrency():
    module = load_module()
    plan = module.plan()
    assert plan["Executed"] is False
    assert "250 independent simultaneous public RPC calls" in plan["Concurrency"]["RANDOM_ASSIGN_250"]
    assert "RACE4CF0CE" in plan["Safety"][3]
    assert len(plan["Gate4ThemeParkRace"]["Assertions"]) == 32
    assert plan["Gate4ThemeParkRace"]["Fixture"].startswith("CERT-TPR-*")
    source = SCRIPT_PATH.read_text()
    assert "ThreadPoolExecutor(max_workers=len(people)" in source
    assert "threading.Barrier(len(people))" in source
    assert "result = run(args) if args.execute else plan()" in source


def test_fixture_credentials_are_opaque_duplicate_names_are_deliberate_and_preassigned_is_stable():
    module = load_module()
    fixture = module.make_fixture("TEST", "PREASSIGNED", 2, 2, "TEST-RUN")
    people = module.build_people(fixture, 4, preassigned=True)
    assert all(len(person.enrollment_credential) == 43 for person in people)
    assert len({person.enrollment_credential for person in people}) == 4
    assert len({person.display_name for person in people}) < 4
    assert [person.expected_team_id for person in people] == [
        fixture.team_ids[0], fixture.team_ids[0], fixture.team_ids[1], fixture.team_ids[1],
    ]
    assert all(len(module.sha256_hex(person.enrollment_credential)) == 64 for person in people)


def test_parallel_runner_uses_all_workers_and_reports_latency_without_a_database():
    module = load_module()
    fixture = module.make_fixture("PAR", "RANDOM_ASSIGN", 2, 2, "TEST-RUN")
    people = module.build_people(fixture, 4, preassigned=False)
    seen_threads = set()
    lock = threading.Lock()

    def call(person):
        with lock:
            seen_threads.add(threading.current_thread().name)
        return {"ParticipantID": str(person.index), "TeamID": "T"}

    operations, summary = module.run_parallel("local parallel proof", people, call, 1)
    assert len(operations) == 4
    assert summary["ConcurrencyWorkers"] == 4
    assert summary["SuccessfulOperations"] == 4
    assert len(seen_threads) == 4
    assert summary["LatencyMs"]["StartSkew"] is not None


def test_sentinel_and_cleanup_controls_are_scoped_to_cert_tf_and_never_use_race_as_a_fixture():
    module = load_module()
    source = SCRIPT_PATH.read_text()
    assert len(module.SENTINEL_TABLES) == 10
    assert "audit_log_v2" in module.CERT_RESIDUE_TABLES
    assert "race_results_v2" in module.CERT_RESIDUE_TABLES
    assert module.SENTINEL_JOIN_CODE == "RACE4CF0CE"
    assert "CERT-TF-*" in source
    assert "WHERE event_id = {quoted}" in source
    assert "set_config('exos.team_formation_write', event_id, true)" in source
    assert "event_id LIKE 'CERT-TF-%'" in source
    assert "make_fixture(\"RND66\"" in source
    assert "make_fixture(\"RND250\"" in source
    assert "make_fixture(\"PRE250\"" in source
    assert "THEME_PARK_CERT_PREFIX = \"CERT-TPR-\"" in source
    assert "event_id LIKE 'CERT-TF-%' OR event_id LIKE 'CERT-TPR-%'" in source
    assert "run_theme_park_gate4" in source
    assert "RACE4CF0CE" in source


def test_execution_requires_explicit_staging_credentials_and_confirmation(monkeypatch):
    module = load_module()
    monkeypatch.delenv("EXOS_ENV", raising=False)
    args = type("Args", (), {"http_timeout": 60})()
    with pytest.raises(module.HarnessError, match="EXOS_ENV must be exactly staging"):
        module.require_execution_environment(args)
