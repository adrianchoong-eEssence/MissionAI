from pathlib import Path
from unittest.mock import patch

import streamlit as st

from data.runtime_database import SupabaseRuntimeDB
from data.google_sheets import GoogleSheetsDB, bayu_country_teams
from screens.live_event_console import approval_score
from screens.participant import (
    EVA_EXPEDITION_OPENING_TRANSMISSION,
    EVA_PORTRAIT_REFERENCE,
    EVA_LABYRINTH_BRIEFING,
    _bayu_submission_status,
    bayu_ai_portrait_reference,
    bayu_morning_experiences,
    current_team_leader,
    participant_ai_identity,
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


def test_bayu_ai_companions_reuse_the_single_existing_eva_portrait():
    class AssetDB:
        @staticmethod
        def get_character_portrait(character_name):
            assert character_name == "EVA"
            return EVA_PORTRAIT_REFERENCE

    references = {
        name: bayu_ai_portrait_reference(AssetDB())
        for name in (
            "EVA", "Alpha", "Bravo", "Luna", "Delta", "Charlie",
            "Echo", "Foxtrot", "Unmapped Companion",
        )
    }

    assert set(references.values()) == {EVA_PORTRAIT_REFERENCE}


def test_bayu_ai_portrait_has_safe_reference_when_catalogue_read_fails():
    class UnavailableAssetDB:
        @staticmethod
        def get_character_portrait(character_name):
            raise RuntimeError("temporary catalogue failure")

    assert bayu_ai_portrait_reference(UnavailableAssetDB()) == EVA_PORTRAIT_REFERENCE


def test_evt0004_replaces_luna_with_eva_without_mutating_stored_identity():
    luna = {
        "Name": "Luna",
        "Personality": "Warm expedition guide",
        "Greeting": "Hello Team. I'm Luna...",
        "PortraitURL": "supabase://characters/luna",
    }

    identity = participant_ai_identity(luna, "EVT-0004")

    assert identity["Name"] == "EVA"
    assert identity["Role"] == "Expedition Virtual Assistant"
    assert identity["PortraitURL"] == EVA_PORTRAIT_REFERENCE
    assert identity["Greeting"] == EVA_EXPEDITION_OPENING_TRANSMISSION
    assert "Luna" not in identity["Greeting"]
    assert luna["Name"] == "Luna"


def test_non_bayu_event_keeps_its_existing_ai_companion():
    luna = {"Name": "Luna", "Greeting": "Hello Team. I'm Luna..."}

    assert participant_ai_identity(luna, "EVT-0099") == luna


def test_bayu_ai_response_keeps_label_but_uses_shared_hologram():
    mission = {
        "CharacterSource": "Alpha",
        "CharacterPortraitURL": "supabase://other-alpha-portrait",
        "MissionCompleteMessage": "Intelligence uploaded.",
    }
    with patch("screens.participant.render_character_card", return_value=True) as card:
        shown = render_ai_response_after_submission(
            mission,
            {"Status": "APPROVED"},
            ai_portrait_reference=EVA_PORTRAIT_REFERENCE,
        )

    assert shown is True
    card.assert_called_once_with(
        "Alpha", EVA_PORTRAIT_REFERENCE, "Intelligence uploaded.",
    )


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


def test_bayu_join_auto_assigns_the_least_populated_country():
    class Runtime:
        is_configured = True
        can_publish = True

        def ensure_event_teams(self, event, teams):
            self.ensured_teams = [team["TeamName"] for team in teams]

        def join_player(self, join_code, name):
            return {
                "EventID": "EVT-0004", "Name": name,
                "Team": "Wrong Round Robin Team", "SessionToken": "TOKEN",
            }

        def assign_participant_country_team(self, token, team, country):
            self.assignment = (token, team, country)

        @staticmethod
        def get_players(event_id):
            return [
                {"Team": "🇰🇷 Korea", "SessionToken": "K1"},
                {"Team": "🇰🇷 Korea", "SessionToken": "K2"},
                {"Team": "🇯🇵 Japan", "SessionToken": "J1"},
            ]

    db = GoogleSheetsDB.__new__(GoogleSheetsDB)
    db.runtime = Runtime()
    db.get_event_by_join_code = lambda code: {"EventID": "EVT-0004"}

    player = db.join_player_by_code("12DYLD", "Adrian Choong")

    assert player["Team"] == "🇹🇭 Thailand"
    assert player["Country"] == "Thailand"
    assert db.runtime.assignment == ("TOKEN", "🇹🇭 Thailand", "Thailand")
    assert db.runtime.ensured_teams == [
        "🇰🇷 Korea", "🇯🇵 Japan", "🇹🇭 Thailand",
        "🇵🇭 Philippines", "🇲🇾 Malaysia", "🇮🇳 India",
    ]


def test_bayu_country_catalogue_contains_exactly_the_approved_six():
    teams = bayu_country_teams()

    assert [(row["Country"], row["TeamName"].split(" ", 1)[0]) for row in teams] == [
        ("Korea", "🇰🇷"),
        ("Japan", "🇯🇵"),
        ("Thailand", "🇹🇭"),
        ("Philippines", "🇵🇭"),
        ("Malaysia", "🇲🇾"),
        ("India", "🇮🇳"),
    ]


def test_required_bayu_participant_copy_and_history_fix_are_present():
    source = (
        Path(__file__).resolve().parents[1] / "screens" / "participant.py"
    ).read_text(encoding="utf-8")

    assert "Seventeen intelligence signals" in EVA_LABYRINTH_BRIEFING
    assert "ENTER THE LABYRINTH" in source
    assert "render_media_evidence_form(db, mission, \"VIDEO\")" in source
    assert "render_media_evidence_form(db, mission, \"AUDIO\")" in source
    assert "render_multiple_evidence_form(db, mission)" in source
    assert "📤 Submit Evidence" in source
    assert "if join_event and not is_bayu_join:" in source
    assert "Enter a valid Join Code first" not in source
    assert "Only your Team Leader can submit evidence for the team." in source
    assert "check #" not in source
    assert 'if str(st.query_params.get(key, "")) != str(value)' in source
    assert "or _is_bayu_event()" in source
    assert 'st.caption(f"Build: {running_build_sha()}")' in source
    assert 'mission_id == "LAB18"' in source
    assert "return morning[:17]" not in source


def test_current_team_leader_grants_only_the_selected_participant():
    class TeamDB:
        @staticmethod
        def get_team_roster(event_id, team_name):
            assert (event_id, team_name) == ("EVT-0004", "Team EVA")
            return [
                {"Name": "Participant A", "IsLeader": True},
                {"Name": "Participant B", "IsLeader": False},
            ]

    with patch.dict(
        "screens.participant.st.session_state",
        {
            "participant_event_id": "EVT-0004",
            "participant_team": "Team EVA",
            "participant_name": "Participant B",
        },
        clear=True,
    ):
        assert current_team_leader(TeamDB()) == (False, "Participant A")


def test_current_team_leader_refreshes_when_leadership_changes():
    class TeamDB:
        @staticmethod
        def get_team_roster(event_id, team_name):
            return [{"Name": "Participant B", "IsLeader": True}]

    with patch.dict(
        "screens.participant.st.session_state",
        {
            "participant_event_id": "EVT-0004",
            "participant_team": "Team EVA",
            "participant_name": "Participant B",
            "participant_is_leader": False,
        },
        clear=True,
    ):
        assert current_team_leader(TeamDB()) == (True, "Participant B")
        assert st.session_state["participant_is_leader"] is True
