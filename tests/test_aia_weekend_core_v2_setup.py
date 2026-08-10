import pytest

from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import StandardCoreV2Adapter
from engines.programme_adapter import CanonicalProgrammeAdapter
from screens.create_event import _resize_cross_event_teams, _resize_event_teams
from scripts.exos_core_v2_prepare_aia_weekend import (
    COUNTRIES,
    PROGRAMME,
    allocate_country_pool,
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
    upper, lower = allocate_country_pool(2, 4)
    teams = team_configuration("EVT-AIA", lower)
    assert [team["Country"] for team in teams] == [
        "India", "Malaysia", "Philippines", "Thailand",
    ]
    assert len({team["Country"] for team in teams}) == 4
    assert len(COUNTRIES) == 6
    assert [country for country, _ in upper] == ["Korea", "Japan"]
    with pytest.raises(ValueError, match="cannot exceed six"):
        allocate_country_pool(3, 4)


def test_event_team_resize_preserves_unique_country_pool():
    pool = [country for country, _ in COUNTRIES]
    initial = team_configuration("EVT-AIA", COUNTRIES[:3])
    expanded = _resize_event_teams("EVT-AIA", initial, 6, pool)
    assert [team["Country"] for team in expanded] == pool
    reduced = _resize_event_teams("EVT-AIA", expanded, 2, pool)
    assert [team["Country"] for team in reduced] == pool[:2]
    with pytest.raises(ValueError, match="unique country identities"):
        _resize_event_teams("EVT-AIA", initial, 7, pool)


class _PairDB:
    def __init__(self, paired_teams, paired_participants=0):
        self.paired_teams = paired_teams
        self.paired_participants = paired_participants

    def get_event(self, event_id):
        return {"EventID": event_id}

    def get_teams(self, event_id):
        return list(self.paired_teams)

    def get_participant_count(self, event_id):
        return self.paired_participants


def test_cross_event_resize_preserves_other_event_and_uses_only_unassigned_country():
    pool = [country for country, _ in COUNTRIES]
    event = {
        "EventID": "UPPER",
        "_EventPayload": {"PairedEventID": "LOWER", "CountryPool": pool},
    }
    upper = team_configuration("UPPER", COUNTRIES[:2])
    lower = team_configuration("LOWER", COUNTRIES[2:5])
    resized = _resize_cross_event_teams(_PairDB(lower), event, upper, 3)
    assert [team["Country"] for team in resized] == ["Korea", "Japan", "Thailand"]
    assert not ({team["Country"] for team in resized} & {team["Country"] for team in lower})


def test_cross_event_resize_rejects_more_than_six_total_or_joined_pair():
    pool = [country for country, _ in COUNTRIES]
    event = {
        "EventID": "UPPER",
        "_EventPayload": {"PairedEventID": "LOWER", "CountryPool": pool},
    }
    upper = team_configuration("UPPER", COUNTRIES[:2])
    lower = team_configuration("LOWER", COUNTRIES[2:])
    with pytest.raises(ValueError, match="at most 6 unique countries"):
        _resize_cross_event_teams(_PairDB(lower), event, upper, 3)
    with pytest.raises(ValueError, match="either paired event"):
        _resize_cross_event_teams(_PairDB(lower[:3], paired_participants=1), event, upper, 2)


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
