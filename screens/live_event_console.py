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


def calculate_leaderboard(submissions):
    leaderboard = {}

    for submission in submissions:
        team = submission.get("TeamName", "Unknown Team")
        judged = str(submission.get("Judged", "")).lower()
        score_raw = submission.get("Score", 0)

        if judged not in ["yes", "true", "approved"]:
            continue

        try:
            score = int(score_raw)
        except Exception:
            score = 0

        leaderboard[team] = leaderboard.get(team, 0) + score

    return sorted(
        leaderboard.items(),
        key=lambda item: item[1],
        reverse=True,
    )


def mission_defaults(submission_type):
    mission_map = {
        "PIPELINE": {
            "mission_id": "M01",
            "title": "Customer Journey: Pipeline Challenge",
            "description": (
                "Every marble represents a customer. Your task is to move customers safely "
                "through the enterprise process and minimise lost clients. Await Adrian's briefing."
            ),
            "points": 100,
            "clue": "Focus on flow, handover, ownership and customer protection.",
        },
        "HELIUM": {
            "mission_id": "M02",
            "title": "Taking Ownership Together: Helium Stick",
            "description": (
                "Lower the stick together. The moment we blame and point fingers, the issue escalates. "
                "Your mission is to take ownership of your own action."
            ),
            "points": 100,
            "clue": "Less blaming. More ownership. Small adjustments matter.",
        },
        "KEYPUNCH": {
            "mission_id": "M03",
            "title": "Balancing Speed, Accuracy and Compliance: Key Punch",
            "description": (
                "Complete the sequence with speed and accuracy. One person cannot do everything alone. "
                "Strategy and coordination determine execution."
            ),
            "points": 100,
            "clue": "If you want to go fast, go alone. If you want to go far, go together.",
        },
        "CATALYST": {
            "mission_id": "M04",
            "title": "Creating Enterprise Success: Catalyst Challenge",
            "description": (
                "Each team builds one part of the enterprise system. Your station must integrate with others "
                "until the final trigger completes the full chain."
            ),
            "points": 100,
            "clue": "Integration requires communication before execution begins.",
        },
        "TEXT": {
            "mission_id": "M05",
            "title": "Mission Reflection",
            "description": "Submit your team's key takeaway, improvement idea or implementation commitment.",
            "points": 50,
            "clue": "Turn the activity into action.",
        },
        "PHOTO": {
            "mission_id": "M06",
            "title": "Photo Evidence Mission",
            "description": "Upload one photo as evidence of mission completion.",
            "points": 100,
            "clue": "One submission per team is enough.",
        },
    }

    return mission_map.get(submission_type, mission_map["PHOTO"])


def render_submission_payload(payload):
    if not payload:
        return

    if str(payload).startswith("data:image"):
        try:
            st.image(
                payload,
                caption="Mission Submission",
                width="stretch",
            )
        except Exception:
            st.warning("Submission image could not be displayed.")
    else:
        st.text_area(
            "Submission Details",
            value=str(payload),
            height=180,
            disabled=True,
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

    submissions = db.get_submissions(event_id)

    st.divider()

    st.subheader("🏆 Live Leaderboard")

    leaderboard = calculate_leaderboard(submissions)

    if not leaderboard:
        st.info("No approved scores yet.")
    else:
        for index, (team, score) in enumerate(leaderboard, start=1):
            medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else "⭐"
            st.metric(f"{medal} {index}. {team}", f"{score} pts")

    st.divider()

    st.subheader("🚀 Launch Mission")

    submission_type = st.selectbox(
        "Mission Type",
        ["PIPELINE", "HELIUM", "KEYPUNCH", "CATALYST", "TEXT", "PHOTO", "NONE"],
    )

    defaults = mission_defaults(submission_type)

    mission_id = st.text_input("Mission ID", value=defaults["mission_id"])
    title = st.text_input("Mission Title", value=defaults["title"])
    description = st.text_area("Mission Instructions", value=defaults["description"])
    points = st.number_input("Points", min_value=0, value=defaults["points"], step=10)
    clue = st.text_area("Clue", value=defaults["clue"])
    answer = st.text_input("Answer", value="")
    hint1 = st.text_input("Hint 1", value="")
    hint2 = st.text_input("Hint 2", value="")
    hint3 = st.text_input("Hint 3", value="")

    ai_help_enabled = st.selectbox(
        "AI Help Enabled",
        ["Yes", "No"],
    )

    if st.button("🚀 Launch Mission", width="stretch"):
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
            ai_help_enabled=ai_help_enabled,
        )

        st.success("Mission launched.")
        st.rerun()

    st.divider()

    st.subheader("Current Mission")

    mission = db.get_current_mission(event_id)

    if mission:
        st.success(mission.get("Title", "Mission"))
        st.write(mission.get("Description", ""))
        st.caption(f"Submission Type: {mission.get('SubmissionType', '')}")
    else:
        st.info("No live mission yet.")

    st.divider()

    st.subheader("📥 Mission Submissions")

    if not submissions:
        st.info("No submissions received yet.")
    else:
        for submission in submissions:
            with st.container():
                st.markdown(
                    f"""
**{submission.get('TeamName', '')}**

- Participant: {submission.get('ParticipantName', '')}
- Mission: {submission.get('MissionID', '')}
- Submitted: {submission.get('SubmittedAt', '')}
- Judged: {submission.get('Judged', 'No')}
- Score: {submission.get('Score', '')}
"""
                )

                render_submission_payload(submission.get("ImageURL", ""))

                score = st.number_input(
                    "Score",
                    min_value=0,
                    max_value=1000,
                    value=int(submission.get("Score") or 0),
                    step=10,
                    key=f"score_{submission.get('SubmissionID')}",
                )

                remarks = st.text_area(
                    "Remarks",
                    value=submission.get("Remarks", ""),
                    key=f"remarks_{submission.get('SubmissionID')}",
                )

                if st.button(
                    "✅ Approve / Update Score",
                    key=f"approve_{submission.get('SubmissionID')}",
                    width="stretch",
                ):
                    db.update_submission_score(
                        submission_id=submission.get("SubmissionID"),
                        score=score,
                        remarks=remarks,
                        judged="Yes",
                    )

                    st.success("Submission updated.")
                    st.rerun()

                st.divider()

    if st.button("🔄 Refresh Now", width="stretch"):
        st.rerun()
