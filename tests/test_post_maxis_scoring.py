import pytest

from engines.theme_park_race import facilitator_rubric_score, participation_prorated_score


@pytest.mark.parametrize(("completed", "expected"), [(10, 150), (9, 135), (8, 120), (1, 15)])
def test_participation_prorating_uses_present_snapshot(completed, expected):
    assert participation_prorated_score(150, participants_completing=completed, present_team_size=10) == expected


@pytest.mark.parametrize(("maximum", "completed", "present", "expected"), [(100, 1, 3, 33), (101, 1, 2, 51), (99, 2, 3, 66)])
def test_participation_prorating_is_deterministic_half_up(maximum, completed, present, expected):
    assert participation_prorated_score(maximum, participants_completing=completed, present_team_size=present) == expected


def test_invalid_participation_never_exceeds_present_denominator():
    with pytest.raises(ValueError):
        participation_prorated_score(150, participants_completing=11, present_team_size=10)
    with pytest.raises(ValueError):
        participation_prorated_score(150, participants_completing=0, present_team_size=0)


def test_weighted_rubric_is_capped_and_deterministic():
    criteria = [{"ID": "craft", "Weight": 60}, {"ID": "teamwork", "Weight": 40}]
    assert facilitator_rubric_score(150, criteria, {"craft": 80, "teamwork": 100}) == 132
    with pytest.raises(ValueError):
        facilitator_rubric_score(150, criteria, {"craft": 101, "teamwork": 100})
