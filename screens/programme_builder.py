from pathlib import Path
from datetime import datetime, time
from copy import deepcopy
import html
import json
import uuid

import pandas as pd
import streamlit as st
import yaml

from data.aia_customer_contact import (
    AIA_CUSTOMER_CONTACT_MARKETPLACE,
    AIA_CUSTOMER_CONTACT_MISSION_PLAN,
    AIA_CUSTOMER_CONTACT_STAGES,
    AIA_CUSTOMER_CONTACT_TEAMS,
    install_aia_customer_contact_pack,
    migrate_evt0004_programme_hierarchy,
)
from data.mahb_media_explore import (
    MAHB_MEDIA_EXPLORE_MISSION_PLAN,
    MAHB_MEDIA_EXPLORE_ROUTE,
    MAHB_MEDIA_EXPLORE_STAGES,
    MAHB_MEDIA_EXPLORE_TEAMS,
    install_mahb_media_explore_pack,
)
from data.google_sheets import GoogleSheetsDB
from data.runtime_database import RuntimeDatabaseError
from engines.programme_engine import ProgrammeEngine
from engines.programme_hierarchy import (
    CONTENT_TYPES,
    activity_content_config,
    activity_details,
    build_programme_hierarchy,
    canonical_event_programme,
    encode_activity_details,
    encode_module_stage_type,
    flatten_programme_hierarchy,
    friendly_type,
)
from engines.recommendation_engine import RecommendationEngine
from engines.transformation_engine import TransformationEngine
from screens.app_state import request_navigation, select_active_event
from screens.app_state import ACTIVE_EVENT_KEY
from engines.formula_race_checkpoints import is_formula_race_event, module_templates
from engines.programme_duplication import (
    duplication_summary,
    programme_family,
    saved_state,
    templates_for_event,
)


def get_activity_name(activity):
    activity_data = activity.get("activity", {})
    if isinstance(activity_data, dict):
        return activity_data.get("name", activity.get("name", "Unknown"))
    return activity.get("name", "Unknown")


def load_codeshift_lens():
    file_path = Path("knowledge_base/transformation_frameworks/codeshift.yaml")
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def build_timeline(recommended_names):
    timeline = [
        ("09:00", "Registration"),
        ("09:15", "Opening & Energizer"),
        ("09:30", "Group Formation"),
    ]
    slots = ["10:00", "11:00", "12:00"]
    for index, activity in enumerate(recommended_names[:3]):
        timeline.append((slots[index], activity))
        timeline.append(("After Activity", "Debrief"))
    timeline.append(("End", "Closing & Commitment"))
    return timeline


def render_existing_programme(db, event_id):
    stages = db.get_programme_stages(event_id)
    st.markdown("#### Current Programme Timeline")
    if not stages:
        st.info("No programme has been built for this event yet.")
        return

    columns = [
        "StageNo",
        "StartTime",
        "DurationMinutes",
        "StageName",
        "StageType",
        "MissionID",
        "DisplayMode",
    ]
    st.dataframe(
        [{column: stage.get(column, "") for column in columns} for stage in stages],
        width="stretch",
        hide_index=True,
    )


def _module_settings(mission):
    raw = str((mission or {}).get("Story", "") or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {"Narrative": raw}
    return value if isinstance(value, dict) else {}


def _save_event_module(db, event_id, mission, values, stage):
    settings = _module_settings(mission)
    settings.update({
        "CreditValue": int(values["credit_value"]),
        "DedicatedAIPrompt": values["ai_prompt"],
        "EvidenceRequired": bool(values["evidence_required"]),
        "QRCodeValue": values["qr_value"],
        "CheckpointName": values["checkpoint_name"],
        "CheckpointLocation": values["checkpoint_location"],
        "Latitude": values["latitude"],
        "Longitude": values["longitude"],
        "GeofenceRadius": values["geofence_radius"],
        "MissionVariants": values["variants"],
        "Mandatory": values["mandatory"],
    })
    updated = dict(mission)
    updated.update({
        "EventID": event_id,
        "MissionID": mission.get("MissionID", ""),
        "Title": values["name"],
        "Description": values["participant_instructions"],
        "ParticipantInstructions": values["participant_instructions"],
        "FacilitatorInstructions": values["facilitator_instructions"],
        "Clue": values["rules"],
        "Answer": values["answers"],
        "ScoringRule": values["scoring"],
        "Points": int(values["maximum_score"]),
        "Status": "DRAFT" if values["active"] else "CLOSED",
        "AIHelpEnabled": "Yes" if values["ai_required"] else "No",
        "SubmissionType": values["evidence_type"],
        "DebriefQuestions": values["debrief"],
        "ImageURL": values["image_url"],
        "DocumentURL": values["document_url"],
        "Story": json.dumps(settings, ensure_ascii=False, sort_keys=True),
    })
    db.upsert_event_mission(updated)
    if stage:
        stages = [dict(row) for row in db.get_programme_stages(event_id)]
        for row in stages:
            if str(row.get("StageNo", "")) == str(stage.get("StageNo", "")):
                row.update({
                    "StageName": values["name"],
                    "ParticipantMessage": values["participant_instructions"],
                    "FacilitatorInstruction": values["facilitator_instructions"],
                    "DurationMinutes": int(values["time_limit"]),
                    "IsActive": "Yes" if values["active"] else "No",
                })
        db.save_programme_stages(event_id, stages)


def render_event_module_editor(db):
    events = db.get_events()
    if not events:
        st.warning("Create an event first.")
        return
    event = select_active_event(events, label="Event", key="module_editor_event")
    event_id = str(event.get("EventID", ""))
    missions = db.get_event_missions(event_id, include_closed=True)
    stages = db.get_programme_stages(event_id)
    if not missions:
        st.info("Add modules from the Module Library first.")
        return

    mission_map = {
        str(mission.get("MissionID", "")): mission
        for mission in missions
    }
    options = [
        stage for stage in stages
        if str(stage.get("MissionID", "")) in mission_map
    ]
    if not options:
        st.info("No editable event modules are in the programme.")
        return
    selected_stage_no = st.selectbox(
        "Open module",
        [str(stage.get("StageNo", "")) for stage in options],
        format_func=lambda value: next(
            str(stage.get("StageName", "Module"))
            for stage in options
            if str(stage.get("StageNo", "")) == value
        ),
        key=f"open_module_{event_id}",
    )
    stage = next(
        row for row in options
        if str(row.get("StageNo", "")) == selected_stage_no
    )
    mission = mission_map[str(stage.get("MissionID", ""))]
    settings = _module_settings(mission)
    st.info(
        f"Event copy for {event.get('EventName', '')}. "
        f"Master {mission.get('TemplateID', '—')} remains unchanged."
    )

    with st.form(f"module_form_{event_id}_{stage.get('StageNo', '')}"):
        with st.expander("Basic Details", expanded=True):
            name = st.text_input("Module name", value=str(mission.get("Title", "")))
            mandatory = st.selectbox(
                "Requirement",
                ["Mandatory", "Optional"],
                index=0 if settings.get("Mandatory", "Mandatory") == "Mandatory" else 1,
            )
            active = st.checkbox(
                "Active",
                value=str(mission.get("Status", "DRAFT")).upper() != "CLOSED",
            )
        with st.expander("Instructions", expanded=True):
            participant_instructions = st.text_area(
                "Participant instructions",
                value=str(
                    mission.get("ParticipantInstructions", "")
                    or mission.get("Description", "")
                ),
            )
            facilitator_instructions = st.text_area(
                "Facilitator instructions",
                value=str(mission.get("FacilitatorInstructions", "")),
            )
            rules = st.text_area("Rules", value=str(mission.get("Clue", "")))
        with st.expander("Timing and Scoring"):
            c1, c2, c3 = st.columns(3)
            time_limit = c1.number_input(
                "Time limit (minutes)",
                min_value=1,
                value=max(int(float(stage.get("DurationMinutes", 30) or 30)), 1),
            )
            maximum_score = c2.number_input(
                "Maximum score",
                min_value=0,
                value=int(float(mission.get("Points", 0) or 0)),
            )
            credit_value = c3.number_input(
                "Credit value",
                min_value=0,
                value=int(settings.get("CreditValue", 0) or 0),
            )
            scoring = st.text_area(
                "Scoring method",
                value=str(mission.get("ScoringRule", "")),
            )
        with st.expander("Experiences and Prompts"):
            questions = st.text_area(
                "Questions",
                value=str(mission.get("DebriefQuestions", "")),
            )
            answers = st.text_area(
                "Answers or evaluation notes",
                value=str(mission.get("Answer", "")),
            )
            variants = st.text_area(
                "Experience variants",
                value=str(settings.get("MissionVariants", "")),
            )
            ai_required = st.checkbox(
                "AI required",
                value=str(mission.get("AIHelpEnabled", "No")).lower()
                in {"yes", "true"},
            )
            ai_prompt = st.text_area(
                "Dedicated AI prompt",
                value=str(settings.get("DedicatedAIPrompt", "")),
            )
        with st.expander("Evidence and Media"):
            evidence_type = st.selectbox(
                "Evidence type",
                ["NONE", "PHOTO", "TEXT", "PIPELINE", "HELIUM", "KEYPUNCH", "CATALYST", "NASI"],
                index=(
                    ["NONE", "PHOTO", "TEXT", "PIPELINE", "HELIUM", "KEYPUNCH", "CATALYST", "NASI"].index(
                        str(mission.get("SubmissionType", "NONE")).upper()
                    )
                    if str(mission.get("SubmissionType", "NONE")).upper()
                    in ["NONE", "PHOTO", "TEXT", "PIPELINE", "HELIUM", "KEYPUNCH", "CATALYST", "NASI"]
                    else 0
                ),
            )
            evidence_required = st.checkbox(
                "Evidence required",
                value=bool(settings.get("EvidenceRequired", False)),
            )
            image_url = st.text_input(
                "Image URL",
                value=str(mission.get("ImageURL", "")),
            )
            document_url = st.text_input(
                "Document URL",
                value=str(mission.get("DocumentURL", "")),
            )
        with st.expander("QR and Location"):
            qr_value = st.text_input(
                "QR code value",
                value=str(settings.get("QRCodeValue", "")),
            )
            if qr_value:
                st.code(qr_value, language=None)
                st.caption("Use this value with the event QR generator or printed materials.")
            checkpoint_name = st.text_input(
                "Checkpoint name",
                value=str(settings.get("CheckpointName", "")),
            )
            checkpoint_location = st.text_input(
                "Checkpoint location",
                value=str(settings.get("CheckpointLocation", "")),
            )
            location1, location2, location3 = st.columns(3)
            latitude = location1.number_input(
                "Latitude",
                value=float(settings.get("Latitude", 0) or 0),
                format="%.6f",
            )
            longitude = location2.number_input(
                "Longitude",
                value=float(settings.get("Longitude", 0) or 0),
                format="%.6f",
            )
            geofence_radius = location3.number_input(
                "Geofence radius (m)",
                min_value=0,
                value=int(settings.get("GeofenceRadius", 0) or 0),
            )
        with st.expander("Debrief"):
            debrief = st.text_area(
                "Debrief notes",
                value=str(mission.get("DebriefQuestions", "")),
            )
        submitted = st.form_submit_button(
            "Save Module Changes",
            type="primary",
            width="stretch",
        )

    if submitted:
        _save_event_module(
            db,
            event_id,
            mission,
            {
                "name": name,
                "mandatory": mandatory,
                "active": active,
                "participant_instructions": participant_instructions,
                "facilitator_instructions": facilitator_instructions,
                "rules": rules,
                "time_limit": time_limit,
                "maximum_score": maximum_score,
                "credit_value": credit_value,
                "scoring": scoring,
                "answers": answers,
                "variants": variants,
                "ai_required": ai_required,
                "ai_prompt": ai_prompt,
                "evidence_type": evidence_type,
                "evidence_required": evidence_required,
                "image_url": image_url,
                "document_url": document_url,
                "qr_value": qr_value,
                "checkpoint_name": checkpoint_name,
                "checkpoint_location": checkpoint_location,
                "latitude": latitude,
                "longitude": longitude,
                "geofence_radius": geofence_radius,
                "debrief": debrief or questions,
            },
            stage,
        )
        st.success("Event module saved. The master template was not changed.")
        st.rerun()


def render_programme_order(db):
    events = db.get_events()
    if not events:
        return
    event = select_active_event(events, label="Event", key="programme_order_event")
    event_id = str(event.get("EventID", ""))
    stages = db.get_programme_stages(event_id)
    if not stages:
        st.info("Add modules before arranging the programme.")
        return
    for index, stage in enumerate(stages):
        with st.container(border=True):
            info, up, down, remove = st.columns([6, 1, 1, 1])
            info.markdown(
                f"**{index + 1}. {stage.get('StageName', '')}**  \n"
                f"{stage.get('DurationMinutes', '—')} min"
            )
            if up.button("↑", disabled=index == 0, key=f"up_{event_id}_{index}"):
                reordered = [dict(row) for row in stages]
                reordered[index - 1], reordered[index] = reordered[index], reordered[index - 1]
                for position, row in enumerate(reordered, start=1):
                    row["StageNo"] = position
                db.save_programme_stages(event_id, reordered)
                st.rerun()
            if down.button("↓", disabled=index == len(stages) - 1, key=f"down_{event_id}_{index}"):
                reordered = [dict(row) for row in stages]
                reordered[index + 1], reordered[index] = reordered[index], reordered[index + 1]
                for position, row in enumerate(reordered, start=1):
                    row["StageNo"] = position
                db.save_programme_stages(event_id, reordered)
                st.rerun()
            if remove.button("Remove", key=f"remove_{event_id}_{index}"):
                remaining = [dict(row) for row in stages if row is not stage]
                for position, row in enumerate(remaining, start=1):
                    row["StageNo"] = position
                db.save_programme_stages(event_id, remaining)
                mission_id = str(stage.get("MissionID", ""))
                if mission_id:
                    mission = db.get_mission(event_id, mission_id)
                    if mission:
                        archived = dict(mission)
                        archived["Status"] = "CLOSED"
                        db.upsert_event_mission(archived)
                st.success("Module removed from this event.")
                st.rerun()


def _save_modules(db, event_id, modules):
    if str(event_id).upper() == "EVT-0004" and any(
        module.get("ProjectionOnly") for module in modules
    ):
        st.session_state[f"canonical_programme_preview_{event_id}"] = deepcopy(modules)
        return
    db.save_programme_stages(event_id, flatten_programme_hierarchy(modules))
    st.session_state[f"programme_save_state_{event_id}"] = saved_state()


def _content_choices(db, event_id, content_type, current_id="", current_name=""):
    choices = [("", "None")]
    if content_type == "Experience Board":
        choices.extend((value, value) for value in db.get_experience_sets(event_id))
        if str(event_id).upper() == "EVT-0004":
            choices = [
                (identifier, (
                    "EVT-0004 Bayu Beach Labyrinth"
                    if identifier == "Operation: The Labyrinth" else label
                ))
                for identifier, label in choices
            ]
    elif content_type == "Sync AI" and db.get_mission(event_id, "S01"):
        choices.append(("S01", "existing EVT-0004 Sync AI configuration"))
    elif content_type == "Catalyst" and db.get_mission(event_id, "C01"):
        choices.append(("C01", "existing EVT-0004 Catalyst configuration"))
    if current_id and current_id not in {item[0] for item in choices}:
        choices.append((current_id, current_name or current_id))
    return choices


def _add_activity(db, event_id, modules, module, name, minutes):
    """Append and persist one activity through the existing stage storage."""
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Activity Name is required.")
    for existing in module["Activities"]:
        existing["StageType"] = encode_module_stage_type(
            module["ModuleName"],
            module["Day"],
            friendly_type(existing),
        )
    activity = _new_activity(
        module["ModuleName"],
        module["Day"],
        clean_name,
        len(module["Activities"]) + 1,
    )
    activity["DurationMinutes"] = int(minutes)
    module["Activities"].append(activity)
    _save_modules(db, event_id, modules)
    return activity


DEFAULT_MODULES = [
    (1, "Arrival & Registration", ["Arrival & Registration"]),
    (1, "Energiser", ["Energiser"]),
    (1, "Launch EXOS", ["Launch EXOS"]),
    (1, "Bridge of Trust", ["Bridge of Trust"]),
    (1, "Mission AI", ["Briefing", "Mission Board", "Missions", "Debrief"]),
    (1, "Lunch", ["Lunch"]),
    (1, "Sync AI", ["Briefing", "Marketplace", "Team Planning", "AI Creation", "Rehearsal", "Performance", "Judging"]),
    (1, "Closing", ["Closing"]),
    (2, "Catalyst Challenge", ["Briefing", "Build", "Run", "Debrief"]),
    (2, "Debrief", ["Debrief"]),
    (2, "Programme Closing", ["Programme Closing"]),
]


def _new_activity(module_name, day, name, order):
    activity_type = {
        "Briefing": "Briefing", "Mission Board": "Activity",
        "Missions": "Mission", "Marketplace": "Marketplace",
        "Team Planning": "Preparation", "AI Creation": "Preparation",
        "Rehearsal": "Preparation", "Performance": "Performance",
        "Judging": "Judging", "Build": "Preparation", "Run": "Performance",
        "Debrief": "Debrief", "Lunch": "Lunch / Break",
        "Closing": "Closing", "Programme Closing": "Closing",
        "Arrival & Registration": "Registration", "Energiser": "Energiser",
    }.get(name, "Activity")
    return {
        "StageNo": order,
        "StartTime": "09:00",
        "DurationMinutes": 15,
        "StageName": name,
        "StageType": encode_module_stage_type(module_name, day, activity_type),
        "MissionID": "",
        "DisplayMode": "Collaboration",
        "ParticipantMessage": "",
        "FacilitatorInstruction": encode_activity_details({
            "FacilitatorInstructions": "", "Questions": "", "Credits": 0,
            "Rules": "", "Objectives": "", "Scoring": "",
            "EvidenceRequired": False, "ModuleDetails": {},
        }),
        "IsActive": "Yes",
    }


def render_race_checkpoint_editor(db, event_id, module):
    """Event-owned four-checkpoint editor; definitions are never hard-coded."""
    runtime = db.runtime
    module_id = str(module.get("ModuleID") or f"{event_id}-RACE-CHECKPOINTS")
    try:
        state = runtime.get_formula_race_checkpoints(event_id)
    except RuntimeDatabaseError as error:
        st.error(str(error)); return
    source = list(state.get("Checkpoints", []))
    state_key = f"race_checkpoint_editor_{event_id}_{module_id}"
    if state_key not in st.session_state:
        st.session_state[state_key] = source
    rows = st.session_state[state_key]
    st.markdown("### RACE Checkpoints")
    st.caption("Four checkpoint activities launch concurrently. Names, proof rules and Credits belong to this event configuration.")
    if len([row for row in rows if row.get("Active", True)]) > 4:
        st.error("Maximum four active RACE checkpoints.")
    for index, row in enumerate(list(rows)):
        with st.container(border=True):
            st.markdown(f"**{index + 1}. {row.get('Name') or 'Untitled checkpoint'}**")
            name = st.text_input("Name", value=str(row.get("Name", "")), key=f"race_cp_name_{event_id}_{index}")
            instructions = st.text_area("Instructions", value=str(row.get("Instructions", "")), key=f"race_cp_instructions_{event_id}_{index}")
            credits_col, proof_col, active_col = st.columns([1, 2, 1])
            credits = credits_col.number_input("Credits available", min_value=0, value=int(float(row.get("Credits", 0) or 0)), key=f"race_cp_credits_{event_id}_{index}")
            proof_types = ["Photo", "Text", "Photo + Text"]
            current_proof = str(row.get("ProofType", "Photo"))
            proof = proof_col.selectbox("Proof type", proof_types, index=proof_types.index(current_proof) if current_proof in proof_types else 0, key=f"race_cp_proof_{event_id}_{index}")
            active = active_col.checkbox("Active", value=bool(row.get("Active", True)), key=f"race_cp_active_{event_id}_{index}")
            notes = st.text_area("Facilitator notes (optional)", value=str(row.get("FacilitatorNotes", "")), key=f"race_cp_notes_{event_id}_{index}")
            row.update({"Name": name, "Instructions": instructions, "Credits": int(credits), "ProofType": proof,
                        "FacilitatorNotes": notes, "Active": active, "Position": index + 1,
                        "ModuleID": module_id, "EventID": event_id})
            up, down, delete = st.columns(3)
            if up.button("Move Up", disabled=index == 0, key=f"race_cp_up_{event_id}_{index}"):
                rows[index - 1], rows[index] = rows[index], rows[index - 1]; st.rerun()
            if down.button("Move Down", disabled=index == len(rows) - 1, key=f"race_cp_down_{event_id}_{index}"):
                rows[index + 1], rows[index] = rows[index], rows[index + 1]; st.rerun()
            if delete.button("Delete", key=f"race_cp_delete_{event_id}_{index}"):
                rows.pop(index); st.rerun()
    add, save = st.columns(2)
    if add.button("＋ Add Checkpoint", disabled=len(rows) >= 4, key=f"race_cp_add_{event_id}"):
        rows.append({"EventID": event_id, "ModuleID": module_id,
                     "ActivityID": f"{event_id}-RACE-CP-{uuid.uuid4().hex[:8].upper()}",
                     "Name": "", "Instructions": "", "Credits": 0, "ProofType": "Photo",
                     "FacilitatorNotes": "", "Position": len(rows) + 1, "Active": True})
        st.rerun()
    if save.button("Save RACE Checkpoints", type="primary", key=f"race_cp_save_{event_id}"):
        if len(rows) != 4 or len([row for row in rows if row.get("Active")]) != 4:
            st.error("EVT-0006 requires exactly four configured active checkpoints.")
        elif any(not str(row.get("Name", "")).strip() for row in rows):
            st.error("Every checkpoint requires a name.")
        else:
            try:
                runtime.save_formula_race_checkpoints(event_id, module_id, rows)
                st.success("Four concurrent RACE checkpoints saved.")
            except RuntimeDatabaseError as error: st.error(str(error))


def render_programme_first_builder(db):
    """PowerPoint-like programme editor backed by existing stage storage."""
    events = db.get_events()
    if not events:
        st.warning("Create an event first.")
        return
    event = select_active_event(events, label="Event", key="programme_first_event")
    event_id = str(event.get("EventID", ""))
    available_modules = templates_for_event(
        event, DEFAULT_MODULES, module_templates(event),
    )
    modules = st.session_state.get(f"canonical_programme_preview_{event_id}")
    if not modules:
        modules = canonical_event_programme(
            db.get_programme_stages(event_id), event_id,
        )
    if is_formula_race_event(event) and not any(
        str(module.get("ModuleName", "")).casefold() == "race checkpoints"
        for module in modules
    ):
        # EVT-0006 previously stored legacy Mission AI stage rows. The R.A.C.E.
        # programme projection is product-owned; checkpoint content stays in the
        # editable canonical checkpoint table rather than being hard-coded here.
        modules = []
        for module_order, (day, name, activity_names) in enumerate(available_modules, 1):
            activities = [_new_activity(name, day, activity_name, activity_order)
                          for activity_order, activity_name in enumerate(activity_names, 1)]
            module_id = f"{event_id}-RACE-CHECKPOINTS" if name == "RACE Checkpoints" else f"{event_id}-RACE-MOD-{module_order:02d}"
            for activity_order, activity in enumerate(activities, 1):
                activity["ProgrammeID"] = f"{event_id}-PROGRAMME"
                activity["ModuleID"] = module_id
                activity["ActivityID"] = f"{module_id}-ACT-{activity_order:02d}"
            modules.append({"EventID": event_id, "ProgrammeID": f"{event_id}-PROGRAMME",
                "ModuleID": module_id, "ModuleName": name, "Day": day,
                "ModuleOrder": module_order, "Activities": activities,
                "ActivityCount": len(activities),
                "DurationMinutes": sum(int(row.get("DurationMinutes", 0)) for row in activities),
                "StartTime": activities[0].get("StartTime", "") if activities else ""})
    st.caption("Arrange the programme like slides. Open a module to edit everything inside it.")
    state = st.session_state.get(f"programme_save_state_{event_id}")
    if state:
        timestamp = datetime.fromisoformat(state["Timestamp"]).astimezone().strftime("%d %b %Y · %H:%M:%S")
        st.success(f"SAVED · {timestamp}")
    else:
        st.caption("SAVED · loaded from persisted configuration")

    with st.expander("Duplicate Existing Programme", expanded=True):
        family = programme_family(event)
        candidates = []
        for candidate in events:
            candidate_id = str(candidate.get("EventID", ""))
            candidate_stages = db.get_programme_stages(candidate_id)
            if candidate_id != event_id and candidate_stages:
                candidates.append((candidate, candidate_stages))
        candidates.sort(
            key=lambda item: (programme_family(item[0]) == family, str(item[0].get("EventDate", ""))),
            reverse=True,
        )
        if not candidates:
            st.info("No existing configured programme is available to duplicate.")
        else:
            source_id = st.selectbox(
                "Source programme",
                [str(item[0].get("EventID", "")) for item in candidates],
                format_func=lambda value: next(
                    f"{value} · {item[0].get('EventName', '')} · {item[0].get('ProgrammeType', 'Generic')}"
                    for item in candidates if str(item[0].get("EventID", "")) == value
                ),
                key=f"duplicate_source_{event_id}",
            )
            source_stages = next(rows for item, rows in candidates if str(item.get("EventID", "")) == source_id)
            summary = duplication_summary(source_stages)
            st.write(f"{summary['ModuleCount']} modules · {summary['ActivityCount']} activities")
            st.caption("Modules: " + ", ".join(summary["Modules"]))
            confirmation = st.selectbox(
                "Safety confirmation",
                [
                    "Not confirmed",
                    "Confirmed — duplicate configuration now",
                ],
                key=f"duplicate_confirm_{event_id}",
            )
            confirmed = confirmation.startswith("Confirmed")
            st.caption(
                "No participants, teams, submissions, scores, wallets, transactions, "
                "judging, results, sessions, or runtime state will be copied."
            )
            applied_key = f"programme_duplication_applied_{event_id}"
            if not confirmed:
                st.session_state[applied_key] = False
            elif not st.session_state.get(applied_key, False):
                result = db.duplicate_programme_configuration(source_id, event_id)
                st.session_state[f"programme_save_state_{event_id}"] = saved_state()
                st.session_state[f"programme_notice_{event_id}"] = (
                    f"Duplicated {result['ModuleCount']} modules and {result['ActivityCount']} activities from {source_id}. Programme remains unlaunched."
                )
                st.session_state[applied_key] = True
                st.rerun()
    from engines.programme_adapter import CanonicalProgrammeAdapter
    validation = CanonicalProgrammeAdapter(event_id, db.get_programme_stages(event_id)).snapshot()
    if validation.errors:
        st.error("Programme hierarchy validation failed.")
        for error in validation.errors:
            st.warning(error)

    selected_module_labels = [
        f"{position}. {module['ModuleName']}"
        for position, module in enumerate(modules, start=1)
    ]
    add_left, position_col, selected_col = st.columns([2, 1, 2])
    module_choice = add_left.selectbox(
        "Add module",
        [f"DAY {day} — {name}" for day, name, _ in available_modules] + ["Custom module"],
        label_visibility="collapsed",
        key=f"add_module_choice_{event_id}",
    )
    insert_position = position_col.selectbox(
        "Insert Position",
        ["At the beginning", "Before selected module", "After selected module", "At the end"],
        index=2,
        key=f"insert_position_{event_id}",
    )
    selected_insert_module = selected_col.selectbox(
        "Selected module",
        selected_module_labels or ["No modules yet"],
        disabled=not modules,
        key=f"insert_selected_module_{event_id}",
    )
    add_button_col, defaults_col = st.columns([1, 1])
    if add_button_col.button("＋ Add Module", type="primary", width="stretch"):
        if module_choice == "Custom module":
            day, name, activities = 1, "New Module", ["New Activity"]
        else:
            selected = available_modules[
                [f"DAY {day} — {name}" for day, name, _ in available_modules].index(module_choice)
            ]
            day, name, activities = selected
        module = {
            "ModuleID": f"new-{len(modules)}-{name}",
            "ModuleName": name,
            "Day": day,
            "Activities": [
                _new_activity(name, day, activity, len(modules) + position)
                for position, activity in enumerate(activities, start=1)
            ],
        }
        if not modules or insert_position == "At the end":
            insert_at = len(modules)
        elif insert_position == "At the beginning":
            insert_at = 0
        else:
            selected_index = selected_module_labels.index(selected_insert_module)
            insert_at = selected_index + (
                1 if insert_position == "After selected module" else 0
            )
        modules.insert(insert_at, module)
        _save_modules(db, event_id, modules)
        st.session_state[f"programme_notice_{event_id}"] = (
            f"{name} added at position {insert_at + 1}"
        )
        st.rerun()
    if defaults_col.button("Add Default Programme", width="stretch"):
        existing_names = {module["ModuleName"].casefold() for module in modules}
        for default_day, default_name, default_activities in available_modules:
            if default_name.casefold() in existing_names:
                continue
            modules.append({
                "ModuleID": f"default-{default_day}-{default_name}",
                "ModuleName": default_name,
                "Day": default_day,
                "Activities": [
                    _new_activity(default_name, default_day, activity, position)
                    for position, activity in enumerate(default_activities, start=1)
                ],
            })
        _save_modules(db, event_id, modules)
        st.session_state[f"programme_notice_{event_id}"] = "Default programme added"
        st.rerun()
    notice = st.session_state.pop(f"programme_notice_{event_id}", "")
    if notice:
        st.success(notice)

    if not modules:
        st.info("This event has no programme yet.")
        st.caption("Use Template · Duplicate Existing Programme · Build From Scratch")
        return

    days = sorted({int(module.get("Day", 1)) for module in modules})
    for day in days:
        st.markdown(f"### DAY {day}")
        day_modules = [
            (index, module)
            for index, module in enumerate(modules)
            if int(module.get("Day", 1)) == day
        ]
        for index, module in day_modules:
            st.markdown(
                f"""
                <div style="
                    border:1px solid rgba(8,45,88,.16);
                    border-left:7px solid #B59A37;
                    border-radius:16px;
                    padding:22px 24px 18px;
                    margin:18px 0 8px;
                    background:#FFFFFF;
                    box-shadow:0 10px 28px rgba(8,45,88,.06);
                ">
                  <div style="font-size:.76rem;font-weight:800;letter-spacing:.15em;
                              color:#B59A37;text-transform:uppercase;">
                    Module {index + 1} · {html.escape(str(module.get("StartTime", "—")))}
                  </div>
                  <div style="font-size:1.65rem;font-weight:800;color:#082D58;
                              margin:.35rem 0 .65rem;line-height:1.1;">
                    {html.escape(str(module["ModuleName"]))}
                  </div>
                  <div style="display:flex;gap:28px;color:#082D58;font-size:1rem;">
                    <span><strong>{module["DurationMinutes"]}</strong> minutes</span>
                    <span><strong>{module["ActivityCount"]}</strong> activities</span>
                    <span><strong>Day {module["Day"]}</strong></span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            move_to_col, move_action_col, up_col, down_col, remove_col = st.columns([2, 1, 1, 1, 1])
            move_target = move_to_col.selectbox(
                "Move To Position",
                list(range(1, len(modules) + 1)),
                index=index,
                key=f"module_move_target_{event_id}_{index}",
            )
            if move_action_col.button("Move", key=f"module_move_direct_{event_id}_{index}"):
                moved = modules.pop(index)
                modules.insert(int(move_target) - 1, moved)
                _save_modules(db, event_id, modules)
                st.session_state[f"programme_notice_{event_id}"] = (
                    f"{moved['ModuleName']} moved to position {move_target}"
                )
                st.rerun()
            if up_col.button("↑ Move", disabled=index == 0, key=f"mod_up_{event_id}_{index}"):
                modules[index - 1], modules[index] = modules[index], modules[index - 1]
                _save_modules(db, event_id, modules)
                st.rerun()
            if down_col.button("↓ Move", disabled=index == len(modules) - 1, key=f"mod_down_{event_id}_{index}"):
                modules[index + 1], modules[index] = modules[index], modules[index + 1]
                _save_modules(db, event_id, modules)
                st.rerun()
            if remove_col.button("Delete", key=f"mod_remove_{event_id}_{index}"):
                modules.pop(index)
                _save_modules(db, event_id, modules)
                st.rerun()

            notice_key = f"activity_added_notice_{event_id}"
            activity_added = (
                st.session_state.get(notice_key) == module["ModuleName"]
            )
            with st.expander(
                "Edit · Expand module",
                expanded=activity_added,
            ):
                if activity_added:
                    st.success("Activity added successfully")
                    st.session_state.pop(notice_key, None)
                first_activity = module["Activities"][0]
                first_details = activity_details(first_activity)
                module_details = first_details.get("ModuleDetails", {})
                name_col, day_col, start_col = st.columns([3, 1, 1])
                edited_name = name_col.text_input(
                    "Module Name", value=module["ModuleName"],
                    key=f"module_name_{event_id}_{index}",
                )
                edited_day = day_col.number_input(
                    "Day", min_value=1, max_value=9, value=int(module["Day"]),
                    key=f"module_day_{event_id}_{index}",
                )
                edited_start = start_col.text_input(
                    "Start Time", value=str(module.get("StartTime", "")),
                    key=f"module_start_{event_id}_{index}",
                )
                duration_col, active_col = st.columns([1, 1])
                edited_duration = duration_col.number_input(
                    "Duration", min_value=1,
                    value=int(module.get("DurationMinutes", 15) or 15),
                    key=f"module_duration_{event_id}_{index}",
                )
                module_status = active_col.selectbox(
                    "Status", ["Active", "Inactive"],
                    index=(
                        0 if str(first_activity.get("IsActive", "Yes")).casefold()
                        != "no" else 1
                    ),
                    key=f"module_status_{event_id}_{index}",
                )
                module_participant_title = st.text_input(
                    "Participant Title",
                    value=str(
                        module_details.get("ParticipantTitle", "")
                        or module.get("ParticipantTitle", module["ModuleName"])
                    ),
                    key=f"module_participant_title_{event_id}_{index}",
                )
                module_participant_narrative = st.text_area(
                    "Participant Narrative",
                    value=str(
                        module_details.get("ParticipantNarrative", "")
                        or module.get("ParticipantNarrative", "")
                    ),
                    key=f"module_participant_narrative_{event_id}_{index}",
                )
                module_facilitator = st.text_area(
                    "Facilitator Notes",
                    value=str(module_details.get(
                        "FacilitatorInstructions",
                        first_details["FacilitatorInstructions"],
                    )),
                    key=f"module_facilitator_{event_id}_{index}",
                )
                module_content = activity_content_config(first_activity, module)
                module_content_type = st.selectbox(
                    "Content Type", list(CONTENT_TYPES),
                    index=list(CONTENT_TYPES).index(module_content["ContentType"]),
                    key=f"module_content_type_{event_id}_{index}",
                )
                module_choices = _content_choices(
                    db, event_id, module_content_type,
                    module_content["LinkedContentID"],
                    module_content["LinkedContentName"],
                )
                module_choice_ids = [item[0] for item in module_choices]
                module_linked_content = st.selectbox(
                    "Linked Content", module_choice_ids,
                    index=(
                        module_choice_ids.index(module_content["LinkedContentID"])
                        if module_content["LinkedContentID"] in module_choice_ids else 0
                    ),
                    format_func=lambda value: next(
                        label for identifier, label in module_choices
                        if identifier == value
                    ),
                    disabled=len(module_choices) == 1,
                    key=f"module_linked_content_{event_id}_{index}",
                )
                module_rules = st.text_area(
                    "Rules", value=str(module_details.get("Rules", "")),
                    key=f"module_rules_{event_id}_{index}",
                )
                module_objectives = st.text_area(
                    "Objectives", value=str(module_details.get("Objectives", "")),
                    key=f"module_objectives_{event_id}_{index}",
                )
                credits_col, scoring_col = st.columns([1, 3])
                module_credits = credits_col.number_input(
                    "Credits", min_value=0,
                    value=int(module_details.get("Credits", 0) or 0),
                    key=f"module_credits_{event_id}_{index}",
                )
                module_scoring = scoring_col.text_area(
                    "Scoring", value=str(module_details.get("Scoring", "")),
                    key=f"module_scoring_{event_id}_{index}",
                )
                save_module_col, cancel_module_col = st.columns([3, 1])
                if save_module_col.button("Save Module", type="primary", key=f"mod_save_{event_id}_{index}"):
                    if module_content_type in {"Experience Board", "Sync AI", "Catalyst"} and not module_linked_content:
                        st.error("Select the event content this module launches.")
                        st.stop()
                    module["ModuleName"] = edited_name.strip() or "Untitled Module"
                    module["AdminDisplayName"] = module["ModuleName"]
                    module["ParticipantTitle"] = (
                        module_participant_title.strip() or module["ModuleName"]
                    )
                    module["ParticipantNarrative"] = module_participant_narrative
                    module["Day"] = int(edited_day)
                    remaining_minutes = sum(
                        int(float(row.get("DurationMinutes", 0) or 0))
                        for row in module["Activities"][1:]
                    )
                    for activity_position, activity in enumerate(module["Activities"]):
                        if activity_position == 0:
                            activity["StartTime"] = edited_start
                            activity["DurationMinutes"] = max(
                                int(edited_duration) - remaining_minutes, 1
                            )
                        activity["StageType"] = encode_module_stage_type(
                            module["ModuleName"], module["Day"], friendly_type(activity)
                        )
                        activity["IsActive"] = "Yes" if module_status == "Active" else "No"
                    first_activity["AdminDisplayName"] = module["ModuleName"]
                    first_activity["ParticipantDisplayName"] = module["ParticipantTitle"]
                    selected_module_label = next(
                        label for identifier, label in module_choices
                        if identifier == module_linked_content
                    )
                    first_activity["FacilitatorInstruction"] = encode_activity_details({
                        **first_details,
                        "AdminDisplayName": module["ModuleName"],
                        "ParticipantDisplayName": module["ParticipantTitle"],
                        "ContentType": module_content_type,
                        "LinkedContent": module_linked_content,
                        "LinkedContentID": module_linked_content,
                        "LinkedContentName": selected_module_label,
                        "ModuleDetails": {
                            "ParticipantTitle": module["ParticipantTitle"],
                            "ParticipantNarrative": module_participant_narrative,
                            "FacilitatorInstructions": module_facilitator,
                            "Rules": module_rules,
                            "Objectives": module_objectives,
                            "Credits": int(module_credits),
                            "Scoring": module_scoring,
                            "ModuleType": (
                                "Experience Set"
                                if module_content_type == "Experience Board"
                                else "Standard"
                            ),
                            "LinkedExperienceSet": (
                                module_linked_content
                                if module_content_type == "Experience Board" else ""
                            ),
                        },
                    })
                    _save_modules(db, event_id, modules)
                    st.session_state[f"programme_notice_{event_id}"] = "Module saved"
                    st.rerun()
                if cancel_module_col.button("Cancel", key=f"mod_cancel_{event_id}_{index}"):
                    st.rerun()
                st.markdown("#### Activities")
                rows = [{
                    "Order": position,
                    "Name": item.get("StageName", ""),
                    "Start": item.get("StartTime", ""),
                    "Minutes": int(float(item.get("DurationMinutes", 0) or 0)),
                    "Active": str(item.get("IsActive", "Yes")).casefold() != "no",
                } for position, item in enumerate(module["Activities"], start=1)]
                edited = st.data_editor(
                    pd.DataFrame(rows),
                    width="stretch",
                    hide_index=True,
                    num_rows="dynamic",
                    key=f"activities_{event_id}_{module['ModuleID']}",
                    column_config={
                        "Order": st.column_config.NumberColumn(min_value=1, step=1),
                        "Minutes": st.column_config.NumberColumn(min_value=0, step=5),
                        "Active": st.column_config.CheckboxColumn(),
                    },
                )
                if st.button(
                    "Save Internal Flow",
                    type="primary",
                    key=f"save_flow_{event_id}_{module['ModuleID']}",
                ):
                    existing = module["Activities"]
                    revised = []
                    for row in edited.sort_values("Order").to_dict("records"):
                        match = next(
                            (
                                item for item in existing
                                if str(item.get("StageName", "")) == str(row["Name"])
                            ),
                            {},
                        )
                        if not match:
                            match = _new_activity(
                                module["ModuleName"], module["Day"], str(row["Name"]), 1
                            )
                        item = dict(match)
                        item.update({
                            "StageName": str(row["Name"]),
                            "StartTime": str(row["Start"]),
                            "DurationMinutes": int(row["Minutes"]),
                            "IsActive": "Yes" if row["Active"] else "No",
                        })
                        revised.append(item)
                    module["Activities"] = revised
                    _save_modules(db, event_id, modules)
                    st.success("Internal flow saved to this event copy.")
                    st.rerun()

                with st.form(
                    f"add_activity_form_{event_id}_{module['ModuleID']}",
                    clear_on_submit=True,
                    border=True,
                ):
                    add_name, add_minutes = st.columns([3, 1])
                    new_name = add_name.text_input(
                        "Activity Name",
                        placeholder="Enter activity name",
                    )
                    new_minutes = add_minutes.number_input(
                        "Minutes",
                        min_value=1,
                        value=15,
                    )
                    add_submitted = st.form_submit_button(
                        "＋ Add Activity",
                        type="primary",
                        width="stretch",
                    )
                    if add_submitted:
                        if not new_name.strip():
                            st.error(
                                "Activity Name is required. Enter a name before adding."
                            )
                        else:
                            _add_activity(
                                db,
                                event_id,
                                modules,
                                module,
                                new_name,
                                new_minutes,
                            )
                            st.session_state[notice_key] = module["ModuleName"]
                            st.rerun()

                activity_names = [
                    f"{position}. {item.get('StageName', 'Activity')}"
                    for position, item in enumerate(module["Activities"], start=1)
                ]
                selected_label = st.selectbox(
                    "Edit activity", activity_names,
                    key=f"edit_activity_select_{event_id}_{index}",
                )
                selected_position = activity_names.index(selected_label)
                selected_activity = module["Activities"][selected_position]
                details = activity_details(selected_activity)
                with st.container(border=True):
                    activity_name_col, activity_start_col, activity_duration_col = st.columns([3, 1, 1])
                    activity_name = activity_name_col.text_input(
                        "Activity Name",
                        value=str(selected_activity.get("StageName", "")),
                        key=f"activity_name_{event_id}_{index}_{selected_position}",
                    )
                    activity_start = activity_start_col.text_input(
                        "Start Time",
                        value=str(selected_activity.get("StartTime", "")),
                        key=f"activity_start_{event_id}_{index}_{selected_position}",
                    )
                    activity_duration = activity_duration_col.number_input(
                        "Duration",
                        min_value=1,
                        value=max(int(float(selected_activity.get("DurationMinutes", 15) or 15)), 1),
                        key=f"activity_duration_{event_id}_{index}_{selected_position}",
                    )
                    active_activity, evidence_required = st.columns(2)
                    activity_status = active_activity.selectbox(
                        "Status", ["Active", "Inactive"],
                        index=(
                            0 if str(selected_activity.get("IsActive", "Yes")).casefold()
                            != "no" else 1
                        ),
                        key=f"activity_status_{event_id}_{index}_{selected_position}",
                    )
                    activity_evidence = evidence_required.checkbox(
                        "Evidence required",
                        value=details["EvidenceRequired"],
                        key=f"activity_evidence_{event_id}_{index}_{selected_position}",
                    )
                    content_config = activity_content_config(
                        selected_activity, module,
                    )
                    content_type = st.selectbox(
                        "Content Type",
                        list(CONTENT_TYPES),
                        index=list(CONTENT_TYPES).index(
                            content_config["ContentType"]
                        ),
                        key=f"content_type_{event_id}_{index}_{selected_position}",
                    )
                    content_choices = _content_choices(
                        db, event_id, content_type,
                        content_config["LinkedContentID"],
                        content_config["LinkedContentName"],
                    )
                    linked_options = [item[0] for item in content_choices]
                    linked_content = st.selectbox(
                        "Linked Content",
                        linked_options,
                        index=(
                            linked_options.index(content_config["LinkedContentID"])
                            if content_config["LinkedContentID"] in linked_options else 0
                        ),
                        format_func=lambda value: next(
                            label for identifier, label in content_choices
                            if identifier == value
                        ),
                        disabled=len(content_choices) == 1,
                        key=f"linked_content_{event_id}_{index}_{selected_position}",
                    )
                    participant_narrative = st.text_area(
                        "Participant Narrative",
                        value=details["ParticipantNarrative"],
                        key=f"participant_narrative_{event_id}_{index}_{selected_position}",
                    )
                    participant_task = st.text_area(
                        "Participant Task",
                        value=details["ParticipantTask"],
                        key=f"participant_task_{event_id}_{index}_{selected_position}",
                    )
                    evidence_requirement = st.text_area(
                        "Evidence Requirement",
                        value=details["EvidenceRequirement"],
                        disabled=not activity_evidence,
                        key=f"evidence_requirement_{event_id}_{index}_{selected_position}",
                    )
                    facilitator_instructions = st.text_area(
                        "Facilitator Notes",
                        value=details["FacilitatorInstructions"],
                        key=f"facilitator_instructions_{event_id}_{index}_{selected_position}",
                    )
                    questions = st.text_area(
                        "Questions", value=details["Questions"],
                        key=f"questions_{event_id}_{index}_{selected_position}",
                    )
                    rules = st.text_area(
                        "Rules", value=details["Rules"],
                        key=f"rules_{event_id}_{index}_{selected_position}",
                    )
                    credits = st.number_input(
                        "Credits", min_value=0, value=details["Credits"],
                        key=f"credits_{event_id}_{index}_{selected_position}",
                    )
                    activity_move_col, activity_move_action = st.columns([3, 1])
                    activity_target = activity_move_col.selectbox(
                        "Move To Position",
                        list(range(1, len(module["Activities"]) + 1)),
                        index=selected_position,
                        key=f"activity_move_target_{event_id}_{index}_{selected_position}",
                    )
                    if activity_move_action.button(
                        "Move Activity",
                        key=f"activity_move_{event_id}_{index}_{selected_position}",
                    ):
                        moved_activity = module["Activities"].pop(selected_position)
                        module["Activities"].insert(int(activity_target) - 1, moved_activity)
                        _save_modules(db, event_id, modules)
                        st.session_state[f"programme_notice_{event_id}"] = (
                            f"{moved_activity.get('StageName', 'Activity')} moved"
                        )
                        st.rerun()
                    save_activity, delete_activity = st.columns([3, 1])
                    if save_activity.button(
                        "Save Activity", type="primary",
                        key=f"save_activity_details_{event_id}_{index}_{selected_position}",
                    ):
                        selected_activity["StageName"] = activity_name.strip() or "Untitled Activity"
                        selected_activity["StartTime"] = activity_start
                        selected_activity["DurationMinutes"] = int(activity_duration)
                        selected_activity["IsActive"] = (
                            "Yes" if activity_status == "Active" else "No"
                        )
                        selected_activity["ParticipantMessage"] = participant_task
                        selected_activity["FacilitatorInstruction"] = encode_activity_details({
                            "FacilitatorInstructions": facilitator_instructions,
                            "ParticipantNarrative": participant_narrative,
                            "ParticipantTask": participant_task,
                            "EvidenceRequirement": (
                                evidence_requirement if activity_evidence else ""
                            ),
                            "ContentType": content_type,
                            "LinkedContent": linked_content,
                            "LinkedContentID": linked_content,
                            "LinkedContentName": next(
                                label for identifier, label in content_choices
                                if identifier == linked_content
                            ),
                            "ActivityID": selected_activity.get("ActivityID", ""),
                            "ModuleID": module.get("ModuleID", ""),
                            "AdminDisplayName": activity_name.strip() or "Untitled Activity",
                            "ParticipantDisplayName": (
                                details.get("ParticipantDisplayName", "")
                                or activity_name.strip() or "Untitled Activity"
                            ),
                            "Questions": questions,
                            "Credits": int(credits),
                            "Rules": rules,
                            "Objectives": details["Objectives"],
                            "Scoring": details["Scoring"],
                            "EvidenceRequired": activity_evidence,
                            "ModuleDetails": details["ModuleDetails"],
                        })
                        _save_modules(db, event_id, modules)
                        st.session_state[f"programme_notice_{event_id}"] = "Activity saved"
                        st.rerun()
                    if delete_activity.button(
                        "Delete Activity",
                        key=f"delete_activity_{event_id}_{index}_{selected_position}",
                    ):
                        module["Activities"].pop(selected_position)
                        if not module["Activities"]:
                            modules.pop(index)
                        _save_modules(db, event_id, modules)
                        st.rerun()
                if module["ModuleName"].casefold() == "sync ai":
                    st.divider()
                    render_sync_ai_editor(db, event_id)
                elif module["ModuleName"].casefold() == "catalyst challenge":
                    st.divider()
                    render_catalyst_editor(db, event_id)
                elif module["ModuleName"].casefold() == "mission ai":
                    st.divider()
                    if st.button(
                        "Edit Experiences",
                        key=f"edit_missions_{event_id}_{index}",
                        width="stretch",
                    ):
                        st.session_state["mission_studio_event_filter"] = event_id
                        st.session_state["mission_studio_module"] = "Mission AI"
                        request_navigation("Mission Studio")
                elif module["ModuleName"].casefold() == "race checkpoints" and is_formula_race_event(event):
                    st.divider()
                    render_race_checkpoint_editor(db, event_id, module)


def render_filtered_mission_library(db):
    st.subheader("Experience Library")
    st.caption("Add Experience → choose a relevant experience from the library.")
    templates = db.get_mission_templates(include_archived=True)
    programme = st.selectbox(
        "Programme",
        ["Mission AI", "Sync AI", "Catalyst Challenge", "Formula R.A.C.E.", "Road Hunt", "All"],
        key="mission_library_programme",
    )
    search = st.text_input("Search experiences", key="mission_library_search").casefold()
    active_only = st.checkbox("Active only", value=True)
    filtered = []
    for template in templates:
        text = " ".join(str(template.get(key, "")) for key in (
            "TemplateID", "Title", "Story", "SubmissionType"
        )).casefold()
        programme_terms = {
            "Mission AI": ("aia-mai", "mission "),
            "Sync AI": ("aia-sync", "sync ai"),
            "Catalyst Challenge": ("catalyst",),
            "Formula R.A.C.E.": ("race", "formula"),
            "Road Hunt": ("road", "hunt", "gps"),
        }
        belongs = programme == "All" or any(
            term in text for term in programme_terms.get(programme, ())
        )
        if search:
            belongs = search in text
        is_active = str(template.get("Status", "ACTIVE")).upper() not in {
            "CLOSED", "ARCHIVED", "INACTIVE"
        }
        if belongs and (is_active or not active_only):
            filtered.append(template)
    st.dataframe(
        [{
            "Experience": row.get("Title", ""),
            "Activity type": row.get("SubmissionType", "Activity"),
            "AI required": row.get("AIHelpEnabled", "No"),
            "Evidence type": row.get("SubmissionType", "None"),
            "Status": row.get("Status", "Active"),
        } for row in filtered],
        width="stretch",
        hide_index=True,
    )
    if not filtered:
        st.info("No experiences match these filters.")


DEFAULT_SYNC_JUDGING = [
    {"Label": "Creativity", "Description": "Original and memorable concept", "MaximumScore": 20, "Weight": 1.0},
    {"Label": "Effective use of AI", "Description": "AI meaningfully strengthens the work", "MaximumScore": 20, "Weight": 1.0},
    {"Label": "Team participation", "Description": "Every member contributes", "MaximumScore": 20, "Weight": 1.0},
    {"Label": "Story / message", "Description": "Clear and relevant message", "MaximumScore": 20, "Weight": 1.0},
    {"Label": "Performance impact", "Description": "Confident delivery and audience impact", "MaximumScore": 20, "Weight": 1.0},
]


def _event_mission_by_id(db, event_id, mission_id):
    return next(
        (
            row for row in db.get_event_missions(event_id, include_closed=True)
            if str(row.get("MissionID", "")).upper() == mission_id
        ),
        None,
    )


def _save_container_settings(db, mission, settings):
    updated = dict(mission)
    updated["Story"] = json.dumps(settings, ensure_ascii=False, sort_keys=True)
    db.upsert_event_mission(updated)


def calculate_judging_rankings(entries):
    totals = {}
    counts = {}
    for row in entries:
        team = str(row.get("Team", "")).strip()
        if not team:
            continue
        totals[team] = totals.get(team, 0.0) + float(row.get("Score", 0) or 0)
        counts[team] = counts.get(team, 0) + 1
    ordered = sorted(
        (
            {"Team": team, "FinalScore": totals[team] / counts[team]}
            for team in totals
        ),
        key=lambda row: (-row["FinalScore"], row["Team"]),
    )
    previous_score = None
    previous_rank = 0
    for position, row in enumerate(ordered, start=1):
        tied = previous_score is not None and row["FinalScore"] == previous_score
        row["Rank"] = previous_rank if tied else position
        row["Tie"] = tied or (
            position < len(ordered)
            and ordered[position]["FinalScore"] == row["FinalScore"]
        )
        previous_score = row["FinalScore"]
        previous_rank = row["Rank"]
    return ordered


def render_sync_ai_editor(db, event_id):
    creation = _event_mission_by_id(db, event_id, "S01")
    performance = _event_mission_by_id(db, event_id, "S02")
    if not creation or not performance:
        st.info("Add the Sync AI container to this event to edit its settings.")
        return
    settings = _module_settings(creation)
    judging = _module_settings(performance)
    st.markdown("### Sync AI")
    st.caption("Event-specific settings. Experience templates remain unchanged.")
    flow, market, performance_tab, judging_tab = st.tabs([
        "Flow & Credits", "Marketplace", "Performance", "Judging",
    ])
    with flow:
        briefing = st.text_area(
            "Briefing instructions",
            value=str(settings.get("BriefingInstructions", "")),
            key=f"sync_brief_{event_id}",
        )
        c1, c2, c3 = st.columns(3)
        credits = c1.number_input(
            "Credits available", min_value=0,
            value=int(settings.get("CreditsAvailable", 500) or 0),
            key=f"sync_credits_{event_id}",
        )
        prep = c2.number_input(
            "Preparation duration", min_value=1,
            value=int(settings.get("PreparationDuration", 70) or 70),
            key=f"sync_prep_{event_id}",
        )
        max_score = c3.number_input(
            "Maximum score", min_value=0,
            value=int(judging.get("MaximumScore", 100) or 100),
            key=f"sync_max_{event_id}",
        )
        purchase_rules = st.text_area(
            "Purchase rules", value=str(settings.get("PurchaseRules", "")),
            key=f"sync_purchase_rules_{event_id}",
        )
        ai_rules = st.text_area(
            "AI support rules", value=str(settings.get("AISupportRules", "")),
            key=f"sync_ai_rules_{event_id}",
        )
        if st.button("Save Flow & Credit Rules", type="primary", key=f"sync_flow_save_{event_id}"):
            settings.update({
                "ContainerType": "Sync AI",
                "BriefingInstructions": briefing,
                "CreditsAvailable": int(credits),
                "PreparationDuration": int(prep),
                "PurchaseRules": purchase_rules,
                "AISupportRules": ai_rules,
            })
            judging["MaximumScore"] = int(max_score)
            _save_container_settings(db, creation, settings)
            _save_container_settings(db, performance, judging)
            st.success("Sync AI settings saved to this event.")
    with market:
        marketplace_rows = settings.get("MarketplaceItems") or AIA_CUSTOMER_CONTACT_MARKETPLACE
        marketplace = st.data_editor(
            pd.DataFrame(marketplace_rows),
            num_rows="dynamic", hide_index=True, width="stretch",
            key=f"sync_market_{event_id}",
        )
        if st.button("Save Marketplace", type="primary", key=f"sync_market_save_{event_id}"):
            items = marketplace.to_dict("records")
            settings["MarketplaceItems"] = items
            _save_container_settings(db, creation, settings)
            st.success("Marketplace saved for this event.")
            st.info("Publish live marketplace changes from Control Centre.")
    with performance_tab:
        p1, p2 = st.columns(2)
        performance_minutes = p1.number_input(
            "Performance duration", min_value=1,
            value=int(judging.get("PerformanceDuration", 4) or 4),
            key=f"sync_performance_duration_{event_id}",
        )
        tie_break = p2.text_input(
            "Tie-break rule",
            value=str(judging.get("TieBreakRule", "Performance impact, then Creativity")),
            key=f"sync_tie_{event_id}",
        )
        notes = st.text_area(
            "Judge notes", value=str(judging.get("JudgeNotes", "")),
            key=f"sync_notes_{event_id}",
        )
        if st.button("Save Performance Rules", type="primary", key=f"sync_performance_save_{event_id}"):
            judging.update({
                "PerformanceDuration": int(performance_minutes),
                "TieBreakRule": tie_break,
                "JudgeNotes": notes,
            })
            _save_container_settings(db, performance, judging)
            st.success("Performance rules saved.")
    with judging_tab:
        criteria = st.data_editor(
            pd.DataFrame(judging.get("Criteria") or DEFAULT_SYNC_JUDGING),
            num_rows="dynamic", hide_index=True, width="stretch",
            key=f"sync_criteria_{event_id}",
        )
        teams = db.get_teams(event_id)
        judges = judging.get("JudgeEntries") or [{
            "Judge": "Judge 1",
            "Team": team.get("TeamName", ""),
            "Score": 0,
            "Confirmed": False,
        } for team in teams]
        entries = st.data_editor(
            pd.DataFrame(judges),
            num_rows="dynamic", hide_index=True, width="stretch",
            key=f"sync_judges_{event_id}",
        )
        ranking_rows = calculate_judging_rankings(entries.to_dict("records"))
        st.markdown("#### Team ranking")
        st.dataframe(ranking_rows, hide_index=True, width="stretch")
        if any(row["Tie"] for row in ranking_rows):
            st.warning(
                "A tie is present. Apply the configured tie-break rule before "
                "final confirmation."
            )
        if st.button("Save & Confirm Judging", type="primary", key=f"sync_judging_save_{event_id}"):
            criteria_rows = criteria.to_dict("records")
            judge_rows = entries.to_dict("records")
            judging.update({
                "ContainerType": "Sync AI",
                "Criteria": criteria_rows,
                "JudgeEntries": judge_rows,
                "TeamRanking": calculate_judging_rankings(judge_rows),
                "FinalScoresConfirmed": all(
                    bool(row.get("Confirmed")) for row in judge_rows
                ) if judge_rows else False,
            })
            _save_container_settings(db, performance, judging)
            st.success("Judge entries and final confirmation saved.")


def render_catalyst_editor(db, event_id):
    mission = _event_mission_by_id(db, event_id, "C01")
    if not mission:
        st.info("Add the Catalyst Challenge container to edit its settings.")
        return
    settings = _module_settings(mission)
    st.markdown("### Catalyst Challenge")
    stages = ["Briefing", "Build", "Run", "Debrief"]
    flow = st.data_editor(
        pd.DataFrame(settings.get("Flow") or [
            {"Order": index, "Activity": name, "Minutes": value, "Active": True}
            for index, (name, value) in enumerate(zip(stages, [10, 70, 30, 10]), start=1)
        ]),
        num_rows="dynamic", hide_index=True, width="stretch",
        key=f"catalyst_flow_{event_id}",
    )
    instructions = st.text_area(
        "Instructions", value=str(settings.get("Instructions", "")),
        key=f"catalyst_instructions_{event_id}",
    )
    materials = st.text_area(
        "Materials", value=str(settings.get("Materials", "")),
        key=f"catalyst_materials_{event_id}",
    )
    scoring = st.text_area(
        "Scoring", value=str(settings.get("Scoring", mission.get("ScoringRule", ""))),
        key=f"catalyst_scoring_{event_id}",
    )
    evidence = st.text_input(
        "Evidence", value=str(settings.get("Evidence", mission.get("SubmissionType", "CATALYST"))),
        key=f"catalyst_evidence_{event_id}",
    )
    notes = st.text_area(
        "Facilitator notes", value=str(settings.get("FacilitatorNotes", "")),
        key=f"catalyst_notes_{event_id}",
    )
    debrief = st.text_area(
        "Debrief questions", value=str(settings.get("DebriefQuestions", mission.get("DebriefQuestions", ""))),
        key=f"catalyst_debrief_{event_id}",
    )
    if st.button("Save Catalyst Challenge", type="primary", key=f"catalyst_save_{event_id}"):
        settings.update({
            "ContainerType": "Catalyst Challenge",
            "Flow": flow.to_dict("records"),
            "Instructions": instructions,
            "Materials": materials,
            "Scoring": scoring,
            "Evidence": evidence,
            "FacilitatorNotes": notes,
            "DebriefQuestions": debrief,
        })
        _save_container_settings(db, mission, settings)
        st.success("Catalyst Challenge saved to this event.")


def render_container_editors(db):
    events = db.get_events()
    if not events:
        return
    event = select_active_event(events, label="Event", key="container_settings_event")
    event_id = str(event.get("EventID", ""))
    sync_tab, catalyst_tab, mission_tab = st.tabs([
        "Sync AI", "Catalyst Challenge", "Mission AI",
    ])
    with sync_tab:
        render_sync_ai_editor(db, event_id)
    with catalyst_tab:
        render_catalyst_editor(db, event_id)
    with mission_tab:
        render_event_module_editor(db)


def render_live_programme_builder(db):
    st.subheader("Build a Live Experience Programme")
    st.caption(
        "Choose missions in running order. EXOS creates the event missions and Show Control timeline together."
    )

    events = db.get_events()
    templates = db.get_mission_templates()
    if not events:
        st.warning("Create an event first.")
        return
    if not templates:
        st.warning("Create or import experiences in Experience Studio first.")
        return

    selected_event = select_active_event(
        events,
        label="Active Event",
        key="programme_builder_event",
    )
    event_id = str(selected_event.get("EventID", ""))

    template_options = {
        f"{template.get('TemplateID', '')} | {template.get('Title', '')}": template
        for template in templates
    }
    selected_template_labels = st.multiselect(
        "Experiences — select them in running order",
        list(template_options),
        key=f"programme_builder_templates_{event_id}",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        programme_start = st.time_input(
            "Programme Start",
            value=time(9, 0),
            key=f"programme_start_{event_id}",
        )
    with col2:
        registration_minutes = st.number_input(
            "Registration Minutes",
            min_value=0,
            max_value=180,
            value=15,
            step=5,
            key=f"registration_minutes_{event_id}",
        )
    with col3:
        debrief_minutes = st.number_input(
            "Debrief Minutes per Experience",
            min_value=0,
            max_value=120,
            value=15,
            step=5,
            key=f"debrief_minutes_{event_id}",
        )

    option1, option2, option3, option4 = st.columns(4)
    with option1:
        include_registration = st.checkbox(
            "Include Registration",
            value=True,
            key=f"include_registration_{event_id}",
        )
    with option2:
        include_team_discovery = st.checkbox(
            "Include Team Discovery",
            value=True,
            key=f"include_team_discovery_{event_id}",
        )
    with option3:
        include_marketplace = st.checkbox(
            "Include Marketplace",
            value=False,
            key=f"include_marketplace_{event_id}",
        )
    with option4:
        include_closing = st.checkbox(
            "Include Closing",
            value=True,
            key=f"include_closing_{event_id}",
        )

    marketplace_minutes = 30
    if include_marketplace:
        marketplace_minutes = st.number_input(
            "Marketplace Minutes",
            min_value=5,
            max_value=240,
            value=30,
            step=5,
            key=f"marketplace_minutes_{event_id}",
        )

    if not selected_template_labels:
        render_existing_programme(db, event_id)
        return

    plan_rows = []
    for index, label in enumerate(selected_template_labels, start=1):
        template = template_options[label]
        plan_rows.append({
            "Order": index,
            "TemplateID": template.get("TemplateID", ""),
            "MissionID": f"M{index:02d}",
            "Mission": template.get("Title", ""),
            "DurationMinutes": 30,
            "IncludeDebrief": True,
        })

    st.markdown("#### Running Order")
    edited_plan = st.data_editor(
        pd.DataFrame(plan_rows),
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        disabled=["TemplateID", "Mission"],
        column_config={
            "Order": st.column_config.NumberColumn(
                "Order",
                min_value=1,
                step=1,
                required=True,
            ),
            "MissionID": st.column_config.TextColumn(
                "Experience ID",
                required=True,
            ),
            "Mission": st.column_config.TextColumn("Experience"),
            "DurationMinutes": st.column_config.NumberColumn(
                "Experience Minutes",
                min_value=1,
                max_value=480,
                step=5,
                required=True,
            ),
            "IncludeDebrief": st.column_config.CheckboxColumn(
                "Add Debrief",
            ),
        },
        key=f"programme_plan_editor_{event_id}",
    )

    confirm_replace = st.checkbox(
        "Replace the current Show Control timeline for this event",
        key=f"confirm_programme_replace_{event_id}",
    )
    if st.button(
        "🚀 Build and Publish Programme",
        width="stretch",
        key=f"build_programme_{event_id}",
    ):
        if not confirm_replace:
            st.error("Confirm the timeline replacement first.")
            return

        plan = edited_plan.sort_values("Order").to_dict("records")
        try:
            result = db.build_event_programme(
                event_id=event_id,
                mission_plan=plan,
                start_time=programme_start.strftime("%H:%M"),
                include_registration=include_registration,
                registration_minutes=int(registration_minutes),
                include_team_discovery=include_team_discovery,
                team_discovery_minutes=15,
                debrief_minutes=int(debrief_minutes),
                include_marketplace=include_marketplace,
                marketplace_minutes=int(marketplace_minutes),
                include_closing=include_closing,
            )
        except Exception as error:
            st.error(f"Programme build failed: {error}")
            return

        st.success("Programme built and published to Show Control.")
        metric1, metric2, metric3 = st.columns(3)
        metric1.metric("Experiences", result["Missions"])
        metric2.metric("Stages", result["Stages"])
        metric3.metric("Scheduled End", result["ProgrammeEndTime"])
        db.clear_cache()
        st.rerun()

    render_existing_programme(db, event_id)


def render_saved_programme_packs(db):
    st.subheader("Reusable Programme Pack Library")
    st.caption(
        "Save a completed event once, then install its teams, missions, timeline "
        "and marketplace into any empty event."
    )

    events = db.get_events()
    if not events:
        st.warning("Create an event before using programme packs.")
        return

    event_options = {
        f"{event.get('EventID', '')} — {event.get('EventName', '')}": event
        for event in events
    }

    with st.expander("➕ Save a configured event as a reusable pack"):
        source_label = st.selectbox(
            "Configured Source Event",
            list(event_options.keys()),
            key="pack_source_event",
        )
        source_event = event_options[source_label]
        source_event_id = str(source_event.get("EventID", ""))
        pack_name = st.text_input(
            "Pack Name",
            value=str(source_event.get("EventName", "")),
            key=f"pack_name_{source_event_id}",
        )
        description = st.text_area(
            "Pack Description",
            value=(
                f"Reusable programme created from {source_event.get('EventName', '')}."
            ),
            key=f"pack_description_{source_event_id}",
        )
        if st.button(
            "💾 Save to Programme Pack Library",
            width="stretch",
            key=f"save_programme_pack_{source_event_id}",
        ):
            try:
                result = db.save_event_as_programme_pack(
                    source_event_id,
                    pack_name,
                    description,
                )
            except Exception as error:
                st.error(f"Programme pack could not be saved: {error}")
            else:
                st.success(
                    f"{result['PackName']} saved as {result['PackID']}."
                )
                st.rerun()

    packs = db.get_programme_packs()
    if not packs:
        st.info(
            "No reusable packs saved yet. The installed AIA event can now be "
            "saved as your first master pack."
        )
        return

    summary_rows = []
    for pack_row in packs:
        pack = db.get_programme_pack(pack_row.get("PackID", "")) or {}
        summary_rows.append({
            "Pack ID": pack.get("PackID", ""),
            "Programme Pack": pack.get("PackName", ""),
            "Source Event": pack.get("SourceEventID", ""),
            "Teams": len(pack.get("Teams", [])),
            "Missions": len(pack.get("Missions", [])),
            "Stages": len(pack.get("Stages", [])),
            "Marketplace": len(pack.get("Marketplace", [])),
            "Version": pack.get("Version", "1.0"),
        })
    st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

    st.markdown("#### Install a Saved Pack")
    pack_options = {
        f"{pack.get('PackID', '')} — {pack.get('PackName', '')}": pack
        for pack in packs
    }
    selected_pack_label = st.selectbox(
        "Programme Pack",
        list(pack_options.keys()),
        key="programme_pack_to_install",
    )
    selected_pack_row = pack_options[selected_pack_label]
    selected_pack = db.get_programme_pack(
        selected_pack_row.get("PackID", ""),
    ) or {}

    target_label = st.selectbox(
        "Empty Target Event",
        list(event_options.keys()),
        key="programme_pack_target_event",
    )
    target_event = event_options[target_label]
    target_event_id = str(target_event.get("EventID", ""))

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Teams", len(selected_pack.get("Teams", [])))
    metric2.metric("Experiences", len(selected_pack.get("Missions", [])))
    metric3.metric("Timeline Stages", len(selected_pack.get("Stages", [])))
    metric4.metric("Marketplace", len(selected_pack.get("Marketplace", [])))

    st.warning(
        "Installing replaces the target event's teams, missions and timeline. "
        "It will stop automatically if participants have already joined."
    )
    confirmed = st.checkbox(
        "I confirm the selected target event is correct and has no participants",
        key=f"confirm_pack_install_{target_event_id}",
    )
    if st.button(
        "🚀 Install Selected Programme Pack",
        width="stretch",
        disabled=not confirmed,
        key=(
            f"install_saved_pack_{selected_pack.get('PackID', '')}_"
            f"{target_event_id}"
        ),
    ):
        try:
            result = db.install_programme_pack(
                selected_pack.get("PackID", ""),
                target_event_id,
            )
        except Exception as error:
            st.error(f"Programme pack installation failed: {error}")
        else:
            st.success(
                f"{result['PackName']} installed and published to "
                f"{result['EventID']}."
            )
            result1, result2, result3, result4 = st.columns(4)
            result1.metric("Teams", result["Teams"])
            result2.metric("Experiences", result["Missions"])
            result3.metric("Stages", result["Stages"])
            result4.metric("Marketplace", result["MarketplaceItems"])


def render_mahb_media_explore_installer(db, events):
    st.divider()
    st.subheader("MAHB Media Explore — GPS Road Hunt")
    st.caption(
        "Installs a complete one-day Sepang → Ipoh → George Town → Penang "
        "Airport Road Hunt with aviation-themed teams, missions, Innovation "
        "Credits, GPS checkpoints and Show Control stages."
    )

    event = select_active_event(
        events,
        label="MAHB Event to Prepare",
        key="mahb_media_explore_pack_event",
    )
    event_id = str(event.get("EventID", ""))

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Teams", len(MAHB_MEDIA_EXPLORE_TEAMS))
    metric2.metric("Experiences", len(MAHB_MEDIA_EXPLORE_MISSION_PLAN))
    metric3.metric("GPS Stops", len(MAHB_MEDIA_EXPLORE_ROUTE))
    metric4.metric("Show Control Stages", len(MAHB_MEDIA_EXPLORE_STAGES))

    st.info(
        "One navigator phone per vehicle shares GPS with facilitators. The driver "
        "must never handle EXOS while the vehicle is moving."
    )
    st.warning(
        "This replaces the selected event's teams and Show Control timeline. "
        "It stops if runtime participants already exist. Route pins, parking, "
        "access, opening hours and stage timing must be confirmed during the "
        "route reconnaissance before live use."
    )
    confirmed = st.checkbox(
        "I confirm this is the correct empty event and I will validate the route before launch",
        key=f"confirm_mahb_media_explore_pack_{event_id}",
    )
    if st.button(
        "🗺️ Install and Publish MAHB Road Hunt",
        width="stretch",
        disabled=not confirmed,
        key=f"install_mahb_media_explore_pack_{event_id}",
    ):
        try:
            result = install_mahb_media_explore_pack(db, event_id)
        except Exception as error:
            st.error(f"MAHB Road Hunt installation failed: {error}")
            return

        st.success("MAHB Media Explore Road Hunt installed and published.")
        result1, result2, result3, result4 = st.columns(4)
        result1.metric("Teams Published", result["Teams"])
        result2.metric("Experiences Published", result["Missions"])
        result3.metric("GPS Stops", result["RouteStops"])
        result4.metric("Timeline Stages", result["Stages"])

    render_existing_programme(db, event_id)


def render_programme_packs(db):
    render_saved_programme_packs(db)
    st.divider()
    st.markdown("### Ready-made Programme Installers")
    st.subheader("AIA Customer Contact — Innovate to Elevate")
    st.caption(
        "Installs the complete two-day programme into an empty event: six teams, "
        "Mission AI, SYNC AI, Innovation Credits, marketplace and Catalyst."
    )

    events = db.get_events()
    if not events:
        st.warning("Create the AIA event first.")
        return

    event = select_active_event(
        events,
        label="Event to Prepare",
        key="aia_pack_event",
    )
    event_id = str(event.get("EventID", ""))

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Teams", len(AIA_CUSTOMER_CONTACT_TEAMS))
    metric2.metric("Experiences", len(AIA_CUSTOMER_CONTACT_MISSION_PLAN))
    metric3.metric("Show Control Stages", len(AIA_CUSTOMER_CONTACT_STAGES))
    metric4.metric("Marketplace Items", len(AIA_CUSTOMER_CONTACT_MARKETPLACE))

    st.info(
        "Mission AI is a synchronized 60-minute mission sprint, not a free-roaming "
        "treasure hunt. All six teams receive the same mission together, and each "
        "team can use its persistent AI Facilitator and controlled hints."
    )
    st.warning(
        "This replaces the selected event's teams and Show Control timeline. "
        "It will stop if any runtime participants already exist."
    )
    confirmed = st.checkbox(
        "I confirm this is the correct event and no participants have joined",
        key=f"confirm_aia_pack_{event_id}",
    )
    if st.button(
        "🚀 Install and Publish AIA Programme",
        width="stretch",
        disabled=not confirmed,
        key=f"install_aia_pack_{event_id}",
    ):
        try:
            result = install_aia_customer_contact_pack(db, event_id)
        except Exception as error:
            st.error(f"AIA programme installation failed: {error}")
            return

        st.success("AIA Customer Contact programme installed and published.")
        result1, result2, result3, result4 = st.columns(4)
        result1.metric("Teams Published", result["Teams"])
        result2.metric("Experiences Published", result["Missions"])
        result3.metric("Timeline Stages", result["Stages"])
        result4.metric("Marketplace Items", result["MarketplaceItems"])

    render_existing_programme(db, event_id)
    render_mahb_media_explore_installer(db, events)


def render_recommendation_builder():
    st.subheader("Programme Recommendations")
    programme_engine = ProgrammeEngine()
    recommendation_engine = RecommendationEngine()
    transformation_engine = TransformationEngine()

    pattern = programme_engine.get_pattern("team_building")
    if pattern:
        st.markdown("#### Learning Journey")
        for stage in pattern.get("learning_journey", []):
            st.write(f"➡️ {stage}")

    st.divider()
    intents = transformation_engine.get_programme_intents()
    selected_intent = st.selectbox(
        "Why is this programme being organised?",
        intents,
        key="recommendation_programme_intent",
    )
    intent_info = transformation_engine.analyse_intent(selected_intent) or {}
    if intent_info:
        st.info(intent_info.get("purpose", ""))
        st.markdown("#### Desired Outcomes")
        for item in intent_info.get("outcome", []):
            st.write(f"• {item}")

    if st.button("Generate Recommendations", key="generate_programme_recommendations"):
        results = recommendation_engine.recommend(intent_info.get("outcome", []))
        recommended = []
        for result in results:
            if result["score"] > 0:
                name = get_activity_name(result["activity"])
                recommended.append(name)
                st.success(name)

        if recommended:
            st.markdown("#### Suggested Timeline")
            for time, activity in build_timeline(recommended):
                st.write(f"**{time}** — {activity}")

        codeshift = load_codeshift_lens()
        if codeshift:
            with st.expander("CodeShift Facilitator Reflection"):
                st.info(codeshift.get("purpose", ""))
                for question in codeshift.get("core_lens", []):
                    st.write(f"• {question}")


def show_programme_builder():
    st.title("Programme Builder")
    st.caption("Build the event in running order. Open any module to edit it.")
    db = GoogleSheetsDB()
    render_programme_first_builder(db)
    event_id = str(st.session_state.get(ACTIVE_EVENT_KEY, ""))
    if event_id:
        from engines.programme_adapter import CanonicalProgrammeAdapter
        from screens.experience_foundation import render_event_assignment_manager
        programme = CanonicalProgrammeAdapter.load(db, event_id)
        st.divider()
        render_event_assignment_manager(db, event_id, programme)
