from pathlib import Path

from data.formula_race_contracts import LiveFormulaRaceProvider

CAPTAIN = Path("screens/formula_race_captain.py").read_text()
SEED = Path("supabase/seeds/formula_race_core_v2_queue5_test_event.sql").read_text()


def test_formula_race_captain_no_google_sheets_runtime_reads():
    assert "from data.google_sheets import GoogleSheetsDB" not in CAPTAIN
    assert "runtime.get_runtime_teams(" in CAPTAIN
    assert "get_canonical_submissions(" in CAPTAIN


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
