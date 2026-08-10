from pathlib import Path

import pytest

from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import StandardCoreV2Adapter
from engines.programme_adapter import CanonicalProgrammeAdapter
from engines.programme_hierarchy import activity_details, encode_activity_details
from screens.create_event import (
    _identity_configuration_error,
    _parse_identity_lines,
    _resize_cross_event_teams,
    _resize_event_teams,
)
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


@pytest.mark.parametrize("event_id", [
    "AIA-WE-260810081110-UPPER",
    "AIA-WE-260810081110-LOWER",
])
def test_real_aia_programmes_validate_all_seven_native_stages(event_id):
    rows = [module["Activities"][0] for module in agile_programme(event_id)]
    catalyst = rows[5]
    catalyst["ActivityID"] = f"{event_id}-ACT-006"
    details = activity_details(catalyst)
    details["ActivityID"] = catalyst["ActivityID"]
    catalyst["FacilitatorInstruction"] = encode_activity_details(details)
    snapshot = CanonicalProgrammeAdapter(event_id, rows).snapshot()
    assert snapshot.errors == []
    assert len(snapshot.activities) == 7
    assert [activity["StageName"] for activity in snapshot.activities] == [
        "Launch App / Country Assignment", "Pipeline", "Helium Stick",
        "Key Punch", "Lunch / Break", "Catalyst Challenge", "NASI",
    ]
    resolved = snapshot.activity(f"{event_id}-ACT-006")
    assert resolved["ActivityType"] == "Activity"
    assert resolved["SubmissionType"] == "CATALYST"
    assert resolved["ContentType"] == "Catalyst"
    assert resolved["LinkedContentID"] == ""


def test_country_pool_is_event_configuration_and_supports_fewer_groups():
    upper, lower = allocate_country_pool(2, 4)
    teams = team_configuration("EVT-AIA", lower)
    assert [team["Country"] for team in teams] == [
        "India", "Malaysia", "Philippines", "Thailand",
    ]
    assert len({team["Country"] for team in teams}) == 4
    assert len(COUNTRIES) == 6
    assert [country for country, _ in upper] == ["Korea", "Japan"]
    with pytest.raises(ValueError, match="7 active groups require 7 unique team identities"):
        allocate_country_pool(3, 4)
    expanded = COUNTRIES + (("Tiger", "🐯"), ("Eagle", "🦅"))
    upper, lower = allocate_country_pool(3, 4, expanded)
    assert len(upper + lower) == 7


def test_event_team_resize_uses_generic_identity_pool_without_six_team_limit():
    pool = [{"TeamIdentity": country, "Country": country, "Emoji": flag} for country, flag in COUNTRIES]
    pool += [{"TeamIdentity": "Tiger", "Emoji": "🐯"}, {"TeamIdentity": "Eagle", "Emoji": "🦅"}]
    initial = team_configuration("EVT-AIA", COUNTRIES[:3])
    expanded = _resize_event_teams("EVT-AIA", initial, 8, pool, "CUSTOM", "Weekend Teams")
    assert [team["TeamIdentity"] for team in expanded] == [item["TeamIdentity"] for item in pool]
    reduced = _resize_event_teams("EVT-AIA", expanded, 2, pool)
    assert [team["TeamIdentity"] for team in reduced] == ["Korea", "Japan"]
    with pytest.raises(ValueError, match="9 active groups require 9 unique team identities"):
        _resize_event_teams("EVT-AIA", initial, 9, pool)


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
        "_EventPayload": {
            "PairedEventID": "LOWER", "CountryPool": pool,
            "CrossEventIdentityUnique": True,
        },
    }
    upper = team_configuration("UPPER", COUNTRIES[:2])
    lower = team_configuration("LOWER", COUNTRIES[2:5])
    resized = _resize_cross_event_teams(_PairDB(lower), event, upper, 3)
    assert [team["Country"] for team in resized] == ["Korea", "Japan", "Thailand"]
    assert not ({team["Country"] for team in resized} & {team["Country"] for team in lower})


def test_cross_event_resize_requires_pool_expansion_and_blocks_joined_pair():
    pool = [country for country, _ in COUNTRIES]
    event = {
        "EventID": "UPPER",
        "_EventPayload": {
            "PairedEventID": "LOWER", "CountryPool": pool,
            "CrossEventIdentityUnique": True,
        },
    }
    upper = team_configuration("UPPER", COUNTRIES[:2])
    lower = team_configuration("LOWER", COUNTRIES[2:])
    with pytest.raises(ValueError, match="7 active groups require 7 unique team identities"):
        _resize_cross_event_teams(_PairDB(lower), event, upper, 3)
    expanded_pool = pool + [{"TeamIdentity": "Tiger"}]
    resized = _resize_cross_event_teams(
        _PairDB(lower), event, upper, 3, expanded_pool,
    )
    assert [team["TeamIdentity"] for team in resized][-1] == "Tiger"
    with pytest.raises(ValueError, match="either paired event"):
        _resize_cross_event_teams(_PairDB(lower[:3], paired_participants=1), event, upper, 3)


def test_standard_adapter_rejects_duplicate_team_identities_before_publish():
    adapter = object.__new__(StandardCoreV2Adapter)
    adapter.get_participant_count = lambda event_id: 0
    adapter.get_event = lambda event_id: {
        "EventName": "AIA", "JoinCode": "ABC123", "ScoringMode": "TEAM_COMPETITIVE"
    }
    adapter._rpc = lambda *args, **kwargs: pytest.fail("must not publish duplicates")
    with pytest.raises(RuntimeDatabaseError, match="Duplicate team identity"):
        adapter.replace_event_teams("EVT-AIA", [
            {"TeamName": "Tiger", "Country": "Korea"},
            {"TeamName": "tiger", "Country": "Malaysia"},
        ])


def test_standard_adapter_round_trips_generic_identity_metadata_without_schema_changes():
    event = {
        "EventID": "EVT-THEMED",
        "EventName": "Animal Teams",
        "JoinCode": "ANIMAL",
        "ScoringMode": "TEAM_COMPETITIVE",
        "_EventPayload": {
            "TeamIdentityConfig": {
                "ThemeType": "ANIMAL",
                "ThemeName": "Jungle",
                "IdentityPool": [{"TeamIdentity": "Tiger", "Emoji": "🐯"}],
                "Identities": [{
                    "TeamID": "EVT-THEMED-TEAM-01",
                    "TeamIdentity": "Tiger",
                    "Emoji": "🐯",
                    "Image": "https://example.test/tiger.png",
                }],
            },
        },
    }
    adapter = object.__new__(StandardCoreV2Adapter)
    adapter.get_event = lambda event_id: event
    adapter._rows = lambda table, query: [{
        "team_id": "EVT-THEMED-TEAM-01", "team_name": "Tiger",
        "country": "", "team_flag": "🐯", "is_active": True,
    }]
    teams = adapter.get_teams("EVT-THEMED")
    assert teams[0] | {
        "ThemeType": "ANIMAL", "ThemeName": "Jungle",
        "TeamIdentity": "Tiger", "Emoji": "🐯",
        "Image": "https://example.test/tiger.png",
    } == teams[0]

    updates = []
    adapter.get_participant_count = lambda event_id: 0
    adapter._rpc = lambda *args, **kwargs: {"ok": True}
    adapter.update_event_metadata = lambda event_id, fields: updates.append(fields)
    adapter.replace_event_teams("EVT-THEMED", teams)
    saved = updates[-1]["TeamIdentityConfig"]
    assert saved["IdentityPool"] == [{"TeamIdentity": "Tiger", "Emoji": "🐯"}]
    assert saved["Identities"][0]["Image"].endswith("tiger.png")


def test_arbitrary_theme_identity_metadata_uses_existing_event_payload():
    identities = _parse_identity_lines(
        "Tiger | 🐯\nEagle | 🦅\nPanther | | https://example.test/panther.png"
    )
    assert [row["TeamIdentity"] for row in identities] == ["Tiger", "Eagle", "Panther"]
    assert identities[0]["Emoji"] == "🐯"
    assert identities[2]["Image"].endswith("panther.png")
    assert _identity_configuration_error(4, identities) == (
        "4 active groups require 4 unique team identities. 3 are currently configured."
    )


def test_theme_changes_do_not_touch_programme_configuration():
    source = (Path(__file__).resolve().parents[1] / "screens/create_event.py").read_text()
    assert "TeamIdentityConfig" in source
    assert "Theme type" in source
    assert "Team identity pool" in source
    assert "Regenerate generic team identities" in source
    assert "save_programme_stages" not in source
    assert "duplicate_programme" not in source


def test_break_cannot_be_launched_through_standard_adapter():
    adapter = object.__new__(StandardCoreV2Adapter)
    adapter._rpc = lambda *args, **kwargs: pytest.fail("break must not call runtime")
    lunch = agile_programme("EVT-AIA")[4]["Activities"][0]
    with pytest.raises(RuntimeDatabaseError, match="programme marker"):
        adapter.set_event_stage("EVT-AIA", lunch)
