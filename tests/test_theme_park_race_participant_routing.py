"""P0 routing contract: a Theme Park Race never reaches the legacy captain app.

Human Genting UAT (CERT-GENTING-UAT-20260824 / GTU824) registered correctly and
was then handed the Formula R.A.C.E. captain shell that is deployed at
``exos-race-captain-v2.streamlit.app``.  These tests execute the real
``Participant.py`` entrypoint against a stubbed Streamlit runtime so the branch
that was taken is observable, and pin the team card back to native elements.
"""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from engines.theme_park_race import OPEN_MISSION_BOARD, is_theme_park_race
from screens.participant import render_team_assignment_card


ROOT = Path(__file__).resolve().parents[1]
LEGACY_CAPTAIN_DEPLOYMENT = "exos-race-captain-v2.streamlit.app"

GENTING_EVENT_ID = "CERT-GENTING-UAT-20260824"
GENTING_JOIN_CODE = "GTU824"

THEME_PARK_EVENT = {
    "EventID": GENTING_EVENT_ID,
    "EventName": "Genting Theme Park Race",
    "JoinCode": GENTING_JOIN_CODE,
    "_EventPayload": {
        "RaceConfiguration": {
            "SchemaVersion": 1,
            "EngineKind": "THEME_PARK_RACE",
            "StrategyMode": OPEN_MISSION_BOARD,
        },
    },
}

FORMULA_EVENT = {
    "EventID": "EVT-FORMULA-1",
    "EventName": "Formula Race Championship",
    "JoinCode": "RACE01",
    "_EventPayload": {},
}


class _Stop(Exception):
    """Stands in for ``st.stop()``, which halts a Streamlit script run."""


class _FakeStreamlit(types.SimpleNamespace):
    def __init__(self, query_params=None, session_state=None):
        super().__init__()
        self.query_params = dict(query_params or {})
        self.session_state = dict(session_state or {})
        self.secrets = {}

    def stop(self):
        raise _Stop()


def _run_entrypoint(query_params=None, session_state=None, event=None, env=""):
    """Execute Participant.py and report which screen it routed to."""
    routed = []
    fake_st = _FakeStreamlit(query_params, session_state)

    class _Adapter:
        def get_event(self, event_id):
            return event if event and event["EventID"] == event_id else None

        def get_event_by_join_code(self, join_code):
            return event if event and event["JoinCode"] == join_code else None

    def _formula_adapter(_runtime):
        adapter = _Adapter()
        adapter.can_publish = True
        return adapter

    modules = {
        "streamlit": fake_st,
        "branding": types.SimpleNamespace(
            apply_branding=lambda **kwargs: None,
            configure_page=lambda **kwargs: None,
        ),
        "screens.participant": types.SimpleNamespace(
            show_participant=lambda: routed.append("PARTICIPANT"),
        ),
        "screens.formula_race_captain": types.SimpleNamespace(
            show_formula_race_captain=lambda: routed.append("FORMULA_CAPTAIN"),
        ),
        "data.standard_core_v2_adapter": types.SimpleNamespace(
            get_standard_database=lambda: _Adapter(),
        ),
        "data.formula_race_core_v2_adapter": types.SimpleNamespace(
            FormulaRaceCoreV2StagingAdapter=_formula_adapter,
        ),
        "data.runtime_database": types.SimpleNamespace(
            get_runtime_database=lambda: None,
        ),
    }

    spec = importlib.util.spec_from_file_location(
        "participant_entrypoint_under_test", ROOT / "Participant.py",
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict("os.environ", {"EXOS_ENV": env}):
        try:
            spec.loader.exec_module(module)
        except _Stop:
            pass
    return routed, fake_st


# 1. THEME_PARK_RACE registration never reaches the legacy captain deployment.

@pytest.mark.parametrize("query_params", [
    {"join_code": GENTING_JOIN_CODE},
    {"event_id": GENTING_EVENT_ID, "join_code": GENTING_JOIN_CODE},
    # A stale PWA session URL or a copied captain link carrying ?race=1 is the
    # exact shape that stranded the Genting UAT participant.
    {"join_code": GENTING_JOIN_CODE, "race": "1"},
    {"event_id": GENTING_EVENT_ID, "race": "1"},
])
@pytest.mark.parametrize("env", ["", "staging", "uat"])
def test_theme_park_race_never_routes_to_legacy_captain_app(query_params, env):
    routed, _ = _run_entrypoint(
        query_params=query_params, event=THEME_PARK_EVENT, env=env,
    )
    assert routed == ["PARTICIPANT"]
    assert "FORMULA_CAPTAIN" not in routed


def test_theme_park_race_survives_a_restored_race_captain_session():
    routed, _ = _run_entrypoint(
        query_params={"join_code": GENTING_JOIN_CODE},
        session_state={"race_captain": {"TeamID": "T1"}},
        event=THEME_PARK_EVENT,
    )
    assert routed == ["PARTICIPANT"]


def test_legacy_captain_deployment_is_not_referenced_anywhere_in_source():
    for path in list(ROOT.glob("*.py")) + list(ROOT.glob("screens/*.py")) + list(ROOT.glob("data/*.py")):
        assert LEGACY_CAPTAIN_DEPLOYMENT not in path.read_text()


# 2. OPEN_MISSION_BOARD stays inside the new Participant/Core v2 flow.

def test_open_mission_board_stays_in_core_v2_participant_flow():
    assert is_theme_park_race(THEME_PARK_EVENT) is True
    routed, _ = _run_entrypoint(
        query_params={"join_code": GENTING_JOIN_CODE, "race": "1"},
        event=THEME_PARK_EVENT,
    )
    assert routed == ["PARTICIPANT"]

    participant_screen = (ROOT / "screens/participant.py").read_text()
    assert "render_theme_park_race_participant" in participant_screen
    assert "db.is_theme_park_race_event(event)" in participant_screen


def test_open_mission_board_participant_surface_is_the_theme_park_module():
    source = (ROOT / "screens/theme_park_race.py").read_text()
    assert "_render_open_mission_board" in source
    assert "formula_race_captain" not in source


# 3. Formula R.A.C.E. captain routing is unchanged.

def test_formula_race_captain_route_is_unchanged_for_explicit_race_request():
    routed, _ = _run_entrypoint(
        query_params={"race": "1", "join_code": "RACE01"},
        event=FORMULA_EVENT,
    )
    assert routed == ["FORMULA_CAPTAIN"]


def test_formula_race_captain_route_is_unchanged_for_a_restored_session():
    routed, _ = _run_entrypoint(
        session_state={"race_captain": {"TeamID": "F1-01"}},
        event=FORMULA_EVENT,
    )
    assert routed == ["FORMULA_CAPTAIN"]


def test_formula_race_captain_route_is_unchanged_on_staging_with_race_flag():
    routed, _ = _run_entrypoint(
        query_params={"race": "1", "join_code": "RACE01"},
        event=FORMULA_EVENT, env="staging",
    )
    assert routed == ["FORMULA_CAPTAIN"]


def test_join_code_heuristic_can_never_claim_a_configured_theme_park_race():
    """The name/prefix heuristic is subordinate to RaceConfiguration.EngineKind.

    ``_is_core_v2_race_request`` is only consulted after the staging guard, so
    it is unreachable today; it is still hardened because it is the historic
    join-code path into the legacy captain shell.
    """
    source = (ROOT / "Participant.py").read_text()
    guard = source.index("if _is_theme_park_race_request():")
    heuristic = source.index("def _is_core_v2_race_request()")
    legacy_call = source.index("show_formula_race_captain()")
    assert guard < heuristic and guard < legacy_call
    assert "if is_theme_park_race(event):" in source
    assert source.index("if is_theme_park_race(event):") < source.index(
        '"FORMULA RACE" in event_name',
    )


def test_standard_staging_participant_guard_is_unchanged():
    routed, _ = _run_entrypoint(
        query_params={"join_code": "STD001"}, event=None, env="staging",
    )
    assert routed == ["PARTICIPANT"]


# 4. Assigned team state persists across the routing decision.

def test_assigned_team_state_is_preserved_by_the_theme_park_route():
    assigned = {
        "participant_event_id": GENTING_EVENT_ID,
        "participant_join_code": GENTING_JOIN_CODE,
        "participant_team": "Velocity",
        "participant_team_id": f"{GENTING_EVENT_ID}-TEAM-06",
        "participant_name": "Ada Lovelace",
        "participant_session_token": "SESSION-1",
    }
    routed, fake_st = _run_entrypoint(
        query_params={"race": "1"},
        session_state=dict(assigned),
        event=THEME_PARK_EVENT,
    )
    assert routed == ["PARTICIPANT"]
    for key, value in assigned.items():
        assert fake_st.session_state[key] == value


def test_session_identity_outranks_query_parameters_for_engine_selection():
    routed, _ = _run_entrypoint(
        query_params={"race": "1", "join_code": "RACE01"},
        session_state={"participant_event_id": GENTING_EVENT_ID},
        event=THEME_PARK_EVENT,
    )
    assert routed == ["PARTICIPANT"]


# 5. Captain / non-Captain routing follows canonical Team Formation state.

def _workspace(lifecycle, is_captain, session_active=True, has_captain=False):
    return {
        "EventID": GENTING_EVENT_ID,
        "Lifecycle": lifecycle,
        "StrategyMode": OPEN_MISSION_BOARD,
        "IsCaptain": is_captain,
        "CaptainSessionActive": session_active,
        "TeamHasCaptain": has_captain or is_captain,
        "CaptainName": "Ruth" if has_captain else "",
        # Canonical eligibility, as projected by participant_projection.
        "CanClaimCaptain": lifecycle == "CAPTAIN_SELECTION"
        and not is_captain and not has_captain,
        "Progress": {"Completed": 0, "Total": 3, "SubmissionsByActivity": {}},
        "MissionBoard": [{
            "ActivityID": "A1", "DisplayName": "Ride", "MissionClass": "RIDE",
            "MissionState": "AVAILABLE", "Zone": "Z", "LocationDescription": "L",
        }],
        "Route": [],
    }


@pytest.mark.parametrize("lifecycle", [
    "REGISTRATION", "TEAM_FORMATION", "FORMATION_LOCKED", "CAPTAIN_SELECTION", "READY",
])
def test_mission_board_is_withheld_until_team_formation_reaches_active(lifecycle):
    from screens import theme_park_race

    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        theme_park_race_participant_workspace=lambda token: _workspace(lifecycle, True),
    ))
    with patch.object(theme_park_race, "_render_open_mission_board") as board, \
            patch.object(theme_park_race, "_render_captain_authority", return_value=True), \
            patch.object(theme_park_race, "st"):
        theme_park_race.render_theme_park_race_participant(db)
    board.assert_not_called()


def test_effective_captain_receives_the_theme_park_mission_board():
    from screens import theme_park_race

    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        theme_park_race_participant_workspace=lambda token: _workspace("ACTIVE", True),
    ))
    with patch.object(theme_park_race, "_render_open_mission_board") as board, \
            patch.object(theme_park_race, "_render_captain_authority", return_value=True), \
            patch.object(theme_park_race, "st"):
        theme_park_race.render_theme_park_race_participant(db)
    board.assert_called_once()
    assert board.call_args[0][2] is True


def test_non_captain_stays_in_the_team_status_view_without_submit_authority():
    from screens import theme_park_race

    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        theme_park_race_participant_workspace=lambda token: _workspace("ACTIVE", False),
    ))
    with patch.object(theme_park_race, "_render_open_mission_board") as board, \
            patch.object(theme_park_race, "_render_captain_authority", return_value=False), \
            patch.object(theme_park_race, "st"):
        theme_park_race.render_theme_park_race_participant(db)
    # The board still renders team state, but never with Captain authority.
    board.assert_called_once()
    assert board.call_args[0][2] is False


def test_captain_selection_is_offered_only_in_the_captain_selection_state():
    from screens import theme_park_race

    db = types.SimpleNamespace(runtime=types.SimpleNamespace(
        claim_team_formation_captain=lambda token, device: {"Claimed": True},
    ))
    with patch.object(theme_park_race, "st") as fake:
        fake.button.return_value = False
        assert theme_park_race._render_captain_authority(
            types.SimpleNamespace(runtime=db.runtime),
            _workspace("CAPTAIN_SELECTION", False), "", "DEVICE",
        ) is False
        assert [call.args[0] for call in fake.button.call_args_list] == [
            "Become Team Captain",
        ]

    with patch.object(theme_park_race, "st") as fake:
        assert theme_park_race._render_captain_authority(
            types.SimpleNamespace(runtime=db.runtime),
            _workspace("TEAM_FORMATION", False), "", "DEVICE",
        ) is False
        fake.button.assert_not_called()
        fake.info.assert_called_once()

    # A team that already has a Captain is never offered the claim again.
    with patch.object(theme_park_race, "st") as fake:
        fake.button.return_value = False
        assert theme_park_race._render_captain_authority(
            types.SimpleNamespace(runtime=db.runtime),
            _workspace("CAPTAIN_SELECTION", False, has_captain=True), "", "DEVICE",
        ) is False
        fake.button.assert_not_called()


# 6. The team card no longer emits raw HTML as literal text.

class _TeamCardDB:
    def __init__(self, instruction):
        self._instruction = instruction

    def get_event(self, event_id):
        return {"EventID": event_id, "ThemeType": "CUSTOM", "ThemeName": "Teams"}

    def event_metadata(self, event):
        return {"TeamIdentityConfig": {
            "ThemeType": "CUSTOM",
            "ThemeName": "Theme Park Teams",
            "ParticipantInstruction": self._instruction,
        }}

    def get_teams(self, event_id):
        return [{
            "TeamID": "T6", "TeamName": "Velocity",
            "TeamIdentity": "Velocity", "Country": "", "Emoji": "🚀", "Image": "",
        }]

    def get_team_roster(self, event_id, team):
        return [{"Name": "Ada Lovelace", "IsLeader": True}]


MULTILINE_INSTRUCTION = (
    "Find your team members and gather together.\nMeet at the main gate."
)


@pytest.mark.parametrize("instruction", [
    "Find your team members and gather together.",
    MULTILINE_INSTRUCTION,
])
def test_team_card_never_renders_raw_html_as_literal_text(instruction):
    from screens import participant as participant_screen

    session = {
        "participant_team": "Velocity",
        "participant_event_id": GENTING_EVENT_ID,
        "participant_team_id": "T6",
        "participant_name": "Ada Lovelace",
    }
    with patch.object(participant_screen, "st") as fake:
        fake.session_state = session
        fake.container.return_value.__enter__ = lambda self: None
        fake.container.return_value.__exit__ = lambda self, *args: False
        render_team_assignment_card(_TeamCardDB(instruction))

    emitted = " ".join(
        str(call.args[0]) for name in ("markdown", "write", "caption", "header", "title", "info")
        for call in getattr(fake, name).call_args_list if call.args
    )
    assert "<div" not in emitted
    assert "style=" not in emitted
    assert "unsafe_allow_html" not in emitted
    assert "Find your team members" in emitted


def test_team_card_uses_native_streamlit_elements_only():
    source = (ROOT / "screens/participant.py").read_text()
    start = source.index("def render_team_assignment_card(")
    end = source.index("def find_existing_submission(", start)
    card = source[start:end]
    assert "unsafe_allow_html" not in card
    assert "<div" not in card
    assert "st.container(border=True)" in card
    # The canonical labels the staging contract pins remain in place.
    assert "YOUR TEAM" in card and "TEAM IDENTITY" in card
