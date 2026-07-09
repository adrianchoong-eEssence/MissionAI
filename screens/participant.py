import uuid
from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from ai.facilitator import ask_facilitator
from data.google_drive import upload_photo
from data.google_sheets import GoogleSheetsDB


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


def show_participant():
    if "participant_event_id" in st.session_state:
        st_autorefresh(interval=30000, key="participant_refresh")

    st.title("📱 EXOS Mission")

    db = GoogleSheetsDB()

    if "participant_event_id" not in st.session_state:
        st.subheader("Join Event")

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

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Team", st.session_state["participant_team"])

    with col2:
        st.metric("Points", st.session_state["participant_points"])

    st.divider()

    mission = db.get_current_mission(st.session_state["participant_event_id"])

    st.subheader("🎯 Current Mission")

    if mission is None:
        st.info("Waiting for facilitator to launch a mission...")
    else:
        st.success(mission["Title"])
        st.write(mission["Description"])

        if mission.get("Clue"):
            st.info("💡 " + mission["Clue"])

        existing_submission = db.get_team_submission(
            event_id=st.session_state["participant_event_id"],
            mission_id=mission["MissionID"],
            team_name=st.session_state["participant_team"],
        )

        st.divider()
        st.subheader("📸 Mission Submission")

        if existing_submission:
            st.success("✅ Your team has already submitted this mission.")

            submitted_at = existing_submission.get("SubmittedAt", "")
            if submitted_at:
                st.caption(f"Submitted at: {submitted_at}")

            image_url = existing_submission.get("ImageURL", "")
            if image_url:
                try:
                    st.image(image_url, width="stretch")
                except Exception:
                    st.markdown(f"[View Submission]({image_url})")

        else:
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

                        submission_id = str(uuid.uuid4())

                        db.save_submission(
                            submission_id=submission_id,
                            event_id=st.session_state["participant_event_id"],
                            mission_id=mission["MissionID"],
                            team_name=st.session_state["participant_team"],
                            participant_name=st.session_state["participant_name"],
                            image_url=drive["url"],
                            drive_file_id=drive["file_id"],
                            submitted_at=datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        )

                    st.success("✅ Mission submitted successfully.")
                    st.balloons()
                    st.rerun()

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