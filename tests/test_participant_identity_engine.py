from pathlib import Path

from data.runtime_database import SupabaseRuntimeDB
from scripts.exos_stabilisation_harness import RuntimeModel, run_scenario


SQL = Path("supabase/011_participant_identity_engine.sql").read_text()
PARTICIPANT = Path("screens/participant.py").read_text()
CONTROL = Path("screens/control_centre.py").read_text()


def test_new_join_and_double_click_create_one_participant():
    runtime = RuntimeModel()
    first = runtime.join("EVT-1", "Adrian Choong", "device-1")
    second = runtime.join("EVT-1", "Adrian Choong", "device-1")
    assert first["ParticipantID"] == second["ParticipantID"]
    assert len(runtime.participants) == 1


def test_normalized_relogin_and_punctuation_restore_identity():
    assert "exos_normalize_participant_name" in SQL
    assert "[[:punct:]]+" in SQL
    runtime = RuntimeModel()
    first = runtime.join("EVT-1", "Adrian Choong", "device-1")
    second = runtime.join("EVT-1", "  ADRIAN   CHOONG ", "device-2")
    assert first["ParticipantID"] == second["ParticipantID"]


def test_lookup_precedes_allocation_in_atomic_rpc():
    body = SQL.split("create or replace function public.exos_join_event", 1)[1]
    lookup = body.index("select count(*) into v_matches")
    allocation = body.index("select team.* into v_team")
    insert = body.index("insert into public.runtime_participants")
    assert lookup < allocation < insert
    assert "for update" in body[:insert].lower()
    assert "on conflict (event_id, idempotency_key)" in body.lower()


def test_ambiguous_same_name_fails_to_safe_recovery_choice():
    assert "if v_matches > 1" in SQL
    assert "'Ambiguous', true" in SQL
    assert "Existing expedition record found." in PARTICIPANT
    assert "Resume Expedition" in PARTICIPANT
    assert "This Is Not Me" in PARTICIPANT


def test_durable_payload_restores_complete_identity_and_rights():
    payload = SQL.split("create or replace function public.exos_identity_payload", 1)[1]
    for field in [
        "ParticipantID", "TeamID", "Country", "Flag", "IsLeader",
        "SubmissionRights", "SessionToken",
    ]:
        assert f"'{field}'" in payload


def test_refresh_restart_and_device_change_are_backend_recoverable():
    assert "rpc/exos_restore_participant" in Path("data/runtime_database.py").read_text()
    assert "runtime.get_player_by_token(session_token)" in PARTICIPANT
    assert "runtime.restore_join(" in PARTICIPANT


def test_leadership_transfer_is_atomic_and_audited():
    function = SQL.split("exos_admin_transfer_leader", 1)[1]
    assert "for update" in function.lower()
    assert "TRANSFER_LEADER" in function
    assert "runtime_identity_audit_log" in function
    assert "Transfer Team Leader" in CONTROL


def test_original_leader_cannot_reclaim_after_transfer():
    function = SQL.split("exos_admin_transfer_leader", 1)[1]
    assert "replace(status,'|LEADER','')" in function
    join = SQL.split("create or replace function public.exos_join_event", 1)[1]
    assert "|| '|LEADER'" not in join.split("create or replace function public.exos_admin", 1)[0]


def test_submission_overrides_are_reversible_and_audited():
    assert "runtime_submission_overrides" in SQL
    assert "SET_SUBMISSION_OVERRIDE" in SQL
    assert "exos_can_participant_submit" in SQL
    assert "EVENT_OVERRIDE" in SQL and "TEAM_OVERRIDE" in SQL
    assert "Allow any team member in this event to submit" in CONTROL
    assert "Allow any member of this team to submit" in CONTROL


def test_migration_is_audit_only_and_flags_all_required_anomalies():
    audit = SQL.split("exos_identity_migration_audit", 1)[1]
    for field in [
        "DuplicateCandidates", "TeamMutationCandidates",
        "LeaderInconsistencies", "OrphanedSubmissions",
        "AutomaticChangesApplied",
    ]:
        assert field in audit
    assert "'AutomaticChangesApplied',false" in audit


def test_runtime_admin_calls_use_protected_service_role():
    from data.runtime_authority import control_centre_mutation
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    calls = []
    runtime._request = lambda *args, **kwargs: calls.append((args, kwargs)) or {"ok": True}
    with control_centre_mutation():
        runtime.transfer_team_leader("EVT-1", "T1", "P1", "Facilitator")
        runtime.set_submission_override("EVT-1", "T1", True, "Facilitator")
        runtime.move_participant("P1", "T2", "Correction", "Facilitator")
    assert all(call[1]["admin"] is True for call in calls)


def test_two_events_do_not_cross_identity_and_100_concurrent_pass():
    result = run_scenario(100, 100, events=2)
    assert result["passed"] is True
    assert result["unique_participants"] == 100
    assert result["duplicate_identity_mismatches"] == 0
    assert result["session_restore_failures"] == 0


def test_migration_does_not_auto_delete_or_merge_production_rows():
    assert "delete from public.runtime_participants" not in SQL.lower()
    assert "merged_into_participant_id" in SQL
    assert "AutomaticChangesApplied" in SQL
