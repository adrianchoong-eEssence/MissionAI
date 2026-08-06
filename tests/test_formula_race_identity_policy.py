from pathlib import Path

from data.runtime_database import SupabaseRuntimeDB
from screens.participant import is_formula_race_event


SQL = Path("supabase/015_formula_race_preassigned_identity.sql").read_text()


def test_formula_race_event_policy_detection():
    assert is_formula_race_event({"EventName": "Formula R.A.C.E. Day One"})
    assert is_formula_race_event({"IdentityPolicy": "PREASSIGNED_ONLY"})
    assert is_formula_race_event({"EventName": "RACE", "Client": "Loreal"})
    assert not is_formula_race_event({"EventName": "Bayu Beach Labyrinth"})


def test_runtime_calls_preassigned_lookup_without_team_or_country_input():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    calls = []
    runtime._request = lambda *args, **kwargs: calls.append((args, kwargs)) or {
        "ParticipantID": "P1", "TeamID": "F1-01", "Team": "Scuderia Ferrari"
    }
    player = runtime.join_preassigned_player("RACE", "Ada", "Lovelace", "DEVICE")
    assert player["TeamID"] == "F1-01"
    assert calls[0][0][1] == "rpc/exos_join_preassigned_event"
    assert set(calls[0][1]["payload"]) == {
        "p_join_code", "p_first_name", "p_last_name", "p_device_id"
    }


def test_preassigned_rpc_is_lookup_only_and_fail_closed():
    function = SQL.split("public.exos_join_preassigned_event", 1)[1]
    forbidden = (
        "insert into public.runtime_participants",
        "insert into public.runtime_teams",
        "order by count(participant.participant_id)",
        "p_requested_team_id",
        "|LEADER",
    )
    assert all(value not in function for value in forbidden)
    assert "v_matches = 0" in function
    assert "PreassignedIdentityRequired" in function
    assert "nullif(trim(v_participant.team_id), '') is null" in function
