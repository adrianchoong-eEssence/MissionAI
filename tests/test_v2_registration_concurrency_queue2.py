from concurrent.futures import ThreadPoolExecutor

from pathlib import Path
from scripts.exos_stabilisation_harness import RuntimeModel, run_scenario


SQL = Path("supabase/020_exos_core_v2_schema.sql").read_text().lower()


def test_v2_join_rpc_is_locked_and_uses_idempotent_session_key():
    assert "perform pg_advisory_xact_lock(v_event_lock)" in SQL
    assert "perform pg_advisory_xact_lock(v_identity_lock)" in SQL
    assert "on conflict (event_id, idempotency_key) do update" in SQL
    assert "returning * into v_session" in SQL
    assert "recoveryrequired', true" in SQL
    assert "v_session.participant_id is distinct from v_participant.participant_id" in SQL


def test_same_name_replay_returns_explicit_recovery():
    assert "select count(*) into v_count" in SQL
    assert "if v_count >= 1 then" in SQL
    assert "recoveryrequired', true" in SQL
    assert "ambiguous', v_count > 1" in SQL
    assert "message', 'same name exists for different device/session" in SQL


def test_same_person_same_device_two_simultaneous_requests_map_to_one_participant():
    runtime = RuntimeModel(teams=4)
    runtime.join("EVT-1", "Ada Lovelace", "device-1")

    def request():
        return runtime.join("EVT-1", "ADA   LOVELACE", "device-1")

    with ThreadPoolExecutor(max_workers=2) as pool:
        participants = list(pool.map(lambda _: request(), range(2)))

    assert participants[0]["ParticipantID"] == participants[1]["ParticipantID"]
    assert participants[0]["TeamID"] == participants[1]["TeamID"]


def test_run_70_260_800_concurrency_reconnect_and_balance_probes():
    results = {
        "70": run_scenario(70, 70),
        "260": run_scenario(260, 120),
        "800": run_scenario(800, 160),
    }

    for label, result in results.items():
        assert result["passed"] is True, f"load probe failed for {label}"
        assert result["duplicate_identity_mismatches"] == 0
        assert result["session_restore_failures"] == 0
        assert result["maximum_team_distribution_spread"] <= 1
        assert result["unique_participants"] == result["participants"]
        assert isinstance(result["latency_ms"]["p95"], (int, float))
