import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from data.google_sheets import GoogleSheetsDB
from data.runtime_authority import (
    RUNTIME_AUTHORITY,
    RuntimeAuthorityError,
    RuntimeEntity,
    authority_manifest,
)
from data.runtime_database import SupabaseRuntimeDB
from scripts.exos_stabilisation_harness import RuntimeModel, run_scenario


MIGRATION = Path("supabase/012_foundation_identity_runtime_authority.sql").read_text()
ROLLBACK = Path("supabase/012_foundation_identity_runtime_authority_rollback.sql").read_text()
DRY_RUN = Path("supabase/012_foundation_identity_runtime_authority_dry_run.sql").read_text()
SHEETS = Path("data/google_sheets.py").read_text()


class RuntimeUnavailable:
    is_configured = False
    can_publish = False


def bare_database(runtime=None):
    database = GoogleSheetsDB.__new__(GoogleSheetsDB)
    database.runtime = runtime or RuntimeUnavailable()
    database._participant_count_warnings = {}
    return database


def test_all_required_runtime_entities_have_one_authority_and_owner():
    assert set(RUNTIME_AUTHORITY) == set(RuntimeEntity)
    manifest = authority_manifest()
    assert len(manifest) == 11
    assert all(row["Authority"] and row["Owner"] for row in manifest.values())
    assert all(row["MemoryRole"] == "cache_only" for row in manifest.values())


def test_participant_team_leader_and_submission_authorities_are_supabase():
    manifest = authority_manifest()
    assert manifest["Participant"]["Authority"] == "runtime_participants"
    assert manifest["Team"]["Authority"] == "runtime_teams"
    assert manifest["Leader"]["Authority"] == "runtime_participants"
    assert manifest["Submission State"]["Authority"] == "runtime_submissions"
    assert manifest["Credits"]["Authority"] == "runtime_credit_transactions"


def test_direct_sheet_identity_and_submission_mutations_fail_closed():
    database = bare_database()
    with pytest.raises(RuntimeAuthorityError):
        database.join_player("EVT-1", "Participant One")
    with pytest.raises(RuntimeAuthorityError):
        database.save_submission("S1", "EVT-1", "M1", "Team 1", "Participant One")
    with pytest.raises(RuntimeAuthorityError):
        database.set_event_state("EVT-1", 1)


def test_runtime_join_uses_v2_with_atomic_requested_team():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    calls = []
    runtime._request = lambda *args, **kwargs: calls.append((args, kwargs)) or {
        "ParticipantID": "P1", "TeamID": "T1", "Country": "France",
    }
    player = runtime.join_player("CODE", "Adrian Choong", "DEVICE", "T1")
    assert player["ParticipantID"] == "P1"
    assert calls[0][0][1] == "rpc/exos_join_event_v2"
    assert calls[0][1]["payload"]["p_requested_team_id"] == "T1"


def test_country_selection_is_passed_once_and_never_patched_after_join():
    class Runtime:
        is_configured = True
        can_publish = True

        def get_event_by_join_code(self, code):
            return {"EventID": "EVT-1"}

        def join_player(self, code, name, device, requested_team_id=""):
            self.requested_team_id = requested_team_id
            return {"ParticipantID": "P1", "TeamID": requested_team_id, "Country": "France"}

        def assign_participant_country_team(self, *args):
            raise AssertionError("Post-join team mutation is forbidden")

    database = bare_database(Runtime())
    database.get_teams = lambda event_id: [{
        "TeamID": "T-FR", "TeamName": "🇫🇷 France", "Country": "France",
    }]
    result = database.join_player_by_code("CODE", "Adrian Choong", "France", "DEVICE")
    assert result["TeamID"] == "T-FR"
    assert database.runtime.requested_team_id == "T-FR"


def test_identity_guard_blocks_automatic_team_country_and_leader_mutation():
    assert "runtime_participant_identity_guard" in MIGRATION
    assert "Durable participant identity requires an audited override" in MIGRATION
    for field in ["team_id", "team_name", "country", "flag", "|LEADER%"]:
        assert field in MIGRATION
    assert "set_config('exos.identity_override','on',true)" in MIGRATION


def test_join_lookup_happens_before_any_allocation_and_is_lock_safe():
    function = MIGRATION.split("public.exos_join_event_v2", 1)[1]
    lookup = function.index("select count(*) into v_matches")
    requested = function.index("if nullif(trim(p_requested_team_id)")
    insert = function.index("insert into public.runtime_participants")
    assert lookup < requested < insert
    assert "for update" in function[:insert].lower()
    assert "on conflict(event_id,idempotency_key)" in function.lower()


def test_reconnect_never_reallocates_or_reclaims_leadership():
    function = MIGRATION.split("public.exos_join_event_v2", 1)[1]
    existing_branch = function.split("elsif v_matches = 1", 1)[1].split("end if;", 1)[0]
    assert "exos_identity_payload" in existing_branch
    assert "runtime_teams" not in existing_branch
    assert "|LEADER" not in existing_branch
    restore = MIGRATION.split("public.exos_restore_join", 1)[1].split(
        "public.exos_admin_transfer_leader", 1
    )[0]
    assert "exos_normalize_participant_name" in restore
    assert "v_matches>1" in restore
    assert "'Ambiguous',true" in restore


def test_credit_award_has_database_duplicate_prevention():
    assert "create unique index if not exists runtime_credit_earn_once" in MIGRATION.lower()
    assert "transaction_type = 'EARN' and source_id <> ''" in MIGRATION


def test_leader_claim_is_one_atomic_audited_rpc():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    calls = []
    runtime._request = lambda *args, **kwargs: calls.append((args, kwargs)) or {"Claimed": True}
    assert runtime.claim_team_leader("TOKEN")["Claimed"] is True
    assert calls[0][0][1] == "rpc/exos_claim_team_leader"
    claim_sql = MIGRATION.split("public.exos_claim_team_leader", 1)[1]
    assert "for update" in claim_sql.lower()
    assert "runtime_identity_audit_log" in claim_sql


def test_runtime_control_state_has_one_validated_write_rpc():
    assert "runtime_control_state jsonb" in MIGRATION
    function = MIGRATION.split("public.exos_set_runtime_control_state", 1)[1]
    for key in ["StageTimers", "ProjectorBroadcast", "CurrentStageStatus", "RegistrationOpen"]:
        assert key in function
    assert "Unsupported runtime control key" in function


def test_stage_timer_reads_and_writes_runtime_not_event_notes():
    class Runtime:
        is_configured = True
        can_publish = True

        def get_runtime_control_state(self, event_id):
            return {"StageTimers": {}}

        def set_runtime_control_state(self, event_id, key, value):
            self.saved = (event_id, key, value)

    database = bare_database(Runtime())
    timer = database.update_stage_timer("EVT-1", 1, "START", 5)
    assert timer["Status"] == "RUNNING"
    assert database.runtime.saved[0:2] == ("EVT-1", "StageTimers")


def test_live_reads_do_not_merge_or_fall_back_to_sheet_records():
    get_players = SHEETS.split("def get_players(self):", 1)[1].split("def get_player(", 1)[0]
    submissions = SHEETS.split("def get_event_submissions", 1)[1].split("def get_submissions", 1)[0]
    event_state = SHEETS.split("def get_event_state", 1)[1].split("def set_event_state", 1)[0]
    assert "sheet_players + runtime_players" not in get_players
    assert "sheet_rows + runtime_rows" not in submissions
    assert "except RuntimeDatabaseError" not in event_state


def test_100_concurrent_join_attempts_create_zero_duplicates():
    result = run_scenario(100, 100)
    assert result["passed"] is True
    assert result["unique_participants"] == 100
    assert result["duplicate_identity_mismatches"] == 0


def test_concurrent_recovery_returns_same_full_identity():
    runtime = RuntimeModel()
    player = runtime.join("EVT-1", "Participant 00000", "DEVICE-1")
    lock = threading.Lock()
    restored = []

    def recover():
        value = runtime.restore(player["SessionToken"])
        with lock:
            restored.append(value)

    with ThreadPoolExecutor(max_workers=100) as pool:
        list(pool.map(lambda _: recover(), range(100)))
    fields = ["ParticipantID", "TeamID", "Country", "Flag", "IsLeader", "IntelligenceCredits"]
    assert len(restored) == 100
    assert all(all(item[field] == player[field] for field in fields) for item in restored)


def test_two_events_have_isolated_runtime_identity():
    result = run_scenario(200, 100, events=2)
    assert result["passed"] is True
    assert result["unique_participants"] == 200


def test_migration_is_non_destructive_and_has_safe_rollback():
    lowered = MIGRATION.lower()
    assert "delete from public.runtime_participants" not in lowered
    assert "drop table" not in lowered
    assert "truncate" not in lowered
    assert "runtime_control_state is intentionally retained" in ROLLBACK
    assert "drop table" not in ROLLBACK.lower()


def test_dry_run_is_select_only_and_reports_every_identity_risk():
    lowered = DRY_RUN.lower()
    for forbidden in ["insert into", "update public", "delete from", "alter table", "drop table", "truncate"]:
        assert forbidden not in lowered
    for field in [
        "DuplicateIdentityCandidates", "IncompleteDurableIdentity",
        "LeaderConflicts", "DuplicateCreditSources", "SafeToApply",
        "ProductionRecordsChanged",
    ]:
        assert field in DRY_RUN
