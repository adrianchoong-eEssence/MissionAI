from pathlib import Path

from engines.formula_race import final_standings, wallet_projection

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase" / "027_formula_race_core_v2_atomic_operations.sql").read_text()
ADJUSTMENT_SQL = (ROOT / "supabase" / "028_formula_race_manual_credit_adjustments.sql").read_text()
RESULT_CORRECTION_SQL = (ROOT / "supabase" / "029_formula_race_result_corrections.sql").read_text()
ADAPTER = (ROOT / "data" / "formula_race_core_v2_adapter.py").read_text()
CAPTAIN = (ROOT / "screens" / "formula_race_captain.py").read_text()
RACE_CONTROL = (ROOT / "screens" / "formula_race.py").read_text()


def test_checkpoint_approval_has_independent_once_only_score_and_credit_awards():
    assert "activity_payload->>'max_score'" in SQL
    assert "activity_payload->>'credits'" in SQL
    assert "race-checkpoint-score|'||p_submission_id::text" in SQL
    assert "race-checkpoint-credit|'||p_submission_id::text" in SQL
    assert "on conflict(event_id,idempotency_key) do update" in SQL


def test_wallet_metrics_are_independent_from_championship_score():
    wallet = wallet_projection([{"event_id":"E","team_id":"T","amount":7},{"event_id":"E","team_id":"T","amount":-3}],"E","T")
    assert wallet == {"Earned":7,"Spent":3,"Balance":4,"Transactions":[{"event_id":"E","team_id":"T","amount":7},{"event_id":"E","team_id":"T","amount":-3}]}
    assert "ChampionshipScore" in ADAPTER
    assert "CreditsEarned" in ADAPTER
    assert "CreditsSpent" in ADAPTER


def test_purchase_is_atomic_idempotent_and_locks_wallet_and_stock():
    assert "exos_v2_formula_race_purchase" in SQL
    assert "RACE_WALLET" in SQL
    assert "marketplace_transactions_v2" in SQL
    assert "race-purchase-credit|" in SQL
    assert "Stable purchase idempotency key is required" in SQL


def test_manual_credit_adjustment_is_idempotent_and_uses_the_canonical_ledger():
    assert "exos_v2_formula_race_manual_credit_adjustment" in ADJUSTMENT_SQL
    assert "credit_transactions_v2" in ADJUSTMENT_SQL
    assert "MANUAL_ADJUSTMENT" in ADJUSTMENT_SQL
    assert "on conflict(event_id,idempotency_key) do nothing" in ADJUSTMENT_SQL


def test_build_status_uses_core_v2_persistence_with_race_display_phases():
    assert "build_status_v2" in ADAPTER
    assert '"race_build_status": race_status' in ADAPTER
    assert '"Collecting Parts": "IN_PROGRESS"' in ADAPTER
    assert '"Ready to Race": "IN_PROGRESS"' in ADAPTER
    assert '"Completed": "COMPLETED"' in ADAPTER


def test_captain_submission_uses_explicit_technical_actor_not_standard_join():
    assert "RACE_CAPTAIN_TECHNICAL_ACTOR" in SQL
    assert "RACE_SUBMISSION" in SQL
    assert "exos_v2_join_event_v2" not in SQL
    assert "_submission_idempotency_key" in CAPTAIN


def test_final_results_use_verified_adjusted_time_and_lock_positions():
    rows=final_standings([{"TeamID":"T2","TeamName":"Bolt"},{"TeamID":"T1","TeamName":"Apex"}],[],[],[{"team_id":"T2","time_ms":1000,"penalty_ms":20,"verified":True},{"team_id":"T1","time_ms":1010,"penalty_ms":10,"verified":True}])
    assert [row["TeamID"] for row in rows] == ["T1","T2"]
    assert [row["Rank"] for row in rows] == [1,2]
    assert "ranking_position=ranked.final_rank" in SQL
    assert "locked=true" in SQL
    assert "exos_v2_formula_race_lock_final_results" in ADAPTER


def test_operational_displays_use_team_identity_and_expose_lock_action():
    assert "team_identity={team.id:team.name" in RACE_CONTROL
    assert "LOCK FINAL RESULTS" in RACE_CONTROL


def test_race_control_reloads_live_state_after_each_facilitator_write():
    assert "def _refresh_after_race_control_write" in RACE_CONTROL
    for mutation in (
        "control.review_race_checkpoint",
        "control.save_race_judging",
        "control.save_race_result",
        "control.set_race_build_status",
        "control.set_race_marketplace_runtime",
    ):
        assert mutation in RACE_CONTROL
    assert RACE_CONTROL.count("_refresh_after_race_control_write()") >= 8


def test_race_result_corrections_are_audited_before_lock_and_blocked_afterward():
    assert "exos_v2_formula_race_save_result" in RESULT_CORRECTION_SQL
    assert "RACE_RESULT_CORRECTED" in RESULT_CORRECTION_SQL
    assert "insert into public.audit_log_v2" in RESULT_CORRECTION_SQL
    assert "Race result is locked and immutable until explicit unlock." in RESULT_CORRECTION_SQL
    assert "Save Result Correction" in RACE_CONTROL


def test_race_performance_keeps_live_reads_fresh_and_optimises_evidence():
    captain = (ROOT / "screens" / "formula_race_captain.py").read_text()
    contracts = (ROOT / "data" / "formula_race_contracts.py").read_text()
    assert "def _optimise_race_photo" in captain
    assert "image.thumbnail((1600, 1600))" in captain
    assert "quality=82" in captain
    assert "Submitting proof…" in captain and "Purchasing…" in captain
    assert "Approving…" in RACE_CONTROL and "Saving race result…" in RACE_CONTROL
    assert "get_formula_race_state(event_id, raw_teams)" in contracts
    assert "operations[\"Checkpoints\"] = self.db.runtime.get_formula_race_checkpoints" not in contracts
