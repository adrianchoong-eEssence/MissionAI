import streamlit as st
import streamlit.components.v1 as components

from data.google_sheets import GoogleSheetsDB


def auto_refresh(seconds=5):
    components.html(
        f"""
        <script>
            setTimeout(function() {{
                window.parent.location.reload();
            }}, {seconds * 1000});
        </script>
        """,
        height=0,
    )


def show_live_event_console():
    st.title("🎮 Live Event Console")

    db = GoogleSheetsDB()
    events = db.get_events()

    if not events:
        st.warning("No events found. Create an event first.")
        return

    event_options = {
        f"{event.get('EventID')} — {event.get('EventName')}": event
        for event in events
    }

    selected_label = st.selectbox("Select Event", list(event_options.keys()))
    event = event_options[selected_label]
    event_id = event.get("EventID")

    auto_refresh_on = st.toggle("Auto Refresh", value=False)

    if auto_refresh_on:
        auto_refresh(5)

    st.divider()

    st.subheader(event.get("EventName", "Unnamed Event"))
    st.caption(f"Client: {event.get('Client', '')}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Join Code", event.get("JoinCode", ""))

    with col2:
        st.metric("Participants", db.get_participant_count(event_id))

    with col3:
        st.metric("Teams", db.get_team_count(event_id))

    st.divider()

    st.subheader("🚀 Launch Mission")

    mission_id = st.text_input("Mission ID", value="M01")
    title = st.text_input("Mission Title", value="Checkpoint 1")
    description = st.text_area("Mission Instructions", value="Complete the challenge.")
    points = st.number_input("Points", min_value=0, value=100, step=10)

    submission_type = st.selectbox(
        "Submission Type",
        ["Photo", "Text", "QR", "None"]
    )

    clue = st.text_area("Clue", value="")
    answer = st.text_input("Answer", value="")

    hint1 = st.text_input("Hint 1", value="")
    hint2 = st.text_input("Hint 2", value="")
    hint3 = st.text_input("Hint 3", value="")

    ai_help_enabled = st.selectbox(
        "AI Help Enabled",
        ["Yes", "No"]
    )

    if st.button("🚀 Launch Mission"):
        db.send_mission(
            event_id=event_id,
            mission_id=mission_id,
            title=title,
            description=description,
            points=points,
            submission_type=submission_type,
            clue=clue,
            answer=answer,
            hint1=hint1,
            hint2=hint2,
            hint3=hint3,
            ai_help_enabled=ai_help_enabled
        )

        st.success("Mission launched.")

    st.divider()

    st.subheader("Current Mission")

    mission = db.get_current_mission(event_id)

    if mission:
        st.success(mission.get("Title", "Mission"))
        st.write(mission.get("Description", ""))
    else:
        st.info("No live mission yet.")
    st.divider()

    st.subheader("📸 Mission Submissions")

    submissions = db.get_submissions(event_id)

    if not submissions:

        st.info("No submissions received yet.")

    else:

        for submission in submissions:

            with st.container():

                col1, col2 = st.columns([3, 1])

                with col1:

                    st.markdown(
                        f"""
**{submission['TeamName']}**
- Participant: {submission['ParticipantName']}
- Mission: {submission['MissionID']}
- Submitted: {submission['SubmittedAt']}
"""
                    )

                with col2:

                    if submission["ImageURL"]:

                        st.link_button(
                            "📷 View Photo",
                            submission["ImageURL"],
                            use_container_width=True,
                        )

                st.divider()
    if st.button("🔄 Refresh Now"):
        st.rerun()