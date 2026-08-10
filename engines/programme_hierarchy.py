"""Programme-first hierarchy over the stable ProgrammeStages transport.

ProgrammeStages remains the persisted/runtime contract.  A module is an
event-owned view over one or more consecutive activity rows, so older events
continue to work without a destructive schema migration.
"""

from copy import deepcopy


FACILITATOR_TYPE_LABELS = {
    "registration": "Registration",
    "teamdiscovery": "Energiser",
    "missionbriefing": "Briefing",
    "activity": "Activity",
    "missionactive": "Mission",
    "break": "Lunch / Break",
    "marketplace": "Marketplace",
    "preparation": "Preparation",
    "performance": "Performance",
    "judging": "Judging",
    "debrief": "Debrief",
    "closing": "Closing",
}
MODULE_MARKER = "EXOSMODULE|"
ACTIVITY_META_MARKER = "EXOSMETA:"
CONTENT_TYPES = (
    "Standard Activity",
    "Experience Board",
    "Sync AI",
    "Catalyst",
    "Break",
    "Briefing",
    "Marketplace",
    "Judging",
    "Debrief",
    "Custom configured content",
)


def encode_module_stage_type(module_name, day, activity_type="Activity"):
    clean_name = str(module_name).replace("|", "/").strip() or "Untitled Module"
    clean_type = str(activity_type).replace("|", "/").strip() or "Activity"
    return f"{MODULE_MARKER}{int(day)}|{clean_name}|{clean_type}"


def decode_module_stage_type(stage):
    raw = str(stage.get("StageType", ""))
    if not raw.startswith(MODULE_MARKER):
        return None
    parts = raw.split("|", 3)
    if len(parts) != 4:
        return None
    try:
        day = int(parts[1])
    except ValueError:
        day = 1
    return {"Day": day, "ModuleName": parts[2], "ActivityType": parts[3]}


def activity_details(stage):
    raw = str(stage.get("FacilitatorInstruction", "") or "")
    if not raw.startswith(ACTIVITY_META_MARKER):
        return {
            "FacilitatorInstructions": raw,
            "Questions": "",
            "Credits": 0,
            "Rules": "",
            "Objectives": "",
            "Scoring": "",
            "EvidenceRequired": False,
            "ParticipantNarrative": "",
            "ParticipantTask": str(stage.get("ParticipantMessage", "") or ""),
            "EvidenceRequirement": "",
            "ContentType": "",
            "LinkedContent": "",
            "LinkedContentID": "",
            "LinkedContentName": "",
            "ProgrammeID": "",
            "ActivityID": "",
            "ModuleID": "",
            "AdminDisplayName": "",
            "ParticipantDisplayName": "",
            "ScoringMode": str(stage.get("ScoringMode", "TEAM_COMPETITIVE")),
            "ParticipantScope": str(stage.get("ParticipantScope", "TEAM")),
            "SubmissionType": str(stage.get("SubmissionType", "NONE")),
            "ModuleDetails": {},
        }
    import json
    try:
        value = json.loads(raw[len(ACTIVITY_META_MARKER):])
    except (TypeError, ValueError):
        value = {}
    return {
        "FacilitatorInstructions": str(value.get("FacilitatorInstructions", "")),
        "Questions": str(value.get("Questions", "")),
        "Credits": int(value.get("Credits", 0) or 0),
        "Rules": str(value.get("Rules", "")),
        "Objectives": str(value.get("Objectives", "")),
        "Scoring": str(value.get("Scoring", "")),
        "EvidenceRequired": bool(value.get("EvidenceRequired", False)),
        "ParticipantNarrative": str(value.get("ParticipantNarrative", "")),
        "ParticipantTask": str(
            value.get("ParticipantTask", stage.get("ParticipantMessage", ""))
        ),
        "EvidenceRequirement": str(value.get("EvidenceRequirement", "")),
        "ContentType": str(value.get("ContentType", "")),
        "LinkedContent": str(value.get("LinkedContent", "")),
        "LinkedContentID": str(value.get("LinkedContentID", "")),
        "LinkedContentName": str(value.get("LinkedContentName", "")),
        "ProgrammeID": str(value.get("ProgrammeID", "")),
        "ActivityID": str(value.get("ActivityID", "")),
        "ModuleID": str(value.get("ModuleID", "")),
        "AdminDisplayName": str(value.get("AdminDisplayName", "")),
        "ParticipantDisplayName": str(value.get("ParticipantDisplayName", "")),
        "ScoringMode": str(value.get("ScoringMode", stage.get("ScoringMode", "TEAM_COMPETITIVE"))),
        "ParticipantScope": str(value.get("ParticipantScope", stage.get("ParticipantScope", "TEAM"))),
        "SubmissionType": str(value.get("SubmissionType", stage.get("SubmissionType", "NONE"))),
        "ModuleDetails": (
            value.get("ModuleDetails", {})
            if isinstance(value.get("ModuleDetails", {}), dict)
            else {}
        ),
    }


def encode_activity_details(values):
    import json
    return ACTIVITY_META_MARKER + json.dumps(values, ensure_ascii=False, sort_keys=True)


def friendly_type(stage):
    marker = decode_module_stage_type(stage)
    if marker:
        return marker["ActivityType"]
    return FACILITATOR_TYPE_LABELS.get(
        str(stage.get("StageType", "")).casefold(),
        "Activity",
    )


def build_programme_hierarchy(stages):
    """Compatibility wrapper; all hierarchy construction belongs to the adapter."""
    from engines.programme_adapter import CanonicalProgrammeAdapter
    event_id = str((stages or [{}])[0].get("EventID", "EVENT"))
    return CanonicalProgrammeAdapter(event_id, stages).snapshot().modules


def canonical_event_programme(stages, event_id):
    """Compatibility wrapper over the sole canonical adapter."""
    from engines.programme_adapter import CanonicalProgrammeAdapter
    return CanonicalProgrammeAdapter(event_id, stages).snapshot().modules


def flatten_programme_hierarchy(modules):
    """Convert edited containers back to the stable ordered stage transport."""
    rows = []
    for module in modules:
        rows.extend(deepcopy(module.get("Activities", [])))
    for position, row in enumerate(rows, start=1):
        row["StageNo"] = position
        row.pop("ActivityTypeLabel", None)
    return rows


def current_module_activity(stages, current_stage_no):
    """Legacy runtime-state compatibility wrapper over the canonical adapter."""
    from engines.programme_adapter import CanonicalProgrammeAdapter, ProgrammeIntegrityError
    event_id = str((stages or [{}])[0].get("EventID", "EVENT"))
    snapshot = CanonicalProgrammeAdapter(event_id, stages).snapshot()
    try:
        return snapshot.resolve_runtime({"StageNo": current_stage_no})
    except ProgrammeIntegrityError:
        return ({}, {})


def experience_set_config(module):
    """Read an Experience Set link from a module's stable metadata envelope."""
    activities = list((module or {}).get("Activities", []) or [])
    if not activities:
        return {"ModuleType": "Standard", "LinkedExperienceSet": ""}
    details = activity_details(activities[0]).get("ModuleDetails", {})
    module_type = str(details.get("ModuleType", "Standard") or "Standard").strip()
    linked = str(details.get("LinkedExperienceSet", "") or "").strip()
    return {
        "ModuleType": module_type,
        "LinkedExperienceSet": linked,
    }


def activity_content_config(stage, module=None):
    """Resolve event-owned participant content from one programme activity."""
    stage = dict(stage or {})
    details = activity_details(stage)
    content_type = str(
        stage.get("ContentType", "") or details.get("ContentType", "") or ""
    ).strip()
    linked = str(
        stage.get("LinkedContentID", "")
        or stage.get("LinkedContent", "")
        or details.get("LinkedContentID", "")
        or details.get("LinkedContent", "")
        or ""
    ).strip()
    linked_name = str(
        stage.get("LinkedContentName", "")
        or details.get("LinkedContentName", "")
        or linked
    ).strip()

    # Preserve links authored before activity-level content linkage existed.
    if not content_type and module:
        legacy = experience_set_config(module)
        if (
            legacy["ModuleType"].casefold() == "experience set"
            and legacy["LinkedExperienceSet"]
        ):
            content_type = "Experience Board"
            linked = legacy["LinkedExperienceSet"]

    if not content_type:
        legacy_types = {
            "break": "Break",
            "missionbriefing": "Briefing",
            "briefing": "Briefing",
            "marketplace": "Marketplace",
            "judging": "Judging",
            "debrief": "Debrief",
        }
        content_type = legacy_types.get(
            str(stage.get("StageType", "")).strip().casefold(),
            "Standard Activity",
        )
    if content_type not in CONTENT_TYPES:
        content_type = "Standard Activity"
    return {
        "ContentType": content_type,
        "LinkedContent": linked,
        "LinkedContentID": linked,
        "LinkedContentName": linked_name,
    }


def linked_content_stage(stage, module=None, experience_count=0):
    """Attach resolved linkage to the live payload without changing the schema."""
    payload = deepcopy(stage or {})
    config = activity_content_config(payload, module)
    payload.update(config)
    # Programme Builder owns canonical activities in ProgrammeStages. The
    # participant runtime still addresses a live submission by MissionID, so a
    # modern activity without a separately linked mission is exposed under its
    # durable ActivityID. The explicit marker prevents legacy mission publish
    # logic from treating this activity as a missing Google Sheets Mission.
    activity_id = str(payload.get("ActivityID", "") or "").strip()
    mission_id = str(payload.get("MissionID", "") or "").strip()
    if activity_id and not mission_id and not payload.get("Legacy"):
        payload["MissionID"] = activity_id
        payload["ProgrammeActivityID"] = activity_id
    if config["ContentType"] == "Experience Board":
        payload.update({
            "ModuleType": "Experience Set",
            "LinkedExperienceSet": config["LinkedContent"],
            "ExperienceCount": int(experience_count or 0),
        })
    return payload


def experience_set_stage(stage, module, experience_count=0):
    """Enrich a live stage without changing the ProgrammeStages schema."""
    config = experience_set_config(module)
    payload = deepcopy(stage or {})
    if config["ModuleType"].casefold() == "experience set" and config["LinkedExperienceSet"]:
        payload.update({
            "ModuleType": "Experience Set",
            "LinkedExperienceSet": config["LinkedExperienceSet"],
            "ExperienceCount": int(experience_count or 0),
        })
    return payload
