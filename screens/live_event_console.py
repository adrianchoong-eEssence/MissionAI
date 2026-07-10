import re
import uuid
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from data.google_sheets import GoogleSheetsDB


APPROVED_VALUES = {"yes", "true", "approved"}


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


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_score(score):
    number = safe_float(score)
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def calculate_leaderboard(submissions):
    leaderboard = {}

    for submission in submissions:
        team = str(submission.get("TeamName", "Unknown Team") or "Unknown Team")
        judged = str(submission.get("Judged", "")).lower()

        if judged not in APPROVED_VALUES:
            continue

        score = safe_float(submission.get("Score", 0))
        leaderboard[team] = leaderboard.get(team, 0.0) + score

    return sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)


def mission_defaults(submission_type):
    mission_map = {
        "PIPELINE": {
            "mission_id": "P02",
            "title": "Customer Journey: Pipeline Challenge",
            "description": "Submit Target, Achieved and Lost Clients after the official team run.",
            "points": 100,
            "clue": "Score = (Achieved - Lost Clients) ÷ Target × 100. Scores may exceed 100.",
        },
        "PIPELINE_ENTERPRISE": {
            "mission_id": "P03",
            "title": "Enterprise Collaboration: Pipeline Challenge",
            "description": "All six groups operate as one enterprise. The facilitator records one collective result.",
            "points": 100,
            "clue": "One enterprise. One target. One collective result.",
        },
        "HELIUM": {
            "mission_id": "H01",
            "title": "Taking Ownership Together: Helium Stick",
            "description": "Lower the stick together while every finger remains in contact.",
            "points": 100,
            "clue": "Completed = 100 points. Not completed = 0 points.",
        },
        "KEYPUNCH": {
            "mission_id": "K01",
            "title": "Balancing Speed, Accuracy and Compliance: Key Punch",
            "description": "Submit the highest correct number reached within the official 60-second attempt.",
            "points": 100,
            "clue": "Score = Highest Number ÷ 30 × 100.",
        },
        "CATALYST": {
            "mission_id": "C01",
            "title": "Creating Enterprise Success: Catalyst Challenge",
            "description": "Build, integrate and complete the full enterprise chain reaction.",
            "points": 100,
            "clue": "Completed = 100 points. Not completed = 0 points.",
        },
        "NASI": {
            "mission_id": "N01",
            "title": "NASI",
            "description": "New Ideas, Areas for Improvement, Strengths and Implementation.",
            "points": 0,
            "clue": "Reflection only. No points awarded.",
        },
        "PHOTO": {
            "mission_id": "M01",
            "title": "Photo Evidence Mission",
            "description": "Upload one photo as evidence of mission completion.",
            "points": 100,
            "clue": "One submission per team is enough.",
        },
        "NONE": {
            "mission_id": "M00",
            "title": "Programme Stage",
            "description": "No participant submission is required.",
            "points": 0,
            "clue": "Await facilitator instruction.",
        },
    }
    return mission_map.get(submission_type, mission_map["PHOTO"])


def parse_payload(payload):
    text = str(payload or "")
    values = {}

    patterns = {
        "target": r"(?:Target|Enterprise Target)\s*:\s*([-+]?\d+(?:\.\d+)?)",
        "achieved": r"(?:Achieved|Actual Achievement|Delivered Customers|Enterprise Achieved)\s*:\s*([-+]?\d+(?:\.\d+)?)",
        "lost": r"(?:Lost Clients|Lost Customers|Dropped Marbles|Enterprise Lost Clients)\s*:\s*([-+]?\d+(?:\.\d+)?)",
        "highest": r"Highest Number(?: Reached)?\s*:\s*([-+]?\d+(?:\.\d+)?)",
        "completed": r"Completed\s*:\s*(Yes|No)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            values[key] = match.group(1)

    return values


def submission_type_for(db, submission):
    mission = db.get_mission(submission.get("EventID"), submission.get("MissionID")) or {}
    raw_type = str(mission.get("SubmissionType", "") or "").upper().strip()
    title = str(mission.get("Title", "") or "").upper()

    if "ENTERPRISE" in raw_type or "ENTERPRISE" in title:
        return "PIPELINE_ENTERPRISE"
    if "PIPELINE" in raw_type or "PIPELINE" in title:
        return "PIPELINE"
    if "HELIUM" in raw_type or "HELIUM" in title:
        return "HELIUM"
    if "KEY" in raw_type and "PUNCH" in raw_type or "KEY PUNCH" in title:
        return "KEYPUNCH"
    if "CATALYST" in raw_type or "CATALYST" in title:
        return "CATALYST"
    if "NASI" in raw_type or "NASI" in title or raw_type == "TEXT":
        return "NASI"
    return raw_type or "PHOTO"


def suggested_score(db, submission):
    mission_type = submission_type_for(db, submission)
    values = parse_payload(submission.get("ImageURL", ""))

    if mission_type in {"PIPELINE", "PIPELINE_ENTERPRISE"}:
        target = safe_float(values.get("target"))
        achieved = safe_float(values.get("achieved"))
        lost = safe_float(values.get("lost"))
        if target <= 0:
            return 0.0, "Target must be greater than zero."
        score = ((achieved - lost) / target) * 100
        return round(max(score, 0), 1), "(Achieved - Lost Clients) ÷ Target × 100"

    if mission_type == "HELIUM":
        completed = str(values.get("completed", "")).lower() == "yes"
        return (100.0 if completed else 0.0), "Completed = 100; not completed = 0"

    if mission_type == "KEYPUNCH":
        highest = min(max(safe_float(values.get("highest")), 0), 30)
        return round((highest / 30) * 100, 1), "Highest Number ÷ 30 × 100"

    if mission_type == "CATALYST":
        completed = str(values.get("completed", "")).lower() == "yes"
        return (100.0 if completed else 0.0), "Completed = 100; not completed = 0"

    if mission_type == "NASI":
        return 0.0, "Reflection only — no points"

    return safe_float(submission.get("Score", 0)), "Manual score"


def render_submission_payload(payload):
    if not payload:
        return

    if str(payload).startswith("data:image"):
        st.image(payload, caption="Mission Submission", width="stretch")
    else:
        st.text_area("Submission Details", value=str(payload), height=190, disabled=True)


def render_enterprise_pipeline_form(db, event_id, mission):
    if not mission:
        return

    mission_type = str(mission.get("SubmissionType", "") or "").upper()
    title = str(mission.get("Title", "") or "").upper()
    if "PIPELINE_ENTERPRISE" not in mission_type and "ENTERPRISE" not in title:
        return

    st.divider()
    st.subheader("🤝 Enterprise Pipeline Result")
    st.caption("Facilitator enters one collective result for all six groups.")

    existing = db.get_team_submission(event_id, mission.get("MissionID"), "ENTERPRISE")
    if existing:
        render_submission_payload(existing.get("ImageURL", ""))
        score, formula = suggested_score(db, existing)
        st.success(f"Collective score: {format_score(score)}%")
        st.caption(formula)
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        target = st.number_input("Enterprise Target", min_value=1, value=300, step=1)
    with col2:
        achieved = st.number_input("Enterprise Achieved", min_value=0, value=0, step=1)
    with col3:
        lost = st.number_input("Enterprise Lost Clients", min_value=0, value=0, step=1)

    calculated = max(((achieved - lost) / target) * 100, 0)
    st.metric("Calculated Enterprise Score", f"{format_score(calculated)}%")

    if st.button("✅ Save & Approve Enterprise Result", width="stretch"):
        payload = (
            "PIPELINE ENTERPRISE RESULT\n"
            f"Enterprise Target: {target}\n"
            f"Enterprise Achieved: {achieved}\n"
            f"Enterprise Lost Clients: {lost}"
        )
        submission_id = str(uuid.uuid4())
        db.save_submission(
            submission_id=submission_id,
            event_id=event_id,
            mission_id=mission.get("MissionID"),
            team_name="ENTERPRISE",
            participant_name="Facilitator",
            image_url=payload,
            drive_file_id="FACILITATOR-ENTRY",
            submitted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            score=round(calculated, 1),
            judged="Yes",
            remarks="Collective enterprise result",
        )
        st.success("Enterprise result saved.")
        st.rerun()


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
            st.metric(f"{medal} {index}. {team}", f"{format_score(score)} pts")

    st.divider()
    st.subheader("🚀 Launch Mission")

    submission_type = st.selectbox(
        "Mission Type",
        ["PIPELINE", "PIPELINE_ENTERPRISE", "HELIUM", "KEYPUNCH", "CATALYST", "NASI", "PHOTO", "NONE"],
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
    ai_help_enabled = st.selectbox("AI Help Enabled", ["Yes", "No"])

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
        st.success("Mission launched. Previous LIVE mission closed automatically.")
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

    render_enterprise_pipeline_form(db, event_id, mission)

    st.divider()
    st.subheader("📥 Mission Submissions")

    current_mission_id = mission.get("MissionID") if mission else None
    current_submissions = [
        row for row in submissions
        if not current_mission_id or str(row.get("MissionID")) == str(current_mission_id)
    ]

    pending_current = [
        row for row in current_submissions
        if str(row.get("Judged", "")).lower() not in APPROVED_VALUES
    ]

    if pending_current and mission and str(mission.get("SubmissionType", "")).upper() in {"NASI", "TEXT"}:
        if st.button("✅ Approve All Pending NASI", width="stretch"):
            count = db.approve_all_pending(
                event_id=event_id,
                mission_id=current_mission_id,
                default_score=0,
                remarks="NASI reflection bulk approved",
            )
            st.success(f"Approved {count} reflection(s).")
            st.rerun()

    if not current_submissions:
        st.info("No submissions received for the current mission yet.")
    else:
        for submission in current_submissions:
            submission_id = submission.get("SubmissionID")
            auto_score, formula = suggested_score(db, submission)
            already_approved = str(submission.get("Judged", "")).lower() in APPROVED_VALUES

            with st.container():
                st.markdown(
                    f"""
**{submission.get('TeamName', '')}**

- Participant: {submission.get('ParticipantName', '')}
- Mission: {submission.get('MissionID', '')}
- Submitted: {submission.get('SubmittedAt', '')}
- Judged: {submission.get('Judged', 'No')}
- Saved Score: {submission.get('Score', '')}
"""
                )
                render_submission_payload(submission.get("ImageURL", ""))

                st.info(f"Suggested score: **{format_score(auto_score)}** — {formula}")

                override = st.checkbox(
                    "Override calculated score",
                    value=False,
                    key=f"override_{submission_id}",
                )
                score = auto_score
                if override:
                    score = st.number_input(
                        "Override Score",
                        min_value=0.0,
                        max_value=1000.0,
                        value=float(auto_score),
                        step=1.0,
                        key=f"score_{submission_id}",
                    )

                remarks = st.text_area(
                    "Remarks",
                    value=submission.get("Remarks", ""),
                    key=f"remarks_{submission_id}",
                )

                button_label = "🔄 Update Score" if already_approved else "✅ Approve Submission"
                if st.button(button_label, key=f"approve_{submission_id}", width="stretch"):
                    db.update_submission_score(
                        submission_id=submission_id,
                        score=round(score, 1),
                        remarks=remarks,
                        judged="Yes",
                    )
                    st.success("Submission updated.")
                    st.rerun()

                st.divider()

    if st.button("🔄 Refresh Now", width="stretch"):
        db.clear_cache()
        st.rerun()
