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


def _module_identity(stage):
    marker = decode_module_stage_type(stage)
    if marker:
        slug = "-".join(marker["ModuleName"].casefold().split())
        return f"custom-{marker['Day']}-{slug}", marker["ModuleName"], marker["Day"]
    name = str(stage.get("StageName", "")).casefold()
    mission_id = str(stage.get("MissionID", "")).upper()
    if "debrief & action" in name or (
        "action plan" in name and "catalyst" not in name
    ):
        return "debrief-action-plan", "Debrief & Action Plan", 2
    if (
        "mission ai" in name
        or "mission board" in name
        or mission_id.startswith("M")
    ):
        return "mission-ai", "Mission AI", 1
    if (
        "sync ai" in name
        or "innovation market" in name
        or mission_id.startswith("S")
    ):
        return "sync-ai", "Sync AI", 1
    if "catalyst" in name or mission_id.startswith("C"):
        return "catalyst-challenge", "Catalyst Challenge", 2
    if "registration" in name or "arrival" in name:
        return "arrival-registration", "Arrival & Registration", 1
    if "team formation" in name or "energiser" in name or "energizer" in name:
        return "energiser", "Energiser", 1
    if "launch exos" in name:
        return "launch-exos", "Launch EXOS", 1
    if "bridge of trust" in name:
        return "bridge-of-trust", "Bridge of Trust", 1
    if "lunch" in name or str(stage.get("StageType", "")).casefold() == "break":
        return "lunch", "Lunch", 1
    if "day 1" in name and ("closing" in name or "celebration" in name):
        return "day-1-closing", "Day 1 Celebration & Closing", 1
    if "debrief" in name or "action plan" in name:
        return "debrief-action-plan", "Debrief & Action Plan", 2
    if "programme closing" in name:
        return "programme-closing", "Programme Closing", 2
    slug = "-".join(name.split()) or f"module-{stage.get('StageNo', '')}"
    return slug, str(stage.get("StageName", "Activity")), 1


def build_programme_hierarchy(stages):
    """Return ordered day/module/activity containers without mutating stages."""
    modules = []
    by_id = {}
    for stage in sorted(stages, key=lambda row: int(row.get("StageNo") or 0)):
        module_id, module_name, day = _module_identity(stage)
        module = by_id.get(module_id)
        if module is None:
            module = {
                "ModuleID": module_id,
                "ModuleName": module_name,
                "Day": day,
                "StartTime": stage.get("StartTime", ""),
                "Status": (
                    "Active"
                    if str(stage.get("IsActive", "Yes")).casefold() != "no"
                    else "Inactive"
                ),
                "Activities": [],
            }
            by_id[module_id] = module
            modules.append(module)
        item = deepcopy(stage)
        item["ActivityTypeLabel"] = friendly_type(stage)
        module["Activities"].append(item)
    for module in modules:
        module["DurationMinutes"] = sum(
            int(float(item.get("DurationMinutes", 0) or 0))
            for item in module["Activities"]
        )
        module["ActivityCount"] = len(module["Activities"])
    return modules


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
    modules = build_programme_hierarchy(stages)
    for module in modules:
        for activity in module["Activities"]:
            if str(activity.get("StageNo", "")) == str(current_stage_no):
                return module, activity
    return (modules[0], modules[0]["Activities"][0]) if modules else ({}, {})


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
