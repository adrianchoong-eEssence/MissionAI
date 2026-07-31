import base64
import html
import io
import re

import pandas as pd
import streamlit as st

from data.google_sheets import GoogleSheetsDB, REQUIRED_WORKSHEETS
from data.mission_media import (
    get_mission_media_url,
    upload_mission_media,
)
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


def reference_image_preview_source(reference, uploaded_file=None):
    if uploaded_file is not None:
        content_type = str(
            getattr(uploaded_file, "type", "") or "application/octet-stream"
        )
        encoded = base64.b64encode(uploaded_file.getvalue()).decode("ascii")
        return f"data:{content_type};base64,{encoded}"
    return get_mission_media_url(reference)


def make_qr_png(value):
    import qrcode

    image = qrcode.make(str(value))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def mission_module_name(mission):
    explicit = str((mission or {}).get("Module", "") or "").strip()
    if explicit:
        return explicit
    mission_id = str((mission or {}).get("MissionID", "") or "").upper()
    searchable = " ".join(
        str((mission or {}).get(field, "") or "")
        for field in ("TemplateID", "Title", "Category")
    ).casefold()
    if mission_id.startswith("S") or "sync" in searchable:
        return "Sync AI"
    if mission_id.startswith("C") or "catalyst" in searchable:
        return "Catalyst Challenge"
    if "road" in searchable or "hunt" in searchable:
        return "Road Hunt"
    if mission_id.startswith("M") or "mission ai" in searchable:
        return "Mission AI"
    return "Other"


def event_module_options(missions):
    modules = []
    for mission in missions:
        module = mission_module_name(mission)
        if module not in modules:
            modules.append(module)
    return modules or ["Mission AI"]


def difficulty_options(current):
    value = str(current or "Moderate").strip() or "Moderate"
    options = ["Easy", "Moderate", "Challenging", "Expert"]
    if value not in options:
        options.insert(0, value)
    return options, value


def _mission_editor(db, event_id, selected):
    mission_id = str(selected.get("MissionID", "")).strip().upper()
    form_key = f"event_mission_editor_{event_id}_{mission_id or 'new'}"
    st.markdown(f"## {selected.get('Title', 'Experience Editor')}")
    st.caption("Experience Editor")
    if st.session_state.get("exos_administration_mode"):
        st.caption(f"Experience code: {mission_id}")
    with st.form(form_key):
        st.markdown("#### Basic Details")
        col1, col2 = st.columns(2)
        with col1:
            title = st.text_input("Experience Name", value=str(selected.get("Title", "")))
            if st.session_state.get("exos_administration_mode"):
                code = st.text_input("Experience Code", value=mission_id)
            else:
                code = mission_id
            category = st.text_input("Experience Category", value=str(selected.get("Category", "Mission AI")))
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

        st.markdown("#### Experience Content")
        story = st.text_area("Narrative", value=str(selected.get("Story", "")))
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
        image_url = st.text_input("Experience Image", value=str(selected.get("ImageURL", "")))
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
        saved = st.form_submit_button("Save Experience", width="stretch")

    if saved:
        if not title.strip() or not clean_id(code):
            st.error("Experience Name and Experience Code are required.")
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
        st.session_state["mission_studio_message"] = f"{result['Action']} experience {result['MissionID']}."
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


def _experience_designer(db, event_id, selected):
    mission_id = str(selected.get("MissionID", "")).strip().upper()
    key = f"experience_{event_id}_{mission_id}"
    db.ensure_existing_assets_catalogued()
    character_assets = db.get_assets("Characters")
    mission_image_assets = db.get_assets("Mission Images")
    st.markdown(
        """
        <style>
        .studio-step{font-size:.72rem;font-weight:800;letter-spacing:.18em;color:#B59A37;text-transform:uppercase}
        .studio-heading{font-size:1.4rem;font-weight:800;color:#082D58;margin:.25rem 0 .9rem}
        .phone{max-width:350px;margin:0 auto;background:#071d38;border:9px solid #071d38;border-radius:42px;padding:9px;box-shadow:0 24px 55px rgba(8,45,88,.25)}
        .phone-screen{min-height:640px;border-radius:29px;background:#f5f7fa;overflow:hidden;color:#082D58}
        .phone-top{height:25px;background:#fff;text-align:center}.phone-notch{display:inline-block;width:92px;height:17px;background:#071d38;border-radius:0 0 14px 14px}
        .phone-body{padding:23px 20px 28px}.transmission{font-size:.67rem;letter-spacing:.17em;font-weight:800;color:#B59A37;text-transform:uppercase}
        .phone h2{font-size:1.7rem!important;line-height:1.08;margin:.55rem 0}.phone p{font-family:Arial,sans-serif;font-size:.9rem;line-height:1.48}
        .mission-card{background:#fff;border:1px solid #dce3eb;border-radius:14px;padding:15px;margin:18px 0}
        .mission-label{font-size:.65rem;letter-spacing:.15em;font-weight:800;color:#557089;text-transform:uppercase;margin:8px 0 5px}
        .evidence-row{display:flex;justify-content:space-between;align-items:center;border-top:1px solid #dce3eb;padding-top:15px;margin-top:15px}
        .credit-pill{background:#082D58;color:#fff;border-radius:20px;padding:7px 11px;font-weight:800}
        .character-preview{margin-top:14px;padding:12px;border-radius:15px;background:linear-gradient(145deg,#071d38,#0b4771);color:#fff;text-align:center}
        .character-preview img{display:block;width:100%;max-height:230px;object-fit:contain;border-radius:11px;margin-bottom:8px}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("## Experience Designer")
    st.caption("Shape what participants feel, do, submit and earn.")
    editor, preview = st.columns([1.55, 1], gap="large")
    with editor:
        with st.container(border=True):
            st.markdown('<div class="studio-step">01 · Narrative</div><div class="studio-heading">Set the scene</div>', unsafe_allow_html=True)
            title = st.text_input("Story Title", value=str(selected.get("NarrativeTitle") or selected.get("Title", "")), key=f"{key}_title")
            narrative = st.text_area("Narrative", value=str(selected.get("Story", "")), height=120, key=f"{key}_narrative")
            context = st.text_area("Experience Context", value=str(selected.get("MissionContext") or selected.get("Description", "")), key=f"{key}_context")
            transmission = st.text_area("Transmission", value=str(selected.get("Transmission") or selected.get("Clue", "")), placeholder="Command Centre to field team…", key=f"{key}_transmission")

        with st.container(border=True):
            st.markdown('<div class="studio-step">02 · Experience</div><div class="studio-heading">Design the action</div>', unsafe_allow_html=True)
            types = ["Observe", "Think", "Interact"]
            current_type = str(selected.get("MissionType", "Observe") or "Observe").title()
            current_type = current_type if current_type in types else "Observe"
            mission_type = st.radio("Experience Type", types, horizontal=True, index=types.index(current_type), key=f"{key}_type")
            mission = st.text_area("Experience", value=str(selected.get("ParticipantInstructions") or selected.get("MainQuestion", "")), height=120, key=f"{key}_mission")
            reference = str(selected.get("ReferenceImageURL", ""))
            interaction = str(selected.get("Interaction", ""))
            reasoning = str(selected.get("ReasoningPrompt", ""))
            companion_prompt = str(selected.get("AIPrompt", ""))
            time_limit = safe_int(selected.get("TimeLimitMinutes"), 10)
            if mission_type == "Observe":
                image_by_id = {
                    str(asset.get("AssetID", "")): asset
                    for asset in mission_image_assets
                }
                image_options = [""] + list(image_by_id)
                current_image_id = next(
                    (
                        asset_id for asset_id, asset in image_by_id.items()
                        if str(asset.get("MediaReference", "")).strip()
                        == reference.strip()
                    ),
                    "",
                )
                selected_image_id = st.selectbox(
                    "Select Mission Image",
                    image_options,
                    index=image_options.index(current_image_id),
                    format_func=lambda asset_id: (
                        "None"
                        if not asset_id
                        else str(image_by_id[asset_id].get("Name", "Untitled"))
                    ),
                    key=f"{key}_reference_asset",
                    help="Add or replace reusable images in Administration → Asset Library.",
                )
                resolved_selected_reference = (
                    str(
                        image_by_id[selected_image_id].get(
                            "MediaReference",
                            "",
                        )
                    ).strip()
                    if selected_image_id
                    else ""
                )
                reference_preview = reference_image_preview_source(
                    resolved_selected_reference
                )
                if reference_preview:
                    try:
                        st.image(
                            reference_preview,
                            caption="Reference image preview",
                            width="stretch",
                        )
                    except Exception:
                        st.warning(
                            "This image is saved, but this browser cannot preview "
                            "its format. JPG, PNG, or WEBP gives the widest support."
                        )
                crop_framing_note = st.text_input(
                    "Crop / Framing Note",
                    value=str(selected.get("CropFramingNote", "")),
                    placeholder="Full image, tight crop, detail crop, silhouette, or partial object",
                    key=f"{key}_crop_framing",
                )
                type_guidance = st.text_area("Observation Instructions", value=str(selected.get("EvidenceInstructions", "")), key=f"{key}_observe")
            elif mission_type == "Think":
                resolved_selected_reference = reference
                reference_preview = reference_image_preview_source(reference)
                crop_framing_note = str(selected.get("CropFramingNote", ""))
                companion_prompt = st.text_area("AI Companion Prompt", value=companion_prompt, key=f"{key}_think_ai")
                reasoning = st.text_area("Reasoning Prompt", value=reasoning, key=f"{key}_reason")
                type_guidance = str(selected.get("EvidenceInstructions", ""))
            else:
                resolved_selected_reference = reference
                reference_preview = reference_image_preview_source(reference)
                crop_framing_note = str(selected.get("CropFramingNote", ""))
                interaction = st.text_area("Interaction", value=interaction, key=f"{key}_interaction")
                time_limit = st.slider("Time Limit (minutes)", 0, 180, min(time_limit, 180), key=f"{key}_time")
                type_guidance = str(selected.get("EvidenceInstructions", ""))

        with st.container(border=True):
            st.markdown('<div class="studio-step">03 · Evidence</div><div class="studio-heading">Choose proof of completion</div>', unsafe_allow_html=True)
            evidence_types = ["PHOTO", "VIDEO", "TEXT", "AUDIO", "MULTIPLE"]
            current_evidence = str(selected.get("SubmissionType", "PHOTO") or "PHOTO").upper()
            current_evidence = current_evidence if current_evidence in evidence_types else "TEXT"
            evidence = st.selectbox("Evidence", evidence_types, index=evidence_types.index(current_evidence), format_func=str.title, key=f"{key}_evidence")
            evidence_instructions = st.text_area("Evidence Instructions", value=type_guidance, key=f"{key}_evidence_instructions")
            if evidence in {"PHOTO", "VIDEO", "MULTIPLE"}:
                st.info("Camera preview example · The participant camera opens with experience guidance above the shutter.")

        with st.container(border=True):
            st.markdown('<div class="studio-step">04 · Reward</div><div class="studio-heading">Make completion matter</div>', unsafe_allow_html=True)
            reward1, reward2 = st.columns(2)
            with reward1:
                credits = st.number_input("Credits", min_value=0, value=safe_int(selected.get("CreditValue", selected.get("Points")), 120), step=10, key=f"{key}_credits")
                difficulty_values, difficulty_default = difficulty_options(
                    selected.get("Difficulty", "Moderate")
                )
                difficulty = st.select_slider(
                    "Difficulty",
                    difficulty_values,
                    value=difficulty_default,
                    key=f"{key}_difficulty",
                )
            with reward2:
                estimated_default = min(max(safe_int(selected.get("EstimatedTimeMinutes"), time_limit or 10), 1), 180)
                estimated = st.slider("Estimated Time (minutes)", 1, 180, estimated_default, key=f"{key}_estimate")
                complete_message = st.text_input("Experience Complete Message", value=str(selected.get("MissionCompleteMessage", "Transmission Restored") or "Transmission Restored"), key=f"{key}_complete")
            st.success(f"{complete_message}  ·  +{credits} Credits")

        ai_enabled = st.toggle("Enable AI Companion", value=yes_no(selected.get("AIRequired", selected.get("AIHelpEnabled"))) == "Yes", key=f"{key}_ai_enabled")
        if ai_enabled:
            with st.container(border=True):
                st.markdown('<div class="studio-step">05 · AI Companion</div>', unsafe_allow_html=True)
                stored_character = str(
                    selected.get("CharacterSource", "None") or "None"
                ).strip()
                stored_portrait = str(
                    selected.get("CharacterPortraitURL", "") or ""
                ).strip()
                character_by_id = {
                    str(asset.get("AssetID", "")): asset
                    for asset in character_assets
                }
                character_options = [""] + list(character_by_id)
                current_character_id = next(
                    (
                        asset_id
                        for asset_id, asset in character_by_id.items()
                        if (
                            str(asset.get("MediaReference", "")).strip()
                            == stored_portrait
                            or (
                                not stored_portrait
                                and str(asset.get("Name", "")).strip()
                                == stored_character
                            )
                        )
                    ),
                    "",
                )
                selected_character_id = st.selectbox(
                    "Select Character",
                    character_options,
                    index=character_options.index(current_character_id),
                    format_func=lambda asset_id: (
                        "None"
                        if not asset_id
                        else str(
                            character_by_id[asset_id].get("Name", "Untitled")
                        )
                    ),
                    key=f"{key}_character_asset",
                    help="Manage reusable portraits in Administration → Asset Library.",
                )
                selected_character = (
                    character_by_id.get(selected_character_id, {})
                    if selected_character_id
                    else {}
                )
                character_source = str(
                    selected_character.get("Name", "None") or "None"
                ).strip()
                portrait_reference = str(
                    selected_character.get("MediaReference", "") or ""
                ).strip()
                portrait_preview = reference_image_preview_source(
                    portrait_reference
                )
                if portrait_preview:
                    try:
                        st.image(
                            portrait_preview,
                            caption=f"{character_source} portrait",
                            width="stretch",
                        )
                    except Exception:
                        st.warning(
                            "This portrait is saved, but this browser cannot "
                            "preview its format. JPG, PNG, or WEBP gives the "
                            "widest support."
                        )
                ai_role = st.text_input("Role", value=str(selected.get("AIRole", "")), key=f"{key}_ai_role")
                ai_prompt = st.text_area("Prompt", value=companion_prompt, key=f"{key}_ai_prompt")
                restrictions = st.text_area("Restrictions", value=str(selected.get("AIRestrictions") or selected.get("AIUsageRules", "")), key=f"{key}_restrictions")
                hints = st.text_area("Hints", value="\n".join(str(selected.get(f"Hint{i}", "") or "") for i in range(1, 4)).strip(), help="One hint per line.", key=f"{key}_hints")
        else:
            ai_role, ai_prompt = str(selected.get("AIRole", "")), companion_prompt
            restrictions = str(selected.get("AIRestrictions") or selected.get("AIUsageRules", ""))
            hints = "\n".join(str(selected.get(f"Hint{i}", "") or "") for i in range(1, 4)).strip()
            character_source = str(selected.get("CharacterSource", "None") or "None")
            portrait_reference = str(selected.get("CharacterPortraitURL", "") or "")
            portrait_preview = get_mission_media_url(portrait_reference)

        with st.expander("06 · Facilitator · Hidden from participants"):
            facilitator = st.text_area("Facilitator Intent", value=str(selected.get("FacilitatorIntent") or selected.get("FacilitatorInstructions", "")), key=f"{key}_facilitator")
            learning = st.text_area("Learning Intent", value=str(selected.get("LearningIntent") or selected.get("LearningObjectives", "")), key=f"{key}_learning")
            safety = st.text_area("Safety Notes", value=str(selected.get("SafetyNotes", "")), key=f"{key}_safety")
        saved = st.button("Save Experience", type="primary", width="stretch", key=f"{key}_save")

    with preview:
        st.markdown('<div class="studio-step">Live Preview</div>', unsafe_allow_html=True)
        st.caption("Participant view · updates as you edit")
        clean = lambda value: html.escape(str(value or "")).replace("\n", "<br>")
        image = f'<img src="{clean(reference_preview)}" alt="Reference" style="width:100%;height:auto;border-radius:12px;margin-top:10px">' if reference_preview and mission_type == "Observe" else ""
        character_card = (
            f'<div class="character-preview"><img src="{clean(portrait_preview)}" '
            f'alt="{clean(character_source)}"><strong>{clean(character_source)}</strong>'
            f'<div>Secure contact channel</div></div>'
            if ai_enabled and character_source != "None" and portrait_preview
            else ""
        )
        st.markdown(
            f"""<div class="phone"><div class="phone-screen"><div class="phone-top"><span class="phone-notch"></span></div>
            <div class="phone-body"><div class="transmission">Incoming transmission</div><h2>{clean(title) or "Untitled experience"}</h2>
            <p>{clean(transmission) or "Command Centre is establishing a secure channel…"}</p>{image}
            <div class="mission-card"><div class="mission-label">Narrative</div><p>{clean(narrative) or "Your narrative will appear here."}</p>
            <div class="mission-label">Experience</div><p><strong>{clean(mission) or "Your experience will appear here."}</strong></p>
            <div class="evidence-row"><span><span class="mission-label">Evidence</span><br>{clean(evidence.title())}</span>
            <span class="credit-pill">+{credits} Credits</span></div></div>{character_card}</div></div></div>""",
            unsafe_allow_html=True,
        )

    if saved:
        if not title.strip() or not mission.strip():
            st.error("Story Title and Experience are required.")
            return
        resolved_reference = resolved_selected_reference
        resolved_portrait = portrait_reference
        hint_values = [line.strip() for line in hints.splitlines() if line.strip()][:3]
        payload = dict(selected)
        payload.update({
            "EventID": event_id, "MissionID": mission_id, "Title": title.strip(),
            "NarrativeTitle": title.strip(), "Story": narrative.strip(),
            "MissionContext": context.strip(), "Description": context.strip(),
            "Transmission": transmission.strip(), "Clue": transmission.strip(),
            "MissionType": mission_type, "ParticipantInstructions": mission.strip(),
            "MainQuestion": mission.strip(), "Interaction": interaction.strip(),
            "ReasoningPrompt": reasoning.strip(),
            "ReferenceImageURL": resolved_reference.strip(),
            "CropFramingNote": crop_framing_note.strip(),
            "EvidenceRequired": "Yes", "SubmissionType": evidence,
            "EvidenceInstructions": evidence_instructions.strip(),
            "CreditValue": int(credits), "Points": int(credits), "MaximumCredits": int(credits),
            "Difficulty": difficulty, "EstimatedTimeMinutes": int(estimated),
            "MissionCompleteMessage": complete_message.strip(), "TimeLimitMinutes": int(time_limit),
            "AIRequired": "Yes" if ai_enabled else "No", "AIHelpEnabled": "Yes" if ai_enabled else "No",
            "AIRole": ai_role.strip(), "AIPrompt": ai_prompt.strip(),
            "AIRestrictions": restrictions.strip(), "AIUsageRules": restrictions.strip(),
            "CharacterSource": character_source,
            "CharacterPortraitURL": resolved_portrait.strip(),
            "Hint1": hint_values[0] if len(hint_values) > 0 else "",
            "Hint2": hint_values[1] if len(hint_values) > 1 else "",
            "Hint3": hint_values[2] if len(hint_values) > 2 else "",
            "FacilitatorIntent": facilitator.strip(), "FacilitatorInstructions": facilitator.strip(),
            "LearningIntent": learning.strip(), "LearningObjectives": learning.strip(),
            "SafetyNotes": safety.strip(),
        })
        result = db.upsert_event_mission(payload)
        st.session_state["mission_studio_message"] = f"{result['Action']} experience {result['MissionID']}."
        st.rerun()


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
    event_id = str(event_map[event_label].get("EventID", "")).strip()
    refresh_col, count_col = st.columns([1, 2])
    if refresh_col.button(
        "Refresh Experiences",
        key=f"refresh_experiences_{event_id}",
        width="stretch",
    ):
        db.clear_cache()
        st.session_state.pop("mission_studio_selected_mission", None)
        st.rerun()
    migration_key = f"mission_editor_backfill_{event_id}"
    if event_id == "EVT-0004" and not st.session_state.get(migration_key):
        db.backfill_event_mission_editor_fields(
            event_id, ["M01", "M02", "M03", "M04"],
        )
        st.session_state[migration_key] = True
    all_missions = db.get_event_missions(event_id)
    modules = event_module_options(all_missions)
    preferred_module = (
        "Operation: The Labyrinth"
        if event_id.casefold() == "evt-0004"
        and "Operation: The Labyrinth" in modules
        else modules[0]
    )
    module_key = f"mission_studio_module_{event_id}"
    if st.session_state.get(module_key) not in modules:
        st.session_state[module_key] = preferred_module
    module = st.selectbox(
        "Module",
        modules,
        key=module_key,
    )
    missions = [
        row for row in all_missions
        if mission_module_name(row).casefold() == module.casefold()
    ]
    count_col.metric("Visible Experiences", len(missions))

    selected_id = str(st.session_state.get("mission_studio_selected_mission", ""))
    selected = next(
        (row for row in missions if str(row.get("MissionID")) == selected_id),
        None,
    )
    if selected_id and selected is None:
        st.session_state.pop("mission_studio_selected_mission", None)

    if selected:
        if st.button("← Back to Experiences", type="secondary"):
            st.session_state.pop("mission_studio_selected_mission", None)
            st.rerun()
        _experience_designer(db, event_id, selected)
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
        return

    st.markdown("## Experiences")
    st.caption("Choose an experience to start authoring.")
    if not missions:
        st.info("No experiences belong to this event and module yet.")
    for row_index, mission in enumerate(missions):
        with st.container(border=True):
            title_col, action_col = st.columns([5, 1])
            with title_col:
                st.markdown(f"### {mission.get('Title', 'Untitled Experience')}")
                status = str(mission.get("Status", "DRAFT") or "DRAFT").title()
                category = str(mission.get("Category", "") or "").strip()
                st.caption(" · ".join(item for item in (category, status) if item))
                if st.session_state.get("exos_administration_mode"):
                    st.caption(f"Experience code: {mission.get('MissionID', '')}")
            with action_col:
                if st.button(
                    "Edit",
                    key=(
                        f"edit_event_mission_{event_id}_"
                        f"{mission.get('MissionID')}_{row_index}"
                    ),
                    width="stretch",
                ):
                    st.session_state["mission_studio_selected_mission"] = str(
                        mission.get("MissionID", "")
                    )
                    st.rerun()

    with st.expander("New Experience"):
        creation_mode = st.radio(
            "Create using", ["Create Blank Experience", "Copy from Experience Library", "Duplicate Existing Event Experience"],
            key=f"new_mission_mode_{event_id}",
        )
        if creation_mode == "Create Blank Experience":
            if st.button("Create Blank Experience", width="stretch"):
                new_id = db.generate_next_event_mission_id(event_id)
                db.upsert_event_mission({
                    "EventID": event_id, "MissionID": new_id, "Title": "New Experience",
                    "Module": module, "Status": "DRAFT", "DisplayOrder": len(missions) + 1,
                })
                st.session_state["mission_studio_selected_mission"] = new_id
                st.rerun()
        elif creation_mode == "Copy from Experience Library":
            templates = db.get_mission_templates()
            template_map = {f"{row.get('TemplateID')} | {row.get('Title')}": row for row in templates}
            if template_map:
                template_label = st.selectbox("Master Experience", list(template_map))
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
                source_label = st.selectbox("Event Experience", list(source_map))
                if st.button("Duplicate Experience", width="stretch"):
                    result = db.duplicate_event_mission(event_id, source_map[source_label]["MissionID"])
                    st.session_state["mission_studio_selected_mission"] = result["MissionID"]
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
    st.subheader("Experience Library")
    templates = db.get_mission_templates(include_archived=True)
    template_map = {
        f"{row.get('TemplateID', '')} | {row.get('Title', '')}": row
        for row in templates
    }
    selected_label = st.selectbox(
        "Create or Edit",
        ["➕ Create New Experience"] + list(template_map.keys()),
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
                "Experience Name *",
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

        st.markdown("#### Experience Guidance")
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

        submitted = st.form_submit_button("💾 Save Experience", width="stretch")

    if submitted:
        if not title.strip():
            st.error("Experience Name is required.")
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
            st.error(f"Experience media upload failed: {error}")
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
    st.subheader("Bulk Import Experiences")
    st.caption("Upload CSV or Excel. Existing Template IDs are updated; new IDs are created.")

    headers = REQUIRED_WORKSHEETS["MissionTemplates"]
    example = pd.DataFrame([
        {
            "TemplateID": "MT-EXAMPLE",
            "Title": "Example Experience",
            "Story": "Experience context goes here.",
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
        "Experience File",
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
    st.caption(f"{len(dataframe)} experience row(s) detected.")
    confirmed = st.checkbox(
        "I have checked the mission titles and submission types",
        key="confirm_mission_import",
    )
    if st.button("📥 Import Experiences", width="stretch"):
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
    st.subheader("Add Experiences to an Event")
    events = db.get_events()
    templates = db.get_mission_templates()
    if not events:
        st.info("Create an event first.")
        return
    if not templates:
        st.info("Create or import an experience first.")
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
        "Experience Template",
        list(template_map),
        key="mission_assignment_template",
    )
    template = template_map[template_label]
    default_mission_id = str(template.get("TemplateID", ""))
    mission_id = st.text_input(
        "Experience ID for this Event",
        value=default_mission_id,
        key=f"assignment_mission_id_{default_mission_id}",
    )

    st.info(str(template.get("ParticipantInstructions", "")))
    if template.get("VideoURL"):
        display_video_url = get_mission_media_url(template.get("VideoURL"))
        if display_video_url:
            st.video(display_video_url)

    if st.button("➕ Add Experience to Event", width="stretch"):
        result = db.add_template_to_event(
            template_id=template.get("TemplateID", ""),
            event_id=event_map[event_label].get("EventID", ""),
            mission_id=clean_id(mission_id),
        )
        st.success(f"{result['Action']} event experience {result['MissionID']}.")


def render_event_missions(db):
    st.subheader("Event Experiences")
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
        st.info("No experiences have been added to this event.")
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
    st.title("🧭 Experience Studio")
    st.caption("Create once, reuse across projects, and launch from the Live Event Console.")
    db = GoogleSheetsDB()
    show_flash_message()

    event_tab, library_tab, import_tab, assign_tab = st.tabs([
        "Event Experiences",
        "Master Experience Templates",
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
