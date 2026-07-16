import re

import pandas as pd
import streamlit as st

from data.google_sheets import GoogleSheetsDB, REQUIRED_WORKSHEETS
from data.mission_media import get_mission_media_url, upload_mission_media
from screens.app_state import active_event_index


SUBMISSION_TYPES = [
    "PHOTO",
    "TEXT",
    "PIPELINE",
    "PIPELINE_ENTERPRISE",
    "HELIUM",
    "KEYPUNCH",
    "CATALYST",
    "NASI",
    "NONE",
]


def safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clean_id(value):
    return re.sub(r"[^A-Z0-9_-]", "-", str(value).strip().upper())


def show_flash_message():
    message = st.session_state.pop("mission_studio_message", "")
    if message:
        st.success(message)


def render_template_editor(db):
    st.subheader("Mission Library")
    templates = db.get_mission_templates(include_archived=True)
    template_map = {
        f"{row.get('TemplateID', '')} | {row.get('Title', '')}": row
        for row in templates
    }
    selected_label = st.selectbox(
        "Create or Edit",
        ["➕ Create New Mission"] + list(template_map.keys()),
        key="mission_template_editor_selection",
    )
    selected = template_map.get(selected_label, {})

    with st.form("mission_template_editor_form", clear_on_submit=False):
        col1, col2 = st.columns([1, 2])
        with col1:
            template_id = st.text_input(
                "Template ID",
                value=str(selected.get("TemplateID", "")),
                help="Leave blank to generate the next ID automatically.",
            )
        with col2:
            title = st.text_input(
                "Mission Title *",
                value=str(selected.get("Title", "")),
            )

        story = st.text_area(
            "Story / Context",
            value=str(selected.get("Story", "")),
            height=120,
        )
        participant_instructions = st.text_area(
            "Participant Instructions *",
            value=str(selected.get("ParticipantInstructions", "")),
            height=160,
        )
        facilitator_instructions = st.text_area(
            "Facilitator Instructions",
            value=str(selected.get("FacilitatorInstructions", "")),
            height=140,
        )
        learning_objectives = st.text_area(
            "Learning Objectives",
            value=str(selected.get("LearningObjectives", "")),
            height=100,
        )

        col3, col4, col5 = st.columns(3)
        with col3:
            current_type = str(selected.get("SubmissionType", "PHOTO") or "PHOTO").upper()
            if current_type not in SUBMISSION_TYPES:
                current_type = "PHOTO"
            submission_type = st.selectbox(
                "Submission Type",
                SUBMISSION_TYPES,
                index=SUBMISSION_TYPES.index(current_type),
            )
        with col4:
            points = st.number_input(
                "Points",
                min_value=0,
                max_value=10000,
                value=safe_int(selected.get("Points", 100), 100),
                step=10,
            )
        with col5:
            ai_help = st.selectbox(
                "AI Help",
                ["Yes", "No"],
                index=0 if str(selected.get("AIHelpEnabled", "Yes")) != "No" else 1,
            )

        scoring_rule = st.text_area(
            "Scoring Rule",
            value=str(selected.get("ScoringRule", "")),
            help="Example: Highest Number ÷ 30 × 100",
        )

        st.markdown("#### Media")
        video_url = st.text_input(
            "Video URL",
            value=str(selected.get("VideoURL", "")),
            help="YouTube, Vimeo, or a direct hosted video URL.",
        )
        image_url = st.text_input(
            "Image URL",
            value=str(selected.get("ImageURL", "")),
        )
        document_url = st.text_input(
            "Document / PDF URL",
            value=str(selected.get("DocumentURL", "")),
        )

        st.caption(
            "Paste a URL above or upload a private file to Supabase below. "
            "An uploaded file takes priority when you save."
        )
        media_key = str(selected.get("TemplateID", "NEW") or "NEW")
        upload_col1, upload_col2, upload_col3 = st.columns(3)
        with upload_col1:
            uploaded_video = st.file_uploader(
                "Upload Video",
                type=["mp4", "mov", "webm"],
                key=f"mission_video_upload_{media_key}",
                help="Maximum 200 MB.",
            )
        with upload_col2:
            uploaded_image = st.file_uploader(
                "Upload Picture",
                type=["jpg", "jpeg", "png", "webp", "gif"],
                key=f"mission_image_upload_{media_key}",
                help="Maximum 10 MB.",
            )
        with upload_col3:
            uploaded_document = st.file_uploader(
                "Upload PDF",
                type=["pdf"],
                key=f"mission_document_upload_{media_key}",
                help="Maximum 25 MB.",
            )

        st.markdown("#### Mission Guidance")
        clue = st.text_area("Clue", value=str(selected.get("Clue", "")))
        answer = st.text_input("Answer", value=str(selected.get("Answer", "")))
        hint1 = st.text_input("Hint 1", value=str(selected.get("Hint1", "")))
        hint2 = st.text_input("Hint 2", value=str(selected.get("Hint2", "")))
        hint3 = st.text_input("Hint 3", value=str(selected.get("Hint3", "")))
        debrief_questions = st.text_area(
            "Debrief Questions",
            value=str(selected.get("DebriefQuestions", "")),
            height=120,
        )

        col6, col7 = st.columns(2)
        with col6:
            status_values = ["ACTIVE", "DRAFT", "ARCHIVED"]
            current_status = str(selected.get("Status", "ACTIVE") or "ACTIVE").upper()
            if current_status not in status_values:
                current_status = "ACTIVE"
            status = st.selectbox(
                "Template Status",
                status_values,
                index=status_values.index(current_status),
            )
        with col7:
            version = st.text_input(
                "Version",
                value=str(selected.get("Version", "1.0") or "1.0"),
            )

        submitted = st.form_submit_button("💾 Save Mission", width="stretch")

    if submitted:
        if not title.strip():
            st.error("Mission Title is required.")
            return
        if not participant_instructions.strip():
            st.error("Participant Instructions are required.")
            return

        resolved_template_id = clean_id(template_id)
        if not resolved_template_id:
            resolved_template_id = db.generate_next_template_id()

        resolved_video_url = video_url.strip()
        resolved_image_url = image_url.strip()
        resolved_document_url = document_url.strip()
        try:
            if uploaded_video is not None:
                resolved_video_url = upload_mission_media(
                    uploaded_video,
                    resolved_template_id,
                    "video",
                )
            if uploaded_image is not None:
                resolved_image_url = upload_mission_media(
                    uploaded_image,
                    resolved_template_id,
                    "image",
                )
            if uploaded_document is not None:
                resolved_document_url = upload_mission_media(
                    uploaded_document,
                    resolved_template_id,
                    "document",
                )
        except Exception as error:
            st.error(f"Mission media upload failed: {error}")
            return

        result = db.upsert_mission_template({
            "TemplateID": resolved_template_id,
            "Title": title.strip(),
            "Story": story.strip(),
            "ParticipantInstructions": participant_instructions.strip(),
            "FacilitatorInstructions": facilitator_instructions.strip(),
            "LearningObjectives": learning_objectives.strip(),
            "SubmissionType": submission_type,
            "ScoringRule": scoring_rule.strip(),
            "Points": int(points),
            "VideoURL": resolved_video_url,
            "ImageURL": resolved_image_url,
            "DocumentURL": resolved_document_url,
            "Clue": clue.strip(),
            "Answer": answer.strip(),
            "Hint1": hint1.strip(),
            "Hint2": hint2.strip(),
            "Hint3": hint3.strip(),
            "DebriefQuestions": debrief_questions.strip(),
            "AIHelpEnabled": ai_help,
            "Status": status,
            "Version": version.strip() or "1.0",
        })
        st.session_state["mission_studio_message"] = (
            f"{result['Action']} mission {result['TemplateID']}."
        )
        st.rerun()


def render_bulk_import(db):
    st.subheader("Bulk Import Missions")
    st.caption("Upload CSV or Excel. Existing Template IDs are updated; new IDs are created.")

    headers = REQUIRED_WORKSHEETS["MissionTemplates"]
    example = pd.DataFrame([
        {
            "TemplateID": "MT-EXAMPLE",
            "Title": "Example Mission",
            "Story": "Mission context goes here.",
            "ParticipantInstructions": "Complete the challenge and submit your result.",
            "FacilitatorInstructions": "Brief the teams and start the timer.",
            "LearningObjectives": "Collaboration; communication",
            "SubmissionType": "PHOTO",
            "ScoringRule": "Manual approval",
            "Points": 100,
            "VideoURL": "",
            "ImageURL": "",
            "DocumentURL": "",
            "Clue": "",
            "Answer": "",
            "Hint1": "",
            "Hint2": "",
            "Hint3": "",
            "DebriefQuestions": "What helped the team succeed?",
            "AIHelpEnabled": "Yes",
            "Status": "ACTIVE",
            "Version": "1.0",
            "UpdatedAt": "",
        }
    ], columns=headers)
    st.download_button(
        "⬇️ Download Import Template",
        data=example.to_csv(index=False).encode("utf-8"),
        file_name="EXOS_Mission_Import_Template.csv",
        mime="text/csv",
    )

    uploaded = st.file_uploader(
        "Mission File",
        type=["csv", "xlsx"],
        key="mission_bulk_import_file",
    )
    if uploaded is None:
        return

    try:
        if uploaded.name.lower().endswith(".csv"):
            dataframe = pd.read_csv(uploaded).fillna("")
        else:
            dataframe = pd.read_excel(uploaded).fillna("")
    except Exception as error:
        st.error(f"Could not read the file: {error}")
        return

    st.dataframe(dataframe.head(50), width="stretch")
    st.caption(f"{len(dataframe)} mission row(s) detected.")
    confirmed = st.checkbox(
        "I have checked the mission titles and submission types",
        key="confirm_mission_import",
    )
    if st.button("📥 Import Missions", width="stretch"):
        if not confirmed:
            st.error("Confirm the import first.")
            return
        result = db.import_mission_templates(dataframe.to_dict("records"))
        st.success(
            f"Created {result['Created']} and updated {result['Updated']} mission(s)."
        )
        if result["Errors"]:
            st.warning(f"{len(result['Errors'])} row(s) were not imported.")
            st.code("\n".join(result["Errors"][:50]))


def render_event_assignment(db):
    st.subheader("Add Missions to an Event")
    events = db.get_events()
    templates = db.get_mission_templates()
    if not events:
        st.info("Create an event first.")
        return
    if not templates:
        st.info("Create or import a mission first.")
        return

    event_map = {
        f"{row.get('EventID', '')} | {row.get('EventName', '')}": row
        for row in events
    }
    template_map = {
        f"{row.get('TemplateID', '')} | {row.get('Title', '')}": row
        for row in templates
    }
    event_label = st.selectbox(
        "Event",
        list(event_map),
        index=active_event_index(events),
        key="mission_assignment_event",
    )
    template_label = st.selectbox(
        "Mission Template",
        list(template_map),
        key="mission_assignment_template",
    )
    template = template_map[template_label]
    default_mission_id = str(template.get("TemplateID", ""))
    mission_id = st.text_input(
        "Mission ID for this Event",
        value=default_mission_id,
        key=f"assignment_mission_id_{default_mission_id}",
    )

    st.info(str(template.get("ParticipantInstructions", "")))
    if template.get("VideoURL"):
        display_video_url = get_mission_media_url(template.get("VideoURL"))
        if display_video_url:
            st.video(display_video_url)

    if st.button("➕ Add Mission to Event", width="stretch"):
        result = db.add_template_to_event(
            template_id=template.get("TemplateID", ""),
            event_id=event_map[event_label].get("EventID", ""),
            mission_id=clean_id(mission_id),
        )
        st.success(f"{result['Action']} event mission {result['MissionID']}.")


def render_event_missions(db):
    st.subheader("Event Missions")
    events = db.get_events()
    if not events:
        st.info("No events found.")
        return
    event_map = {
        f"{row.get('EventID', '')} | {row.get('EventName', '')}": row
        for row in events
    }
    selected = st.selectbox(
        "Event",
        list(event_map),
        index=active_event_index(events),
        key="event_mission_list_event",
    )
    event_id = event_map[selected].get("EventID", "")
    missions = db.get_event_missions(event_id)
    if not missions:
        st.info("No missions have been added to this event.")
        return

    display_fields = [
        "MissionID",
        "Title",
        "Status",
        "SubmissionType",
        "Points",
        "VideoURL",
        "TemplateID",
        "Version",
    ]
    st.dataframe(
        [{field: row.get(field, "") for field in display_fields} for row in missions],
        width="stretch",
        hide_index=True,
    )


def show_mission_setup():
    st.title("🧭 Mission Studio")
    st.caption("Create once, reuse across projects, and launch from the Live Event Console.")
    db = GoogleSheetsDB()
    show_flash_message()

    library_tab, import_tab, assign_tab, event_tab = st.tabs([
        "Mission Library",
        "Bulk Import",
        "Add to Event",
        "Event Missions",
    ])
    with library_tab:
        render_template_editor(db)
    with import_tab:
        render_bulk_import(db)
    with assign_tab:
        render_event_assignment(db)
    with event_tab:
        render_event_missions(db)
