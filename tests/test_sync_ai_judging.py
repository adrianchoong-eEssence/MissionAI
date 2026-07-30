from screens.programme_builder import calculate_judging_rankings


def test_multiple_judges_are_averaged_and_ranked():
    rankings = calculate_judging_rankings([
        {"Judge": "A", "Team": "One", "Score": 80},
        {"Judge": "B", "Team": "One", "Score": 100},
        {"Judge": "A", "Team": "Two", "Score": 70},
        {"Judge": "B", "Team": "Two", "Score": 80},
    ])
    assert rankings[0] == {
        "Team": "One", "FinalScore": 90.0, "Rank": 1, "Tie": False
    }
    assert rankings[1]["Rank"] == 2


def test_ties_share_rank_and_are_flagged():
    rankings = calculate_judging_rankings([
        {"Judge": "A", "Team": "One", "Score": 90},
        {"Judge": "A", "Team": "Two", "Score": 90},
    ])
    assert [row["Rank"] for row in rankings] == [1, 1]
    assert all(row["Tie"] for row in rankings)
