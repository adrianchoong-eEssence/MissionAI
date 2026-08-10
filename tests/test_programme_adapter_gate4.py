from concurrent.futures import ThreadPoolExecutor

import pytest

from engines.programme_adapter import (
    CONTENT_HANDLERS,
    CanonicalProgrammeAdapter,
    ProgrammeIntegrityError,
)
from engines.programme_hierarchy import encode_activity_details
from screens.control_centre import _start_programme_activity


def row(event="E1", module="M1", activity="A1", module_order=1,
        activity_order=1, content_type="Standard Activity", linked="",
        active="Yes", admin="Admin label", participant="Participant label"):
    return {
        "EventID": event,
        "ProgrammeID": f"{event}-PROGRAMME",
        "ModuleID": module,
        "ActivityID": activity,
        "ModuleOrder": module_order,
        "ActivityOrder": activity_order,
        "StageNo": activity_order,
        "StageName": admin,
        "IsActive": active,
        "FacilitatorInstruction": encode_activity_details({
            "ModuleID": module,
            "ActivityID": activity,
            "AdminDisplayName": admin,
            "ParticipantDisplayName": participant,
            "ContentType": content_type,
            "LinkedContentID": linked,
            "ParticipantNarrative": "Narrative",
            "ParticipantTask": "Task",
            "EvidenceRequirement": "Photo",
        }),
    }


@pytest.mark.parametrize("content_type", [
    "Standard Activity", "Experience Board", "Sync AI", "Catalyst",
    "Briefing", "Break", "Marketplace", "Judging", "Debrief",
    "Custom configured content",
])
def test_registered_content_types_resolve_without_name_routing(content_type):
    linked = "CONTENT-1" if content_type in {
        "Experience Board", "Sync AI", "Catalyst", "Marketplace",
        "Custom configured content",
    } else ""
    snapshot = CanonicalProgrammeAdapter("E1", [
        row(content_type=content_type, linked=linked),
    ]).snapshot()
    assert snapshot.activities[0]["LinkedContentHandler"] == CONTENT_HANDLERS[content_type]


def test_stable_ids_survive_display_label_rename():
    first = CanonicalProgrammeAdapter("E1", [row()]).snapshot()
    renamed = CanonicalProgrammeAdapter("E1", [
        row(admin="Renamed admin", participant="Renamed participant"),
    ]).snapshot()
    assert first.report_identity("A1") == renamed.report_identity("A1")
    assert renamed.participant_view({"Stage": {"ActivityID": "A1"}})["Activity"] == "Renamed participant"


def test_duplicate_orders_ids_missing_parent_and_missing_link_fail_closed():
    rows = [
        row(activity="A1", module="M1", module_order=1, activity_order=1),
        row(activity="A1", module="M2", module_order=1, activity_order=1),
        row(activity="A3", module="", module_order=3, activity_order=1),
        row(activity="A4", module="M4", module_order=4, activity_order=1,
            content_type="Experience Board", linked=""),
    ]
    snapshot = CanonicalProgrammeAdapter("E1", rows).snapshot()
    with pytest.raises(ProgrammeIntegrityError):
        snapshot.require_valid()
    message = " ".join(snapshot.errors)
    assert "Duplicate stable ActivityID" in message
    assert "Duplicate active Module order" in message
    assert "no canonical parent ModuleID" in message
    assert "missing linked content" in message


def test_linked_content_event_type_and_active_validation():
    activity = row(content_type="Sync AI", linked="SYNC-1")
    invalid = CanonicalProgrammeAdapter("E1", [activity], linked_content={
        "SYNC-1": {"EventID": "E2", "ContentType": "Catalyst", "Active": False},
    }).snapshot()
    assert len(invalid.errors) >= 1


def test_native_catalyst_submission_does_not_require_fake_linked_content():
    activity = row(content_type="Catalyst", linked="")
    activity["SubmissionType"] = "CATALYST"
    snapshot = CanonicalProgrammeAdapter("E1", [activity]).snapshot()
    assert snapshot.errors == []
    assert snapshot.activities[0]["LinkedContentID"] == ""


def test_non_native_catalyst_content_still_requires_linked_content():
    snapshot = CanonicalProgrammeAdapter("E1", [
        row(content_type="Catalyst", linked=""),
    ]).snapshot()
    assert snapshot.errors == ["Activity A1 is missing linked content."]


def test_inactive_activity_is_filtered_and_cannot_launch():
    snapshot = CanonicalProgrammeAdapter("E1", [row(active="No")]).snapshot()
    assert snapshot.activities == []
    with pytest.raises(ProgrammeIntegrityError):
        snapshot.resolve_runtime({"Stage": {"ActivityID": "A1"}})


def test_legacy_duplicates_are_audited_without_rewrite():
    legacy = [
        {"EventID": "E1", "StageNo": 1, "StageName": "Legacy"},
        {"EventID": "E1", "StageNo": 1, "StageName": "Legacy copy"},
    ]
    audit = CanonicalProgrammeAdapter("E1", legacy).snapshot().legacy_audit
    assert audit["LegacyRows"] == 2
    assert audit["DuplicateLogicalActivities"]
    assert audit["ProductionRecordsChanged"] is False
    assert all(not row["AutomaticRewrite"] for row in audit["ProposedCanonicalMappings"])


def test_two_events_and_concurrent_reads_remain_isolated():
    event_a = CanonicalProgrammeAdapter("E1", [row(event="E1")]).snapshot()
    event_b = CanonicalProgrammeAdapter("E2", [row(event="E2")]).snapshot()
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(
            lambda snapshot: snapshot.resolve_runtime({"Stage": {"ActivityID": "A1"}})[1]["EventID"],
            [event_a, event_b] * 50,
        ))
    assert results.count("E1") == 50
    assert results.count("E2") == 50


def test_control_manual_selection_launches_by_stable_activity_id():
    class Control:
        def set_stage(self, event_id, stage):
            self.launched = (event_id, stage["ActivityID"])

    control = Control()
    activity = CanonicalProgrammeAdapter("E1", [row()]).snapshot().activity("A1")
    _start_programme_activity(control, "E1", activity, {})
    assert control.launched == ("E1", "A1")


def test_generic_hierarchy_code_contains_no_client_or_event_shortcuts():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "engines" / "programme_adapter.py").read_text()
    for forbidden in ("EVT-0004", "Bayu", "Formula RACE", "AIA", "MAHB"):
        assert forbidden not in source
