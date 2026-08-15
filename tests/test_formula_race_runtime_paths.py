from pathlib import Path
import pytest

from data.formula_race_contracts import LiveFormulaRaceProvider

CAPTAIN = Path("screens/formula_race_captain.py").read_text()
SEED = Path("supabase/seeds/formula_race_core_v2_queue5_test_event.sql").read_text()


def test_formula_race_captain_no_google_sheets_runtime_reads():
    assert "from data.google_sheets import GoogleSheetsDB" not in CAPTAIN
    assert "runtime.get_runtime_teams(" in CAPTAIN
    assert 'submissions=list(workspace.get("Submissions", []))' in CAPTAIN


def test_formula_race_core_v2_queue5_seed_is_isolated():
    assert "EVT-0006" not in SEED.split("\n", 1)[1]
    assert "RACEQ5" in SEED


def test_live_provider_prefers_runtime_sources():
    calls = {"event": False, "teams": False, "missions": False}

    class Runtime:
        is_configured = True
        can_publish = True

        def get_runtime_event(self, event_id):
            calls["event"] = True
            return {"EventID": event_id, "EventName": "Runtime Event"}

        def get_runtime_teams(self, event_id):
            calls["teams"] = True
            return [{"TeamID": "Q5-TEAM", "TeamName": "Thunder"}]

        def get_canonical_submissions(self, event_id):
            calls["missions"] = True
            return [{"TeamID": "Q5-TEAM", "Status": "APPROVED", "SubmissionID": "SUB-1"}]

        def get_programme_hierarchy(self, event_id):
            return [{"ActivityID": "A1"}]

        def get_formula_race_state(self, event_id):
            return {"Checkpoints": {"Status": "READY", "Checkpoints": []}}

        def get_formula_race_checkpoints(self, event_id):
            return []

        def get_canonical_transaction_report(self, event_id):
            return {"AwardTransactions": [], "TeamBalances": [], "Leaderboard": []}

        def formula_race_team_status(self, event_id):
            return []

    class DB:
        runtime = Runtime()

        def get_event_state(self, event_id):
            return {}

        def get_runtime_control_state(self, event_id):
            return {}

    snapshot = LiveFormulaRaceProvider(DB()).snapshot("RACE-Q5-01")
    assert snapshot.source == "LIVE"
    assert calls["event"] and calls["teams"] and calls["missions"]


def test_staging_formula_provider_requires_core_v2_when_strict():
    calls = {"event": 0, "teams": 0, "missions": 0}

    class Runtime:
        is_configured = True
        can_publish = True

        def get_runtime_event(self, event_id):
            calls["event"] += 1
            return {"EventID": event_id, "EventName": "Runtime Event"}

        def get_runtime_teams(self, event_id):
            calls["teams"] += 1
            return [{"TeamID": "Q5-TEAM", "TeamName": "Thunder"}]

        def get_canonical_submissions(self, event_id):
            return []

        def get_programme_hierarchy(self, event_id):
            calls["missions"] += 1
            return [{"ActivityID": "A1"}]

        def get_formula_race_state(self, event_id):
            return {"Checkpoints": {"Status": "READY", "Checkpoints": []}}

        def get_formula_race_checkpoints(self, event_id):
            return []

        def get_canonical_transaction_report(self, event_id):
            return {"AwardTransactions": [], "TeamBalances": [], "Leaderboard": []}

        def formula_race_team_status(self, event_id):
            return []

    class DB:
        runtime = Runtime()

        def get_event_state(self, event_id):
            raise AssertionError("legacy fallback path used")

        def get_runtime_control_state(self, event_id):
            raise AssertionError("legacy fallback path used")

        def get_event(self, event_id):
            raise AssertionError("legacy fallback path used")

        def get_teams(self, event_id):
            raise AssertionError("legacy fallback path used")

        def get_event_submissions(self, event_id):
            raise AssertionError("legacy fallback path used")

        def get_event_missions(self, event_id):
            raise AssertionError("legacy fallback path used")

    snapshot = LiveFormulaRaceProvider(DB()).snapshot("RACE-Q5-01", strict_core_v2=True)
    assert snapshot.source == "LIVE"
    assert calls == {"event": 1, "teams": 1, "missions": 1}


def test_staging_formula_provider_strict_submissions_failure_is_error():
    class Runtime:
        is_configured = True
        can_publish = True

        def get_runtime_event(self, event_id):
            return {"EventID": event_id, "EventName": "Runtime Event"}

        def get_runtime_teams(self, event_id):
            return [{"TeamID": "Q5-TEAM", "TeamName": "Thunder"}]

        def get_canonical_submissions(self, event_id):
            raise RuntimeError("core2_down")

        def get_programme_hierarchy(self, event_id):
            return [{"ActivityID": "A1"}]

        def get_formula_race_state(self, event_id):
            return {"CurrentStageName": "RUNNING"}

        def get_formula_race_checkpoints(self, event_id):
            return []

        def get_canonical_transaction_report(self, event_id):
            return {"AwardTransactions": [], "TeamBalances": [], "Leaderboard": []}

        def formula_race_team_status(self, event_id):
            return []

    class DB:
        runtime = Runtime()

        def get_event_state(self, event_id):
            raise AssertionError("legacy fallback path used")

    with pytest.raises(RuntimeError, match="Core v2 runtime unavailable for submissions"):
        LiveFormulaRaceProvider(DB()).snapshot("RACE-Q5-01", strict_core_v2=True)


def test_staging_formula_provider_accepts_fresh_event_empty_state():
    events = {"RACE-Q5-EMPTY"}
    teams = [ {"TeamID": f"TEAM-{index:02d}", "TeamName": f"Team {index:02d}"} for index in range(1, 11)]

    class Runtime:
        is_configured = True
        can_publish = True

        def get_runtime_event(self, event_id):
            assert event_id in events
            return {"EventID": event_id, "EventName": "Fresh R.A.C.E. Event"}

        def get_runtime_teams(self, event_id):
            return teams

        def get_canonical_submissions(self, event_id):
            assert event_id in events
            return []

        def get_programme_hierarchy(self, event_id):
            assert event_id in events
            return [
                {"ActivityID": "CP-01", "ActivityName": "Checkpoint 1"},
                {"ActivityID": "CP-02", "ActivityName": "Checkpoint 2"},
                {"ActivityID": "CP-03", "ActivityName": "Checkpoint 3"},
                {"ActivityID": "CP-04", "ActivityName": "Checkpoint 4"},
            ]

        def get_formula_race_state(self, event_id):
            assert event_id in events
            return {}

        def get_formula_race_checkpoints(self, event_id):
            assert event_id in events
            return {"Checkpoints": [], "Status": "READY", "ModuleID": "RACE-MOD"}

        def get_canonical_transaction_report(self, event_id):
            assert event_id in events
            return {"AwardTransactions": [], "TeamBalances": [], "Leaderboard": []}

        def formula_race_team_status(self, event_id):
            assert event_id in events
            return []

    class DB:
        runtime = Runtime()

    snapshot = LiveFormulaRaceProvider(DB()).snapshot("RACE-Q5-EMPTY", strict_core_v2=True)
    assert snapshot.source == "LIVE"
    assert snapshot.event_id == "RACE-Q5-EMPTY"
    assert len(snapshot.teams) == 10
    assert len(snapshot.submissions) == 0
    assert len(snapshot.transactions) == 0
