from pathlib import Path

import pytest

from data.standard_core_v2_adapter import StandardCoreV2Adapter
from engines.programme_adapter import CanonicalProgrammeAdapter
from scripts.exos_core_v2_prepare_aia_weekend import (
    agile_programme,
    allocate_country_pool,
    team_configuration,
)
from screens.control_centre import stage_family


ROOT = Path(__file__).resolve().parents[1]
AIA_EVENTS = {
    "AIA-WE-260810081110-UPPER": ["Korea", "Japan"],
    "AIA-WE-260810081110-LOWER": ["India", "Malaysia", "Philippines", "Thailand"],
}
AGILE_ORDER = [
    "Launch App / Country Assignment", "Pipeline", "Helium Stick",
    "Key Punch", "Lunch / Break", "Catalyst Challenge", "NASI",
]


def test_staging_facilitator_shell_stops_before_legacy_imports():
    source = (ROOT / "Facilitator.py").read_text()
    staging = source.index('if _deployment_environment() == "staging":')
    stop = source.index("st.stop()", staging)
    google = source.index("from data.google_sheets import GoogleSheetsDB")
    assert staging < stop < google
    strict_path = source[staging:stop]
    assert "show_control_centre(db=db)" in strict_path
    assert "assert_core_v2_only" in strict_path
    assert "GoogleSheetsDB" not in strict_path


@pytest.mark.parametrize("event_id,countries", AIA_EVENTS.items())
def test_canonical_aia_facilitator_shape(event_id, countries):
    rows = [module["Activities"][0] for module in agile_programme(event_id)]
    snapshot = CanonicalProgrammeAdapter(event_id, rows).snapshot()
    upper, lower = allocate_country_pool(2, 4)
    allocation = upper if event_id.endswith("-UPPER") else lower
    teams = team_configuration(event_id, allocation)
    assert snapshot.errors == []
    assert [row["StageName"] for row in snapshot.activities] == AGILE_ORDER
    assert [team["Country"] for team in teams] == countries
    for row in snapshot.activities:
        if row["SubmissionType"] not in {"", "NONE", "NASI"}:
            assert stage_family(row) == "scored"


def test_control_review_reads_programme_through_core_v2_adapter():
    assert StandardCoreV2Adapter.get_programme_hierarchy is StandardCoreV2Adapter.get_programme_stages


def test_revision_decision_remains_pending_in_core_v2():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    captured = {}

    def rpc(name, payload, admin=True):
        captured.update({"name": name, "payload": payload, "admin": admin})
        return payload

    adapter._rpc = rpc
    adapter.decide_canonical_submission(
        "00000000-0000-0000-0000-000000000001",
        "RETURN_FOR_REVISION",
        "Facilitator",
    )
    assert captured["name"] == "exos_v2_standard_review_submission"
    assert captured["payload"]["p_decision"] == "PENDING"
