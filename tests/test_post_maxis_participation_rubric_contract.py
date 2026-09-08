"""P0-B source contracts: opt-in scoring must not reinterpret old board flow."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from data.runtime_database import RuntimeDatabaseError
from engines.theme_park_race import (
    facilitator_rubric_score,
    participation_prorated_score,
    validate_configuration,
)
from screens.theme_park_race import submit_theme_park_race_review


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "043_post_maxis_p0_participation_rubric_scoring.sql"
GUARD_FIX = ROOT / "supabase" / "043a_post_maxis_p0_participation_rubric_guard_consumption.sql"
ROLLBACK = ROOT / "supabase" / "043_post_maxis_p0_participation_rubric_scoring_rollback.sql"
VERIFIER = ROOT / "supabase" / "verification" / "exos_v2_post_maxis_participation_rubric_verify.sql"
CERTIFICATION = ROOT / "supabase" / "certification" / "exos_v2_post_maxis_participation_rubric_certification.sql"
CONCURRENCY_SETUP = ROOT / "supabase" / "certification" / "exos_v2_post_maxis_participation_rubric_concurrency_setup.sql"
CONCURRENCY_CLEANUP = ROOT / "supabase" / "certification" / "exos_v2_post_maxis_participation_rubric_concurrency_verify_cleanup.sql"


def _submission():
    return {"SubmissionID": "00000000-0000-0000-0000-000000000043", "SubmittedAt": "2026-09-08T00:00:00Z"}


def test_participation_formula_is_snapshot_bounded_and_half_up():
    assert participation_prorated_score(150, participants_completing=10, present_team_size=10) == 150
    assert participation_prorated_score(150, participants_completing=9, present_team_size=10) == 135
    assert participation_prorated_score(101, participants_completing=1, present_team_size=2) == 51
    with pytest.raises(ValueError):
        participation_prorated_score(150, participants_completing=11, present_team_size=10)


def test_rubric_score_is_configured_weighted_bounded_and_deterministic():
    criteria = [{"ID": "quality", "Weight": 2}, {"ID": "teamwork", "Weight": 1}]
    assert facilitator_rubric_score(101, criteria, {"quality": 100, "teamwork": 50}) == 84
    with pytest.raises(ValueError):
        facilitator_rubric_score(101, criteria, {"quality": 101, "teamwork": 50})


def test_new_scoring_modes_require_explicit_valid_activity_configuration():
    configuration = {
        "SchemaVersion": 1, "EngineKind": "THEME_PARK_RACE", "StrategyMode": "OPEN_MISSION_BOARD",
        "RuntimePhase": "ACTIVE", "MissionBoard": {"MaximumConcurrentSelections": 1, "MissionOperations": {"P": {}}},
    }
    teams = [{"TeamID": "T"}]
    station = {
        "ActivityID": "P", "Enabled": True, "DisplayName": "P",
        "Scoring": {"Mode": "PARTICIPATION_PRORATED", "Maximum": 150, "Rounding": "HALF_UP"},
    }
    assert validate_configuration(configuration, teams, [station]) == []
    station["Scoring"]["Rounding"] = "BANKERS"
    assert any("HALF_UP" in error for error in validate_configuration(configuration, teams, [station]))
    station["Scoring"] = {"Mode": "FACILITATOR_RUBRIC", "Maximum": 150, "Rounding": "HALF_UP", "Rubric": {"Criteria": []}}
    assert any("criterion" in error.casefold() for error in validate_configuration(configuration, teams, [station]))


def test_open_board_team_full_review_remains_on_frozen_039_path():
    calls = []
    control = SimpleNamespace(
        review_theme_park_race_board_submission=lambda *args, **kwargs: calls.append((args, kwargs)),
        review_theme_park_race_scored_submission=lambda *args, **kwargs: pytest.fail("must not route old scoring through P0-B"),
    )
    outcome = submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", _submission(), decision="APPROVE", score=12, actor="Kai", notes="ok",
        scoring={"Mode": "TEAM_FULL"},
    )
    assert outcome == {"Reviewed": True}
    assert len(calls) == 1 and calls[0][1]["score"] == 12


@pytest.mark.parametrize("mode, rubric", [
    ("PARTICIPATION_PRORATED", {}),
    ("FACILITATOR_RUBRIC", {"quality": 90}),
])
def test_opt_in_scoring_review_has_no_client_final_score_authority(mode, rubric):
    calls = []
    control = SimpleNamespace(
        review_theme_park_race_board_submission=lambda *args, **kwargs: pytest.fail("must not bypass canonical scored review"),
        review_theme_park_race_scored_submission=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    outcome = submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", _submission(), decision="APPROVE", score=999999,
        actor="Kai", notes="verified", scoring={"Mode": mode}, rubric_scores=rubric,
    )
    assert outcome == {"Reviewed": True}
    assert len(calls) == 1
    assert calls[0][1]["rubric_scores"] == rubric


def test_stale_scored_review_keeps_existing_stale_revision_ux():
    control = SimpleNamespace(
        review_theme_park_race_scored_submission=lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeDatabaseError("Submission revision is stale")
        ),
    )
    outcome = submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", _submission(), decision="APPROVE", score=0,
        actor="Kai", notes="", scoring={"Mode": "PARTICIPATION_PRORATED"},
    )
    assert outcome["Reviewed"] is False
    assert outcome["Level"] == "warning"


def test_migration_enforces_server_side_snapshot_guards_and_explicit_acl_matrix():
    sql = MIGRATION.read_text()
    assert "exos_v2_theme_park_race_submit_participation" in sql
    assert "exos_v2_theme_park_race_review_scored_submission" in sql
    assert "theme_park_race_scoring_snapshots_v2" in sql
    assert "exos.tpr_participation_submission" in sql
    assert "exos.tpr_scored_review" in sql
    assert "set_config('exos.tpr_scored_review', '', true)" in sql
    assert "set_config('exos.tpr_participation_submission', '', true)" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "round(v_maximum * v_selected_count::numeric / v_present_count::numeric, 0)" in sql
    assert "ON CONFLICT (submission_id, submitted_at) DO NOTHING" in sql
    assert "REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_review_scored_submission" in sql
    assert "TO service_role" in sql
    assert "GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_submit_participation" in sql
    assert "TO anon, authenticated, service_role" in sql
    assert "EXECUTE IMMEDIATE" not in sql


def test_rollback_refuses_to_reinterpret_opted_in_scoring_history():
    sql = ROLLBACK.read_text()
    assert "theme_park_race_scoring_snapshots_v2" in sql
    assert "PARTICIPATION_PRORATED" in sql
    assert "FACILITATOR_RUBRIC" in sql
    assert "THEME_PARK_RACE_PARTICIPATION_SUBMITTED" in sql
    assert "DELETE FROM" not in sql
    assert "UPDATE public." not in sql


def test_guard_companion_consumes_transaction_local_permits_without_changing_data():
    sql = GUARD_FIX.read_text()
    assert "CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_scored_review_guard" in sql
    assert "set_config('exos.tpr_scored_review', '', true)" in sql
    assert "set_config('exos.tpr_participation_submission', '', true)" in sql
    assert "set_config('exos.tpr_scoring_snapshot_write', '', true)" in sql
    assert "CREATE TABLE" not in sql
    assert "DELETE FROM" not in sql
    assert "UPDATE public." not in sql


def test_verifier_checks_signatures_security_acl_trigger_and_opt_in_definition():
    sql = VERIFIER.read_text()
    assert "exos_v2_theme_park_race_participation_preview(text,text)" in sql
    assert "exos_v2_theme_park_race_submit_participation(text,text,jsonb,jsonb)" in sql
    assert "exos_v2_theme_park_race_review_scored_submission" in sql
    assert "search_path=\"\"" in sql
    assert "public_execute_revoked" in sql
    assert "anon_authenticated" in sql
    assert "no_unexpected_overloads" in sql
    assert "canonical_participation_snapshot_installed" in sql


def test_certification_is_exact_fixture_only_and_checks_snapshots_idempotency_and_sentinel():
    sql = CERTIFICATION.read_text()
    assert "CERT-P0B-20260908" in sql
    assert "MAXIS-20260907-MISSION-AI" in sql
    assert "PARTICIPATION_PRORATED" in sql
    assert "FACILITATOR_RUBRIC" in sql
    assert "stale participation review was accepted" in sql
    assert "direct manual participation score was accepted" in sql
    assert "ABSENT completion selection was accepted" in sql
    assert "zero PRESENT denominator was accepted" in sql
    assert "direct manual rubric score was accepted" in sql
    assert "historical Maxis sentinel changed" in sql
    assert "\nTRUNCATE " not in sql
    assert "DELETE FROM public.events_v2 WHERE event_id = 'CERT-P0B-20260908'" in sql


def test_concurrency_certification_uses_a_separate_exact_fixture_and_serial_outcome_bounds():
    setup = CONCURRENCY_SETUP.read_text()
    cleanup = CONCURRENCY_CLEANUP.read_text()
    assert "CERT-P0B-CONC-20260908" in setup
    assert "PARTICIPATION_PRORATED" in setup
    assert "CERT-P0B-CONC-20260908" in cleanup
    assert "present_team_size NOT IN (2, 3)" in cleanup
    assert "eligible_score NOT IN (67, 101)" in cleanup
    assert "score_delta > 0) <> 1" in cleanup
    assert "TRUNCATE" not in setup + cleanup
