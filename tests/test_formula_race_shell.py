from pathlib import Path

from data.formula_race_contracts import DemoFormulaRaceProvider, LiveFormulaRaceProvider, snapshot_as_contract
from screens import formula_race


def test_demo_contract_is_explicit_and_complete():
    contract = snapshot_as_contract(DemoFormulaRaceProvider().snapshot())
    assert contract["provenance"] == {"source": "DEMO", "is_demo": True}
    assert len(contract["teams"]) >= 6
    assert contract["transactions"] and contract["submissions"] and contract["stock"]


def test_all_promised_navigation_destinations_exist():
    assert formula_race.NAV == [
        "Overview", "Programme", "Teams", "Reviews", "Parts Depot", "Build",
        "Championship", "Race", "Control",
    ]


def test_all_fifteen_screen_renderers_are_present():
    expected = {"overview", "live_programme", "championship", "teams", "wallet",
                "checkpoints", "reviews", "gallery", "marketplace", "build_status",
                "race_map", "judging", "drag_results", "control_centre"}
    # Home/Day One is the programme landing state, and both live/final championship
    # are arguments of the shared standings renderer.
    assert expected.issubset(vars(formula_race))


def test_pit_wall_reuses_snapshot_data_for_dense_team_operations():
    source = Path("screens/formula_race.py").read_text()
    assert "def _operational_team_rows(snapshot: RaceSnapshot)" in source
    assert "st.dataframe(_operational_team_rows(s)" in source
    assert 'st.session_state.setdefault("race_control_operator", "")' in source
    assert "I understand final ranking will be frozen" in source


def test_marketplace_catalog_has_stock_contract_keys():
    snapshot = DemoFormulaRaceProvider().snapshot()
    assert {name for name, _ in formula_race.MATERIALS} == set(snapshot.stock)


def test_live_provider_scopes_every_read_to_selected_event():
    class Runtime:
        is_configured = True
        can_publish = True
        def get_players(self, event_id): assert event_id == "RACE-1"; return []
        def get_canonical_transaction_report(self, event_id): assert event_id == "RACE-1"; return {}
    class DB:
        runtime = Runtime()
        def get_event(self, event_id): assert event_id == "RACE-1"; return {"EventID": event_id, "EventName": "Formula R.A.C.E."}
        def get_teams(self, event_id): assert event_id == "RACE-1"; return [{"TeamID":"F1-01","TeamName":"Ferrari"}]
        def get_event_submissions(self, event_id): assert event_id == "RACE-1"; return []
        def get_event_missions(self, event_id): assert event_id == "RACE-1"; return []
        def get_event_state(self, event_id): assert event_id == "RACE-1"; return {}
        def get_runtime_control_state(self, event_id): assert event_id == "RACE-1"; return {}
    snapshot = LiveFormulaRaceProvider(DB()).snapshot("RACE-1")
    assert snapshot.event_id == "RACE-1" and snapshot.source == "LIVE"
