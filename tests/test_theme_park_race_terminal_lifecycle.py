"""Regression contract for the Theme Park Race READY/ACTIVE/HELD/ENDED lifecycle.

These tests are credential-free source and Streamlit widget tests.  They do
not install 040 or contact a Supabase environment.
"""
from pathlib import Path
import types

from streamlit.testing.v1 import AppTest

from engines.theme_park_race import (
    facilitator_projection,
    normalise_configuration,
    participant_lifecycle,
    participant_projection,
    projector_projection,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_RPC = "exos_v2_set_theme_park_race_runtime_phase"
OPERATION_RPC = "exos_v2_theme_park_race_board_set_mission_operation"


def _event(runtime_phase="READY", formation_phase="ACTIVE", strategy="OPEN_MISSION_BOARD"):
    return {
        "EventID": "CERT-END-1",
        "_EventPayload": {
            "TeamFormation": {"SchemaVersion": 1, "Mode": "RANDOM_ASSIGN", "Phase": formation_phase},
            "RaceConfiguration": {
                "SchemaVersion": 1,
                "EngineKind": "THEME_PARK_RACE",
                "StrategyMode": strategy,
                "RouteStrategy": "CONFIGURED_TEAM_ROUTE",
                "RuntimePhase": runtime_phase,
                "TeamRoutes": {"T-1": ["A"]},
                "MissionBoard": {"MaximumConcurrentSelections": 1, "MissionOperations": {
                    "A": {"OperationalStatus": "AVAILABLE", "SecretState": "RELEASED"},
                }},
                "Projector": {"DefaultView": "TEAM_PROGRESS", "ShowOverallScoring": True},
            },
        },
    }


def _station():
    return [{
        "ActivityID": "A", "DisplayName": "Mission A", "DisplayOrder": 1, "Enabled": True,
        "MissionClass": "SECRET", "ReviewRequired": True,
        "Evidence": {"Text": {"Required": True}},
    }]


def _participant():
    return {
        "ParticipantID": "P-1", "TeamID": "T-1", "TeamIdentity": "Orion",
        "IsTeamFormationCaptain": True, "CaptainSessionActive": True,
    }


def test_canonical_lifecycle_distinguishes_ready_active_held_and_terminal_ended():
    config = _event()["_EventPayload"]["RaceConfiguration"]
    assert participant_lifecycle({"Phase": "ACTIVE"}, config) == "READY"
    config["RuntimePhase"] = "ACTIVE"
    assert participant_lifecycle({"Phase": "ACTIVE"}, config) == "ACTIVE"
    config["RuntimePhase"] = "HELD"
    assert participant_lifecycle({"Phase": "ACTIVE"}, config) == "HELD"
    config["RuntimePhase"] = "ACTIVE"
    assert participant_lifecycle({"Phase": "ACTIVE"}, config) == "ACTIVE"
    config["RuntimePhase"] = "CLOSED"
    assert participant_lifecycle({"Phase": "ACTIVE"}, config) == "ENDED"


def test_ended_is_terminal_across_refresh_and_cannot_fall_back_to_team_formation_or_ready():
    closed = _event("CLOSED")["_EventPayload"]["RaceConfiguration"]
    assert participant_lifecycle({"Phase": "ACTIVE"}, closed) == "ENDED"
    assert participant_lifecycle({"Phase": "REGISTRATION_OPEN"}, closed) == "ENDED"
    assert participant_lifecycle({"Phase": "ACTIVE"}, closed) == "ENDED"  # reconnect re-read


def test_held_is_preserved_by_configuration_normalisation_not_coerced_to_ready():
    assert normalise_configuration(_event("HELD"))["RuntimePhase"] == "HELD"


def test_ended_participant_projection_preserves_team_captain_progress_and_history():
    projection = participant_projection(
        event=_event("CLOSED"), participant=_participant(), stations=_station(),
        submissions=[{
            "SubmissionID": "S-1", "TeamID": "T-1", "ActivityID": "A", "Status": "APPROVED",
            "Score": 9, "ReviewedAt": "2026-08-26T10:00:00Z", "ReviewedBy": "Kai",
        }],
        team_members=[{"ParticipantID": "P-1", "Name": "Kai", "IsTeamFormationCaptain": True}],
    )
    assert projection["Lifecycle"] == "ENDED"
    assert projection["RuntimePhase"] == "CLOSED"
    assert projection["TeamIdentity"] == "Orion"
    assert projection["CaptainParticipantID"] == "P-1"
    assert projection["Progress"]["Completed"] == 1
    preserved = projection["Progress"]["SubmissionsByActivity"]["A"]
    assert preserved["Status"] == "APPROVED" and preserved["Score"] == 9
    assert preserved["ReviewedAt"] == "2026-08-26T10:00:00Z"


def test_ended_facilitator_and_projector_projections_preserve_results_without_team_strategy_leakage():
    facilitator = facilitator_projection(
        event=_event("CLOSED"), teams=[{"TeamID": "T-1", "TeamIdentity": "Orion"}],
        participants=[{"ParticipantID": "P-1", "TeamID": "T-1", "Name": "Kai", "IsTeamFormationCaptain": True}],
        stations=_station(),
        submissions=[{"SubmissionID": "S-1", "TeamID": "T-1", "ActivityID": "A", "Status": "APPROVED"}],
        leaderboard=[{"TeamID": "T-1", "TeamName": "Orion", "Score": 9}],
    )
    projector = projector_projection(facilitator, _event("CLOSED"))
    assert facilitator["Lifecycle"] == projector["Lifecycle"] == "ENDED"
    assert facilitator["Teams"][0]["CaptainName"] == "Kai"
    assert facilitator["Leaderboard"][0]["Score"] == projector["Leaderboard"][0]["Score"] == 9
    assert "SelectedMissionActivityIDs" not in projector["Teams"][0]
    assert facilitator["MissionOperations"][0]["SecretState"] == "RELEASED"


def test_040_runtime_contract_is_irreversible_and_accepts_only_the_required_states():
    migration = (ROOT / "supabase/040_theme_park_race_terminal_lifecycle.sql").read_text()
    runtime = migration.split(f"CREATE OR REPLACE FUNCTION public.{RUNTIME_RPC}", 1)[1].split(
        "CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_board_set_mission_operation", 1
    )[0]
    assert "('READY', 'ACTIVE', 'HELD', 'CLOSED')" in runtime
    assert "Mission is ended and cannot be restarted" in runtime
    assert "cannot be reset to READY after it has started" in runtime
    assert "'Lifecycle', CASE WHEN v_phase = 'CLOSED' THEN 'ENDED'" in runtime
    assert "SECURITY DEFINER" in runtime and "SET search_path = ''" in runtime


def test_040_operation_contract_blocks_secret_and_availability_writes_only_after_end():
    migration = (ROOT / "supabase/040_theme_park_race_terminal_lifecycle.sql").read_text()
    operation = migration.split(f"CREATE OR REPLACE FUNCTION public.{OPERATION_RPC}", 1)[1]
    assert "RuntimePhase', 'READY')) = 'CLOSED'" in operation
    assert "operational mission controls are closed" in operation
    assert "('AVAILABLE','TEMPORARILY_UNAVAILABLE','CLOSED')" in operation
    assert "('LOCKED','RELEASED')" in operation
    assert "nullif(trim(p_actor), '') IS NULL" in operation


def test_existing_canonical_participant_writes_remain_active_only_for_routes_and_open_board():
    route_source = (ROOT / "supabase/037_theme_park_race_engine.sql").read_text()
    board_source = (ROOT / "supabase/038_theme_park_race_open_mission_board.sql").read_text()
    for function_name in (
        "exos_v2_theme_park_race_submit",
        "exos_v2_theme_park_race_submission_guard",
    ):
        definition = route_source.split(f"FUNCTION public.{function_name}", 1)[1]
        assert "RuntimePhase" in definition and "ACTIVE" in definition
    for function_name in (
        "exos_v2_theme_park_race_board_select",
        "exos_v2_theme_park_race_board_submit",
        "exos_v2_theme_park_race_board_record_ride_outcome",
    ):
        definition = board_source.split(f"FUNCTION public.{function_name}", 1)[1]
        assert "RuntimePhase" in definition and "<> 'ACTIVE'" in definition


def test_ended_server_boundary_rejects_select_submit_resubmit_ride_bonus_and_secret_actions():
    """Every participant action is gated by the same canonical ACTIVE check."""
    source = (ROOT / "supabase/038_theme_park_race_open_mission_board.sql").read_text()
    select = source.split("FUNCTION public.exos_v2_theme_park_race_board_select", 1)[1]
    submit = source.split("FUNCTION public.exos_v2_theme_park_race_board_submit", 1)[1]
    ride = source.split("FUNCTION public.exos_v2_theme_park_race_board_record_ride_outcome", 1)[1]
    assert "OPEN_MISSION_BOARD is not active" in select
    assert "OPEN_MISSION_BOARD is not active" in submit  # initial + resubmission, BONUS, SECRET
    assert "OPEN_MISSION_BOARD is not active" in ride
    assert "MissionState','REJECTED'" in submit or "'REJECTED'" in submit


def test_040_rollback_refuses_held_state_and_restores_pre_040_contracts_without_deleting_data():
    rollback = (ROOT / "supabase/040_theme_park_race_terminal_lifecycle_rollback.sql").read_text()
    assert "Rollback blocked: Theme Park Race HELD runtime state exists" in rollback
    assert "CREATE OR REPLACE FUNCTION public.exos_v2_set_theme_park_race_runtime_phase" in rollback
    assert "('READY', 'ACTIVE', 'CLOSED')" in rollback
    assert "CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_board_set_mission_operation" in rollback
    assert "DROP " not in rollback.upper()
    assert "DELETE " not in rollback.upper()


def test_040_verifier_is_read_only_and_checks_acl_path_and_terminal_definitions():
    verifier = (ROOT / "supabase/verification/exos_v2_theme_park_race_terminal_lifecycle_verify.sql").read_text()
    assert "search_path=\"\"" in verifier
    assert "anon_authenticated_execute_revoked" in verifier
    assert "service_role_execute_present" in verifier
    assert "held_and_terminal_runtime_definition_installed" in verifier
    assert "ended_operation_guard_definition_installed" in verifier
    assert all(token not in verifier.upper() for token in ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "DROP "))


def _run_ended_participant_surface(shared):
    import types
    import streamlit as st
    from screens.theme_park_race import render_theme_park_race_participant

    if "seeded" not in st.session_state:
        st.session_state["participant_session_token"] = "SESSION"
        st.session_state["seeded"] = True
    index = shared.get("index", 0)
    workspace = shared["workspaces"][min(index, len(shared["workspaces"]) - 1)]
    shared["index"] = index + 1
    runtime = types.SimpleNamespace(
        theme_park_race_participant_workspace=lambda _token: workspace,
        save_theme_park_race_submission=lambda *args, **kwargs: shared["calls"].append(("submit", args)),
        select_theme_park_race_mission=lambda *args, **kwargs: shared["calls"].append(("select", args)),
        record_theme_park_race_ride_outcome=lambda *args, **kwargs: shared["calls"].append(("ride", args)),
        claim_team_formation_captain=lambda *args, **kwargs: shared["calls"].append(("claim", args)),
        recover_team_formation_captain=lambda *args, **kwargs: shared["calls"].append(("recover", args)),
    )
    render_theme_park_race_participant(types.SimpleNamespace(runtime=runtime), device_id="DEV")


def _ended_workspace():
    return {
        "EventID": "CERT-END-1", "TeamID": "T-1", "TeamIdentity": "Orion",
        "Lifecycle": "ENDED", "RuntimePhase": "CLOSED", "StrategyMode": "OPEN_MISSION_BOARD",
        "IsCaptain": True, "CaptainSessionActive": True, "Route": [], "TeamMembers": [],
        "Progress": {"Completed": 1, "Total": 3, "SubmissionsByActivity": {}},
        "MissionBoard": [{"ActivityID": "A", "MissionState": "SELECTED", "DisplayName": "Mission A"}],
    }


def test_app_ended_participant_screen_is_terminal_dynamic_and_has_no_write_controls():
    shared = {"workspaces": [_ended_workspace()], "calls": []}
    at = AppTest.from_function(_run_ended_participant_surface, args=(shared,))
    at.run()
    assert not at.exception
    text = " ".join(item.value for item in at.markdown) + " " + " ".join(item.value for item in at.success)
    assert "Mission Complete 🎉" in text and "Orion" in text
    assert any(item.value == "1/3" for item in at.metric)
    all_text = text + " " + " ".join(item.value for item in at.info)
    assert "Waiting for the facilitator to start" not in all_text
    assert "SESSION" not in all_text
    assert not [button for button in at.button if "submit" in button.key or "select" in button.key or "captain" in button.key]
    assert shared["calls"] == []


def test_app_stale_active_browser_cannot_reach_a_write_after_canonical_end():
    active = _ended_workspace() | {
        "Lifecycle": "ACTIVE", "RuntimePhase": "ACTIVE",
        "MissionBoard": [{
            "ActivityID": "A", "DisplayName": "Mission A", "MissionClass": "STANDARD", "MissionState": "SELECTED",
            "Evidence": {"Text": {"Required": True}},
        }],
    }
    shared = {"workspaces": [active, _ended_workspace()], "calls": []}
    at = AppTest.from_function(_run_ended_participant_surface, args=(shared,))
    at.run()
    text_area = next(item for item in at.text_area if item.key == "theme_race_text_A")
    text_area.set_value("evidence")
    at.run()
    # The second canonical read is ENDED.  The formerly visible submit widget
    # is intentionally absent, so no stale client click can reach the adapter.
    assert not [button for button in at.button if button.key == "theme_race_submit_A"]
    assert shared["calls"] == []


def _run_ended_facilitator_surface(shared):
    import types
    import streamlit as st
    from screens.theme_park_race import render_theme_park_race_facilitator

    workspace = shared["workspace"]
    runtime = types.SimpleNamespace(
        theme_park_race_facilitator_workspace=lambda _event_id: workspace,
        get_theme_park_race_players=lambda _event_id: [],
    )
    render_theme_park_race_facilitator(
        types.SimpleNamespace(runtime=runtime),
        types.SimpleNamespace(set_theme_park_race_runtime_phase=lambda *args: shared["calls"].append(args)),
        "CERT-END-1",
    )


def test_app_ended_facilitator_screen_has_no_start_or_reopen_control_and_preserves_status():
    workspace = {
        "Lifecycle": "ENDED", "RuntimePhase": "CLOSED", "TeamFormationPhase": "ACTIVE",
        "RegistrationCount": 2, "TeamCount": 1, "CaptainCount": 1, "MissionCount": 3,
        "PendingReviewCount": 0, "StrategyMode": "OPEN_MISSION_BOARD", "MissionOperations": [],
        "Teams": [{"TeamID": "T-1", "TeamIdentity": "Orion", "RegisteredParticipants": 2,
                   "CaptainName": "Kai", "Completed": 1, "Total": 3, "PendingReview": 0, "Rejected": 0,
                   "CurrentActivityID": "", "SelectedMissionActivityIDs": []}], "ReviewQueue": [],
    }
    shared = {"workspace": workspace, "calls": []}
    at = AppTest.from_function(_run_ended_facilitator_surface, args=(shared,))
    at.run()
    assert not at.exception
    labels = [button.label for button in at.button]
    assert "Start Mission" not in labels and "Resume Mission" not in labels and "End Mission" not in labels
    assert any(item.value == "MISSION ENDED" for item in at.error)
    assert not any("Team Formation is active" in item.value for item in at.success)
    assert shared["calls"] == []
