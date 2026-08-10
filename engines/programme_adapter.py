"""Canonical Event -> Programme -> Module -> Activity hierarchy adapter.

ProgrammeStages is a legacy persistence transport only. Stable IDs and the
metadata envelope are authoritative; StageNo and display names are accepted
solely by the compatibility mapper and never by canonical runtime routing.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock

from engines.programme_hierarchy import (
    activity_details,
    decode_module_stage_type,
    friendly_type,
)


CONTENT_HANDLERS = {
    "Standard Activity": "standard",
    "Experience Board": "experience_board",
    "Briefing": "briefing",
    "Break": "break",
    "Sync AI": "sync_ai",
    "Catalyst": "catalyst",
    "Marketplace": "marketplace",
    "RACE Checkpoints": "race_checkpoints",
    "Judging": "judging",
    "Debrief": "debrief",
    "Custom configured content": "custom",
}
LINK_REQUIRED = {"Experience Board", "Sync AI", "Catalyst", "Marketplace", "Custom configured content"}
_READ_LOCK = RLock()


class ProgrammeIntegrityError(ValueError):
    """Raised when unsafe hierarchy data is selected for runtime use."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


@dataclass
class ProgrammeSnapshot:
    event_id: str
    programme_id: str
    modules: list
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    legacy_audit: dict = field(default_factory=dict)

    @property
    def activities(self):
        return [activity for module in self.modules for activity in module["Activities"]]

    def require_valid(self):
        if self.errors:
            raise ProgrammeIntegrityError(self.errors)
        return self

    def activity(self, activity_id, *, active_only=True):
        matches = [
            row for row in self.activities
            if row["ActivityID"] == str(activity_id)
            and (row["Active"] or not active_only)
        ]
        if len(matches) != 1:
            return None
        return matches[0]

    def module_for(self, activity_id):
        return next(
            (module for module in self.modules
             if any(row["ActivityID"] == str(activity_id) for row in module["Activities"])),
            None,
        )

    def resolve_runtime(self, runtime_state):
        payload = dict((runtime_state or {}).get("Stage", {}) or runtime_state or {})
        activity_id = str(payload.get("ActivityID", "")).strip()
        if activity_id:
            activity = self.activity(activity_id, active_only=False)
            if not activity:
                raise ProgrammeIntegrityError([f"Runtime ActivityID {activity_id} is not canonical."])
            if not activity["Active"] or activity["Superseded"]:
                raise ProgrammeIntegrityError([f"Runtime ActivityID {activity_id} is inactive or superseded."])
            return self.module_for(activity_id), activity

        # Compatibility is allowed only for runtime payloads created before stable IDs.
        legacy_order = str(payload.get("StageNo", "")).strip()
        matches = [row for row in self.activities if row["LegacyStageNo"] == legacy_order and row["Active"]]
        if len(matches) != 1:
            raise ProgrammeIntegrityError(["Legacy runtime state does not resolve to one active ActivityID."])
        activity = matches[0]
        return self.module_for(activity["ActivityID"]), activity

    def resolve_runtime_set(self, runtime_state):
        """Resolve a parallel module explicitly; retain legacy single-activity rules."""
        payload = dict((runtime_state or {}).get("Stage", {}) or runtime_state or {})
        activity_ids = [str(value).strip() for value in payload.get("ParallelActivityIDs", []) if str(value).strip()]
        module_id = str(payload.get("ModuleID", "")).strip()
        if not activity_ids:
            module, activity = self.resolve_runtime(runtime_state)
            return module, [activity]
        matches = [row for row in self.activities if row["ActivityID"] in activity_ids and row["Active"] and not row["Superseded"]]
        if len(matches) != len(set(activity_ids)):
            raise ProgrammeIntegrityError(["Parallel runtime state contains a missing or inactive ActivityID."])
        modules = {row["ModuleID"] for row in matches}
        if len(modules) != 1 or (module_id and module_id not in modules):
            raise ProgrammeIntegrityError(["Parallel runtime activities must belong to one canonical ModuleID."])
        module = next(item for item in self.modules if item["ModuleID"] in modules)
        return module, sorted(matches, key=lambda row: (row["ActivityOrder"], row["ActivityID"]))

    def participant_view(self, runtime_state):
        module, activity = self.resolve_runtime(runtime_state)
        return {
            "Module": module.get("ParticipantDisplayName", ""),
            "Activity": activity["ParticipantDisplayName"],
            "Narrative": activity["ParticipantNarrative"],
            "Task": activity["ParticipantTask"],
            "EvidenceRequirement": activity["EvidenceRequirement"],
            "ContentType": activity["ContentType"],
            "LinkedContentID": activity["LinkedContentID"],
            "Handler": activity["LinkedContentHandler"],
        }

    def report_identity(self, activity_id):
        activity = self.activity(activity_id, active_only=False)
        if not activity:
            return None
        return {
            "ProgrammeID": self.programme_id,
            "ModuleID": activity["ModuleID"],
            "ActivityID": activity["ActivityID"],
            "ExperienceID": activity["LinkedContentID"],
        }


class CanonicalProgrammeAdapter:
    """Single hierarchy loader and validator shared by all EXOS centres."""

    def __init__(self, event_id, rows, *, linked_content=None, programme_id=""):
        self.event_id = str(event_id).strip()
        self.rows = [deepcopy(row) for row in (rows or [])]
        self.programme_id = str(programme_id).strip() or f"{self.event_id}-PROGRAMME"
        self.linked_content = dict(linked_content or {})

    @classmethod
    def load(cls, db, event_id, *, linked_content=None):
        with _READ_LOCK:
            rows = db.get_programme_stages(event_id)
        return cls(event_id, rows, linked_content=linked_content).snapshot()

    @staticmethod
    def _active(row):
        return str(row.get("IsActive", "Yes")).strip().casefold() not in {"no", "false", "0", "inactive"}

    def _canonical_activity(self, row, position):
        details = activity_details(row)
        marker = decode_module_stage_type(row) or {}
        legacy_stage = str(row.get("StageNo", "")).strip()
        module_id = str(details.get("ModuleID") or row.get("ModuleID") or "").strip()
        activity_id = str(details.get("ActivityID") or row.get("ActivityID") or "").strip()
        missing_canonical_parent = bool(activity_id and not module_id)
        legacy = not (module_id and activity_id)
        if not module_id:
            if marker:
                marker_slug = "-".join(str(marker.get("ModuleName", "module")).casefold().split())
                module_id = f"{self.event_id}-LEGACY-MOD-{marker.get('Day', 1)}-{marker_slug}"
            else:
                module_id = f"{self.event_id}-LEGACY-MOD-{legacy_stage or position}"
        if not activity_id:
            activity_id = f"{self.event_id}-LEGACY-ACT-{legacy_stage or position}"
        content_type = str(
            row.get("ContentType") or details.get("ContentType") or "Standard Activity"
        ).strip()
        module_details = details.get("ModuleDetails", {}) or {}
        if (
            content_type == "Standard Activity"
            and str(module_details.get("ModuleType", "")).casefold() == "experience set"
        ):
            content_type = "Experience Board"
        if content_type not in CONTENT_HANDLERS:
            content_type = "Custom configured content"
        linked_id = str(
            row.get("LinkedContentID") or details.get("LinkedContentID")
            or details.get("LinkedContent") or module_details.get("LinkedExperienceSet")
            or row.get("MissionID") or ""
        ).strip()
        module_order = int(float(row.get("ModuleOrder") or position))
        activity_order = int(float(row.get("ActivityOrder") or row.get("StageNo") or position))
        active = self._active(row)
        superseded = str(row.get("Superseded", "")).strip().casefold() in {"yes", "true", "1"}
        return {
            **deepcopy(row),
            "EventID": self.event_id,
            "ProgrammeID": str(details.get("ProgrammeID") or row.get("ProgrammeID") or self.programme_id),
            "ModuleID": module_id,
            "ActivityID": activity_id,
            "ModuleOrder": module_order,
            "ActivityOrder": activity_order,
            "AdminDisplayName": str(details.get("AdminDisplayName") or row.get("AdminDisplayName") or row.get("StageName") or "Activity"),
            "ParticipantDisplayName": str(details.get("ParticipantDisplayName") or row.get("ParticipantDisplayName") or row.get("StageName") or "Activity"),
            "ActivityType": str(row.get("ActivityType") or marker.get("ActivityType") or friendly_type(row)),
            "ContentType": content_type,
            "LinkedContentID": linked_id,
            "LinkedContentName": str(row.get("LinkedContentName") or details.get("LinkedContentName") or linked_id),
            "LinkedContentHandler": CONTENT_HANDLERS[content_type],
            "Active": active,
            "Superseded": superseded,
            # Breaks remain visible in the authored programme order, but are
            # schedule markers rather than launchable runtime activities.
            "RuntimeEligible": (
                active and not superseded and content_type.casefold() != "break"
            ),
            "StartRule": str(row.get("StartRule") or "Facilitator"),
            "EndRule": str(row.get("EndRule") or "Facilitator"),
            "FacilitatorNotes": str(details.get("FacilitatorInstructions") or row.get("FacilitatorInstruction") or ""),
            "ParticipantNarrative": str(details.get("ParticipantNarrative") or ""),
            "ParticipantTask": str(details.get("ParticipantTask") or row.get("ParticipantMessage") or ""),
            "EvidenceRequirement": str(details.get("EvidenceRequirement") or ""),
            "Legacy": legacy,
            "MissingCanonicalParent": missing_canonical_parent,
            "LegacyStageNo": legacy_stage,
        }

    def snapshot(self):
        activities = [self._canonical_activity(row, i) for i, row in enumerate(self.rows, 1)]
        errors, warnings = [], []
        ids = {}
        for activity in activities:
            for key in ("ActivityID",):
                ids.setdefault((key, activity[key]), []).append(activity)
            if activity["ProgrammeID"] != self.programme_id:
                errors.append(f"Activity {activity['ActivityID']} has missing or foreign parent ProgrammeID.")
            if activity["MissingCanonicalParent"]:
                errors.append(f"Activity {activity['ActivityID']} has no canonical parent ModuleID.")
            if activity["ContentType"] in LINK_REQUIRED and not activity["LinkedContentID"]:
                errors.append(f"Activity {activity['ActivityID']} is missing linked content.")
            linked = self.linked_content.get(activity["LinkedContentID"])
            if activity["LinkedContentID"] and self.linked_content:
                if not linked:
                    errors.append(f"Linked content {activity['LinkedContentID']} does not exist.")
                elif not bool(linked.get("Active", True)):
                    errors.append(f"Linked content {activity['LinkedContentID']} is inactive.")
                elif str(linked.get("ContentType", activity["ContentType"])) != activity["ContentType"]:
                    errors.append(f"Linked content {activity['LinkedContentID']} has an incompatible content type.")
                elif linked.get("EventID") not in (None, "", self.event_id) and not linked.get("Reusable"):
                    errors.append(f"Linked content {activity['LinkedContentID']} belongs to another event.")
        for (kind, stable_id), rows in ids.items():
            if stable_id and len(rows) > 1:
                errors.append(f"Duplicate stable {kind} {stable_id}.")

        active = [row for row in activities if row["Active"] and not row["Superseded"]]
        module_orders, activity_orders = {}, {}
        for row in active:
            module_orders.setdefault(row["ModuleOrder"], set()).add(row["ModuleID"])
            activity_orders.setdefault((row["ModuleID"], row["ActivityOrder"]), []).append(row)
        for order, module_ids in module_orders.items():
            if len(module_ids) > 1:
                errors.append(f"Duplicate active Module order {order}.")
        for (module_id, order), rows in activity_orders.items():
            if len(rows) > 1:
                errors.append(f"Duplicate active Activity order {order} in Module {module_id}.")

        modules_by_id = {}
        for row in sorted(active, key=lambda item: (item["ModuleOrder"], item["ActivityOrder"], item["ActivityID"])):
            module = modules_by_id.setdefault(row["ModuleID"], {
                "EventID": self.event_id,
                "ProgrammeID": self.programme_id,
                "ModuleID": row["ModuleID"],
                "ModuleOrder": row["ModuleOrder"],
                "ModuleName": str(row.get("ModuleName") or (decode_module_stage_type(row) or {}).get("ModuleName") or row["AdminDisplayName"]),
                "AdminDisplayName": str(row.get("ModuleName") or row["AdminDisplayName"]),
                "ParticipantDisplayName": str(row.get("ParticipantModuleName") or row.get("ModuleName") or row["ParticipantDisplayName"]),
                "Status": "Active",
                "Day": int((decode_module_stage_type(row) or {}).get("Day", 1)),
                "StartTime": row.get("StartTime", ""),
                "Activities": [],
            })
            module["Activities"].append(row)
        modules = sorted(modules_by_id.values(), key=lambda row: (row["ModuleOrder"], row["ModuleID"]))
        for module in modules:
            module["ActivityCount"] = len(module["Activities"])
            module["DurationMinutes"] = sum(int(float(row.get("DurationMinutes", 0) or 0)) for row in module["Activities"])

        logical = {}
        for row in activities:
            key = (row["ModuleID"], row["ActivityOrder"])
            logical.setdefault(key, []).append(row)
        duplicates = [rows for rows in logical.values() if len(rows) > 1]
        legacy_rows = [row for row in activities if row["Legacy"]]
        if legacy_rows:
            warnings.append(f"{len(legacy_rows)} legacy row(s) mapped read-only to stable compatibility IDs.")
        audit = {
            "EventID": self.event_id,
            "RowsInspected": len(activities),
            "LegacyRows": len(legacy_rows),
            "DuplicateLogicalActivities": [
                [row["ActivityID"] for row in rows] for rows in duplicates
            ],
            "SupersededRows": [row["ActivityID"] for row in activities if row["Superseded"]],
            "ProposedCanonicalMappings": [{
                "LegacyStageNo": row["LegacyStageNo"],
                "ProgrammeID": row["ProgrammeID"],
                "ModuleID": row["ModuleID"],
                "ActivityID": row["ActivityID"],
                "AutomaticRewrite": False,
            } for row in legacy_rows],
            "ProductionRecordsChanged": False,
        }
        return ProgrammeSnapshot(self.event_id, self.programme_id, modules, errors, warnings, audit)
