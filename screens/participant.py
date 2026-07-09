import uuid
from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from ai.facilitator import ask_facilitator
from data.google_drive import upload_photo
from data.google_sheets import GoogleSheetsDB


COUNTRY_LANGUAGE_PROMPTS = {
    "Japan": "Find your team. You may greet them with: Konnichiwa.",
    "Malaysia": "Find your team. You may greet them with: Apa khabar.",
    "France": "Find your team. You may greet them with: Bonjour.",
    "India": "Find your team. You may greet them with: Namaste.",
    "Thailand": "Find your team. You may greet them with: Sawadee.",
    "China": "Find your team. You may greet them with: Ni hao.",
}


def reset_session():
    keys = [
        "participant_event_id",
        "participant_name",
        "participant_team",
        "participant_points",
        "participant_event_name",
        "ai_name",
        "ai_personality",
        "ai_greeting",
    ]

    for key in keys:
        if key in st.session_state:
            del st.session_state[key]


def normalise_submission_type(mission):
    raw_type = str(mission.get("SubmissionType", "") or "").strip().upper()
    title = str(mission.get("Title", "") or "").strip().upper()
    description = str(mission.get("Description", "") or "").strip().upper()
    combined = f"{raw_type} {title} {description}"

    if "PIPELINE" in combined or "CUSTOMER JOURNEY" in combined:
        return "PIPELINE"

    if "HELIUM" in combined:
        return "HELIUM"

    if "KEY" in combined and "PUNCH" in combined:
        return "KEYPUNCH"

    if "CATALYST" in combined:
        return "CATALYST"

    if "NASI" in combined or "REFLECTION" in combined:
        return "NASI"

    if raw_type in ["PHOTO", "IMAGE"]:
        return "PHOTO"

    if raw_type in ["TEXT", "REFLECTION"]:
        return "TEXT"

    if raw_type in ["NONE", "NO SUBMISSION"]:
        return "NONE"

    return raw_type or "PHOTO"


def render_team_assignment_card():
    team = st.session_state.get("participant_team", "")
    instruction = COUNTRY_LANGUAGE_PROMPTS.get(
        team,
        "Find your team members and gather together.",
    )

    st.markdown(
        f"""
        <div style="
            padding: 24px;
            border-radius: 22px;
            background: linear-gradient(135deg, #0f172a, #1e293b);
            color: white;
            text-align: center;
            margin-bottom: 18px;
        ">
            <div style="font-size: 18px; opacity: 0.8;">Mission Assignment</div>
            <div style="font-size: 46px; font-weight: 900; margin-top: 8px;">{team}</div>
            <div style="font-size: 18px; margin-top: 12px; opacity: 0.9;">{instruction}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_existing_submission(existing_submission):
    st.success("✅ Your team has already submitted this mission.")

    submitted_at = existing_submission.get("SubmittedAt", "")
    if submitted_at:
        st.caption(f"Submitted at: {submitted_at}")

    payload = existing_submission.get("ImageURL", "")

    if not payload:
        return

    if str(payload).startswith("data:image"):
        try:
            st.image(payload, width="stretch")
        except Exception:
            st.warning("Submission image could not be displayed.")
    else:
        st.info(payload)


def save_text_submission(db, mission, payload):
    db.save_submission(
        submission_id=str(uuid.uuid4()),
        event_id=st.session_state["participant_event_id"],
        mission_id=mission["MissionID"],
        team_name=st.session_state["participant_team"],
        participant_name=st.session_state["participant_name"],
        image_url=payload,
        drive_file_id="TEXT-SUBMISSION",
        submitted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def render_pipeline_form(db, mission):
    st.subheader("📊 Customer Journey Results")
    st.write("Submit your team's result after the official run.")

    delivered = st.number_input(
        "Customers Delivered / Closed Cases",
        min_value=0,
        value=0,
        step=1,
    )

    lost = st.number_input(
        "Lost Customers / Dropped Marbles",
        min_value=0,
        value=0,
        step=1,
    )

    if st.button("📤 Submit Pipeline Results", width="stretch"):
        payload = (
            "PIPELINE RESULTS\n"
            f"Team: {st.session_state['participant_team']}\n"
            f"Delivered Customers: {delivered}\n"
            f"Lost Customers: {lost}"
        )

        save_text_submission(db, mission, payload)

        st.success("✅ Pipeline results submitted.")
        st.balloons()
        st.rerun()


def render_helium_form(db, mission):
    st.subheader("🪄 Taking Ownership Together")
    st.write("Submit your team's completion status after Helium Stick.")

    completed = st.radio(
        "Did your team complete the Helium Stick challenge?",
        ["Yes", "No"],
        horizontal=True,
    )

    if st.button("📤 Submit Helium Stick Result", width="stretch"):
        payload = (
            "HELIUM STICK RESULT\n"
            f"Team: {st.session_state['participant_team']}\n"
            f"Completed: {completed}"
        )

        save_text_submission(db, mission, payload)

        st.success("✅ Helium Stick result submitted.")
        st.balloons()
        st.rerun()


def render_keypunch_form(db, mission):
    st.subheader("⚡ Key Punch")
    st.write("Submit your team's OFFICIAL attempt.")

    highest_number = st.number_input(
        "Highest Number Reached Within 60 Seconds",
        min_value=0,
        max_value=30,
        value=0,
        step=1,
    )

    if st.button("📤 Submit Key Punch Result", width="stretch"):
        payload = (
            "KEY PUNCH RESULT\n"
            f"Team: {st.session_state['participant_team']}\n"
            f"Highest Number Reached: {highest_number}"
        )

        save_text_submission(db, mission, payload)

        st.success("✅ Key Punch submitted.")
        st.balloons()
        st.rerun()


def render_catalyst_form(db, mission):
    st.subheader("⚙️ Creating Enterprise Success")
    st.write("Submit your team's Catalyst Challenge status.")

    completed = st.radio(
        "Did your section complete?",
        ["Yes", "No"],
        horizontal=True,
    )

    uploaded_image = st.file_uploader(
        "Optional Final Structure Photo",
        type=["jpg", "jpeg", "png"],
    )

    if uploaded_image is not None:
        st.image(uploaded_image, width="stretch")

    if st.button("📤 Submit Catalyst Status", width="stretch"):
        if uploaded_image is not None:
            drive = upload_photo(
                event_id=st.session_state["participant_event_id"],
                mission_id=mission["MissionID"],
                team_name=st.session_state["participant_team"],
                participant_name=st.session_state["participant_name"],
                uploaded_file=uploaded_image,
            )

            payload = (
                "CATALYST STATUS\n"
                f"Team: {st.session_state['participant_team']}\n"
                f"Completed: {completed}\n"
                f"Photo: {drive['url']}"
            )

            drive_file_id = drive["file_id"]
        else:
            payload = (
                "CATALYST STATUS\n"
                f"Team: {st.session_state['participant_team']}\n"
                f"Completed: {completed}\n"
                "Photo: Not submitted"
            )

            drive_file_id = "TEXT-SUBMISSION"

        db.save_submission(
            submission_id=str(uuid.uuid4()),
            event_id=st.session_state["participant_event_id"],
            mission_id=mission["MissionID"],
            team_name=st.session_state["participant_team"],
            participant_name=st.session_state["participant_name"],
            image_url=payload,
            drive_file_id=drive_file_id,
            submitted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        st.success("✅ Catalyst status submitted.")
        st.balloons()
        st.rerun()


def render_nasi_form(db, mission):
    st.subheader("📝 NASI Reflection")
    st.write("Submit your team's final reflection.")

    new_ideas = st.text_area(
        "N — New Ideas",
        placeholder="What new ideas did your team discover?",
    )

    areas = st.text_area(
        "A — Areas for Improvement",
        placeholder="What should the enterprise improve?",
    )

    strengths = st.text_area(
        "S — Strengths",
        placeholder="What strengths should the team protect and continue?",
    )

    implementation = st.text_area(
        "I — Implementation",
        placeholder="What is one action your team will implement next?",
    )

    if st.button("📤 Submit NASI Reflection", width="stretch"):
        if not any([
            new_ideas.strip(),
            areas.strip(),
            strengths.strip(),
            implementation.strip(),
        ]):
            st.warning("Please enter at least one reflection before submitting.")
            st.stop()

        payload = (
            "NASI REFLECTION\n"
            f"Team: {st.session_state['participant_team']}\n\n"
            f"N - New Ideas:\n{new_ideas.strip() or '-'}\n\n"
            f"A - Areas for Improvement:\n{areas.strip() or '-'}\n\n"
            f"S - Strengths:\n{strengths.strip() or '-'}\n\n"
            f"I - Implementation:\n{implementation.strip() or '-'}"
        )

        save_text_submission(db, mission, payload)

        st.success("✅ NASI reflection submitted.")
        st.balloons()
        st.rerun()


def render_text_form(db, mission):
    st.subheader("📝 Team Response")

    response = st.text_area(
        "Submit your team's response",
        placeholder="Type your team's response here.",
    )

    if st.button("📤 Submit Response", width="stretch"):
        if not response.strip():
            st.warning("Please enter a response before submitting.")
            st.stop()

        payload = (
            "TEXT RESPONSE\n"
            f"Team: {st.session_state['participant_team']}\n"
            f"Response: {response.strip()}"
        )

        save_text_submission(db, mission, payload)

        st.success("✅ Response submitted.")
        st.balloons()
        st.rerun()


def render_photo_form(db, mission):
    st.subheader("📸 Mission Submission")

    uploaded_image = st.file_uploader(
        "Choose Photo",
        type=["jpg", "jpeg", "png"],
    )

    if uploaded_image is not None:
        st.image(uploaded_image, width="stretch")

        if st.button("📤 Submit Mission", width="stretch"):
            with st.spinner("Submitting mission..."):
                drive = upload_photo(
                    event_id=st.session_state["participant_event_id"],
                    mission_id=mission["MissionID"],
                    team_name=st.session_state["participant_team"],
                    participant_name=st.session_state["participant_name"],
                    uploaded_file=uploaded_image,
                )

                db.save_submission(
                    submission_id=str(uuid.uuid4()),
                    event_id=st.session_state["participant_event_id"],
                    mission_id=mission["MissionID"],
                    team_name=st.session_state["participant_team"],
                    participant_name=st.session_state["participant_name"],
                    image_url=drive["url"],
                    drive_file_id=drive["file_id"],
                    submitted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )

            st.success("✅ Mission submitted successfully.")
            st.balloons()
            st.rerun()


def render_submission_form(db, mission):
    submission_type = normalise_submission_type(mission)

    if submission_type == "PIPELINE":
        render_pipeline_form(db, mission)
    elif submission_type == "HELIUM":
        render_helium_form(db, mission)
    elif submission_type == "KEYPUNCH":
        render_keypunch_form(db, mission)
    elif submission_type == "CATALYST":
        render_catalyst_form(db, mission)
    elif submission_type == "NASI":
        render_nasi_form(db, mission)
    elif submission_type == "TEXT":
        render_text_form(db, mission)
    elif submission_type == "NONE":
        st.info("No participant submission is required for this mission.")
    else:
        render_photo_form(db, mission)


def show_participant():
    if "participant_event_id" in st.session_state:
        st_autorefresh(interval=30000, key="participant_refresh")

    st.title("📱 EXOS Mission")

    db = GoogleSheetsDB()

    if "participant_event_id" not in st.session_state:
        st.markdown(
            """
            <div style="text-align:center; padding: 18px 0 28px 0;">
                <div style="font-size: 20px; letter-spacing: 3px; font-weight: 700;">EXOS</div>
                <div style="font-size: 42px; font-weight: 900; margin-top: 8px;">Mission AI</div>
                <div style="font-size: 18px; opacity: 0.75; margin-top: 8px;">Join your live mission experience</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        join_code = st.text_input("Join Code").upper().strip()
        participant_name = st.text_input("Your Name")

        if st.button("🚀 Join Event", width="stretch"):
            if not join_code:
                st.warning("Enter Join Code")
                st.stop()

            if not participant_name:
                st.warning("Enter your name")
                st.stop()

            event = db.get_event_by_join_code(join_code)

            if event is None:
                st.error("Invalid Join Code")
                st.stop()

            player = db.join_player(event["EventID"], participant_name)
            ai = db.assign_ai_facilitator(player["Team"]) or {}

            st.session_state["participant_event_id"] = player["EventID"]
            st.session_state["participant_name"] = player["Name"]
            st.session_state["participant_team"] = player["Team"]
            st.session_state["participant_points"] = player["Points"]
            st.session_state["participant_event_name"] = event["EventName"]
            st.session_state["ai_name"] = ai.get("Name", "Atlas")
            st.session_state["ai_personality"] = ai.get("Personality", "")
            st.session_state["ai_greeting"] = ai.get("Greeting", "")

            st.rerun()

        return

    st.success(f"Welcome {st.session_state['participant_name']}")
    st.caption(st.session_state["participant_event_name"])

    render_team_assignment_card()

    st.divider()

    mission = db.get_current_mission(st.session_state["participant_event_id"])

    st.subheader("🎯 Current Mission")

    if mission is None:
        st.info("Waiting for facilitator to launch a mission...")
    else:
        st.success(mission.get("Title", "Mission"))
        st.write(mission.get("Description", ""))

        if mission.get("Clue"):
            st.info("💡 " + mission["Clue"])

        existing_submission = db.get_team_submission(
            event_id=st.session_state["participant_event_id"],
            mission_id=mission["MissionID"],
            team_name=st.session_state["participant_team"],
        )

        st.divider()

        if existing_submission:
            render_existing_submission(existing_submission)
        else:
            render_submission_form(db, mission)

    st.divider()

    st.subheader(f"🤖 {st.session_state['ai_name']}")

    if st.session_state["ai_greeting"]:
        st.info(st.session_state["ai_greeting"])

    conversation = db.get_conversation(
        st.session_state["participant_event_id"],
        st.session_state["participant_team"],
    )

    for row in conversation:
        role = "assistant"

        if str(row.get("Role", "")).lower() == "user":
            role = "user"

        with st.chat_message(role):
            st.markdown(row.get("Message", ""))

    prompt = st.chat_input(f"Ask {st.session_state['ai_name']}...")

    if prompt:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db.save_conversation(
            event_id=st.session_state["participant_event_id"],
            team=st.session_state["participant_team"],
            ai=st.session_state["ai_name"],
            role="User",
            message=prompt,
            timestamp=timestamp,
        )

        reply = ask_facilitator(
            facilitator_name=st.session_state["ai_name"],
            personality=st.session_state["ai_personality"],
            greeting=st.session_state["ai_greeting"],
            mission=mission,
            user_message=prompt,
        )

        db.save_conversation(
            event_id=st.session_state["participant_event_id"],
            team=st.session_state["participant_team"],
            ai=st.session_state["ai_name"],
            role="Assistant",
            message=reply,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        st.rerun()

    st.divider()

    col1, col2 = st.columns([3, 1])

    with col2:
        if st.button("🚪 Leave Event", width="stretch"):
            reset_session()
            st.rerun()