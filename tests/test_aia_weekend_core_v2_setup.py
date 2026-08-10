import pytest

from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import StandardCoreV2Adapter
from engines.programme_adapter import CanonicalProgrammeAdapter
from screens.create_event import _resize_event_teams
from scripts.exos_core_v2_prepare_aia_weekend import (
    COUNTRIES,
    PROGRAMME,
    agile_programme,
    team_configuration,
)


def test_agile_weekend_template_has_required_order_and_break_marker():
    modules = agile_programme("EVT-AIA")
    rows = [module["Activities"][0] for module in modules]
    assert [row["StageName"] for row in rows] == [item[0] for item in PROGRAMME]
    assert [row["StageName"] for row in rows] == [
        "Launch App / Country Assignment", "Pipeline", "Helium Stick",
        "Key Punch", "Lunch / Break", "Catalyst Challenge", "NASI",
    ]
    snapshot = CanonicalProgrammeAdapter("EVT-AIA", rows).snapshot()
    lunch = snapshot.activity("EVT-AIA-ACT-05")
    assert lunch["ContentType"] == "Break"
    assert lunch["ScoringMode"] == "NON_SCORING"
    assert lunch["SubmissionType"] == "NONE"
    assert lunch["RuntimeEligible"] is False


def test_country_pool_is_event_configuration_and_supports_fewer_groups():
    teams = team_configuration("EVT-AIA", 4)
    assert [team["Country"] for team in teams] == [
        "Korea", "Japan", "India", "Malaysia",
    ]
    assert len({team["Country"] for team in teams}) == 4
    assert len(COUNTRIES) == 6
    with pytest.raises(ValueError, match="between 1 and 6"):
        team_configuration("EVT-AIA", 7)


def test_event_team_resize_preserves_unique_country_pool():
    pool = [country for country, _ in COUNTRIES]
    initial = team_configuration("EVT-AIA", 3)
    expanded = _resize_event_teams("EVT-AIA", initial, 6, pool)
    assert [team["Country"] for team in expanded] == pool
    reduced = _resize_event_teams("EVT-AIA", expanded, 2, pool)
    assert [team["Country"] for team in reduced] == pool[:2]
    with pytest.raises(ValueError, match="unique country identities"):
        _resize_event_teams("EVT-AIA", initial, 7, pool)


def test_standard_adapter_rejects_duplicate_countries_before_publish():
    adapter = object.__new__(StandardCoreV2Adapter)
    adapter.get_participant_count = lambda event_id: 0
    adapter.get_event = lambda event_id: {
        "EventName": "AIA", "JoinCode": "ABC123", "ScoringMode": "TEAM_COMPETITIVE"
    }
    adapter._rpc = lambda *args, **kwargs: pytest.fail("must not publish duplicates")
    with pytest.raises(RuntimeDatabaseError, match="Duplicate country"):
        adapter.replace_event_teams("EVT-AIA", [
            {"TeamName": "Korea", "Country": "Korea"},
            {"TeamName": "Korea 2", "Country": "korea"},
        ])


def test_break_cannot_be_launched_through_standard_adapter():
    adapter = object.__new__(StandardCoreV2Adapter)
    adapter._rpc = lambda *args, **kwargs: pytest.fail("break must not call runtime")
    lunch = agile_programme("EVT-AIA")[4]["Activities"][0]
    with pytest.raises(RuntimeDatabaseError, match="programme marker"):
        adapter.set_event_stage("EVT-AIA", lunch)
