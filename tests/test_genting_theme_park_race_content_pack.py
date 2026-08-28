"""Contract tests for the local-only Genting strategic mission-board draft."""
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import re

from engines.theme_park_race import (
    OPEN_MISSION_BOARD,
    RIDE_ATTEMPT_STATES,
    current_route_mission,
    is_theme_park_race,
    mission_board,
    participant_projection,
    project_stations,
    projector_projection,
    required_ride_participants,
    ride_competitive_score,
    ride_submission_errors,
    validate_configuration,
)


ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "content_packs" / "genting_theme_park_race_v1"


def _materializer():
    spec = spec_from_file_location("genting_content_materializer", PACK_DIR / "materialize.py")
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _content(event_id="GENTING-LOCAL-01"):
    return _materializer().materialize_genting_content(event_id)


def _stations(content):
    return project_stations(content["ActivitiesV2"])


def test_genting_pack_is_local_open_board_placeholder_configuration():
    content = _content()
    package, config = content["Package"], content["RaceConfiguration"]
    assert package["PackageSchemaVersion"] == 1
    assert package["LocalOnly"] is True
    assert package["ActivationStatus"] == "DRAFT_PLACEHOLDER_NOT_APPROVED"
    assert config["EngineKind"] == "THEME_PARK_RACE"
    assert config["StrategyMode"] == OPEN_MISSION_BOARD
    assert config["RuntimePhase"] == "READY"
    assert "TeamRoutes" not in config
    assert is_theme_park_race({"_EventPayload": {"RaceConfiguration": config}})
    assert "{{EVENT_ID}}" not in str(content)


def test_team_capacity_and_random_assignment_remain_balanced_for_expected_sixty_six_participants():
    content = _content()
    blueprint, teams = content["EventBlueprint"], content["TeamTemplates"]
    capacities = content["TeamFormationConfiguration"]["TeamCapacities"]
    assert blueprint["TeamStructure"]["FormationMode"] == "RANDOM_ASSIGN"
    assert blueprint["TeamStructure"]["RecommendedTeamCount"] == 6
    assert blueprint["TeamStructure"]["TargetBalancedTeamSize"] == 11
    assert blueprint["ExpectedParticipants"] == 66
    assert len(teams) == len(capacities) == 6
    assert sum(capacities.values()) == 66
    assert {team["Capacity"] for team in teams} == {11}


def test_draft_catalogue_is_valid_open_board_shape_with_ride_bonus_and_locked_secret():
    content = _content()
    team_ids = [team["TeamID"] for team in content["TeamTemplates"]]
    stations = _stations(content)
    config = content["RaceConfiguration"]
    assert validate_configuration({"RaceConfiguration": config}, team_ids, stations) == []
    assert len(stations) == 6
    assert {station["MissionClass"] for station in stations} >= {"RIDE", "BONUS", "SECRET", "STANDARD"}
    assert all(station["RawActivity"]["RaceStation"]["ContentStatus"] == "DRAFT_PLACEHOLDER_NOT_APPROVED" for station in stations)
    operations = config["MissionBoard"]["MissionOperations"]
    assert set(operations) == {station["ActivityID"] for station in stations}
    assert next(row for row in operations.values() if row["SecretState"] == "LOCKED")


def test_required_ride_participation_uses_ceiling_current_canonical_membership():
    assert required_ride_participants(11, 80) == 9
    assert required_ride_participants(10, 80) == 8
    assert required_ride_participants(9, 80) == 8


def _ride_station():
    return {
        "ActivityID": "RIDE-1", "DisplayOrder": 1, "DisplayName": "Ride",
        "MissionClass": "RIDE",
        "RideParticipation": {
            "RequiredPercent": 80, "Rounding": "CEILING",
            "EvidencePathways": ["GROUND_CONTROL", "FULL_TEAM", "FACILITATOR_VERIFIED"],
            "FullParticipationBonus": 0,
        },
        "Evidence": {"Text": {"Required": False}, "Photo": {"Required": False}, "NumericResult": {"Required": False}},
    }


def test_full_team_participation_has_no_competitive_score_advantage():
    assert ride_competitive_score(100, rider_count=9, canonical_team_member_count=11) == 100
    assert ride_competitive_score(100, rider_count=11, canonical_team_member_count=11) == 100


def test_exterior_only_evidence_cannot_satisfy_completed_ride():
    errors = ride_submission_errors(_ride_station(), {
        "RideAttemptStatus": "COMPLETED", "RideEvidencePathway": "GROUND_CONTROL",
        "RiderParticipantIDs": [str(index) for index in range(9)],
        "ImageURL": "attraction-exterior.jpg",
    }, canonical_team_member_count=11)
    assert "Official queue-entry evidence is required; an attraction exterior photo is insufficient." in errors


def test_closed_temporarily_unavailable_and_secret_release_are_canonical_board_states():
    config = {
        "SchemaVersion": 1, "EngineKind": "THEME_PARK_RACE", "StrategyMode": OPEN_MISSION_BOARD,
        "MissionBoard": {"MissionOperations": {
            "RIDE-1": {"OperationalStatus": "CLOSED", "SecretState": "RELEASED"},
            "BONUS-1": {"OperationalStatus": "TEMPORARILY_UNAVAILABLE", "SecretState": "RELEASED"},
            "SECRET-1": {"OperationalStatus": "AVAILABLE", "SecretState": "LOCKED"},
        }},
    }
    stations = [
        _ride_station(),
        {"ActivityID": "BONUS-1", "DisplayOrder": 2, "MissionClass": "BONUS", "Evidence": {}},
        {"ActivityID": "SECRET-1", "DisplayOrder": 3, "MissionClass": "SECRET", "Evidence": {}},
    ]
    board = mission_board(config, stations, team_id="T1", submissions=[])
    assert {row["ActivityID"]: row["MissionState"] for row in board} == {"RIDE-1": "CLOSED", "BONUS-1": "TEMPORARILY_UNAVAILABLE"}
    assert not any(row["CanSelect"] for row in board)
    released = deepcopy(config)
    released["MissionBoard"]["MissionOperations"]["SECRET-1"]["SecretState"] = "RELEASED"
    assert next(row for row in mission_board(released, stations, team_id="T1", submissions=[]) if row["ActivityID"] == "SECRET-1")["MissionState"] == "AVAILABLE"


def test_open_board_refresh_reconnect_restores_own_canonical_selection_without_competitor_leakage():
    config = {
        "SchemaVersion": 1, "EngineKind": "THEME_PARK_RACE", "StrategyMode": OPEN_MISSION_BOARD,
        "RuntimePhase": "ACTIVE", "MissionBoard": {"MaximumConcurrentSelections": 1, "MissionOperations": {
            "A": {"OperationalStatus": "AVAILABLE", "SecretState": "RELEASED"},
            "B": {"OperationalStatus": "AVAILABLE", "SecretState": "RELEASED"},
        }},
    }
    stations = [
        {"ActivityID": "A", "RaceStation": {"Enabled": True, "DisplayOrder": 1, "DisplayName": "A", "MissionClass": "BONUS"}},
        {"ActivityID": "B", "RaceStation": {"Enabled": True, "DisplayOrder": 2, "DisplayName": "B", "MissionClass": "BONUS"}},
    ]
    event = {"EventID": "E", "_EventPayload": {"TeamFormation": {"Phase": "ACTIVE"}, "RaceConfiguration": config}}
    runtime = [
        {"TeamID": "T1", "ActivityID": "A", "StatePayload": {"MissionState": "SELECTED"}, "UpdatedAt": "2026-01-01T00:00:00Z"},
        {"TeamID": "T2", "ActivityID": "B", "StatePayload": {"MissionState": "SELECTED"}, "UpdatedAt": "2026-01-01T00:00:00Z"},
    ]
    participant = {"ParticipantID": "P1", "TeamID": "T1", "CaptainSessionActive": True}
    members = [{"ParticipantID": "P1", "TeamID": "T1"}, {"ParticipantID": "P2", "TeamID": "T1"}]
    first = participant_projection(event=event, participant=participant, stations=project_stations(stations), submissions=[], mission_runtime=runtime, team_members=members)
    reconnected = participant_projection(event=event, participant=participant, stations=project_stations(stations), submissions=[], mission_runtime=runtime, team_members=members)
    assert [(row["ActivityID"], row["MissionState"]) for row in first["MissionBoard"]] == [(row["ActivityID"], row["MissionState"]) for row in reconnected["MissionBoard"]]
    assert next(row for row in first["MissionBoard"] if row["ActivityID"] == "A")["MissionState"] == "SELECTED"
    assert "T2" not in str(first["MissionBoard"])


def test_open_board_server_contract_serialises_selection_and_submission_without_new_tables():
    migration = (ROOT / "supabase" / "038_theme_park_race_open_mission_board.sql").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in migration
    assert "FOR UPDATE" in migration
    assert "ON CONFLICT(event_id,submission_key)" in migration
    assert "create table public" not in migration.lower()
    assert "exos_v2_theme_park_race_board_select" in migration
    assert "exos_v2_theme_park_race_board_submit" in migration
    assert "RiderParticipantIDs" in migration
    assert "FORMULA_RACE" not in migration


def test_ride_attempt_outcomes_remain_distinct_runtime_facts():
    assert set(RIDE_ATTEMPT_STATES) == {"ATTEMPTED", "COMPLETED", "ABORTED_BY_ATTRACTION", "TEAM_WITHDREW"}


def test_open_board_projector_never_leaks_selected_or_current_team_strategy():
    facilitator = {
        "Teams": [{"TeamID": "T1", "TeamIdentity": "Alpha", "Completed": 1, "Total": 3, "CurrentActivityID": "SECRET", "SelectedMissionActivityIDs": ["SECRET"], "MissionBoard": [{"ActivityID": "SECRET"}]}],
        "MissionOperations": [{"ActivityID": "SECRET", "DisplayName": "Secret", "MissionClass": "SECRET", "OperationalStatus": "AVAILABLE", "SecretState": "RELEASED"}],
    }
    projection = projector_projection(facilitator, {"SchemaVersion": 1, "EngineKind": "THEME_PARK_RACE", "StrategyMode": OPEN_MISSION_BOARD, "MissionBoard": {}})
    assert "CurrentActivityID" not in projection["Teams"][0]
    assert "SelectedMissionActivityIDs" not in projection["Teams"][0]
    assert "MissionBoard" not in projection["Teams"][0]
    assert projection["ReleasedSecretMissionAnnouncements"] == ["Secret"]


def test_no_wallet_leaderboard_conflation_and_formula_and_route_strategy_remain_unchanged():
    content = _content()
    assert content["EventBlueprint"]["ScoringPolicy"]["WalletCredits"]["Enabled"] is False
    package_text = (PACK_DIR / "genting_theme_park_race_v1.json").read_text(encoding="utf-8")
    assert "FORMULA_RACE" not in package_text
    assert not is_theme_park_race({"_EventPayload": {"RaceConfiguration": {"EngineKind": "FORMULA_RACE"}}})
    assert current_route_mission(["A", "B"], [{"ActivityID": "A", "Status": "SUBMITTED"}]) == ("B", "")


def _sql_function(source, function_name):
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{re.escape(function_name)}\(.*?\n\$\$;",
        source,
        flags=re.DOTALL,
    )
    assert match, f"{function_name} definition is missing"
    return match.group(0)


def test_038_preserves_037_foreign_engine_protection_and_route_strategy_contract():
    migration = (ROOT / "supabase" / "038_theme_park_race_open_mission_board.sql").read_text(encoding="utf-8")
    guard = _sql_function(migration, "exos_v2_theme_park_race_submission_guard")
    assert "NOT IN ('', 'THEME_PARK_RACE')" in migration
    assert "This event is already configured for a different race engine" in migration
    assert "IF v_strategy = 'CONFIGURED_TEAM_ROUTE' THEN" in guard
    assert "Only the configured current Theme Park Race mission can be submitted" in guard
    assert "FORMULA_RACE" not in migration


def test_038_freezes_structural_configuration_after_canonical_runtime_or_submission_state():
    migration = (ROOT / "supabase" / "038_theme_park_race_open_mission_board.sql").read_text(encoding="utf-8")
    save_configuration = _sql_function(migration, "exos_v2_theme_park_race_save_configuration")
    assert "public.activity_runtime_v2" in save_configuration
    assert "public.submissions_v2" in save_configuration
    assert "v_has_authoritative_play_state" in save_configuration
    assert "v_existing_structural IS DISTINCT FROM v_incoming_structural" in save_configuration
    assert "'StrategyMode', v_strategy" in save_configuration
    assert "'MissionBoard'" in save_configuration
    assert "Theme Park Race structural configuration is frozen after authoritative runtime or submissions exist" in save_configuration
    assert "RuntimePhase must be changed through its dedicated runtime RPC after play begins" in save_configuration


def test_038_retains_independent_during_play_mission_operation_controls_and_requires_facilitator_actor():
    migration = (ROOT / "supabase" / "038_theme_park_race_open_mission_board.sql").read_text(encoding="utf-8")
    operation = _sql_function(migration, "exos_v2_theme_park_race_board_set_mission_operation")
    assert "nullif(trim(p_actor), '') IS NULL" in operation
    assert "Event ID, mission ActivityID, and facilitator identity are required" in operation
    assert "('AVAILABLE','TEMPORARILY_UNAVAILABLE','CLOSED')" in operation
    assert "('LOCKED','RELEASED')" in operation
    assert "'MissionOperations'" in operation
    assert "v_configuration := jsonb_set" in operation


def test_038_security_definer_contract_is_pinned_and_public_is_revoked_for_every_new_function():
    migration = (ROOT / "supabase" / "038_theme_park_race_open_mission_board.sql").read_text(encoding="utf-8")
    functions = re.findall(r"CREATE OR REPLACE FUNCTION public\.(exos_v2_theme_park_race_[a-z_]+)\(", migration)
    assert functions == [
        "exos_v2_theme_park_race_save_configuration",
        "exos_v2_theme_park_race_board_set_mission_operation",
        "exos_v2_theme_park_race_board_select",
        "exos_v2_theme_park_race_board_record_ride_outcome",
        "exos_v2_theme_park_race_board_submit",
        "exos_v2_theme_park_race_submission_guard",
        "exos_v2_theme_park_race_score_guard",
    ]
    for function_name in functions:
        definition = _sql_function(migration, function_name)
        assert "SECURITY DEFINER" in definition
        assert "SET search_path = ''" in definition
    assert "REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_score_guard() FROM anon, authenticated, service_role, PUBLIC;" in migration
    assert not re.search(r"(?m)^\s*EXECUTE\s+(?!FUNCTION\b)", migration)


def test_037_and_038_explicitly_reset_persistent_create_or_replace_acls_to_the_role_matrix():
    migration_037 = (ROOT / "supabase" / "037_theme_park_race_engine.sql").read_text(encoding="utf-8")
    migration_038 = (ROOT / "supabase" / "038_theme_park_race_open_mission_board.sql").read_text(encoding="utf-8")
    revoke_roles = "FROM anon, authenticated, service_role, PUBLIC;"
    expected_037 = {
        "public.exos_v2_theme_park_race_save_configuration(text,jsonb,text)": "service_role",
        "public.exos_v2_set_theme_park_race_runtime_phase(text,text,text)": "service_role",
        "public.exos_v2_theme_park_race_submit(text,text,jsonb)": "anon, authenticated, service_role",
        "public.exos_v2_theme_park_race_submission_guard()": None,
    }
    expected_038 = {
        "public.exos_v2_theme_park_race_save_configuration(text,jsonb,text)": "service_role",
        "public.exos_v2_theme_park_race_board_set_mission_operation(text,text,text,text,text)": "service_role",
        "public.exos_v2_theme_park_race_board_select(text,text)": "anon, authenticated, service_role",
        "public.exos_v2_theme_park_race_board_record_ride_outcome(text,text,text,jsonb)": "anon, authenticated, service_role",
        "public.exos_v2_theme_park_race_board_submit(text,text,jsonb)": "anon, authenticated, service_role",
        "public.exos_v2_theme_park_race_submission_guard()": None,
        "public.exos_v2_theme_park_race_score_guard()": None,
    }
    for migration, matrix in ((migration_037, expected_037), (migration_038, expected_038)):
        for signature, grantees in matrix.items():
            assert f"REVOKE ALL ON FUNCTION {signature} {revoke_roles}" in migration
            grant = f"GRANT EXECUTE ON FUNCTION {signature}"
            if grantees is None:
                assert grant not in migration
            else:
                assert f"{grant} TO {grantees};" in migration


def test_037a_is_a_privilege_only_additive_remediation_with_the_037_role_matrix():
    remediation = (ROOT / "supabase" / "037a_theme_park_race_acl_hardening.sql").read_text(encoding="utf-8")
    assert remediation.lstrip().startswith("--")
    assert "BEGIN;" in remediation and remediation.rstrip().endswith("COMMIT;")
    assert "CREATE OR REPLACE FUNCTION" not in remediation
    assert "CREATE TABLE" not in remediation
    assert "CREATE TRIGGER" not in remediation
    assert "INSERT INTO" not in remediation
    assert "UPDATE public." not in remediation
    assert "DELETE FROM" not in remediation
    assert "REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_save_configuration(text,jsonb,text) FROM anon, authenticated, service_role, PUBLIC;" in remediation
    assert "REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_submission_guard() FROM anon, authenticated, service_role, PUBLIC;" in remediation
    assert "GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_save_configuration(text,jsonb,text) TO service_role;" in remediation
    assert "GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_submit(text,text,jsonb) TO anon, authenticated, service_role;" in remediation
    assert "GRANT EXECUTE ON FUNCTION public.exos_v2_theme_park_race_submission_guard()" not in remediation


def test_039_board_review_reopen_contract_is_additive_scoped_and_guarded():
    migration = (ROOT / "supabase" / "039_theme_park_race_review_reopen_contract.sql").read_text(encoding="utf-8")
    rollback = (ROOT / "supabase" / "039_theme_park_race_review_reopen_contract_rollback.sql").read_text(encoding="utf-8")
    verifier = (ROOT / "supabase" / "verification" / "exos_v2_theme_park_race_review_reopen_contract_verify.sql").read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION public.exos_v2_theme_park_race_board_review" in migration
    assert "OPEN_MISSION_BOARD" in migration and "THEME_PARK_RACE" in migration
    assert "p_expected_submitted_at" in migration and "Submission revision is stale" in migration
    assert "'MissionState', 'REJECTED'" in migration
    assert "'MissionState', 'APPROVED'" in migration
    assert "pg_advisory_xact_lock" in migration
    assert "THEME_PARK_RACE_BOARD_REVIEWED" in migration
    assert "theme-park-race-board-review-039|" in migration
    assert "RevisionSubmittedAt" in migration
    assert "ON CONFLICT(event_id, idempotency_key) DO NOTHING" in migration
    assert "DO UPDATE SET score_delta" not in migration
    assert "REVOKE ALL ON FUNCTION public.exos_v2_theme_park_race_board_review" in migration
    assert "TO service_role" in migration
    assert "Rollback blocked: Theme Park Race board review/reopen state exists" in rollback
    assert "THEME_PARK_RACE_BOARD_REVIEW_039" in rollback
    assert "DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_board_review" in rollback
    assert "to_regprocedure" in verifier and "no_unexpected_overloads" in verifier
    assert "service_role_execute_present" in verifier
    assert "INSERT INTO" not in verifier.upper()


def test_038_rollback_blocks_open_board_data_and_restores_the_exact_037_replacements():
    baseline = (ROOT / "supabase" / "037_theme_park_race_engine.sql").read_text(encoding="utf-8")
    rollback = (ROOT / "supabase" / "038_theme_park_race_open_mission_board_rollback.sql").read_text(encoding="utf-8")
    assert "OPEN_MISSION_BOARD configuration, runtime, submission lineage, or audit history exists" in rollback
    assert "public.events_v2" in rollback
    assert "public.activity_runtime_v2" in rollback
    assert "public.submissions_v2" in rollback
    assert "public.audit_log_v2" in rollback
    assert "DROP TRIGGER IF EXISTS exos_v2_theme_park_race_score_guard_trg" in rollback
    assert "DROP FUNCTION IF EXISTS public.exos_v2_theme_park_race_score_guard()" in rollback
    assert _sql_function(rollback, "exos_v2_theme_park_race_save_configuration") == _sql_function(
        baseline, "exos_v2_theme_park_race_save_configuration"
    )
    assert _sql_function(rollback, "exos_v2_theme_park_race_submission_guard") == _sql_function(
        baseline, "exos_v2_theme_park_race_submission_guard"
    )
    assert "FOR EACH ROW EXECUTE FUNCTION public.exos_v2_theme_park_race_submission_guard();" in rollback


def test_037_and_038_verifiers_check_release_properties_without_creating_fixtures():
    verifier_037 = (ROOT / "supabase" / "verification" / "exos_v2_theme_park_race_engine_verify.sql").read_text(encoding="utf-8")
    verifier_038 = (ROOT / "supabase" / "verification" / "exos_v2_theme_park_race_open_mission_board_verify.sql").read_text(encoding="utf-8")
    for verifier in (verifier_037, verifier_038):
        assert "to_regprocedure" in verifier
        assert "prosecdef" in verifier
        assert "search_path=" in verifier
        assert "aclexplode" in verifier
        assert "no_unexpected_overloads" in verifier
        assert "no_unintended_anon_authenticated_execute" in verifier
        assert "INSERT INTO" not in verifier.upper()
        assert "CREATE TABLE" not in verifier.upper()
    assert "trigger_points_to_037_guard" in verifier_037
    assert "replaced_save_configuration_definition_installed" in verifier_038
    assert "open_board_submission_guard_definition_installed" in verifier_038
    assert "score_guard_trigger_points_to_expected_function" in verifier_038
    assert "StrategyMode" in verifier_038


def test_037_and_038_verifiers_accept_only_postgresql_empty_search_path_representations():
    verifier_037 = (ROOT / "supabase" / "verification" / "exos_v2_theme_park_race_engine_verify.sql").read_text(encoding="utf-8")
    verifier_038 = (ROOT / "supabase" / "verification" / "exos_v2_theme_park_race_open_mission_board_verify.sql").read_text(encoding="utf-8")
    accepted_clause = "setting.value IN ('search_path=', 'search_path=\"\"')"
    accepts_empty_search_path = lambda setting: setting in {"search_path=", 'search_path=""'}
    assert accepts_empty_search_path("search_path=")
    assert accepts_empty_search_path('search_path=""')
    assert not accepts_empty_search_path("search_path=public")
    assert not accepts_empty_search_path("search_path=pg_catalog")
    for verifier in (verifier_037, verifier_038):
        assert accepted_clause in verifier
