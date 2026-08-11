from engines.canonical_performance import (
    activity_scoring_contract,
    build_performance_snapshot,
    evaluate_activity,
)
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _activity(activity_id, name, contract):
    return {
        "ActivityID": activity_id,
        "StageName": name,
        "ScoringMode": contract.get("ScoringMode", "TEAM_COMPETITIVE"),
        "ScoringContract": contract,
    }


def test_target_achievement_loss_preserves_components_and_net_score():
    activity = _activity("A1", "Configured Challenge", {
        "Type": "TARGET_ACHIEVEMENT_LOSS",
        "CanonicalScore": "NET_ACHIEVEMENT",
        "Fields": {"Target": "Metric1", "Achievement": "Metric2", "Loss": "Metric3"},
    })
    result = evaluate_activity(activity, {
        "Status": "APPROVED", "Metric1": 125, "Metric2": 120, "Metric3": 5, "Score": 92,
    })
    assert result | {
        "Target": 125.0, "Achievement": 120.0, "Loss": 5.0,
        "NetAchievement": 115.0, "PerformancePercentage": 92.0,
        "Score": 115.0,
    } == result


def test_overall_percentage_is_weighted_by_targets_not_average_percentages():
    programme = [{"Activities": [
        _activity("A1", "One", {"Type": "TARGET_ACHIEVEMENT_LOSS", "CanonicalScore": "NET_ACHIEVEMENT"}),
        _activity("A2", "Two", {"Type": "TARGET_ACHIEVEMENT_LOSS", "CanonicalScore": "NET_ACHIEVEMENT"}),
        _activity("A3", "Reflection", {"Type": "NON_SCORING", "ScoringMode": "NON_SCORING"}),
    ]}]
    submissions = [
        {"TeamID": "T1", "ActivityID": "A1", "Status": "APPROVED", "Metric1": 125, "Metric2": 120, "Metric3": 5, "Score": 115},
        {"TeamID": "T1", "ActivityID": "A2", "Status": "APPROVED", "Metric1": 75, "Metric2": 65, "Metric3": 5, "Score": 60},
    ]
    snapshot = build_performance_snapshot(
        programme, submissions, [{"TeamID": "T1", "TeamIdentity": "Tiger"}],
        [{"TeamID": "T1", "Score": 175}],
    )
    team = snapshot["Teams"][0]
    assert team["TotalNetAchievement"] == 175
    assert team["TotalTarget"] == 200
    assert team["PerformancePercentage"] == 87.5


def test_unapproved_activity_does_not_distort_denominator_and_status_is_visible():
    programme = [{"Activities": [
        _activity("A1", "Approved", {"Type": "DIRECT_SCORE", "Maximum": 100}),
        _activity("A2", "Waiting", {"Type": "DIRECT_SCORE", "Maximum": 500}),
    ]}]
    rows = [
        {"TeamID": "T1", "ActivityID": "A1", "Status": "APPROVED", "Score": 80},
        {"TeamID": "T1", "ActivityID": "A2", "Status": "SUBMITTED"},
    ]
    team = build_performance_snapshot(programme, rows, [{"TeamID": "T1", "TeamName": "Red"}], [{"TeamID": "T1", "Score": 80}])["Teams"][0]
    assert team["TotalTarget"] == 100
    assert team["Activities"][1]["Status"] == "Awaiting Review"


def test_ties_are_deterministic_and_points_credits_wallet_stay_separate():
    teams = [{"TeamID": "B", "TeamName": "Eagle"}, {"TeamID": "A", "TeamName": "Tiger"}]
    snapshot = build_performance_snapshot(
        [], [], teams,
        [{"TeamID": "A", "Score": 50}, {"TeamID": "B", "Score": 50}],
        earned_credits=[{"TeamID": "A", "EarnedCredits": 180}],
        wallets=[{"TeamID": "A", "Balance": 120}],
    )
    assert [row["TeamIdentity"] for row in snapshot["Teams"]] == ["Eagle", "Tiger"]
    assert [row["Rank"] for row in snapshot["Teams"]] == [1, 1]
    tiger = snapshot["Teams"][1]
    assert (tiger["TotalScore"], tiger["CreditsEarned"], tiger["WalletBalance"]) == (50, 180, 120)


def test_missing_contract_defaults_by_scoring_mode_without_activity_name_rules():
    assert activity_scoring_contract({"StageName": "Anything", "ScoringMode": "NON_SCORING"})["Type"] == "NON_SCORING"
    assert activity_scoring_contract({"StageName": "Anything", "ScoringMode": "TEAM_COMPETITIVE"})["Type"] == "DIRECT_SCORE"


def test_all_live_surfaces_use_shared_service_and_scoped_refresh():
    participant = (ROOT / "screens/participant.py").read_text()
    facilitator = (ROOT / "screens/control_centre.py").read_text()
    projector = (ROOT / "screens/leaderboard_display.py").read_text()
    assert '@st.fragment(run_every="5s")' in participant
    assert '@st.fragment(run_every="5s")' in facilitator
    assert '@st.fragment(run_every="3s")' in projector
    assert "load_performance_snapshot" in participant
    assert "load_performance_snapshot" in facilitator
    assert "load_performance_snapshot" in projector
    assert "st_autorefresh" not in projector


def test_preview_does_not_write_and_projector_route_is_event_scoped():
    broadcast = (ROOT / "screens/projector_broadcast.py").read_text()
    facilitator = (ROOT / "Facilitator.py").read_text()
    preview_block = broadcast.split('"Preview Broadcast"', 1)[1].split('"Apply Broadcast"', 1)[0]
    assert "control.broadcast" not in preview_block
    assert 'f"?view=projector&event_id={quote(str(event_id))}"' in broadcast
    assert 'st.query_params.get("view", "")' in facilitator
    assert "requested_event_id" in facilitator


def test_admin_branding_uses_existing_event_payload():
    source = (ROOT / "screens/create_event.py").read_text()
    for field in ("ClientLogo", "EventLogo", "ProjectorBackground", "ProjectorTheme", "DefaultBroadcast"):
        assert field in source
    assert '"ProjectorBranding": dict(projector_branding or {})' in source


def test_programme_builder_exposes_reusable_activity_scoring_contracts():
    source = (ROOT / "screens/programme_builder.py").read_text()
    assert '"TARGET_ACHIEVEMENT_LOSS"' in source
    assert '"DIRECT_SCORE"' in source
    assert '"CREDITS_BASED"' in source
    assert '"CanonicalScore": canonical_score' in source
