import io
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

EVIDENCE_TYPES = ["TEXT", "PHOTO", "VIDEO", "AUDIO", "QR", "GPS", "MULTIPLE"]


def yes_no(value, default="No"):
    return "Yes" if str(value or default).strip().upper() in {
        "YES", "TRUE", "1", "ON", "ACTIVE", "MANDATORY",
    } else "No"


def make_qr_png(value):
    import qrcode

    image = qrcode.make(str(value))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _mission_editor(db, event_id, selected):
    mission_id = str(selected.get("MissionID", "")).strip().upper()
    form_key = f"event_mission_editor_{event_id}_{mission_id or 'new'}"
    st.markdown(f"### {mission_id or 'New Mission'} Editor")
    with st.form(form_key):
        st.markdown("#### Basic Details")
        col1, col2 = st.columns(2)
        with col1:
            title = st.text_input("Mission Name", value=str(selected.get("Title", "")))
            code = st.text_input("Mission Code", value=mission_id)
            category = st.text_input("Mission Category", value=str(selected.get("Category", "Mission AI")))
            status = st.selectbox(
                "Active / Inactive", ["ACTIVE", "INACTIVE"],
                index=0 if str(selected.get("Status", "ACTIVE")).upper() not in {"INACTIVE", "CLOSED"} else 1,
            )
        with col2:
            mandatory = st.selectbox(
                "Mandatory / Optional", ["MANDATORY", "OPTIONAL"],
                index=0 if yes_no(selected.get("IsMandatory"), "Yes") == "Yes" else 1,
            )
            display_order = st.number_input(
                "Display Order", min_value=1,
                value=safe_int(selected.get("DisplayOrder"), 1),
            )
            module = st.text_input("Module", value=str(selected.get("Module", "Mission AI")))

        st.markdown("#### Mission Content")
        story = st.text_area("Mission Story", value=str(selected.get("Story", "")))
        clue = st.text_area("Treasure Hunt Clue", value=str(selected.get("Clue", "")))
        question = st.text_area("Main Question", value=str(selected.get("MainQuestion", "")))
        answer = st.text_input("Correct Answer", value=str(selected.get("Answer", "")))
        alternatives = st.text_area(
            "Alternative Accepted Answers",
            value=str(selected.get("AlternativeAnswers", "")),
            help="Enter one answer per line.",
        )
        evaluation = st.text_area(
            "Facilitator Evaluation Notes",
            value=str(selected.get("FacilitatorEvaluationNotes", "")),
        )

        st.markdown("#### AI Companion")
        ai1, ai2 = st.columns(2)
        with ai1:
            ai_required = st.checkbox(
                "AI Required", value=yes_no(selected.get("AIRequired", selected.get("AIHelpEnabled"))) == "Yes",
            )
            ai_role = st.text_input("AI Role", value=str(selected.get("AIRole", "")))
            max_hints = st.number_input(
                "Maximum AI Hints", min_value=0,
                value=safe_int(selected.get("MaxAIHints"), 3),
            )
        with ai2:
            ai_prompt = st.text_area("AI Prompt", value=str(selected.get("AIPrompt", "")))
            ai_hint_prompt = st.text_area("AI Hint Prompt", value=str(selected.get("AIHintPrompt", "")))
        ai_rules = st.text_area("AI Usage Rules", value=str(selected.get("AIUsageRules", "")))

        st.markdown("#### Hints")
        hint1 = st.text_input("Hint 1", value=str(selected.get("Hint1", "")))
        hint2 = st.text_input("Hint 2", value=str(selected.get("Hint2", "")))
        hint3 = st.text_input("Hint 3", value=str(selected.get("Hint3", "")))
        hint_unlock = st.text_area("Hint Unlock Rules", value=str(selected.get("HintUnlockRules", "")))
        hint_credit_penalty = st.number_input(
            "Hint Credit Penalty", min_value=0,
            value=safe_int(selected.get("HintCreditPenalty"), 0),
        )

        st.markdown("#### Location")
        checkpoint = st.text_input("Checkpoint Name", value=str(selected.get("CheckpointName", "")))
        location_description = st.text_area(
            "Location Description", value=str(selected.get("LocationDescription", "")),
        )
        gps1, gps2, gps3 = st.columns(3)
        with gps1:
            latitude = st.number_input(
                "Latitude", min_value=-90.0, max_value=90.0,
                value=float(selected.get("Latitude") or 0), format="%.7f",
            )
        with gps2:
            longitude = st.number_input(
                "Longitude", min_value=-180.0, max_value=180.0,
                value=float(selected.get("Longitude") or 0), format="%.7f",
            )
        with gps3:
            geofence = st.number_input(
                "Geofence Radius (metres)", min_value=0,
                value=safe_int(selected.get("GeofenceRadius"), 50),
            )
        gps_required = st.checkbox(
            "GPS Required", value=yes_no(selected.get("GPSRequired")) == "Yes",
        )

        st.markdown("#### QR")
        qr_required = st.checkbox(
            "QR Required", value=yes_no(selected.get("QRRequired")) == "Yes",
        )
        qr_value = st.text_input("QR Code Value", value=str(selected.get("QRCodeValue", "")))
        qr_rule = st.text_area("QR Validation Rule", value=str(selected.get("QRValidationRule", "")))

        st.markdown("#### Evidence")
        evidence_required = st.checkbox(
            "Evidence Required", value=yes_no(selected.get("EvidenceRequired"), "Yes") == "Yes",
        )
        current_evidence = str(selected.get("SubmissionType", "TEXT") or "TEXT").upper()
        if current_evidence not in EVIDENCE_TYPES:
            current_evidence = "TEXT"
        evidence_type = st.selectbox(
            "Evidence Type", EVIDENCE_TYPES, index=EVIDENCE_TYPES.index(current_evidence),
        )
        evidence_instructions = st.text_area(
            "Evidence Instructions", value=str(selected.get("EvidenceInstructions", "")),
        )
        maximum_uploads = st.number_input(
            "Maximum Uploads", min_value=0,
            value=safe_int(selected.get("MaximumUploads"), 1),
        )

        st.markdown("#### Scoring and Credits")
        score1, score2, score3 = st.columns(3)
        with score1:
            credit_value = st.number_input("Credit Value", min_value=0, value=safe_int(selected.get("CreditValue", selected.get("Points")), 100))
            maximum_credits = st.number_input("Maximum Credits", min_value=0, value=safe_int(selected.get("MaximumCredits", selected.get("Points")), 100))
        with score2:
            time_bonus = st.number_input("Time Bonus", min_value=0, value=safe_int(selected.get("TimeBonus"), 0))
            hint_penalty = st.number_input("Hint Penalty", min_value=0, value=safe_int(selected.get("HintPenalty"), 0))
        with score3:
            wrong_penalty = st.number_input("Wrong Answer Penalty", min_value=0, value=safe_int(selected.get("WrongAnswerPenalty"), 0))
            manual_review = st.checkbox("Manual Review Required", value=yes_no(selected.get("ManualReviewRequired"), "Yes") == "Yes")
            auto_approval = st.checkbox("Auto Approval Allowed", value=yes_no(selected.get("AutoApprovalAllowed")) == "Yes")

        st.markdown("#### Timing")
        time_limit = st.number_input(
            "Time Limit (minutes)", min_value=0,
            value=safe_int(selected.get("TimeLimitMinutes"), 10),
        )
        availability_start = st.text_input(
            "Availability Start", value=str(selected.get("AvailabilityStart", "")),
            placeholder="YYYY-MM-DD HH:MM",
        )
        availability_end = st.text_input(
            "Availability End", value=str(selected.get("AvailabilityEnd", "")),
            placeholder="YYYY-MM-DD HH:MM",
        )
        countdown = st.checkbox(
            "Countdown Enabled", value=yes_no(selected.get("CountdownEnabled"), "Yes") == "Yes",
        )

        st.markdown("#### Media")
        image_url = st.text_input("Mission Image", value=str(selected.get("ImageURL", "")))
        reference_image = st.text_input(
            "Reference Image", value=str(selected.get("ReferenceImageURL", "")),
        )
        uploaded_image = st.file_uploader(
            "Upload Image", type=["jpg", "jpeg", "png", "webp", "gif"],
            key=f"event_mission_image_{event_id}_{mission_id or 'new'}",
        )
        remove_image = st.checkbox("Remove Image")

        st.markdown("#### Debrief")
        debrief = st.text_area(
            "Debrief Question", value=str(selected.get("DebriefQuestions", "")),
        )
        learning_point = st.text_area(
            "Learning Point", value=str(selected.get("LearningPoint", "")),
        )
        facilitator_debrief = st.text_area(
            "Facilitator Debrief Notes",
            value=str(selected.get("FacilitatorDebriefNotes", "")),
        )
        saved = st.form_submit_button("Save Mission", width="stretch")

    if saved:
        if not title.strip() or not clean_id(code):
            st.error("Mission Name and Mission Code are required.")
            return
        resolved_image = "" if remove_image else image_url.strip()
        if uploaded_image is not None:
            resolved_image = upload_mission_media(
                uploaded_image, f"{event_id}-{clean_id(code)}", "image",
            )
        payload = dict(selected)
        payload.update({
            "EventID": event_id, "MissionID": clean_id(code), "Title": title.strip(),
            "Category": category.strip(), "Status": status,
            "IsMandatory": "Yes" if mandatory == "MANDATORY" else "No",
            "DisplayOrder": int(display_order), "Module": module.strip() or "Mission AI",
            "Story": story.strip(), "Clue": clue.strip(), "MainQuestion": question.strip(),
            "Answer": answer.strip(), "AlternativeAnswers": alternatives.strip(),
            "FacilitatorEvaluationNotes": evaluation.strip(),
            "AIRequired": "Yes" if ai_required else "No", "AIHelpEnabled": "Yes" if ai_required else "No",
            "AIPrompt": ai_prompt.strip(), "AIRole": ai_role.strip(),
            "AIHintPrompt": ai_hint_prompt.strip(), "MaxAIHints": int(max_hints),
            "AIUsageRules": ai_rules.strip(), "Hint1": hint1.strip(), "Hint2": hint2.strip(),
            "Hint3": hint3.strip(), "HintUnlockRules": hint_unlock.strip(),
            "HintCreditPenalty": int(hint_credit_penalty), "CheckpointName": checkpoint.strip(),
            "LocationDescription": location_description.strip(), "Latitude": latitude,
            "Longitude": longitude, "GeofenceRadius": int(geofence),
            "GPSRequired": "Yes" if gps_required else "No", "QRRequired": "Yes" if qr_required else "No",
            "QRCodeValue": qr_value.strip(), "QRValidationRule": qr_rule.strip(),
            "EvidenceRequired": "Yes" if evidence_required else "No",
            "SubmissionType": evidence_type, "EvidenceInstructions": evidence_instructions.strip(),
            "MaximumUploads": int(maximum_uploads), "CreditValue": int(credit_value),
            "Points": int(maximum_credits), "MaximumCredits": int(maximum_credits),
            "TimeBonus": int(time_bonus), "HintPenalty": int(hint_penalty),
            "WrongAnswerPenalty": int(wrong_penalty),
            "ManualReviewRequired": "Yes" if manual_review else "No",
            "AutoApprovalAllowed": "Yes" if auto_approval else "No",
            "TimeLimitMinutes": int(time_limit), "AvailabilityStart": availability_start.strip(),
            "AvailabilityEnd": availability_end.strip(),
            "CountdownEnabled": "Yes" if countdown else "No", "ImageURL": resolved_image,
            "ReferenceImageURL": reference_image.strip(), "DebriefQuestions": debrief.strip(),
            "LearningPoint": learning_point.strip(),
            "FacilitatorDebriefNotes": facilitator_debrief.strip(),
            "Description": story.strip(), "ParticipantInstructions": question.strip() or story.strip(),
        })
        result = db.upsert_event_mission(payload)
        st.session_state["mission_studio_message"] = f"{result['Action']} mission {result['MissionID']}."
        st.rerun()

    if qr_value:
        st.button("Generate QR Code", key=f"generate_qr_{event_id}_{mission_id}")
        st.markdown("##### Generated QR Code")
        qr_png = make_qr_png(qr_value)
        st.image(qr_png, width=220)
        st.download_button(
            "Download QR Code", data=qr_png,
            file_name=f"{event_id}-{mission_id or 'mission'}-qr.png",
            mime="image/png",
        )


def render_event_mission_editor(db):
    events = db.get_events()
    if not events:
        st.info("Create an event first.")
        return
    event_map = {f"{row.get('EventID', '')} | {row.get('EventName', '')}": row for row in events}
    requested_event = str(st.session_state.pop("mission_studio_event_filter", ""))
    options = list(event_map)
    default_index = active_event_index(events)
    if requested_event:
        default_index = next(
            (index for index, label in enumerate(options) if label.startswith(f"{requested_event} |")),
            default_index,
        )
    event_label = st.selectbox("Event", options, index=default_index, key="mission_studio_event")
    event_id = str(event_map[event_label].get("EventID", ""))
    migration_key = f"mission_editor_backfill_{event_id}"
    if event_id == "EVT-0004" and not st.session_state.get(migration_key):
        db.backfill_event_mission_editor_fields(
            event_id, ["M01", "M02", "M03", "M04"],
        )
        st.session_state[migration_key] = True
    module = st.selectbox("Module", ["Mission AI"], key="mission_studio_module")
    missions = [
        row for row in db.get_event_missions(event_id)
        if str(row.get("Module", "Mission AI") or "Mission AI") == module
    ]

    st.markdown("### Event Missions")
    for row_index, mission in enumerate(missions):
        cols = st.columns([1, 4, 1, 1])
        cols[0].write(str(mission.get("MissionID", "")))
        cols[1].write(str(mission.get("Title", "")))
        cols[2].write(str(mission.get("Status", "")))
        if cols[3].button(
            "Open",
            key=(
                f"open_event_mission_{event_id}_"
                f"{mission.get('MissionID')}_{row_index}"
            ),
        ):
            st.session_state["mission_studio_selected_mission"] = str(mission.get("MissionID", ""))
            st.rerun()

    with st.expander("New Mission"):
        creation_mode = st.radio(
            "Create using", ["Create Blank Mission", "Copy from Mission Library", "Duplicate Existing Event Mission"],
            key=f"new_mission_mode_{event_id}",
        )
        if creation_mode == "Create Blank Mission":
            if st.button("Create Blank Mission", width="stretch"):
                new_id = db.generate_next_event_mission_id(event_id)
                db.upsert_event_mission({
                    "EventID": event_id, "MissionID": new_id, "Title": "New Mission",
                    "Module": module, "Status": "DRAFT", "DisplayOrder": len(missions) + 1,
                })
                st.session_state["mission_studio_selected_mission"] = new_id
                st.rerun()
        elif creation_mode == "Copy from Mission Library":
            templates = db.get_mission_templates()
            template_map = {f"{row.get('TemplateID')} | {row.get('Title')}": row for row in templates}
            if template_map:
                template_label = st.selectbox("Master Mission", list(template_map))
                if st.button("Copy to Event", width="stretch"):
                    new_id = db.generate_next_event_mission_id(event_id)
                    db.add_template_to_event(template_map[template_label]["TemplateID"], event_id, new_id)
                    copied = db.get_mission(event_id, new_id)
                    copied.update({"Module": module, "DisplayOrder": len(missions) + 1})
                    db.upsert_event_mission(copied)
                    st.session_state["mission_studio_selected_mission"] = new_id
                    st.rerun()
        else:
            source_map = {f"{row.get('MissionID')} | {row.get('Title')}": row for row in missions}
            if source_map:
                source_label = st.selectbox("Event Mission", list(source_map))
                if st.button("Duplicate Mission", width="stretch"):
                    result = db.duplicate_event_mission(event_id, source_map[source_label]["MissionID"])
                    st.session_state["mission_studio_selected_mission"] = result["MissionID"]
                    st.rerun()

    if missions:
        order = st.multiselect(
            "Mission Order (select all in desired order)",
            [str(row.get("MissionID")) for row in missions],
            default=[str(row.get("MissionID")) for row in missions],
        )
        if st.button("Save Mission Order") and len(order) == len(missions):
            db.reorder_event_missions(event_id, order)
            st.success("Event-specific mission order saved.")

    selected_id = str(st.session_state.get("mission_studio_selected_mission", ""))
    selected = next((row for row in missions if str(row.get("MissionID")) == selected_id), None)
    if selected:
        st.divider()
        _mission_editor(db, event_id, selected)
        action1, action2, action3 = st.columns(3)
        new_status = "INACTIVE" if str(selected.get("Status", "")).upper() == "ACTIVE" else "ACTIVE"
        if action1.button(f"Set {new_status.title()}", width="stretch"):
            changed = dict(selected)
            changed["Status"] = new_status
            db.upsert_event_mission(changed)
            st.rerun()
        if action2.button("Duplicate", width="stretch"):
            db.duplicate_event_mission(event_id, selected_id)
            st.rerun()
        confirmed = action3.checkbox("Confirm delete", key=f"confirm_delete_{event_id}_{selected_id}")
        if action3.button("Delete", width="stretch", disabled=not confirmed):
            db.delete_event_mission(event_id, selected_id)
            st.session_state.pop("mission_studio_selected_mission", None)
            st.rerun()


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

    event_tab, library_tab, import_tab, assign_tab = st.tabs([
        "Event Missions",
        "Master Mission Templates",
        "Bulk Import",
        "Add to Event",
    ])
    with event_tab:
        render_event_mission_editor(db)
    with library_tab:
        render_template_editor(db)
    with import_tab:
        render_bulk_import(db)
    with assign_tab:
        render_event_assignment(db)
