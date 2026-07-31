from pathlib import Path
from unittest.mock import patch

from data.runtime_database import SupabaseRuntimeDB
from data.google_sheets import GoogleSheetsDB
from screens.live_event_console import approval_score
from screens.participant import (
    BRIDGE_OF_TRUST_TRANSMISSION,
    EVA_LABYRINTH_BRIEFING,
    _bayu_submission_status,
    bayu_morning_experiences,
    render_ai_response_after_submission,
)


class MissionDB:
    def get_event_missions(self, event_id):
        return [
            {
                "EventID": event_id,
                "MissionID": f"C{number:02d}",
                "Title": "The King" if number == 18 else f"Experience {number}",
                "DisplayOrder": number,
                "CreditValue": 100 + number,
            }
            for number in range(1, 19)
        ]


def test_bayu_board_contains_exactly_17_and_hides_experience_18():
    missions = bayu_morning_experiences(MissionDB())

    assert len(missions) == 17
    assert {row["MissionID"] for row in missions} == {
        f"C{number:02d}" for number in range(1, 18)
    }


def test_bayu_board_statuses_follow_submission_review_state():
    assert _bayu_submission_status(None) == "Available"
    assert _bayu_submission_status({"Status": "PENDING"}) == "Submitted"
    assert _bayu_submission_status({"Status": "APPROVED"}) == "Approved"
    assert _bayu_submission_status({"Status": "REJECTED"}) == "Rejected"


def test_bayu_approval_uses_authored_intelligence_credits():
    score = approval_score(
        MissionDB(), "EVT-0004", {"MissionID": "C01"},
    )
    assert score == 101


def test_ai_response_is_hidden_until_facilitator_approval():
    mission = {"MissionCompleteMessage": "Archive restored."}
    with patch("screens.participant.st.markdown") as markdown:
        shown = render_ai_response_after_submission(
            mission, {"Status": "PENDING"},
        )
    assert shown is False
    markdown.assert_not_called()


def test_runtime_country_assignment_and_roster_preserve_one_reference_team():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET":
            return [{
                "participant_id": "P1",
                "display_name": "Adrian Choong",
                "team_name": "Malaysia",
                "status": "COUNTRY:Malaysia|LEADER",
                "session_token": "TOKEN",
            }]
        return []

    runtime._request = request
    runtime.assign_participant_country_team("TOKEN", "Malaysia", "Malaysia")
    roster = runtime.get_team_roster("EVT-0004", "Malaysia")

    assignment = calls[0][2]["payload"]
    assert assignment == {
        "team_name": "Malaysia", "status": "COUNTRY:Malaysia",
    }
    assert roster[0]["Country"] == "Malaysia"
    assert roster[0]["IsLeader"] is True


def test_existing_team_leader_prevents_a_second_claim():
    runtime = SupabaseRuntimeDB.__new__(SupabaseRuntimeDB)
    runtime.get_player_by_token = lambda token: {
        "EventID": "EVT-0004", "Team": "Team Malaysia",
        "Name": "Second Member", "Status": "COUNTRY:Malaysia",
    }
    runtime.get_team_roster = lambda event_id, team: [
        {"Name": "Existing Leader", "IsLeader": True},
    ]
    runtime._request = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("A second leader must not be written")
    )

    result = runtime.claim_team_leader("SECOND-TOKEN")

    assert result == {"Claimed": False, "LeaderName": "Existing Leader"}


def test_country_join_overrides_round_robin_with_configured_team_mapping():
    class Runtime:
        is_configured = True
        can_publish = True

        def join_player(self, join_code, name):
            return {
                "EventID": "EVT-0004", "Name": name,
                "Team": "Wrong Round Robin Team", "SessionToken": "TOKEN",
            }

        def assign_participant_country_team(self, token, team, country):
            self.assignment = (token, team, country)

    db = GoogleSheetsDB.__new__(GoogleSheetsDB)
    db.runtime = Runtime()
    db.get_event_by_join_code = lambda code: {"EventID": "EVT-0004"}
    db.get_teams = lambda event_id: [
        {"TeamName": "Team Malaysia", "Country": "Malaysia"},
        {"TeamName": "Team Japan", "Country": "Japan"},
    ]

    player = db.join_player_by_code("12DYLD", "Adrian Choong", "Malaysia")

    assert player["Team"] == "Team Malaysia"
    assert player["Country"] == "Malaysia"
    assert db.runtime.assignment == ("TOKEN", "Team Malaysia", "Malaysia")


def test_required_bayu_participant_copy_and_history_fix_are_present():
    source = (
        Path(__file__).resolve().parents[1] / "screens" / "participant.py"
    ).read_text(encoding="utf-8")

    assert "No expedition member may be left behind." in BRIDGE_OF_TRUST_TRANSMISSION
    assert "Seventeen intelligence signals" in EVA_LABYRINTH_BRIEFING
    assert "ENTER THE LABYRINTH" in source
    assert "Your Team Leader submits evidence for the team." in source
    assert "check #" not in source
    assert 'if str(st.query_params.get(key, "")) != str(value)' in source
