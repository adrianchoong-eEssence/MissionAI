import types

from screens import live_event_console


class _Runtime:
    def __init__(self, programme, submissions=(), can_publish=True):
        self._programme = programme
        self._submissions = submissions
        self.can_publish = can_publish

    def get_programme_hierarchy(self, event_id):
        return self._programme

    def get_canonical_submissions(self, event_id):
        return self._submissions


class _DB:
    def __init__(self, programme=None, submissions=None, can_publish=True, event_missions=None):
        self.runtime = _Runtime(programme or [], submissions or ())
        self.runtime.can_publish = can_publish
        self._event_missions = event_missions or []

    def get_event_missions(self, _event_id):
        return self._event_missions


def test_is_canonical_mode_even_without_existing_canonical_rows():
    db = _DB(
        programme=[{
            "Activities": [{"ActivityID": "A1", "ScoringMode": "TEAM_COMPETITIVE"}],
        }],
        submissions=[],
    )
    assert live_event_console._is_canonical_review_mode(db, "EVT-1000") is True
    assert live_event_console._build_activity_scoring_mode_map(db, "EVT-1000") == {
        "A1": "TEAM_COMPETITIVE",
    }


def test_canonical_scoring_modes_route_to_scores_and_credits_correctly():
    db = _DB(programme=[{
        "Activities": [
            {"ActivityID": "A1", "ScoringMode": "TEAM_COMPETITIVE"},
            {"ActivityID": "A2", "ScoringMode": "ENTERPRISE"},
            {"ActivityID": "A3", "ScoringMode": "NON_SCORING"},
        ],
    }])
    map_cache = live_event_console._build_activity_scoring_mode_map(db, "EVT-1000")

    competitive = live_event_console._canonical_review_metrics(
        {"ActivityID": "A1", "SubmissionType": "PHOTO", "SubmissionID": "S1", "Score": 88},
        "EVT-1000",
        db,
        map_cache,
    )
    assert competitive["mode"] == "TEAM_COMPETITIVE"
    assert competitive["score"] == 88.0
    assert competitive["credits"] == 88.0
    assert competitive["score_disabled"] is False

    enterprise = live_event_console._canonical_review_metrics(
        {"ActivityID": "A2", "SubmissionType": "PHOTO", "SubmissionID": "S2", "Score": 77},
        "EVT-1000",
        db,
        map_cache,
    )
    assert enterprise["mode"] == "ENTERPRISE"
    assert enterprise["score"] == 0.0
    assert enterprise["credits"] == 0.0
    assert enterprise["score_disabled"] is False

    non_scoring = live_event_console._canonical_review_metrics(
        {"ActivityID": "A3", "SubmissionType": "PHOTO", "SubmissionID": "S3", "Score": 77},
        "EVT-1000",
        db,
        map_cache,
    )
    assert non_scoring["mode"] == "NON_SCORING"
    assert non_scoring["score"] == 0.0
    assert non_scoring["credits"] == 0.0
    assert non_scoring["score_disabled"] is True


def test_nasi_is_forced_to_non_scoring():
    db = _DB(programme=[{
        "Activities": [{"ActivityID": "A4", "ScoringMode": "TEAM_COMPETITIVE"}],
    }])
    map_cache = live_event_console._build_activity_scoring_mode_map(db, "EVT-1000")
    values = live_event_console._canonical_review_metrics(
        {"ActivityID": "A4", "SubmissionType": "NASI", "SubmissionID": "S4"},
        "EVT-1000",
        db,
        map_cache,
    )
    assert values["mode"] == "NON_SCORING"
    assert values["label"] == "No score/credits"


def test_calculate_leaderboard_respects_scoring_mode_and_submission_type():
    rows = [
        {"Status": "APPROVED", "TeamName": "Gamma", "Score": 50, "ScoringMode": "TEAM_COMPETITIVE", "SubmissionType": "PHOTO"},
        {"Status": "APPROVED", "TeamName": "Gamma", "Score": 30, "ScoringMode": "ENTERPRISE", "SubmissionType": "PHOTO"},
        {"Status": "APPROVED", "TeamName": "Gamma", "Score": 25, "ScoringMode": "NON_SCORING", "SubmissionType": "PHOTO"},
        {"Status": "APPROVED", "TeamName": "Delta", "Score": 99, "SubmissionType": "PIPELINE_ENTERPRISE"},
    ]
    leaderboard = live_event_console.calculate_leaderboard(rows)
    assert leaderboard == [("Gamma", 50.0)]
