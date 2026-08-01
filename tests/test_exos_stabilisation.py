from scripts.exos_stabilisation_harness import RuntimeModel, run_scenario


def test_duplicate_join_is_idempotent_and_team_is_stable():
    runtime = RuntimeModel(teams=4)
    first = runtime.join("EVT-1", "Adrian Choong", "device-a")
    second = runtime.join("EVT-1", "  ADRIAN   CHOONG ", "device-b")
    assert second["ParticipantID"] == first["ParticipantID"]
    assert second["Team"] == first["Team"]
    assert second["TeamID"] == first["TeamID"]
    assert second["Country"] == first["Country"]
    assert second["Flag"] == first["Flag"]
    assert second["IsLeader"] == first["IsLeader"]
    assert second["IntelligenceCredits"] == first["IntelligenceCredits"]


def test_session_token_restores_exact_committed_identity():
    runtime = RuntimeModel()
    player = runtime.join("EVT-1", "Participant One", "device-a")
    assert runtime.restore(player["SessionToken"]) == player
    assert runtime.restore("invalid-token") is None


def test_leader_rights_and_credits_survive_reconnect_without_reaward():
    runtime = RuntimeModel()
    leader = runtime.join("EVT-1", "Load Participant 00000", "ios-safari")
    assert leader["IsLeader"] is True
    leader["IntelligenceCredits"] = 50
    runtime.participants[("EVT-1", "load participant 00000")]["IntelligenceCredits"] = 50
    rejoined = runtime.join("EVT-1", "LOAD PARTICIPANT 00000", "android-chrome")
    assert rejoined["ParticipantID"] == leader["ParticipantID"]
    assert rejoined["TeamID"] == leader["TeamID"]
    assert rejoined["IsLeader"] is True
    assert rejoined["IntelligenceCredits"] == 50


def test_retry_budget_recovers_two_transient_failures():
    runtime = RuntimeModel(transient_failures=2)
    player = runtime.join_with_retry("EVT-1", "Participant One", "device-a")
    assert player["ParticipantID"]
    assert runtime.attempts[(("EVT-1", "participant one"), "device-a")] == 3


def test_retry_budget_fails_closed_when_exhausted():
    runtime = RuntimeModel(transient_failures=3)
    try:
        runtime.join_with_retry("EVT-1", "Participant One", "device-a")
    except Exception as error:
        assert type(error).__name__ == "TransientFailure"
    else:
        raise AssertionError("Exhausted retries must not report success")


def test_concurrent_capacity_gate_at_100_participants():
    result = run_scenario(100, 100)
    assert result["passed"] is True
    assert result["unique_participants"] == 100
    assert result["maximum_team_distribution_spread"] <= 1


def test_two_events_are_isolated_under_concurrency():
    result = run_scenario(200, 100, events=2)
    assert result["passed"] is True
    assert result["unique_participants"] == 200
