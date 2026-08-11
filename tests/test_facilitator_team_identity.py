from pathlib import Path

from screens.team_identity import resolve_leaderboard_rows, team_identity


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_leaderboard_resolves_generic_team_identities():
    teams = [
        {"TeamID": "TEAM-01", "TeamIdentity": "India", "TeamName": "Old Name"},
        {"TeamID": "TEAM-02", "TeamName": "Tiger"},
        {"TeamID": "TEAM-03", "TeamIdentity": "Ferrari"},
    ]
    rankings = [
        {"TeamID": "TEAM-01", "TeamName": "TEAM-01", "Score": 125},
        {"TeamID": "TEAM-02", "Score": 80},
        {"TeamID": "TEAM-03", "Score": 40},
        {"TeamID": "TEAM-99", "Score": 0},
    ]

    assert resolve_leaderboard_rows(rankings, teams) == [
        ("India", 125.0),
        ("Tiger", 80.0),
        ("Ferrari", 40.0),
        ("TEAM-99", 0.0),
    ]


def test_team_identity_falls_back_from_identity_to_name_to_id():
    assert team_identity({"TeamIdentity": "Eagle", "TeamName": "Team 1", "TeamID": "T1"}) == "Eagle"
    assert team_identity({"TeamName": "Red", "TeamID": "T2"}) == "Red"
    assert team_identity({"TeamID": "T3"}) == "T3"


def test_tuple_leaderboard_also_resolves_raw_team_ids():
    assert resolve_leaderboard_rows(
        [("TEAM-01", 10)], [{"TeamID": "TEAM-01", "TeamName": "Custom Team Name"}],
    ) == [("Custom Team Name", 10.0)]


def test_facilitator_and_projector_share_canonical_identity_resolution():
    for path in ("screens/control_centre.py", "screens/leaderboard_display.py"):
        source = (ROOT / path).read_text()
        assert "resolve_leaderboard_rows(source_rows, db.get_teams(event_id))" in source
        assert '[(row["TeamID"], float(row["Score"]))' not in source
