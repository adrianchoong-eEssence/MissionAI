from pathlib import Path
from types import SimpleNamespace

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
        "Championship", "Race", "Control", "Event Setup",
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


def test_event_setup_renders_all_configuration_sections_without_writes(monkeypatch):
    class Context:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def button(self, *args, **kwargs): return False
        def markdown(self, *args, **kwargs): pass
        def caption(self, *args, **kwargs): pass

    class StreamlitStub:
        session_state = {}
        def __init__(self): self.tab_labels = []
        def markdown(self, *args, **kwargs): pass
        def title(self, *args, **kwargs): pass
        def subheader(self, *args, **kwargs): pass
        def text_input(self, *args, **kwargs): return ""
        def tabs(self, labels): self.tab_labels = labels; return [Context() for _ in labels]
        def columns(self, count): return [Context() for _ in range(count if isinstance(count, int) else len(count))]
        def container(self, **kwargs): return Context()
        def expander(self, *args, **kwargs): return Context()
        def data_editor(self, frame, **kwargs): return frame
        def download_button(self, *args, **kwargs): pass
        def file_uploader(self, *args, **kwargs): return None
        def button(self, *args, **kwargs): return False
        def number_input(self, *args, **kwargs): return kwargs.get("value", 0)
        def text_area(self, *args, **kwargs): return kwargs.get("value", "")
        def selectbox(self, label, options, **kwargs): return options[kwargs.get("index", 0)]
        def checkbox(self, *args, **kwargs): return kwargs.get("value", False)
        def multiselect(self, *args, **kwargs): return kwargs.get("default", [])
        def dataframe(self, *args, **kwargs): pass
        def caption(self, *args, **kwargs): pass
        def warning(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): pass
        def success(self, *args, **kwargs): pass
        def rerun(self): pass

    class Runtime:
        writes = 0
        def get_formula_race_configuration(self, event_id): return {"TeamRoutes": {}, "Marketplace": [], "JudgingCriteria": []}
        def get_formula_race_stations(self, event_id): return [{"ActivityID": "CP-1", "DisplayName": "Station", "ShortCode": "S1"}]
        def get_runtime_teams(self, event_id): return [{"TeamID": f"T-{index}", "TeamName": f"Team {index}", "IsActive": True} for index in range(1, 11)]
        def get_canonical_submissions(self, event_id): return []
        def _marketplace_payload(self, *args, **kwargs): return {"items": []}
        def save_formula_race_configuration(self, *args, **kwargs): self.writes += 1
        def set_team_pin(self, *args, **kwargs): self.writes += 1
        def reset_formula_race_event(self, *args, **kwargs): self.writes += 1

    stub, runtime = StreamlitStub(), Runtime()
    monkeypatch.setattr(formula_race, "st", stub)
    formula_race.event_setup(SimpleNamespace(event_id="EVT-DISPOSABLE"), runtime)

    assert stub.tab_labels == ["Stations", "Team Routes", "Parts Depot", "Judging", "Teams & Access", "Reset Event"]
    assert runtime.writes == 0


def test_event_setup_station_editor_exposes_the_030_facilitator_controls_and_history_guard():
    source = Path("screens/formula_race.py").read_text()

    for label in (
        '"ADD STATION"', '"EDIT"', '"SAVE"', '"CANCEL"', '"DISABLE"',
        '"SAVE STATION CONFIGURATION"', '"CANCEL STATION CHANGES"',
        '"Display Order"', '"Short Code"', '"Display Name"',
        '"Participant Instruction"', '"Facilitator Instruction"',
        '"Scoring Method"', '"Evidence Requirement"', '"Base Credits"',
        '"Credits per success"',
    ):
        assert label in source
    assert 'f"Rank {rank} Credits"' in source
    for method in ("FACILITATOR_SCORE", "LOWEST_TIME", "HIGHEST_COUNT", "SUCCESS_COUNT"):
        assert method in source
    assert "historical_submissions = runtime.get_canonical_submissions(event_id) or []" in source
    assert "Station configuration is locked because this event already has submissions" in source
    assert "runtime.save_formula_race_configuration(event_id, {\"Stations\": stations}, actor)" in source
    assert 'st.subheader("Team Routes editor")' in source
    assert 'st.subheader("Parts Depot editor")' in source
    assert 'st.subheader("Judging editor")' in source


def test_captain_pin_export_is_unique_and_excludes_internal_team_ids():
    teams = [{"TeamID": f"INTERNAL-{index}", "TeamName": f"Team {index}", "IsActive": True} for index in range(1, 11)]
    values = iter(["111111", "111111", "222222", "333333", "444444", "555555", "666666", "777777", "888888", "999999", "000000"])

    rows = formula_race._generate_unique_captain_pin_rows(teams, pin_factory=lambda: next(values))

    assert len(rows) == 10
    assert len({row["Captain PIN"] for row in rows}) == 10
    assert list(rows[0]) == ["Team Number", "Team Name", "Captain PIN"]
    assert all("TeamID" not in row and "INTERNAL-" not in str(row) for row in rows)
    assert [row["Team Number"] for row in rows] == list(range(1, 11))


def test_event_setup_generates_one_unique_pin_per_active_team_and_immediately_forgets_plaintext(monkeypatch):
    class Context:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def button(self, *args, **kwargs): return False
        def markdown(self, *args, **kwargs): pass
        def caption(self, *args, **kwargs): pass

    class StreamlitStub:
        def __init__(self): self.session_state, self.downloads = {}, []
        def markdown(self, *args, **kwargs): pass
        def title(self, *args, **kwargs): pass
        def subheader(self, *args, **kwargs): pass
        def text_input(self, *args, **kwargs): return "Race Control"
        def tabs(self, labels): return [Context() for _ in labels]
        def columns(self, count): return [Context() for _ in range(count if isinstance(count, int) else len(count))]
        def container(self, **kwargs): return Context()
        def expander(self, *args, **kwargs): return Context()
        def data_editor(self, frame, **kwargs): return frame
        def download_button(self, label, data, *args, **kwargs): self.downloads.append((label, data))
        def file_uploader(self, *args, **kwargs): return None
        def button(self, label, *args, **kwargs): return label == "GENERATE / RESET CAPTAIN PINS"
        def number_input(self, *args, **kwargs): return kwargs.get("value", 0)
        def text_area(self, *args, **kwargs): return kwargs.get("value", "")
        def selectbox(self, label, options, **kwargs): return options[kwargs.get("index", 0)]
        def checkbox(self, *args, **kwargs): return kwargs.get("value", False)
        def multiselect(self, *args, **kwargs): return kwargs.get("default", [])
        def dataframe(self, *args, **kwargs): pass
        def caption(self, *args, **kwargs): pass
        def warning(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): pass
        def success(self, *args, **kwargs): pass
        def rerun(self): pass

    class Runtime:
        def __init__(self): self.pin_writes = []
        def get_formula_race_configuration(self, event_id): return {"TeamRoutes": {}, "Marketplace": [], "JudgingCriteria": []}
        def get_formula_race_stations(self, event_id): return [{"ActivityID": "CP-1", "DisplayName": "Station", "ShortCode": "S1"}]
        def get_canonical_submissions(self, event_id): return []
        def get_runtime_teams(self, event_id):
            return [{"TeamID": f"INTERNAL-{index}", "TeamName": f"Team {index}", "IsActive": True} for index in range(1, 11)]
        def _marketplace_payload(self, *args, **kwargs): return {"items": []}
        def set_team_pin(self, event_id, team_id, pin, actor): self.pin_writes.append((event_id, team_id, pin, actor))

    stub, runtime = StreamlitStub(), Runtime()
    monkeypatch.setattr(formula_race, "st", stub)
    formula_race.event_setup(SimpleNamespace(event_id="EVT-DISPOSABLE"), runtime)

    assert len(runtime.pin_writes) == 10
    assert len({row[2] for row in runtime.pin_writes}) == 10
    assert "race_generated_pins" not in stub.session_state
    assert len(stub.downloads) == 3  # Two templates plus the immediate PIN export.
    pin_export = stub.downloads[-1][1]
    assert "Team Number,Team Name,Captain PIN" in pin_export
    assert "INTERNAL-" not in pin_export
