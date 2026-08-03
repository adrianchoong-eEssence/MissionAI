"""Gate 5 Experience Centre authoring and Event Centre assignment surfaces."""

import streamlit as st

from components.experience_preview import render_experience_participant
from data.experience_repository import SupabaseExperienceRepository
from data.runtime_database import RuntimeDatabaseError
from engines.experience_library import ExperienceLibraryService, filter_definitions, resolve_experience


def _service(db):
    repository = SupabaseExperienceRepository(db.runtime)
    return ExperienceLibraryService(repository), repository


def render_definition_library(db):
    st.subheader("Reusable Experience Definitions")
    st.caption("Definitions are event-independent, versioned authored content.")
    try:
        service, repository = _service(db)
        definitions = repository.definitions(include_archived=True)
    except Exception as error:
        st.warning("Canonical Experience Library is unavailable until migration 013 is applied.")
        st.caption(str(error))
        return
    latest = {}
    for definition in definitions:
        key = definition["ExperienceDefinitionID"]
        if key not in latest or int(definition["Version"]) > int(latest[key]["Version"]):
            latest[key] = definition
    choices = {"Create new Definition": None}
    choices.update({
        f"{row['Name']} · v{row['Version']} · {row['Status']}": row
        for row in latest.values()
    })
    selected = choices[st.selectbox("Definition", list(choices))] or {}
    with st.form("canonical_definition_editor"):
        name = st.text_input("Name", value=str(selected.get("Name", "")))
        participant_title = st.text_input(
            "Participant title", value=str(selected.get("ParticipantTitle", "")),
        )
        internal = st.text_area(
            "Internal description", value=str(selected.get("InternalDescription", "")),
        )
        narrative = st.text_area(
            "Participant narrative", value=str(selected.get("ParticipantNarrative", "")),
        )
        task = st.text_area("Participant task", value=str(selected.get("ParticipantTask", "")))
        c1, c2, c3 = st.columns(3)
        experience_type = c1.text_input("Experience type", value=str(selected.get("ExperienceType", "Standard")))
        difficulty = c2.text_input("Difficulty", value=str(selected.get("Difficulty", "Unspecified")))
        credits = c3.number_input(
            "Default Intelligence Credits", min_value=0,
            value=int(selected.get("DefaultIntelligenceCredits", 0) or 0),
        )
        evidence_type = st.text_input(
            "Default evidence type", value=str(selected.get("DefaultEvidenceType", "NONE")),
        )
        evidence = st.text_area(
            "Default evidence instructions",
            value=str(selected.get("DefaultEvidenceInstructions", "")),
        )
        character = st.text_input(
            "Default CharacterID", value=str(selected.get("DefaultCharacterID", "")),
        )
        assets = st.text_input(
            "Reference AssetIDs", value=", ".join(selected.get("ReferenceAssetIDs", []) or []),
        )
        hint = st.text_input("Default hint", value=str(selected.get("DefaultHint", "")))
        ai_response = st.text_area(
            "Default AI response", value=str(selected.get("DefaultAIResponse", "")),
        )
        submitted = st.form_submit_button("Save Definition", type="primary")
    values = {
        "Name": name, "ParticipantTitle": participant_title, "InternalDescription": internal,
        "ParticipantNarrative": narrative, "ParticipantTask": task,
        "ExperienceType": experience_type, "Difficulty": difficulty,
        "DefaultIntelligenceCredits": credits, "DefaultEvidenceType": evidence_type,
        "DefaultEvidenceInstructions": evidence, "DefaultCharacterID": character,
        "ReferenceAssetIDs": [item.strip() for item in assets.split(",") if item.strip()],
        "DefaultHint": hint, "DefaultAIResponse": ai_response,
    }
    if submitted:
        if selected:
            service.edit_definition(
                selected["ExperienceDefinitionID"], selected["Version"], values,
            )
        else:
            service.create_definition(values)
        st.success("Definition saved without changing event assignments.")
        st.rerun()
    if selected:
        preview_assignment = {
            "ExperienceAssignmentID": "PREVIEW", "EventID": "PREVIEW",
            "ProgrammeID": "PREVIEW", "ModuleID": "PREVIEW", "ActivityID": "PREVIEW",
            "ExperienceDefinitionID": selected["ExperienceDefinitionID"],
            "DefinitionVersion": selected["Version"], "AssignmentVersion": 1,
            "Active": True, "RuntimeEligible": True,
        }
        with st.expander("Participant Preview", expanded=True):
            render_experience_participant(resolve_experience(selected, preview_assignment))
        publish, duplicate, archive = st.columns(3)
        if publish.button("Publish"):
            service.publish(selected["ExperienceDefinitionID"], selected["Version"])
            st.rerun()
        if duplicate.button("Duplicate as New Definition"):
            service.duplicate_definition(selected["ExperienceDefinitionID"], selected["Version"])
            st.rerun()
        if archive.button("Archive"):
            service.archive(selected["ExperienceDefinitionID"], selected["Version"])
            st.rerun()


def render_event_assignment_manager(db, event_id, programme):
    st.subheader("Experience Assignments")
    st.caption("Assign reusable Definitions to the selected event Activity; no content is copied.")
    try:
        service, repository = _service(db)
        definitions = [row for row in repository.definitions() if row["Status"] == "PUBLISHED"]
    except Exception as error:
        st.info("Canonical assignment management requires migration 013.")
        st.caption(str(error))
        return
    activities = programme.activities
    if not activities:
        st.info("Create a Programme Activity before assigning Experiences.")
        return
    activity = next(row for row in activities if row["ActivityID"] == st.selectbox(
        "Activity", [row["ActivityID"] for row in activities],
        format_func=lambda value: next(
            row["AdminDisplayName"] for row in activities if row["ActivityID"] == value
        ),
    ))
    assignments = repository.assignments(event_id, activity["ActivityID"])
    query = st.text_input("Search by name").casefold().strip()
    filter_columns = st.columns(3)
    statuses = filter_columns[0].multiselect("Status", ["PUBLISHED"], default=["PUBLISHED"])
    types = filter_columns[1].multiselect(
        "Type", sorted({row["ExperienceType"] for row in definitions}),
    )
    difficulties = filter_columns[2].multiselect(
        "Difficulty", sorted({row["Difficulty"] for row in definitions}),
    )
    filter_columns2 = st.columns(4)
    venues = filter_columns2[0].multiselect(
        "Venue", sorted({item for row in definitions for item in row.get("VenueTags", []) or []}),
    )
    characters = filter_columns2[1].multiselect(
        "Character", sorted({row["DefaultCharacterID"] for row in definitions if row.get("DefaultCharacterID")}),
    )
    evidence_types = filter_columns2[2].multiselect(
        "Evidence type", sorted({row["DefaultEvidenceType"] for row in definitions}),
    )
    tags = filter_columns2[3].multiselect(
        "Tag", sorted({item for row in definitions for item in row.get("Tags", []) or []}),
    )
    visible = filter_definitions(
        definitions, search=query, experience_types=types, difficulties=difficulties,
        venues=venues, characters=characters, evidence_types=evidence_types,
        statuses=statuses, tags=tags,
    )
    selected = st.multiselect(
        "Experience Library", [row["ExperienceDefinitionID"] for row in visible],
        format_func=lambda value: next(row["Name"] for row in visible if row["ExperienceDefinitionID"] == value),
        key="event_definition_selection",
    )
    selection_controls = st.columns(4)
    if selection_controls[0].button("Select All"):
        st.session_state["event_definition_selection"] = [row["ExperienceDefinitionID"] for row in visible]
        st.rerun()
    if selection_controls[1].button("Clear Selection"):
        st.session_state["event_definition_selection"] = []
        st.rerun()
    if st.button("Assign Selected", disabled=not selected):
        existing = {row["ExperienceDefinitionID"] for row in assignments}
        for definition_id in selected:
            if definition_id in existing:
                continue
            definition = next(row for row in visible if row["ExperienceDefinitionID"] == definition_id)
            service.assign({
                "EventID": event_id, "ProgrammeID": programme.programme_id,
                "ModuleID": activity["ModuleID"], "ActivityID": activity["ActivityID"],
                "ExperienceDefinitionID": definition_id, "DefinitionVersion": definition["Version"],
                "AssignmentOrder": len(assignments) + 1, "Active": True, "RuntimeEligible": True,
            })
        st.rerun()
    assignment_ids = [row["ExperienceAssignmentID"] for row in assignments]
    active_ids = [row["ExperienceAssignmentID"] for row in assignments if row["Active"]]
    inactive_ids = [row["ExperienceAssignmentID"] for row in assignments if not row["Active"]]
    assignment_selection = st.multiselect(
        "Assigned selection", assignment_ids, key=f"assignment_selection_{event_id}_{activity['ActivityID']}",
    )
    bulk = st.columns(5)
    if bulk[0].button("Select Active"):
        st.session_state[f"assignment_selection_{event_id}_{activity['ActivityID']}"] = active_ids
        st.rerun()
    if bulk[1].button("Select Inactive"):
        st.session_state[f"assignment_selection_{event_id}_{activity['ActivityID']}"] = inactive_ids
        st.rerun()
    if bulk[2].button("Activate Selected", disabled=not assignment_selection):
        service.set_assignments_active(assignment_selection, True)
        st.rerun()
    if bulk[3].button("Deactivate Selected", disabled=not assignment_selection):
        service.set_assignments_active(assignment_selection, False)
        st.rerun()
    if bulk[4].button("Remove Selected From Event", disabled=not assignment_selection):
        for assignment_id in assignment_selection:
            service.remove_assignment(assignment_id)
        st.rerun()
    for assignment in assignments:
        definition = repository.get_definition(
            assignment["ExperienceDefinitionID"], assignment["DefinitionVersion"],
        )
        with st.expander(f"{definition['Name']} · order {assignment['AssignmentOrder']}"):
            resolved = resolve_experience(definition, assignment)
            render_experience_participant(resolved)
            active = st.toggle("Active", value=bool(assignment["Active"]), key=assignment["ExperienceAssignmentID"])
            order = st.number_input(
                "Assignment order", min_value=1, value=int(assignment["AssignmentOrder"]),
                key=f"order_{assignment['ExperienceAssignmentID']}",
            )
            if st.button("Save Assignment", key=f"save_{assignment['ExperienceAssignmentID']}"):
                assignment.update({"Active": active, "AssignmentOrder": order,
                                   "AssignmentVersion": int(assignment["AssignmentVersion"]) + 1})
                repository.save_assignment(assignment)
                st.rerun()
            if st.button("Remove From Event", key=f"remove_{assignment['ExperienceAssignmentID']}"):
                service.remove_assignment(assignment["ExperienceAssignmentID"])
                st.rerun()
