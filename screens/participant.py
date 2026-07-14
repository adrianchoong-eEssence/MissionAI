import uuid
from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from ai.facilitator import ask_facilitator
from data.google_drive import upload_photo
from data.google_sheets import GoogleSheetsDB
from data.runtime_database import RuntimeDatabaseError


COUNTRY_LANGUAGE_PROMPTS = {
    "Japan": "Find your team. You may greet them with: Konnichiwa.",
    "Malaysia": "Find your team. You may greet them with: Apa khabar.",
    "France": "Find your team. You may greet them with: Bonjour.",
    "India": "Find your team. You may greet them with: Namaste.",
    "Thailand": "Find your team. You may greet them with: Sawadee.",
    "China": "Find your team. You may greet them with: Ni hao.",
}

SESSION_KEYS = [
    "participant_event_id",
    "participant_name",
    "participant_team",
    "participant_points",
    "participant_event_name",
    "participant_session_token",
    "ai_name",
    "ai_personality",
    "ai_greeting",
]


def reset_session():
    for key in SESSION_KEYS:
        st.session_state.pop(key, None)

    for key in [
        "event_id",
        "participant_name",
        "participant_team",
        "event_name",
        "session_token",
    ]:
        if key in st.query_params:
            del st.query_params[key]


def restore_session_from_query_params(db):
    if "participant_event_id" in st.session_state:
        return

    event_id = str(st.query_params.get("event_id", "")).strip()
    participant_name = str(st.query_params.get("participant_name", "")).strip()
    session_token = str(st.query_params.get("session_token", "")).strip()

    if session_token:
        try:
            runtime_player = db.get_player_by_session_token(session_token)
        except RuntimeDatabaseError:
            runtime_player = None

        if runtime_player:
            team_name = str(runtime_player.get("Team", ""))
            ai = db.assign_ai_facilitator(team_name) or {}
            st.session_state["participant_event_id"] = runtime_player.get(
                "EventID", ""
            )
            st.session_state["participant_name"] = runtime_player.get("Name", "")
            st.session_state["participant_team"] = team_name
            st.session_state["participant_points"] = runtime_player.get("Points", 0)
            st.session_state["participant_event_name"] = runtime_player.get(
                "EventName", "EXOS Event"
            )
            st.session_state["participant_session_token"] = runtime_player.get(
                "SessionToken", session_token
            )
            st.session_state["ai_name"] = ai.get("Name", "Atlas")
            st.session_state["ai_personality"] = ai.get("Personality", "")
            st.session_state["ai_greeting"] = ai.get("Greeting", "")
            return

    if not event_id or not participant_name:
        return

    player = db.get_player(event_id, participant_name)
    if not player:
        return

    event = next(
        (
            row
            for row in db.get_events()
            if str(row.get("EventID", "")) == event_id
        ),
        {},
    )
    team_name = str(
        player.get("Team", "")
        or player.get("TeamName", "")
        or st.query_params.get("participant_team", "")
    )
    ai = db.assign_ai_facilitator(team_name) or {}

    st.session_state["participant_event_id"] = event_id
    st.session_state["participant_name"] = participant_name
    st.session_state["participant_team"] = team_name
    st.session_state["participant_points"] = player.get("Points", 0)
    st.session_state["participant_event_name"] = event.get(
        "EventName",
        str(st.query_params.get("event_name", "EXOS Event")),
    )
    st.session_state["participant_session_token"] = ""
    st.session_state["ai_name"] = ai.get("Name", "Atlas")
    st.session_state["ai_personality"] = ai.get("Personality", "")
    st.session_state["ai_greeting"] = ai.get("Greeting", "")


def persist_session_in_query_params():
    st.query_params["event_id"] = st.session_state["participant_event_id"]
    st.query_params["participant_name"] = st.session_state["participant_name"]
    st.query_params["participant_team"] = st.session_state["participant_team"]
    st.query_params["event_name"] = st.session_state["participant_event_name"]
    session_token = st.session_state.get("participant_session_token", "")
    if session_token:
        st.query_params["session_token"] = session_token


def normalise_submission_type(mission):
    raw_type = str(mission.get("SubmissionType", "") or "").strip().upper()
    title = str(mission.get("Title", "") or "").strip().upper()
    description = str(mission.get("Description", "") or "").strip().upper()
    combined = f"{raw_type} {title} {description}"

    if "ENTERPRISE" in combined and (
        "PIPELINE" in combined or "CUSTOMER JOURNEY" in combined
    ):
        return "PIPELINE_ENTERPRISE"

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
            padding:24px;
            border-radius:22px;
            background:linear-gradient(135deg,#0f172a,#1e293b);
            color:white;
            text-align:center;
            margin-bottom:18px;
        ">
            <div style="font-size:18px;opacity:.8;">Mission Assignment</div>
            <div style="font-size:46px;font-weight:900;margin-top:8px;">{team}</div>
            <div style="font-size:18px;margin-top:12px;opacity:.9;">{instruction}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def find_existing_submission(db, mission, submission_type):
    event_id = st.session_state["participant_event_id"]
    mission_id = mission["MissionID"]

    if submission_type == "NASI":
        return db.get_participant_submission(
            event_id=event_id,
            mission_id=mission_id,
            participant_name=st.session_state["participant_name"],
        )

    return db.get_team_submission(
        event_id=event_id,
        mission_id=mission_id,
        team_name=st.session_state["participant_team"],
    )


def render_existing_submission(existing_submission):
    st.success("✅ Submission received.")

    submitted_at = existing_submission.get("SubmittedAt", "")
    if submitted_at:
        st.caption(f"Submitted at: {submitted_at}")

    submission_type = str(existing_submission.get("SubmissionType", "")).upper()
    metric1 = existing_submission.get("Metric1", "")
    metric2 = existing_submission.get("Metric2", "")
    metric3 = existing_submission.get("Metric3", "")
    remarks = existing_submission.get("Remarks", "")
    image_url = existing_submission.get("ImageURL", "")

    if submission_type == "PIPELINE":
        st.write(f"**Target:** {metric1}")
        st.write(f"**Achieved:** {metric2}")
        st.write(f"**Lost clients:** {metric3}")
    elif submission_type == "KEYPUNCH":
        st.write(f"**Highest number reached:** {metric1}")
    elif submission_type in ["HELIUM", "CATALYST"]:
        st.write(f"**Completed:** {metric1}")
    elif submission_type == "NASI" and remarks:
        st.info(remarks)
    elif remarks:
        st.info(remarks)

    if image_url and str(image_url).startswith("data:image"):
        try:
            st.image(image_url, width="stretch")
        except Exception:
            st.warning("Submission image could not be displayed.")


def save_structured_submission(
    db,
    mission,
    submission_type,
    metric1="",
    metric2="",
    metric3="",
    remarks="",
    image_url="",
    drive_file_id="",
):
    return db.save_submission(
        submission_id=str(uuid.uuid4()),
        event_id=st.session_state["participant_event_id"],
        mission_id=mission["MissionID"],
        team_name=st.session_state["participant_team"],
        participant_name=st.session_state["participant_name"],
        image_url=image_url,
        drive_file_id=drive_file_id,
        submitted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        score="",
        judged="No",
        remarks=remarks,
        submission_type=submission_type,
        metric1=metric1,
        metric2=metric2,
        metric3=metric3,
        status="PENDING",
    )


def render_pipeline_form(db, mission):
    st.subheader("📊 Customer Journey Results")
    st.write("Submit your team's recorded result.")

    target = st.number_input(
        "Target",
        min_value=1,
        value=1,
        step=1,
        key=f"pipeline_target_{mission['MissionID']}",
    )
    achieved = st.number_input(
        "Achieved",
        min_value=0,
        value=0,
        step=1,
        key=f"pipeline_achieved_{mission['MissionID']}",
    )
    lost = st.number_input(
        "Lost Clients",
        min_value=0,
        value=0,
        step=1,
        key=f"pipeline_lost_{mission['MissionID']}",
    )

    net_achievement = max(0, achieved - lost)
    calculated_score = (net_achievement / target) * 100
    st.caption(f"Calculated performance: {calculated_score:.1f}%")

    if st.button(
        "📤 Submit Pipeline Results",
        width="stretch",
        key=f"submit_pipeline_{mission['MissionID']}",
    ):
        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="PIPELINE",
            metric1=target,
            metric2=achieved,
            metric3=lost,
            remarks=(
                f"Net achievement: {net_achievement}; "
                f"Calculated performance: {calculated_score:.1f}%"
            ),
        )
        st.success("✅ Pipeline results submitted.")
        st.balloons()
        st.rerun()


def render_helium_form(db, mission):
    st.subheader("🪄 Taking Ownership Together")
    completed = st.radio(
        "Did your team complete the Helium Stick challenge?",
        ["Yes", "No"],
        horizontal=True,
        key=f"helium_completed_{mission['MissionID']}",
    )

    if st.button(
        "📤 Submit Helium Stick Result",
        width="stretch",
        key=f"submit_helium_{mission['MissionID']}",
    ):
        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="HELIUM",
            metric1=completed.upper(),
        )
        st.success("✅ Helium Stick result submitted.")
        st.balloons()
        st.rerun()


def render_keypunch_form(db, mission):
    st.subheader("⚡ Key Punch")
    st.write("Submit your team's official 60-second attempt.")

    highest_number = st.number_input(
        "Highest Number Reached Within 60 Seconds",
        min_value=0,
        max_value=30,
        value=0,
        step=1,
        key=f"keypunch_highest_{mission['MissionID']}",
    )
    calculated_score = (highest_number / 30) * 100
    st.caption(f"Calculated performance: {calculated_score:.1f}%")

    if st.button(
        "📤 Submit Key Punch Result",
        width="stretch",
        key=f"submit_keypunch_{mission['MissionID']}",
    ):
        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="KEYPUNCH",
            metric1=highest_number,
            remarks=f"Calculated performance: {calculated_score:.1f}%",
        )
        st.success("✅ Key Punch result submitted.")
        st.balloons()
        st.rerun()


def render_catalyst_form(db, mission):
    st.subheader("⚙️ Creating Enterprise Success")
    completed = st.radio(
        "Did your section complete?",
        ["Yes", "No"],
        horizontal=True,
        key=f"catalyst_completed_{mission['MissionID']}",
    )
    uploaded_image = st.file_uploader(
        "Optional Final Structure Photo",
        type=["jpg", "jpeg", "png"],
        key=f"catalyst_photo_{mission['MissionID']}",
    )

    if uploaded_image is not None:
        st.image(uploaded_image, width="stretch")

    if st.button(
        "📤 Submit Catalyst Status",
        width="stretch",
        key=f"submit_catalyst_{mission['MissionID']}",
    ):
        image_url = ""
        drive_file_id = ""

        if uploaded_image is not None:
            uploaded = upload_photo(
                event_id=st.session_state["participant_event_id"],
                mission_id=mission["MissionID"],
                team_name=st.session_state["participant_team"],
                participant_name=st.session_state["participant_name"],
                uploaded_file=uploaded_image,
            )
            image_url = uploaded.get("url", "")
            drive_file_id = uploaded.get("file_id", "")

        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="CATALYST",
            metric1=completed.upper(),
            image_url=image_url,
            drive_file_id=drive_file_id,
        )
        st.success("✅ Catalyst status submitted.")
        st.balloons()
        st.rerun()


def render_nasi_form(db, mission):
    st.subheader("📝 NASI")
    st.write("Submit your individual learning reflection.")

    new_ideas = st.text_area(
        "N — New Ideas",
        placeholder="What new ideas did you discover?",
        key=f"nasi_n_{mission['MissionID']}",
    )
    areas = st.text_area(
        "A — Areas for Improvement",
        placeholder="What should be improved?",
        key=f"nasi_a_{mission['MissionID']}",
    )
    strengths = st.text_area(
        "S — Strengths",
        placeholder="What strengths should be protected and continued?",
        key=f"nasi_s_{mission['MissionID']}",
    )
    implementation = st.text_area(
        "I — Implementation",
        placeholder="What is one action you will implement?",
        key=f"nasi_i_{mission['MissionID']}",
    )

    if st.button(
        "📤 Submit NASI",
        width="stretch",
        key=f"submit_nasi_{mission['MissionID']}",
    ):
        if not any(
            [
                new_ideas.strip(),
                areas.strip(),
                strengths.strip(),
                implementation.strip(),
            ]
        ):
            st.warning("Please enter at least one reflection before submitting.")
            st.stop()

        remarks = (
            f"N - New Ideas:\n{new_ideas.strip() or '-'}\n\n"
            f"A - Areas for Improvement:\n{areas.strip() or '-'}\n\n"
            f"S - Strengths:\n{strengths.strip() or '-'}\n\n"
            f"I - Implementation:\n{implementation.strip() or '-'}"
        )
        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="NASI",
            remarks=remarks,
        )
        st.success("✅ NASI submitted.")
        st.balloons()
        st.rerun()


def render_text_form(db, mission):
    st.subheader("📝 Team Response")
    response = st.text_area(
        "Submit your team's response",
        placeholder="Type your team's response here.",
        key=f"text_response_{mission['MissionID']}",
    )

    if st.button(
        "📤 Submit Response",
        width="stretch",
        key=f"submit_text_{mission['MissionID']}",
    ):
        if not response.strip():
            st.warning("Please enter a response before submitting.")
            st.stop()

        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="TEXT",
            remarks=response.strip(),
        )
        st.success("✅ Response submitted.")
        st.balloons()
        st.rerun()


def render_photo_form(db, mission):
    st.subheader("📸 Mission Submission")
    uploaded_image = st.file_uploader(
        "Choose Photo",
        type=["jpg", "jpeg", "png"],
        key=f"photo_upload_{mission['MissionID']}",
    )

    if uploaded_image is not None:
        st.image(uploaded_image, width="stretch")

        if st.button(
            "📤 Submit Mission",
            width="stretch",
            key=f"submit_photo_{mission['MissionID']}",
        ):
            with st.spinner("Submitting mission..."):
                uploaded = upload_photo(
                    event_id=st.session_state["participant_event_id"],
                    mission_id=mission["MissionID"],
                    team_name=st.session_state["participant_team"],
                    participant_name=st.session_state["participant_name"],
                    uploaded_file=uploaded_image,
                )
                save_structured_submission(
                    db=db,
                    mission=mission,
                    submission_type="PHOTO",
                    image_url=uploaded.get("url", ""),
                    drive_file_id=uploaded.get("file_id", ""),
                )

            st.success("✅ Mission submitted successfully.")
            st.balloons()
            st.rerun()


def render_submission_form(db, mission, submission_type):
    if submission_type == "PIPELINE":
        render_pipeline_form(db, mission)
    elif submission_type == "PIPELINE_ENTERPRISE":
        st.info(
            "The Enterprise Pipeline result will be entered once by the facilitator."
        )
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


def render_mission_content(mission):
    story = str(mission.get("Story", "") or "").strip()
    instructions = str(
        mission.get("ParticipantInstructions", "")
        or mission.get("Description", "")
        or ""
    ).strip()
    video_url = str(mission.get("VideoURL", "") or "").strip()
    image_url = str(mission.get("ImageURL", "") or "").strip()
    document_url = str(mission.get("DocumentURL", "") or "").strip()

    if story:
        st.markdown("#### Mission Story")
        st.markdown(story)

    if video_url:
        try:
            st.video(video_url)
        except Exception:
            st.warning("The mission video could not be displayed.")
            st.link_button("▶️ Open Mission Video", video_url, width="stretch")

    if image_url:
        try:
            st.image(image_url, width="stretch")
        except Exception:
            st.warning("The mission image could not be displayed.")

    if instructions:
        st.markdown("#### Instructions")
        st.info(instructions)

    if document_url:
        st.link_button(
            "📄 Open Mission Document",
            document_url,
            width="stretch",
        )


def show_participant():
    st.title("📱 EXOS Mission")

    db = GoogleSheetsDB()
    restore_session_from_query_params(db)

    if "participant_event_id" in st.session_state:
        persist_session_in_query_params()

    if "participant_event_id" not in st.session_state:
        st.markdown(
            """
            <div style="text-align:center;padding:18px 0 28px 0;">
                <div style="font-size:20px;letter-spacing:3px;font-weight:700;">EXOS</div>
                <div style="font-size:42px;font-weight:900;margin-top:8px;">Mission AI</div>
                <div style="font-size:18px;opacity:.75;margin-top:8px;">Join your live mission experience</div>
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
            if not participant_name.strip():
                st.warning("Enter your name")
                st.stop()

            try:
                player = db.join_player_by_code(
                    join_code,
                    participant_name.strip(),
                )
            except RuntimeDatabaseError as error:
                st.error(
                    "Registration is temporarily busy. Your team has not been changed. "
                    "Please wait a few seconds and press Join Event again."
                )
                st.caption(str(error))
                st.stop()
            except ValueError as error:
                st.error(str(error))
                st.stop()

            ai = db.assign_ai_facilitator(player["Team"]) or {}

            st.session_state["participant_event_id"] = player["EventID"]
            st.session_state["participant_name"] = player["Name"]
            st.session_state["participant_team"] = player["Team"]
            st.session_state["participant_points"] = player.get("Points", 0)
            st.session_state["participant_event_name"] = player.get(
                "EventName", "EXOS Event"
            )
            st.session_state["participant_session_token"] = player.get(
                "SessionToken", ""
            )
            st.session_state["ai_name"] = ai.get("Name", "Atlas")
            st.session_state["ai_personality"] = ai.get("Personality", "")
            st.session_state["ai_greeting"] = ai.get("Greeting", "")
            persist_session_in_query_params()
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
        st_autorefresh(interval=5000, key="waiting_for_mission_refresh")
    else:
        st.success(mission.get("Title", "Mission"))
        render_mission_content(mission)

        if mission.get("Clue"):
            st.info("💡 " + str(mission["Clue"]))

        submission_type = normalise_submission_type(mission)
        existing_submission = find_existing_submission(
            db,
            mission,
            submission_type,
        )

        st.divider()
        if existing_submission:
            render_existing_submission(existing_submission)
            st_autorefresh(interval=5000, key="submitted_mission_refresh")
        else:
            st.caption(
                "Auto-refresh pauses while you enter results so your values are not reset."
            )
            if st.button(
                "🔄 Check for New Mission",
                width="stretch",
                key=f"check_mission_{mission.get('MissionID', 'current')}",
            ):
                st.rerun()

            render_submission_form(db, mission, submission_type)

    st.divider()
    st.subheader(f"🤖 {st.session_state['ai_name']}")

    if st.session_state["ai_greeting"]:
        st.info(st.session_state["ai_greeting"])

    conversation = db.get_conversation(
        st.session_state["participant_event_id"],
        st.session_state["participant_team"],
    )

    for row in conversation:
        role = "user" if str(row.get("Role", "")).lower() == "user" else "assistant"
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
    _, leave_col = st.columns([3, 1])
    with leave_col:
        if st.button("🚪 Leave Event", width="stretch"):
            reset_session()
            st.rerun()
