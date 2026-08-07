"""Configuration-only programme cloning and product-aware template selection."""
from copy import deepcopy
from datetime import datetime, timezone
import uuid

from engines.programme_hierarchy import activity_details, decode_module_stage_type, encode_activity_details


GENERIC_MODULES = [
    (1, "Arrival & Registration", ["Arrival & Registration"]),
    (1, "Opening", ["Opening"]), (1, "Break", ["Break"]),
    (1, "Lunch", ["Lunch"]), (1, "Debrief", ["Debrief"]),
    (1, "Closing", ["Closing"]),
]
AGILE_MODULES = [
    (1, "Opening", ["Opening"]),
    (1, "Pipeline", ["Pipeline Challenge", "Pipeline Results", "Pipeline Debrief"]),
    (1, "Helium Stick", ["Helium Stick", "Helium Stick Debrief"]),
    (1, "Key Punch", ["Key Punch", "Key Punch Results"]),
    (1, "Lunch", ["Lunch"]),
    (1, "Catalyst Challenge", ["Catalyst Challenge", "Enterprise Integration"]),
    (1, "Debrief", ["Mission Reflection"]), (1, "Closing", ["Closing"]),
]


def programme_family(event):
    event = event or {}
    name = str(event.get("EventName", "")).casefold()
    kind = str(event.get("ProgrammeType", "")).casefold()
    client = str(event.get("Client", "")).casefold()
    if "formula r.a.c.e" in kind or "formula race" in kind or name.strip() == "race": return "RACE"
    if "agile" in kind or "agile" in name or ("aia" in client and "squad" in name): return "AGILE"
    if "mission ai" in kind: return "MISSION_AI"
    return "GENERIC"


def templates_for_event(event, mission_ai_modules, race_modules):
    family = programme_family(event)
    if family == "RACE": return list(race_modules) + list(GENERIC_MODULES)
    if family == "AGILE": return list(AGILE_MODULES) + [row for row in GENERIC_MODULES if row[1] not in {x[1] for x in AGILE_MODULES}]
    if family == "MISSION_AI": return list(mission_ai_modules) + list(GENERIC_MODULES)
    return list(GENERIC_MODULES)


def clone_programme_stages(stages, source_event_id, destination_event_id):
    """Clone structure with destination-owned stable Programme/Module/Activity IDs."""
    source = sorted((deepcopy(row) for row in stages or []), key=lambda row: int(row.get("StageNo") or 0))
    programme_id = f"{destination_event_id}-PROGRAMME"
    module_ids, activity_map, cloned = {}, {}, []
    for position, row in enumerate(source, 1):
        details = activity_details(row)
        marker = decode_module_stage_type(row) or {}
        source_module = str(details.get("ModuleID") or row.get("ModuleID") or marker.get("ModuleName") or f"MODULE-{position}")
        if source_module not in module_ids:
            module_ids[source_module] = f"{destination_event_id}-MOD-{len(module_ids)+1:02d}"
        source_activity = str(details.get("ActivityID") or row.get("ActivityID") or f"{source_event_id}-LEGACY-ACT-{row.get('StageNo',position)}")
        destination_activity = f"{destination_event_id}-ACT-{position:03d}"
        activity_map[source_activity] = destination_activity
        copied = deepcopy(row)
        copied.update({"EventID": destination_event_id, "ProgrammeID": programme_id,
                       "ModuleID": module_ids[source_module], "ActivityID": destination_activity,
                       "StageNo": position, "IsActive": row.get("IsActive", "Yes")})
        details.update({"ProgrammeID": programme_id, "ModuleID": module_ids[source_module],
                        "ActivityID": destination_activity})
        copied["FacilitatorInstruction"] = encode_activity_details(details)
        cloned.append(copied)
    return cloned, {"ProgrammeID": programme_id, "ModuleIDs": module_ids, "ActivityIDs": activity_map}


def clone_experience_assignments(assignments, destination_event_id, id_map):
    rows = []
    for row in assignments or []:
        source_activity = str(row.get("ActivityID", ""))
        if source_activity not in id_map.get("ActivityIDs", {}): continue
        source_module = str(row.get("ModuleID", ""))
        copied = deepcopy(row)
        copied.update({"ExperienceAssignmentID": f"ASN-{uuid.uuid4()}", "EventID": destination_event_id,
            "ProgrammeID": id_map["ProgrammeID"], "ModuleID": id_map["ModuleIDs"].get(source_module, f"{destination_event_id}-MOD-01"),
            "ActivityID": id_map["ActivityIDs"][source_activity], "Active": True})
        rows.append(copied)
    return rows


def saved_state(timestamp=None):
    value = timestamp or datetime.now(timezone.utc)
    return {"State": "SAVED", "Timestamp": value.isoformat()}


def duplication_summary(stages):
    """Return a review-safe summary without exposing any operational records."""
    modules, activities = [], []
    for row in sorted(stages or [], key=lambda item: int(item.get("StageNo") or 0)):
        marker = decode_module_stage_type(row) or {}
        module = str(marker.get("ModuleName") or row.get("ModuleID") or "Programme")
        if module not in modules:
            modules.append(module)
        activities.append(str(row.get("StageName") or "Untitled activity"))
    return {"Modules": modules, "Activities": activities,
            "ModuleCount": len(modules), "ActivityCount": len(activities)}
