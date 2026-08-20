"""Sprint 1 — truth and contracts for EXOS results.

A live event encoded four non-finishers as multi-million millisecond finish
times so they would rank.  These tests hold the line against that: a status is
first class, a non-finisher never carries a time, placement is explicit and
unique, humans work in minutes and seconds, and every layer agrees on who owns
the official result.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import pytest

from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
from engines.exos_result_contract import (
    DEFAULT_RESULT_ENTRY_OWNER, MEASURED_RESULT_STATUSES, RESULT_ENTRY_OWNERS, RESULT_STATUSES,
    describe_result, duration_ms, format_duration_ms, is_measured, normalise_race_result,
    normalise_result_entry_owner, normalise_result_status, rank_race_results, split_duration_ms,
    validate_race_result, validate_race_results,
)
from engines.formula_race_configuration import RESULT_ENTRY_OWNERS as CONFIGURATION_OWNERS, normalise_station

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "supabase" / "035_formula_race_result_status_and_placement.sql").read_text()


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


class _CapturingRuntime:
    is_configured = True
    can_publish = True
    url = "https://staging.disposable.example.test"

    def __init__(self):
        self.calls = []

    def _request(self, method, path, payload=None, query=None, admin=True):
        self.calls.append((path, payload))
        return {"RaceResultID": "DISPOSABLE-RESULT"}


def _adapter(runtime):
    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)
    adapter._get_checkpoint_activities = lambda _event_id: [{"activity_id": "DISPOSABLE-ACTIVITY"}]
    return adapter


# --------------------------------------------------------------------------
# 1-4  Result status contract
# --------------------------------------------------------------------------

def test_status_vocabulary_is_small_and_measured_status_is_explicit():
    assert RESULT_STATUSES == ("FINISHED", "DNF", "DNS", "DISQUALIFIED")
    assert MEASURED_RESULT_STATUSES == ("FINISHED",)
    assert is_measured("FINISHED") and not any(is_measured(s) for s in ("DNF", "DNS", "DISQUALIFIED"))


def test_finished_result_keeps_its_measured_time():
    row = normalise_race_result({"team_id": "T1", "result_status": "FINISHED", "time_ms": 63500, "penalty_ms": 2000})
    assert row["TimeMs"] == 63500 and row["PenaltyMs"] == 2000 and row["AdjustedMs"] == 65500
    assert row["ManualPlacement"] is None
    assert validate_race_result({"team_id": "T1", "result_status": "FINISHED", "time_ms": 63500}) == []


@pytest.mark.parametrize("status", ["DNF", "DNS", "DISQUALIFIED"])
def test_unmeasured_status_never_carries_a_time(status):
    row = normalise_race_result({"team_id": "T1", "result_status": status, "time_ms": 9_999_999, "penalty_ms": 5000})
    assert row["TimeMs"] is None and row["AdjustedMs"] is None and row["PenaltyMs"] == 0
    assert validate_race_result({"team_id": "T1", "result_status": status, "time_ms": 9_999_999}) == [
        f"A {status} result must not carry a finish time."
    ]
    assert validate_race_result({"team_id": "T1", "result_status": status, "manual_placement": 7}) == []


def test_absent_status_reads_as_finished_so_historical_rows_keep_meaning():
    assert normalise_result_status(None) == "FINISHED"
    assert normalise_result_status("") == "FINISHED"
    assert normalise_result_status("did not finish") == "DNF"
    assert normalise_result_status("nonsense") == "FINISHED"


# --------------------------------------------------------------------------
# 5-6  Manual placement
# --------------------------------------------------------------------------

def test_manual_placement_ranks_non_finishers_behind_every_finisher():
    """The live shape: six measured finishes, four observed placements."""
    rows = [
        {"team_id": "F-03", "result_status": "FINISHED", "time_ms": 61000},
        {"team_id": "F-01", "result_status": "FINISHED", "time_ms": 45000},
        {"team_id": "F-02", "result_status": "FINISHED", "time_ms": 45000, "penalty_ms": 5000},
        {"team_id": "F-04", "result_status": "FINISHED", "time_ms": 72000},
        {"team_id": "F-05", "result_status": "FINISHED", "time_ms": 80000},
        {"team_id": "F-06", "result_status": "FINISHED", "time_ms": 91000},
        {"team_id": "N-Sandstorm", "result_status": "DNF", "manual_placement": 10},
        {"team_id": "N-Lakas", "result_status": "DNF", "manual_placement": 7},
        {"team_id": "N-Drift", "result_status": "DNF", "manual_placement": 9},
        {"team_id": "N-Papaya", "result_status": "DNF", "manual_placement": 8},
    ]
    ranked = rank_race_results(rows)
    assert [row["TeamID"] for row in ranked] == [
        "F-01", "F-02", "F-03", "F-04", "F-05", "F-06",
        "N-Lakas", "N-Papaya", "N-Drift", "N-Sandstorm",
    ]
    assert [row["RankingPosition"] for row in ranked] == list(range(1, 11))
    # No fabricated time was needed anywhere.
    assert all(row["TimeMs"] is None for row in ranked if row["ResultStatus"] != "FINISHED")


def test_duplicate_manual_placement_is_rejected():
    rows = [
        {"team_id": "A", "result_status": "DNF", "manual_placement": 7},
        {"team_id": "B", "result_status": "DNF", "manual_placement": 7},
    ]
    assert "Manual placement must be unique within the event." in validate_race_results(rows)
    rows[1]["manual_placement"] = 8
    assert validate_race_results(rows) == []
    assert validate_race_result({"team_id": "A", "result_status": "DNF", "manual_placement": 0}) == [
        "Manual placement must be 1 or greater."
    ]


def test_unplaced_non_finishers_still_rank_deterministically():
    rows = [
        {"team_id": "B", "result_status": "DISQUALIFIED"},
        {"team_id": "A", "result_status": "DNS"},
        {"team_id": "C", "result_status": "DNF"},
        {"team_id": "D", "result_status": "DNF", "manual_placement": 1},
    ]
    order = [row["TeamID"] for row in rank_race_results(rows)]
    assert order == ["D", "C", "A", "B"]
    assert order == [row["TeamID"] for row in rank_race_results(list(reversed(rows)))]


def test_ranking_is_total_and_reproducible_on_a_tie():
    rows = [{"team_id": t, "result_status": "FINISHED", "time_ms": 60000} for t in ("C", "A", "B")]
    assert [row["TeamID"] for row in rank_race_results(rows)] == ["A", "B", "C"]


# --------------------------------------------------------------------------
# 7-9  Human time entry
# --------------------------------------------------------------------------

def test_minutes_and_seconds_convert_deterministically():
    assert duration_ms(1, 30, 250) == 90_250
    assert duration_ms(0, 0, 0) == 0
    assert duration_ms(minutes=2) == 120_000
    assert split_duration_ms(90_250) == (1, 30, 250)
    assert duration_ms(*split_duration_ms(613_499)) == 613_499


def test_stored_milliseconds_display_in_human_form():
    assert format_duration_ms(90_250) == "01:30.250"
    assert format_duration_ms(0) == "00:00.000"
    assert format_duration_ms(None) == "—"
    assert describe_result({"result_status": "FINISHED", "time_ms": 90_250}) == "01:30.250"
    assert describe_result({"result_status": "DNF", "manual_placement": 7}) == "DNF · placed 7"
    assert describe_result({"result_status": "DNS"}) == "DNS"


def test_race_control_never_exposes_raw_milliseconds_or_bounds_a_historical_value():
    source = (ROOT / "screens" / "formula_race.py").read_text()
    block = source.split("def drag_results", 1)[1].split("def build_status", 1)[0]
    # The control that crashed on the live workaround is gone.
    assert 'number_input("Finish time (ms)"' not in block
    assert 'number_input("Penalty (ms)"' not in block
    assert '"Minutes",0,59' in block and '"Seconds",0,59' in block and '"Milliseconds",0,999' in block
    # A stored value outside the entry range is reported, never forced into a
    # bounded control -- this is what raised StreamlitValueAboveMaxError live.
    assert "is outside the entry range" in block
    assert "stored_minutes,stored_seconds,stored_ms=0,0,0" in block
    # A non-finisher renders a placement control instead of a time control.
    assert "if is_measured(status):" in block and '"Manual placement",1' in block


# --------------------------------------------------------------------------
# 10-13  Ownership and layer parity
# --------------------------------------------------------------------------

def test_one_ownership_vocabulary_is_shared_by_every_python_layer():
    assert RESULT_ENTRY_OWNERS == ("FACILITATOR", "CAPTAIN")
    assert CONFIGURATION_OWNERS is RESULT_ENTRY_OWNERS, "configuration must not redeclare the vocabulary"
    assert normalise_station({"ActivityID": "S1"})["ResultEntryOwner"] == DEFAULT_RESULT_ENTRY_OWNER
    assert normalise_result_entry_owner("captain") == "CAPTAIN"
    assert normalise_result_entry_owner("SYSTEM") == DEFAULT_RESULT_ENTRY_OWNER


def test_sql_agrees_with_python_on_owners_and_statuses():
    """The migration-033 failure was two layers disagreeing in silence."""
    submit = (ROOT / "supabase" / "033_formula_race_facilitator_owned_results.sql").read_text()
    for owner in RESULT_ENTRY_OWNERS:
        assert f"'{owner}'" in submit
    # SYSTEM is deliberately unimplemented; no layer may claim to accept it.
    assert "'SYSTEM'" not in submit
    for status in RESULT_STATUSES:
        assert f"'{status}'" in MIGRATION


def test_facilitator_owned_result_never_depends_on_a_captain_result_value():
    submit = (ROOT / "supabase" / "033_formula_race_facilitator_owned_results.sql").read_text()
    body = submit.split("exos_v2_formula_race_submit_station", 1)[1].split("$$;", 1)[0]
    assert "if v_result_owner='FACILITATOR' and p_result_value is not null then raise exception" in body
    assert "if v_result_owner='CAPTAIN' and v_method in ('LOWEST_TIME','HIGHEST_COUNT','SUCCESS_COUNT') and p_result_value is null then raise exception" in body
    # Race Control supplies the official result for a measured station.
    race_control = (ROOT / "screens" / "formula_race.py").read_text()
    assert "_official_result_control(station_by_submission.get(str(x.id), {}), x.id)" in race_control
    assert 'official_result if decision == "APPROVE" else None' in race_control


def test_adapter_sends_the_status_contract_and_refuses_a_fabricated_time():
    runtime = _CapturingRuntime()
    adapter = _adapter(runtime)

    adapter.save_formula_race_result("E", "T", 90_250, 1000, 0, True, "measured", "Judge")
    path, payload = runtime.calls[-1]
    assert path == "rpc/exos_v2_formula_race_save_result"
    assert payload["p_result_status"] == "FINISHED" and payload["p_time_ms"] == 90_250
    assert payload["p_manual_placement"] is None

    adapter.save_formula_race_result("E", "T", 0, 0, 0, True, "did not finish", "Judge",
                                     result_status="DNF", manual_placement=7)
    path, payload = runtime.calls[-1]
    assert payload["p_result_status"] == "DNF"
    assert payload["p_time_ms"] == 0 and payload["p_penalty_ms"] == 0
    assert payload["p_manual_placement"] == 7

    with pytest.raises(RuntimeError, match="must not carry a finish time"):
        adapter.save_formula_race_result("E", "T", 9_999_999, 0, 0, True, "bad", "Judge", result_status="DNF")


def test_rpc_signature_is_replaced_not_overloaded():
    """Two candidates for one RPC name is how PostgREST calls start failing."""
    assert "drop function if exists public.exos_v2_formula_race_save_result(text,text,text,integer,integer,numeric,boolean,text,text);" in MIGRATION
    assert "p_result_status text default 'FINISHED'" in MIGRATION
    assert "p_manual_placement integer default null" in MIGRATION
    adapter_source = (ROOT / "data" / "formula_race_core_v2_adapter.py").read_text()
    assert '"p_result_status": status' in adapter_source and '"p_manual_placement"' in adapter_source


def test_sql_enforces_the_same_rules_as_the_python_contract():
    assert "if coalesce(p_time_ms,0)<>0 then raise exception 'A non-finished result must not carry a finish time'" in MIGRATION
    assert "raise exception 'Manual placement % is already assigned in this event'" in MIGRATION
    assert "raise exception 'A finished result is ranked by its time, not by manual placement'" in MIGRATION
    assert "raise exception 'Unsupported result status'" in MIGRATION
    assert "Manual placement must be unique before the final ranking can be locked" in MIGRATION


def test_lock_ordering_mirrors_the_python_ranking_definition():
    lock = MIGRATION.split("exos_v2_formula_race_lock_final_results", 1)[1]
    assert "case when coalesce(r.result_payload->>'result_status','FINISHED')='FINISHED' then 0 else 1 end" in lock
    assert "coalesce((r.result_payload->>'manual_placement')::integer,2147483647) asc" in lock
    assert "when 'FINISHED' then 0 when 'DNF' then 1 when 'DNS' then 2 when 'DISQUALIFIED' then 3" in lock
    assert "r.team_id asc" in lock
    # Every pre-existing guarantee survives.
    assert "Every active team requires one verified Race Final result before locking" in lock
    assert "Race Final has a partial lock state and requires controlled reconciliation" in lock
    assert "exos_v2_formula_race_reconcile_championship" in lock


# --------------------------------------------------------------------------
# 14  Backward compatibility
# --------------------------------------------------------------------------

def test_historical_rows_without_a_status_remain_readable_and_rank_unchanged():
    """Rows written before this sprint carry no result_status."""
    legacy = [
        {"team_id": "B", "time_ms": 61000, "penalty_ms": 0},
        {"team_id": "A", "time_ms": 45000, "penalty_ms": 0},
        {"team_id": "C", "time_ms": 9_000_000, "penalty_ms": 0},   # the live DNF workaround
    ]
    ranked = rank_race_results(legacy)
    assert [row["TeamID"] for row in ranked] == ["A", "B", "C"]
    assert all(row["ResultStatus"] == "FINISHED" for row in ranked)
    # The huge historical value is still readable rather than fatal.
    assert format_duration_ms(9_000_000) == "150:00.000"
    assert describe_result(legacy[2]) == "150:00.000"


def test_migration_is_additive_and_non_destructive():
    assert "alter table" not in MIGRATION.lower()
    assert "drop table" not in MIGRATION.lower()
    assert "drop column" not in MIGRATION.lower()
    assert "delete from" not in MIGRATION.lower()
    assert "update public.race_results_v2 r set ranking_position" in MIGRATION  # lock only
    assert MIGRATION.strip().startswith("--") and MIGRATION.strip().endswith("COMMIT;")
    assert "coalesce(r.result_payload->>'result_status','FINISHED')" in MIGRATION


def test_adapter_reads_status_and_placement_from_stored_results():
    class Runtime:
        is_configured = True
        can_publish = True
        url = "https://staging.disposable.example.test"

        def _request(self, method, path, payload=None, query=None, admin=True):
            return [
                {"team_id": "A", "checkpoint": "Race Final", "ranking_position": 1, "locked": True,
                 "result_payload": {"time_ms": 45000, "penalty_ms": 0, "verified": True}},
                {"team_id": "B", "checkpoint": "Race Final", "ranking_position": 7, "locked": True,
                 "result_payload": {"time_ms": None, "result_status": "DNF", "manual_placement": 7, "verified": True}},
            ]

    rows = _adapter(Runtime()).get_race_results("E")
    assert rows[0]["result_status"] == "FINISHED" and rows[0]["manual_placement"] is None
    assert rows[1]["result_status"] == "DNF" and rows[1]["manual_placement"] == 7
    assert rows[1]["time_ms"] is None


# --------------------------------------------------------------------------
# Behavioural: the screen that crashed live
# --------------------------------------------------------------------------

def _drag_results_app(status: str, stored_time: int) -> str:
    return f'''
import streamlit as st
from types import SimpleNamespace
from screens.formula_race import drag_results

TEAMS = [("T{{:02d}}".format(n), "Disposable Team {{:02d}}".format(n)) for n in range(1, 11)]
saved = {{}}

class Control:
    runtime = SimpleNamespace()
    def save_race_result(self, event_id, team_id, time_ms, penalty_ms, bonus, verified, reason, actor,
                         result_status="FINISHED", manual_placement=None):
        saved.update({{"team_id": team_id, "time_ms": time_ms, "penalty_ms": penalty_ms,
                      "result_status": result_status, "manual_placement": manual_placement}})
        st.session_state["saved"] = dict(saved)

results = [
    {{"team_id": "T01", "result_status": {status!r}, "time_ms": {stored_time!r},
     "penalty_ms": 0, "manual_placement": 7 if {status!r} != "FINISHED" else None,
     "verified": True, "locked": False, "position": 1, "checkpoint": "Race Final"}},
]
snapshot = SimpleNamespace(
    event_id="DISPOSABLE-EVT",
    teams=[SimpleNamespace(id=t, name=n) for t, n in TEAMS],
    operations={{"RaceResults": results}},
)
drag_results(snapshot, Control())
'''


def _render_drag(status: str, stored_time):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string(_drag_results_app(status, stored_time), default_timeout=90)
    app.run()
    assert not app.exception, [str(e.value) for e in app.exception]
    return app


def test_dnf_renders_race_control_without_a_value_range_failure():
    """The live crash was StreamlitValueAboveMaxError from a fabricated time."""
    app = _render_drag("DNF", None)
    labels = [w.label for w in app.number_input]
    assert "Manual placement" in labels
    assert "Minutes" not in labels and "Seconds" not in labels
    assert app.selectbox(key="race_result_status_T01").value == "DNF"


def test_historical_out_of_range_time_is_reported_not_forced_into_a_control():
    """A 9,000,000 ms legacy row must remain readable rather than crash."""
    app = _render_drag("FINISHED", 9_000_000)
    assert any("outside the entry range" in w.value for w in app.warning)
    minutes = app.number_input(key="race_result_min_T01")
    assert minutes.value == 0 and minutes.max == 59
    assert any("150:00.000" in w.value for w in app.warning)


def test_finished_entry_saves_human_units_as_canonical_milliseconds():
    app = _render_drag("FINISHED", 0)
    app.number_input(key="race_result_min_T01").set_value(1)
    app.number_input(key="race_result_sec_T01").set_value(30)
    app.number_input(key="race_result_ms_T01").set_value(250)
    app.text_input(key="race_control_operator").set_value("Disposable Judge")
    app.text_input(key="race_result_reason").set_value("Disposable UAT")
    app.run()
    next(b for b in app.button if b.label.startswith("Save Result")).click().run()
    saved = app.session_state["saved"]
    assert saved["time_ms"] == 90_250 and saved["result_status"] == "FINISHED"
    assert saved["manual_placement"] is None


def test_non_finisher_saves_placement_and_no_time():
    app = _render_drag("DNF", None)
    app.number_input(key="race_result_place_T01").set_value(8)
    app.text_input(key="race_control_operator").set_value("Disposable Judge")
    app.text_input(key="race_result_reason").set_value("Did not finish")
    app.run()
    next(b for b in app.button if b.label.startswith("Save Result")).click().run()
    saved = app.session_state["saved"]
    assert saved["result_status"] == "DNF"
    assert saved["time_ms"] == 0 and saved["penalty_ms"] == 0
    assert saved["manual_placement"] == 8
