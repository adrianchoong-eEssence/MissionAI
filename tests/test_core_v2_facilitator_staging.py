from pathlib import Path

import pytest

from data.runtime_database import RuntimeDatabaseError
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


def test_duplicate_audit_adapter_returns_canonical_empty_report():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    assert adapter.audit_participant_duplicates(
        "AIA-WE-260810081110-LOWER"
    ) == {
        "EventID": "AIA-WE-260810081110-LOWER",
        "DuplicateGroups": [],
    }


def test_diagnostic_audit_renders_after_operational_sections():
    source = (ROOT / "screens/control_centre.py").read_text()
    show = source.split("def show_control_centre", 1)[1]

    submission_view = show.index("_render_stage_widgets(")
    team_management = show.index("_render_team_management(")
    emergency = show.index('st.subheader("Emergency Recovery")')
    scoring = show.index('with st.expander("Scoring Finalisation and Recovery")')
    diagnostics = show.index("_render_duplicate_audit(")

    assert submission_view < team_management < emergency < scoring < diagnostics


def test_lower_pipeline_submission_read_path_uses_canonical_v2_rows():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    adapter._rows = lambda path, query, admin=True: [{
        "submission_id": "SUB-PIPELINE-EXISTING",
        "event_id": "AIA-WE-260810081110-LOWER",
        "team_id": "AIA-WE-260810081110-LOWER-TEAM-01",
        "participant_id": "P-ADRIAN",
        "activity_id": "AIA-WE-260810081110-LOWER-ACT-002",
        "submission_status": "SUBMITTED",
        "submission_payload": {
            "ParticipantName": "Adrian Choong",
            "TeamName": "India",
            "SubmissionType": "PIPELINE",
            "Metric1": 100,
            "Metric2": 150,
            "Metric3": 25,
        },
        "submitted_at": "2026-08-11T00:00:00Z",
        "reviewed_at": None,
        "reviewed_by": None,
        "score": None,
    }]

    submissions = adapter.get_canonical_submissions(
        "AIA-WE-260810081110-LOWER"
    )

    assert len(submissions) == 1
    assert submissions[0]["SubmissionID"] == "SUB-PIPELINE-EXISTING"
    assert submissions[0]["ParticipantName"] == "Adrian Choong"
    assert submissions[0]["TeamName"] == "India"
    assert submissions[0]["ActivityID"].endswith("ACT-002")
    assert submissions[0]["Status"] == "SUBMITTED"


def test_standard_control_centre_does_not_probe_legacy_experience_assignments():
    source = (ROOT / "screens/control_centre.py").read_text()
    assert "SupabaseExperienceRepository" not in source
    assert "event_experience_assignments" not in source


def test_blocked_assignment_probe_explains_exact_assertion_counts():
    adapter = StandardCoreV2Adapter.__new__(StandardCoreV2Adapter)
    adapter.legacy_runtime_calls = 0
    adapter.google_sheets_runtime_calls = 0

    with pytest.raises(RuntimeDatabaseError, match="Blocked non-Core-v2 table"):
        adapter._guard("event_experience_assignments")

    assert adapter.get_staging_call_counts() == {
        "LEGACY_RUNTIME_CALLS": 1,
        "GOOGLE_SHEETS_RUNTIME_CALLS": 0,
    }


def test_standard_facilitator_render_has_only_core_v2_data_routes():
    adapter_source = (ROOT / "data/standard_core_v2_adapter.py").read_text()
    control_source = (ROOT / "screens/control_centre.py").read_text()
    for legacy_path in (
        "runtime_events", "runtime_participants", "runtime_submissions",
        "event_experience_assignments", "experience_definitions",
    ):
        assert legacy_path not in control_source
    assert "GoogleSheetsDB" not in control_source
    assert '"LEGACY_RUNTIME_CALLS": self.legacy_runtime_calls' in adapter_source
    assert '"GOOGLE_SHEETS_RUNTIME_CALLS": self.google_sheets_runtime_calls' in adapter_source
