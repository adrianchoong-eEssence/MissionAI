"""P0-C source contracts: additive live operations cannot weaken Core v2."""
from pathlib import Path
from types import SimpleNamespace

from data.runtime_database import RuntimeDatabaseError
from screens.theme_park_race import submit_theme_park_race_review


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "044_post_maxis_p0_live_operations.sql"
ROLLBACK = ROOT / "supabase" / "044_post_maxis_p0_live_operations_rollback.sql"
VERIFIER = ROOT / "supabase" / "verification" / "exos_v2_post_maxis_live_operations_verify.sql"
CERTIFICATION = ROOT / "supabase" / "certification" / "exos_v2_post_maxis_live_operations_certification.sql"
SCREEN = ROOT / "screens" / "theme_park_race.py"
ADAPTER = ROOT / "data" / "standard_core_v2_adapter.py"
CONTROL = ROOT / "data" / "control_runtime.py"


def test_immutable_adjustment_is_server_namespaced_audited_and_never_upserted():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "exos_v2_theme_park_race_adjust_team_score" in sql
    assert "THEME_PARK_RACE_SCORE_ADJUSTMENT" in sql
    assert "TEAM_SCORE_ADJUSTMENT" in sql
    assert "ON CONFLICT (event_id, idempotency_key) DO NOTHING" in sql
    assert "Adjustment idempotency key conflicts with an immutable canonical score adjustment" in sql
    assert "THEME_PARK_RACE_TEAM_SCORE_ADJUSTED" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "DO UPDATE" not in sql
    assert "EXECUTE IMMEDIATE" not in sql


def test_clear_reopens_selection_revokes_session_and_requires_present_replacement():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "exos_v2_clear_team_formation_captain" in sql
    assert "TEAM_FORMATION_CAPTAIN_CLEARED" in sql
    assert "is_team_formation_captain = false" in sql
    assert "team_access_sessions_v2" in sql
    assert "CaptainSelectionReopenedReason" in sql
    assert "exos_v2_team_formation_captain_attendance_guard" in sql
    assert "attendance_state = 'PRESENT'" in sql
    assert "hashtextextended(v_event.event_id || '|TEAM_FORMATION_CAPTAIN|'" in sql


def test_new_mutation_acl_matrix_is_service_only_and_search_path_is_empty():
    sql = MIGRATION.read_text(encoding="utf-8")
    for name in (
        "exos_v2_theme_park_race_adjust_team_score",
        "exos_v2_clear_team_formation_captain",
        "exos_v2_theme_park_race_operator_status",
    ):
        assert f"REVOKE ALL ON FUNCTION public.{name}" in sql
    assert "FROM PUBLIC, anon, authenticated, service_role" in sql
    assert sql.count("TO service_role") == 4
    assert "SET search_path = ''" in sql


def test_guarded_rollback_refuses_live_history_and_never_deletes_it():
    sql = ROLLBACK.read_text(encoding="utf-8")
    assert "THEME_PARK_RACE_LIVE_OPERATIONS_044" in sql
    assert "TEAM_FORMATION_CAPTAIN_CLEARED" in sql
    assert "attendance-enabled Theme Park Captain eligibility" in sql
    assert "DELETE FROM" not in sql
    assert "UPDATE public." not in sql


def test_verifier_proves_signatures_acl_trigger_and_immutable_definition():
    sql = VERIFIER.read_text(encoding="utf-8")
    assert "exos_v2_theme_park_race_adjust_team_score(text,text,numeric,text,text,text)" in sql
    assert "exos_v2_clear_team_formation_captain(text,text,text,text)" in sql
    assert "search_path=\"\"" in sql
    assert "anon_authenticated_revoked" in sql
    assert "no_unexpected_overloads" in sql
    assert "present_captain_guard_trigger_present" in sql
    assert "DO UPDATE" in sql


def test_disposable_certification_checks_bonus_clear_authority_and_maxis_sentinel():
    sql = CERTIFICATION.read_text(encoding="utf-8")
    assert "CERT-P0C-20260908" in sql
    assert "MAXIS-20260907-MISSION-AI" in sql
    assert "conflicting adjustment retry mutated canonical score" in sql
    assert "Outstanding collaboration" in sql
    assert "Safety initiative" in sql
    assert ") <> 205" in sql
    assert "cleared Captain retained submission authority" in sql
    assert "ABSENT participant claimed Captain authority" in sql
    assert "replacement Captain claim created invalid authority" in sql
    assert "historical Maxis sentinel changed" in sql
    assert "TRUNCATE" not in sql
    assert "DELETE FROM public.events_v2 WHERE event_id = 'CERT-P0C-20260908'" in sql


def test_separate_connection_certification_covers_bonus_and_captain_races():
    setup = (ROOT / "supabase" / "certification" /
             "exos_v2_post_maxis_live_operations_concurrency_setup.sql").read_text(encoding="utf-8")
    cleanup = (ROOT / "supabase" / "certification" /
               "exos_v2_post_maxis_live_operations_concurrency_verify_cleanup.sql").read_text(encoding="utf-8")
    assert "CERT-P0C-CONC-DUP" in setup
    assert "CERT-P0C-CONC-DISTINCT-A" in setup
    assert "clear/submission race" in setup
    assert "captain_a_session_token" in setup
    assert "duplicate adjustment request created more than one canonical ledger transaction" in cleanup
    assert "concurrent clear/claim created dual Captain authority" in cleanup
    assert "cleared Captain wrote a stale post-clear submission" in cleanup
    assert "max(a.created_at)" in cleanup


def test_control_and_adapter_route_only_to_canonical_operations():
    adapter = ADAPTER.read_text(encoding="utf-8")
    control = CONTROL.read_text(encoding="utf-8")
    assert '"exos_v2_theme_park_race_adjust_team_score"' in adapter
    assert '"exos_v2_clear_team_formation_captain"' in adapter
    assert "adjust_theme_park_race_team_score" in control
    assert "clear_team_formation_captain" in control


def test_review_success_shows_final_server_score_and_expected_errors_are_safe():
    submission = {"SubmissionID": "00000000-0000-0000-0000-000000000044", "SubmittedAt": "2026-09-08T00:00:00Z"}
    control = SimpleNamespace(
        review_theme_park_race_board_submission=lambda *args, **kwargs: {"Score": 75, "Idempotent": False},
    )
    result = submit_theme_park_race_review(
        control, "OPEN_MISSION_BOARD", submission, decision="APPROVE", score=999,
        actor="Kai", notes="Verified", scoring={"Mode": "TEAM_FULL"},
    )
    assert result["Reviewed"] is True
    assert result["Score"] == 75
    assert "75" in result["Message"]
    failed = SimpleNamespace(
        review_theme_park_race_board_submission=lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeDatabaseError("P0001 untrusted database internals")
        ),
    )
    failure = submit_theme_park_race_review(
        failed, "OPEN_MISSION_BOARD", submission, decision="APPROVE", score=1,
        actor="Kai", notes="Verified", scoring={"Mode": "TEAM_FULL"},
    )
    assert failure["Reviewed"] is False
    assert "P0001" not in failure["Message"]


def test_mobile_evidence_is_explicit_private_two_step_and_preserves_retry_state():
    source = SCREEN.read_text(encoding="utf-8")
    assert "SHORT VIDEO RECOMMENDED" in source
    assert "approximately 5–10 seconds" in source
    assert "Preparing video…" in source
    assert "Uploading video…" in source
    assert "Upload complete." in source
    assert "✓ {kind} READY" in source
    assert "Submit Mission" in source
    assert "Video upload failed. Your mission has not been submitted." in source
    assert "theme_race_prepared_evidence_" in source
    assert "PHOTO_OR_VIDEO" in (ROOT / "engines" / "theme_park_race.py").read_text(encoding="utf-8")
