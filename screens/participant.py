import streamlit as st
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from data.google_sheets import GoogleSheetsDB
from ai.facilitator import ask_facilitator


def reset_session():
    for key in [
        "participant_event_id",
        "participant_name",
        "participant_team",
        "participant_points",
        "participant_event_name",
        "ai_name",
        "ai_personality",
        "ai_greeting",
    ]:
        st.session_state.pop(key, None)


def show_participant():

    # Refresh every 5 seconds once participant has joined
    if "participant_event_id" in st.session_state:
        st_autorefresh(interval=5000, key="participant_refresh")

    st.title("📱 Mission App")
    st.caption("Powered by EXOS")

    db = GoogleSheetsDB()

    if "participant_event_id" not in st.session_state:
        st.subheader("Join Event")

        join_code = st.text_input("Join Code").upper().strip()
        name = st.text_input("Display Name")

        if st.button("🚀 Join Event"):
            if not join_code:
                st.warning("Please enter a Join Code.")
            elif not name.strip():
                st.warning("Please enter your name.")
            else:
                event = db.get_event_by_join_code(join_code)

                if event is None:
                    st.error("Invalid Join Code.")
                else:
                    player = db.join_player(event["EventID"], name.strip())
                    ai = db.assign_ai_facilitator(player["Team"])

                    st.session_state["participant_event_id"] = player["EventID"]
                    st.session_state["participant_name"] = player["Name"]
                    st.session_state["participant_team"] = player["Team"]
                    st.session_state["participant_points"] = player["Points"]
                    st.session_state["participant_event_name"] = event["EventName"]

                    st.session_state["ai_name"] = ai.get("Name", "Atlas") if ai else "Atlas"
                    st.session_state["ai_personality"] = ai.get("Personality", "") if ai else ""
                    st.session_state["ai_greeting"] = ai.get("Greeting", "") if ai else ""

                    st.rerun()

        return

    st.success(f"Welcome {st.session_state['participant_name']}!")
    st.caption(st.session_state["participant_event_name"])

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Team", st.session_state["participant_team"])

    with col2:
        st.metric("Points", st.session_state["participant_points"])

    st.divider()

    st.subheader("🎯 Current Mission")

    mission = db.get_current_mission(
        st.session_state["participant_event_id"]
    )

    if mission:

        st.success(mission.get("Title", "Mission"))

        st.write(mission.get("Description", ""))

        if mission.get("Clue"):
            st.info("💡 " + mission["Clue"])

        st.button("🤖 Ask Atlas", disabled=True)

        st.button("📸 Submit Photo", disabled=True)

    else:

        st.info("Waiting for facilitator to launch a mission...")

    st.divider()

    st.subheader(f"🧠 {st.session_state['ai_name']}")

    if st.session_state.get("ai_personality"):
        st.caption(st.session_state["ai_personality"])

    if st.session_state.get("ai_greeting"):
        st.info(st.session_state["ai_greeting"])

    conversation = db.get_conversation(
        st.session_state["participant_event_id"],
        st.session_state["participant_team"],
    )

    for message in conversation:

        role = "assistant"

        if str(message.get("Role", "")).lower() == "user":
            role = "user"

        with st.chat_message(role):
            st.markdown(message.get("Message", ""))

    prompt = st.chat_input(f"Message {st.session_state['ai_name']}...")

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

    if st.button("🚪 Leave Event"):
        reset_session()
        st.rerun()