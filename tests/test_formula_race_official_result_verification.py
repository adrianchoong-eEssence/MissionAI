"""Regression coverage for facilitator-owned official result verification.

Migration 033 made the official result facilitator-owned, so the Captain no
longer submits one.  `exos_v2_formula_race_verify_station_result` still refuses
to approve a measured station without a result, which crashed Race Control's
Review Queue with RuntimeDatabaseError.  Station Results already collected the
value; the Review Queue did not.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
from engines.formula_race_configuration import CAPTAIN_RESULT_METHODS
from screens.formula_race import _official_result_control

ROOT = Path(__file__).resolve().parents[1]


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


class _DisposableRuntime:
    is_configured = True
    can_publish = True
    url = "https://staging.disposable.example.test"

    def _request(self, *_args, **_kwargs):
        return []


def test_unmeasured_stations_never_require_an_official_result():
    """Proof-only and facilitator-scored stations keep their existing approval."""
    for station in ({}, {"ScoringMethod": "NON_SCORING"}, {"ScoringMethod": "FACILITATOR_SCORE"}):
        assert _official_result_control(station, "DISPOSABLE-SUBMISSION") == (None, False)


def test_verification_rpc_receives_the_facilitator_official_result():
    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(_DisposableRuntime())
    captured: dict[str, dict] = {}

    def fake_rpc(name, payload, admin=True):
        captured[name] = payload
        return {}

    adapter._rpc = fake_rpc
    adapter._get = lambda *_args, **_kwargs: []
    adapter.formula_race_review_checkpoint(
        "00000000-0000-0000-0000-000000000042",
        "APPROVE",
        "Disposable Facilitator",
        official_result=18250,
    )

    payload = captured["exos_v2_formula_race_verify_station_result"]
    assert payload["p_decision"] == "APPROVE"
    assert payload["p_official_result"] == 18250


def test_review_queue_collects_the_result_the_verification_contract_requires():
    migration = (ROOT / "supabase" / "030_formula_race_configurable_event_architecture.sql").read_text()
    assert "An official result is required for this station" in migration
    for method in CAPTAIN_RESULT_METHODS:
        assert method in migration

    source = (ROOT / "screens" / "formula_race.py").read_text()
    assert "_official_result_control(station_by_submission.get(str(x.id), {}), x.id)" in source
    assert 'official_result if decision == "APPROVE" else None' in source
    # A measured station cannot be approved until its official result is entered.
    assert "or awaiting_result" in source
