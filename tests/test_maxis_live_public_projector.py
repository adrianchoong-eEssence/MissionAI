"""Security and presentation contract for the distinct public Maxis projector."""
from __future__ import annotations

from pathlib import Path

from screens.maxis_live_public_projector import _state_copy
from services.maxis_public_projector import (
    POLL_INTERVAL_SECONDS,
    PUBLIC_PROJECTOR_RPC,
    normalise_public_projection,
)


ROOT = Path(__file__).resolve().parents[1]


def _projection(*, state="LIVE", has_score=True):
    return {
        "Event": {"DisplayName": "Maxis Corporate & Mid-Market — Mission AI", "State": state, "HasAwardedScore": has_score,
                  "ParticipantName": "must be discarded"},
        "Teams": [
            {"Country": "Brazil", "Flag": "🇧🇷", "Rank": 2, "Score": 490, "Completed": 5, "Total": 13,
             "ParticipantID": "must be discarded", "EvidenceURL": "must be discarded"},
            {"Country": "Japan", "Flag": "🇯🇵", "Rank": 1, "Score": 540, "Completed": 6, "Total": 13,
             "SessionToken": "must be discarded", "DeviceID": "must be discarded"},
        ],
    }


def test_public_projection_model_discards_every_non_allow_list_field():
    projection = normalise_public_projection(_projection())
    assert set(projection) == {"Event", "Teams"}
    assert set(projection["Event"]) == {"DisplayName", "State", "HasAwardedScore"}
    assert all(set(team) == {"Country", "Flag", "Rank", "Score", "Completed", "Total"} for team in projection["Teams"])
    assert [team["Country"] for team in projection["Teams"]] == ["Japan", "Brazil"]


def test_zero_score_state_has_stable_countries_not_tied_rank_one():
    projection = normalise_public_projection(_projection(has_score=False))
    assert [team["Country"] for team in projection["Teams"]] == ["Brazil", "Japan"]
    assert all(_rank is not None for _rank in [team["Rank"] for team in projection["Teams"]])
    assert _state_copy("LIVE", False) == ("MISSION AI", "IS LIVE", "ALL TEAMS START AT 0")


def test_ready_live_hold_copy_is_hall_safe_and_has_no_secret_terminology():
    assert _state_copy("READY", False) == ("MISSION AI", "GET READY", "TEAMS ARE STANDING BY")
    assert _state_copy("LIVE", True) == ("MAXIS MISSION AI", "LIVE LEADERBOARD", "● LIVE")
    assert _state_copy("HOLD", True) == ("MISSION AI", "PAUSED", "STAY WITH YOUR TEAM")
    source = (ROOT / "screens/maxis_live_public_projector.py").read_text(encoding="utf-8").lower()
    assert "secret mission" not in source


def test_public_projector_is_distinct_read_only_and_five_second_polled():
    entry = (ROOT / "Projector_Maxis_Live.py").read_text(encoding="utf-8")
    screen = (ROOT / "screens/maxis_live_public_projector.py").read_text(encoding="utf-8")
    client = (ROOT / "services/maxis_public_projector.py").read_text(encoding="utf-8")
    assert POLL_INTERVAL_SECONDS == 5
    assert '@st.fragment(run_every=f"{POLL_INTERVAL_SECONDS}s")' in screen
    assert "Facilitator" not in entry + screen + client
    assert "st.query_params" not in entry + screen + client
    assert "SUPABASE_SECRET_KEY" not in entry + screen + client
    assert "SUPABASE_SERVICE_ROLE_KEY" not in entry + screen + client
    assert "PUBLIC_PROJECTOR_RPC" in client
    assert "/rest/v1/rpc/" in client
    assert 'method="POST"' in client
    for mutation in ("board_review", "board_select", "set_mission_operation", "claim_team_formation_captain", "submit", "upload"):
        assert mutation not in entry.lower() + screen.lower() + client.lower()
    assert "height:100vh" in screen
    assert "overflow:hidden" in screen
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in screen
    assert "st.dataframe" not in screen
    assert "st.selectbox" not in screen


def test_migration_is_fixed_event_allow_listed_and_no_write_surface():
    migration = (ROOT / "supabase/041_maxis_live_public_projector_projection.sql").read_text(encoding="utf-8")
    assert "exos_v2_maxis_live_projector_projection()" in migration
    assert "MAXIS-20260907-MISSION-AI" in migration
    assert "p_event_id" not in migration
    assert "SECURITY DEFINER" in migration
    assert "SET search_path = ''" in migration
    assert "GRANT EXECUTE ON FUNCTION public.exos_v2_maxis_live_projector_projection()\n    TO anon, authenticated" in migration
    assert "REVOKE ALL ON FUNCTION public.exos_v2_maxis_live_projector_projection()\n    FROM PUBLIC, anon, authenticated, service_role" in migration
    for forbidden in ("public.participants_v2", "public.submissions_v2", "public.participant_sessions_v2", "EXECUTE IMMEDIATE"):
        assert forbidden not in migration


def test_six_country_payload_and_dynamic_total_are_presentable():
    countries = ["Japan", "South Korea", "France", "Italy", "Brazil", "Thailand"]
    projection = normalise_public_projection({
        "Event": {"State": "LIVE", "HasAwardedScore": True},
        "Teams": [
            {"Country": country, "Flag": "🏳️", "Rank": index, "Score": index * 10,
             "Completed": index, "Total": 13}
            for index, country in enumerate(countries, start=1)
        ],
    })
    assert len(projection["Teams"]) == 6
    assert all(team["Total"] == 13 for team in projection["Teams"])
