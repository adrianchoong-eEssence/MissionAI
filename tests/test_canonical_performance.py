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
        "Target": 125,
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
        _activity("A2", "Two", {"Type": "TARGET_ACHIEVEMENT_LOSS", "Target": 75, "CanonicalScore": "NET_ACHIEVEMENT"}),
        _activity("A3", "Reflection", {"Type": "NON_SCORING", "ScoringMode": "NON_SCORING"}),
    ]}]
    programme[0]["Activities"][0]["ScoringContract"]["Target"] = 125
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


def test_participant_reported_target_cannot_control_official_denominator():
    activity = _activity("A1", "Configured Challenge", {
        "Type": "TARGET_ACHIEVEMENT_LOSS", "Target": 125,
        "CanonicalScore": "NET_ACHIEVEMENT",
    })
    result = evaluate_activity(activity, {
        "Status": "APPROVED", "Metric1": 1, "Metric2": 120, "Metric3": 5, "Score": 115,
    })
    assert result["Target"] == 125
    assert result["PerformancePercentage"] == 92


def test_existing_direct_score_has_no_fake_target_or_none_percentage_display():
    activity = _activity("A1", "Existing AIA Pipeline", {"Type": "DIRECT_SCORE", "Maximum": 0})
    team = build_performance_snapshot(
        [{"Activities": [activity]}],
        [{"TeamID": "T1", "ActivityID": "A1", "Status": "APPROVED", "Score": 118}],
        [{"TeamID": "T1", "TeamName": "India"}],
        [{"TeamID": "T1", "Score": 118}],
    )["Teams"][0]
    assert team["TotalScore"] == 118
    assert team["TotalTarget"] == 0
    assert team["PerformancePercentage"] is None
    assert team["Activities"][0]["Score"] == 118
    assert team["Activities"][0]["Target"] is None


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


def test_non_scoring_approved_review_value_never_becomes_a_canonical_score():
    activity = _activity("A3", "Helium Stick", {
        "Type": "NON_SCORING", "ScoringMode": "NON_SCORING",
    })
    result = evaluate_activity(activity, {
        "Status": "APPROVED", "Metric1": "YES", "Score": 80,
    })
    assert result["Status"] == "Non-Scoring"
    assert result["Score"] is None
    assert result["Included"] is False


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


def test_standard_scores_broadcast_uses_canonical_performance_not_credit_wallet():
    broadcast = (ROOT / "screens/projector_broadcast.py").read_text()
    projector = (ROOT / "screens/leaderboard_display.py").read_text()
    scores_block = broadcast.split('if mode == "Scores":', 1)[1].split(
        'if mode == "Custom Message":', 1
    )[0]
    assert 'performance_snapshot' in scores_block
    assert 'TotalScore' in scores_block
    assert 'EarnedCredits' not in scores_block
    assert 'broadcast_state.get("Mode") in {"Scores", "Credits"}' not in projector


def test_projector_refresh_rereads_event_scoped_broadcast_state():
    projector = (ROOT / "screens/leaderboard_display.py").read_text()
    assert '@st.fragment(run_every="3s")' in projector
    assert "stored_broadcast = db.get_broadcast_state(event_id)" in projector
    assert "broadcast_state.update(stored_broadcast)" in projector


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
    assert '"Target": float(contract_maximum)' in source


def test_preview_and_standalone_use_same_styles_and_clean_shell():
    preview = (ROOT / "screens/projector_broadcast.py").read_text()
    projector = (ROOT / "screens/leaderboard_display.py").read_text()
    styles = (ROOT / "screens/projector_presentation.py").read_text()
    facilitator = (ROOT / "Facilitator.py").read_text()
    assert "from screens.projector_presentation import PROJECTOR_STYLES" in preview
    assert "SHARED_PROJECTOR_STYLES" in projector
    assert "PROJECTOR_STANDALONE_STYLES" in projector
    assert "broadcast-preview" in styles
    assert '.stApp { background:#082b50 !important' in styles
    assert '.block-container { padding:0 !important' in styles
    assert 'initial_sidebar_state="collapsed" if projector_request else "auto"' in facilitator
    assert "if not projector_request:\n    apply_branding()" in facilitator
    assert "st.file_uploader" not in preview


def test_scoring_contract_round_trips_through_canonical_activity_payload():
    runtime = (ROOT / "data/runtime_database.py").read_text()
    assert '"scoring_contract": (' in runtime
    assert '"ScoringContract": (' in runtime
    assert 'payload.get("scoring_contract", {})' in runtime


def test_admin_projector_entry_uses_selected_event_id():
    source = (ROOT / "MissionAI.py").read_text()
    assert 'if requested_view == "projector":' in source
    assert 'event_id = str(st.query_params.get("event_id", "")).strip()' in source
    assert 'show_leaderboard_display(event_id=event_id, standalone=True)' in source
    assert 'f"?view=projector&event_id={selected_event_id}"' in source


def test_admin_and_facilitator_share_the_standalone_projector_surface():
    admin = (ROOT / "MissionAI.py").read_text()
    facilitator = (ROOT / "Facilitator.py").read_text()
    expected = "show_leaderboard_display"
    assert expected in admin
    assert expected in facilitator
    assert "standalone=True" in admin.split('if requested_view == "projector":', 1)[1]
    assert "standalone=True" in facilitator.split("if projector_request:", 1)[1]
