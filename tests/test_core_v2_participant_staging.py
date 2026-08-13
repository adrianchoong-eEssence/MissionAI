from pathlib import Path

import pytest

from data.standard_core_v2_adapter import StandardCoreV2Adapter
from engines.programme_adapter import CanonicalProgrammeAdapter
from scripts.exos_core_v2_prepare_aia_weekend import (
    agile_programme,
    allocate_country_pool,
    team_configuration,
)


ROOT = Path(__file__).resolve().parents[1]
AIA = {
    "OXO0DT": (
        "AIA-WE-260810081110-UPPER",
        ["Korea", "Japan"],
    ),
    "C0OCUS": (
        "AIA-WE-260810081110-LOWER",
        ["India", "Malaysia", "Philippines", "Thailand"],
    ),
}


def test_staging_entrypoint_preserves_standard_guard_but_allows_explicit_race_captain_route():
    source = (ROOT / "Participant.py").read_text()
    assert '_race_captain_requested = str(st.query_params.get("race", "")).strip() == "1"' in source
    staging = source.index('if _deployment_environment() == "staging" and not _race_captain_requested:')
    stop = source.index("st.stop()", staging)
    race_import = source.index("from data.formula_race_core_v2_adapter")
    strict_path = source[staging:stop]
    assert staging < stop < race_import
    assert "show_participant()" in strict_path
    assert "GoogleSheetsDB" not in strict_path
    assert "get_runtime_database" not in strict_path
    assert "formula_race" not in strict_path.casefold()
    assert "if _race_captain_requested or st.session_state.get(\"race_captain\"):" in source
    assert source.index("if _race_captain_requested or st.session_state.get(\"race_captain\"):") < source.index("show_formula_race_captain()")


def test_standard_participant_screen_has_no_hybrid_data_source():
    source = (ROOT / "screens/participant.py").read_text()
    assert "GoogleSheetsDB" not in source
    assert "data.google_sheets" not in source
    assert "get_runtime_database" not in source
    assert "get_standard_database" in source
    assert "YOUR TEAM" in source
    assert "TEAM IDENTITY" in source
    assert "YOUR COUNTRY" not in source
    assert "Country team" not in source
    assert "COUNTRY_LANGUAGE_PROMPTS" not in source


@pytest.mark.parametrize("join_code,expected", AIA.items())
def test_existing_aia_join_codes_and_team_configuration(join_code, expected):
    event_id, countries = expected
    upper, lower = allocate_country_pool(2, 4)
    allocation = upper if event_id.endswith("-UPPER") else lower
    teams = team_configuration(event_id, allocation)
    assert join_code in AIA
    assert [team["Country"] for team in teams] == countries
    assert len(countries) == len(set(countries))


def test_aia_standard_activity_visibility_contract():
    event_id = AIA["C0OCUS"][0]
    rows = [module["Activities"][0] for module in agile_programme(event_id)]
    snapshot = CanonicalProgrammeAdapter(event_id, rows).snapshot()
    assert snapshot.errors == []
    expected = {
        "Pipeline": "PIPELINE",
        "Helium Stick": "HELIUM",
        "Key Punch": "KEYPUNCH",
        "Catalyst Challenge": "CATALYST",
        "NASI": "NASI",
    }
    for activity in snapshot.activities:
        if activity["StageName"] in expected:
            state = {"Stage": {"ActivityID": activity["ActivityID"]}}
            view = snapshot.participant_view(state)
            assert view["Activity"] == activity["StageName"]
            assert activity["SubmissionType"] == expected[activity["StageName"]]
    lunch = next(row for row in snapshot.activities if row["StageName"] == "Lunch / Break")
    assert lunch["ContentType"] == "Break"
    assert lunch["RuntimeEligible"] is False


def test_join_and_restore_use_only_canonical_identity_rpcs():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    calls = []

    def rpc(name, payload, admin=True):
        calls.append((name, payload, admin))
        return {
            "EventID": AIA["OXO0DT"][0], "ParticipantID": "P1",
            "TeamID": "T1", "Team": "Korea", "Country": "Korea",
            "Name": "Ada Lovelace", "SessionToken": "S1",
        }

    adapter._rpc = rpc
    joined = adapter.join_player_by_code("OXO0DT", "Ada Lovelace", device_id="DEVICE-1")
    restored = adapter.restore_join("OXO0DT", "Ada Lovelace", "DEVICE-1")
    assert joined["Team"] == restored["Team"] == "Korea"
    assert [call[0] for call in calls] == [
        "exos_v2_join_event_v2", "exos_v2_restore_join",
    ]
    assert all(call[2] is False for call in calls)


def test_team_and_nasi_submission_keys_are_idempotent_and_facilitator_compatible():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    calls = []
    adapter.get_player_by_token = lambda token: {
        "ParticipantID": "P1", "TeamID": "T1", "Team": "Korea",
    }
    adapter._one = lambda path, query, admin=True: {
        "activity_payload": {"participant_scope": "TEAM"},
    }

    def rpc(name, payload, admin=True):
        calls.append((name, payload, admin))
        return payload

    adapter._rpc = rpc
    adapter.save_submission(
        event_id="E1", mission_id="PIPELINE", team_name="Korea",
        participant_name="Ada Lovelace", submission_type="PIPELINE",
        metric1=10, metric2=8, metric3=1, session_token="S1",
    )
    adapter.save_submission(
        event_id="E1", mission_id="NASI", team_name="Korea",
        participant_name="Ada Lovelace", submission_type="NASI",
        remarks=(
            "N - New Ideas: N\nA - Areas for Improvement: A\n"
            "S - Strengths: S\nI - Implementation: I"
        ), session_token="S1",
    )
    assert [call[0] for call in calls] == [
        "exos_v2_standard_submit", "exos_v2_standard_submit",
    ]
    assert calls[0][1]["p_submission_key"] == "E1|PIPELINE|T1"
    assert calls[1][1]["p_submission_key"] == "E1|NASI|P1"
    assert calls[1][1]["p_submission_payload"]["SubmissionType"] == "NASI"
    assert all(call[2] is False for call in calls)


def test_core_v2_sql_keeps_round_robin_and_duplicate_guards_canonical():
    schema = (ROOT / "supabase/020_exos_core_v2_schema.sql").read_text()
    runtime = (ROOT / "supabase/025_standard_programme_runtime.sql").read_text()
    assert "exos_v2_next_team_id(v_event.event_id)" in schema
    assert "v_event.event_id || '|' || v_normalized || '|'" in schema
    assert "on conflict(event_id,submission_key) do update" in runtime
    for table in (
        "events_v2", "teams_v2", "participants_v2",
        "participant_sessions_v2", "submissions_v2",
    ):
        assert table in schema or table in runtime


def test_stale_session_recovery_preserves_join_and_device_context():
    source = (ROOT / "screens/participant.py").read_text()
    assert 'join_code = normalise_join_code(st.query_params.get("join_code", ""))' in source
    assert "device_id = participant_device_id()" in source
    assert "runtime.restore_join(join_code, participant_name, device_id)" in source
    assert 'desired["join_code"] = join_code' in source
    assert "This identity needs facilitator recovery" in source
