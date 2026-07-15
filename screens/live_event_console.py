import uuid
from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from data.google_drive import get_photo_url
from data.google_sheets import GoogleSheetsDB


APPROVED_VALUES = {"yes", "true", "approved"}


def auto_refresh(seconds=5):
    st_autorefresh(
        interval=seconds * 1000,
        key="live_event_console_refresh",
    )




def get_value(record, field_name, default=""):
    """Read a Google Sheets record safely, even if a header has spaces/case differences."""
    if not isinstance(record, dict):
        return default

    wanted = str(field_name).strip().lower()
    for key, value in record.items():
        if str(key).strip().lower() == wanted:
            return value

    return default


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
        if str(submission.get("Status", "")).upper() != "APPROVED":
            continue

        submission_type = str(submission.get("SubmissionType", "")).upper()
        if submission_type in {"NASI", "PIPELINE_ENTERPRISE"}:
            continue

        team = str(submission.get("TeamName", "Unknown Team") or "Unknown Team")
        score = safe_float(submission.get("Score", 0))
        leaderboard[team] = leaderboard.get(team, 0.0) + score

    return sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)


def calculate_score(submission):
    submission_type = str(get_value(submission, "SubmissionType", "")).upper().strip()
    metric1 = get_value(submission, "Metric1", "")
    metric2 = get_value(submission, "Metric2", "")
    metric3 = get_value(submission, "Metric3", "")

    if submission_type in {"PIPELINE", "PIPELINE_ENTERPRISE"}:
        target = safe_float(metric1)
        achieved = safe_float(metric2)
        lost = safe_float(metric3)

        if target <= 0:
            return 0.0, (
                f"Target must be greater than zero. "
                f"Received Target={metric1!r}, Achieved={metric2!r}, Lost={metric3!r}."
            )

        score = ((achieved - lost) / target) * 100
        return round(max(score, 0), 1), "(Achieved - Lost Clients) ÷ Target × 100"

    if submission_type == "HELIUM":
        completed = str(metric1).strip().upper() == "YES"
        return (100.0 if completed else 0.0), "Completed = 100; Not completed = 0"

    if submission_type == "KEYPUNCH":
        highest = min(max(safe_float(metric1), 0), 30)
        return round((highest / 30) * 100, 1), "Highest Number ÷ 30 × 100"

    if submission_type == "CATALYST":
        completed = str(metric1).strip().upper() == "YES"
        return (100.0 if completed else 0.0), "Completed = 100; Not completed = 0"

    if submission_type == "NASI":
        return 0.0, "Reflection only — no score"

    return safe_float(get_value(submission, "Score", 0)), "Manual score"


def mission_defaults(submission_type):
    defaults = {
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
            "points": 0,
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
            "clue": "Individual reflection. No points awarded.",
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
    return defaults.get(submission_type, defaults["PHOTO"])


def render_submission_details(submission):
    submission_type = str(get_value(submission, "SubmissionType", "")).upper().strip()
    metric1 = get_value(submission, "Metric1", "")
    metric2 = get_value(submission, "Metric2", "")
    metric3 = get_value(submission, "Metric3", "")
    remarks = get_value(submission, "Remarks", "")
    image_url = get_value(submission, "ImageURL", "")
    drive_file_id = get_value(submission, "DriveFileID", "")

    if submission_type in {"PIPELINE", "PIPELINE_ENTERPRISE"}:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Target", metric1)
        with col2:
            st.metric("Achieved", metric2)
        with col3:
            st.metric("Lost Clients", metric3)
    elif submission_type == "KEYPUNCH":
        st.metric("Highest Number Reached", metric1)
    elif submission_type in {"HELIUM", "CATALYST"}:
        st.metric("Completed", metric1)
    elif submission_type == "NASI":
        st.markdown("### NASI Reflection")
        st.info(remarks or "No reflection text recorded.")
    elif remarks:
        st.info(remarks)

    display_url = get_photo_url(image_url, drive_file_id)
    if display_url:
        st.image(
            display_url,
            caption="Mission Submission",
            width="stretch",
        )
    elif image_url or drive_file_id:
        st.warning("Submission image is temporarily unavailable.")


def render_enterprise_pipeline_form(db, event_id, mission):
    if not mission:
        return

    mission_type = str(mission.get("SubmissionType", "")).upper()
    if mission_type != "PIPELINE_ENTERPRISE":
        return

    st.divider()
    st.subheader("🤝 Enterprise Pipeline Result")
    st.caption("Facilitator enters one collective result for all six groups.")

    existing = db.get_team_submission(event_id, mission.get("MissionID"), "ENTERPRISE")
    if existing:
        render_submission_details(existing)
        score, formula = calculate_score(existing)
        st.success(f"Collective enterprise score: {format_score(score)}%")
        st.caption(formula)
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        target = st.number_input("Enterprise Target", min_value=1, value=300, step=1)
    with col2:
        achieved = st.number_input("Enterprise Achieved", min_value=0, value=0, step=1)
    with col3:
        lost = st.number_input("Enterprise Lost Clients", min_value=0, value=0, step=1)

    score = max(((achieved - lost) / target) * 100, 0)
    st.metric("Calculated Enterprise Score", f"{format_score(score)}%")

    if st.button("✅ Save Enterprise Result", width="stretch"):
        db.save_submission(
            submission_id=str(uuid.uuid4()),
            event_id=event_id,
            mission_id=mission.get("MissionID"),
            team_name="ENTERPRISE",
            participant_name="Facilitator",
            image_url="",
            drive_file_id="FACILITATOR-ENTRY",
            submitted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            score=round(score, 1),
            judged="Yes",
            remarks="Collective enterprise result",
            submission_type="PIPELINE_ENTERPRISE",
            metric1=target,
            metric2=achieved,
            metric3=lost,
            status="APPROVED",
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
        st.info("No approved team scores yet.")
    else:
        for index, (team, score) in enumerate(leaderboard, start=1):
            medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else "⭐"
            st.metric(f"{medal} {index}. {team}", f"{format_score(score)} pts")

    enterprise_results = [
        s for s in submissions
        if str(s.get("SubmissionType", "")).upper() == "PIPELINE_ENTERPRISE"
        and str(s.get("Status", "")).upper() == "APPROVED"
    ]
    if enterprise_results:
        latest_enterprise = enterprise_results[-1]
        st.success(
            f"🤝 Enterprise Pipeline Score: {format_score(latest_enterprise.get('Score', 0))}%"
        )

    st.divider()
    st.subheader("🚀 Launch Mission")

    event_missions = db.get_event_missions(event_id, include_closed=True)
    if event_missions:
        mission_options = {
            f"{row.get('MissionID', '')} | {row.get('Title', '')} | {row.get('Status', '')}": row
            for row in event_missions
        }
        mission_label = st.selectbox(
            "Event Mission",
            list(mission_options),
            key="console_event_mission",
        )
        selected_mission = mission_options[mission_label]
        facilitator_instructions = str(
            selected_mission.get("FacilitatorInstructions", "") or ""
        ).strip()
        if facilitator_instructions:
            st.info("Facilitator: " + facilitator_instructions)
        if st.button("🚀 Launch Selected Mission", width="stretch"):
            db.launch_event_mission(
                event_id,
                selected_mission.get("MissionID", ""),
            )
            st.success("Mission launched. Previous LIVE mission closed automatically.")
            st.rerun()
    else:
        st.info("No event missions yet. Add them in Mission Studio or use Quick Create.")

    with st.expander("Quick Create Mission"):
        submission_type = st.selectbox(
            "Mission Type",
            [
                "PIPELINE",
                "PIPELINE_ENTERPRISE",
                "HELIUM",
                "KEYPUNCH",
                "CATALYST",
                "NASI",
                "PHOTO",
                "TEXT",
                "NONE",
            ],
            key="quick_mission_type",
        )
        defaults = mission_defaults(submission_type)

        mission_id = st.text_input("Mission ID", value=defaults["mission_id"])
        title = st.text_input("Mission Title", value=defaults["title"])
        description = st.text_area("Mission Instructions", value=defaults["description"])
        facilitator_instructions = st.text_area("Facilitator Instructions", value="")
        points = st.number_input("Points", min_value=0, value=defaults["points"], step=10)
        video_url = st.text_input("Video URL", value="")
        image_url = st.text_input("Image URL", value="")
        document_url = st.text_input("Document / PDF URL", value="")
        clue = st.text_area("Clue", value=defaults["clue"])
        answer = st.text_input("Answer", value="")
        hint1 = st.text_input("Hint 1", value="")
        hint2 = st.text_input("Hint 2", value="")
        hint3 = st.text_input("Hint 3", value="")
        ai_help_enabled = st.selectbox("AI Help Enabled", ["Yes", "No"])

        if st.button("🚀 Create and Launch", width="stretch"):
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
                participant_instructions=description,
                facilitator_instructions=facilitator_instructions,
                video_url=video_url,
                image_url=image_url,
                document_url=document_url,
            )
            st.success("Mission created and launched.")
            st.rerun()

    st.divider()
    st.subheader("Current Mission")

    mission = db.get_current_mission(event_id)
    if mission:
        st.success(mission.get("Title", "Mission"))
        participant_instructions = str(
            mission.get("ParticipantInstructions", "")
            or mission.get("Description", "")
        ).strip()
        facilitator_instructions = str(
            mission.get("FacilitatorInstructions", "") or ""
        ).strip()
        if participant_instructions:
            st.write(participant_instructions)
        if facilitator_instructions:
            st.info("Facilitator: " + facilitator_instructions)
        if mission.get("VideoURL"):
            st.video(str(mission.get("VideoURL")))
        if mission.get("ImageURL"):
            st.image(str(mission.get("ImageURL")), width="stretch")
        if mission.get("DocumentURL"):
            st.link_button(
                "📄 Open Mission Document",
                str(mission.get("DocumentURL")),
            )
        if mission.get("DebriefQuestions"):
            with st.expander("Debrief Questions"):
                st.markdown(str(mission.get("DebriefQuestions")))
        st.caption(f"Submission Type: {mission.get('SubmissionType', '')}")
    else:
        st.info("No live mission yet.")

    render_enterprise_pipeline_form(db, event_id, mission)

    st.divider()
    st.subheader("📥 Mission Submissions")

    current_mission_id = mission.get("MissionID") if mission else None
    current_submissions = [
        row for row in submissions
        if not current_mission_id
        or str(row.get("MissionID", "")) == str(current_mission_id)
    ]

    pending_current = [
        row for row in current_submissions
        if str(row.get("Status", "")).upper() == "PENDING"
    ]

    if pending_current:
        mission_type = str(mission.get("SubmissionType", "") if mission else "").upper()
        bulk_score = 0 if mission_type == "NASI" else None

        if st.button(
            f"✅ Approve All Pending ({len(pending_current)})",
            width="stretch",
        ):
            count = 0
            for submission in pending_current:
                calculated_score, _ = calculate_score(submission)
                final_score = bulk_score if bulk_score is not None else calculated_score
                updated = db.update_submission_score(
                    submission_id=submission.get("SubmissionID"),
                    score=round(final_score, 1),
                    remarks=submission.get("Remarks", ""),
                    judged="Yes",
                    status="APPROVED",
                )
                if updated:
                    count += 1

            st.success(f"Approved {count} submission(s).")
            st.rerun()

    if not current_submissions:
        st.info("No submissions received for the current mission yet.")
    else:
        for submission in current_submissions:
            submission_id = submission.get("SubmissionID")
            suggested, formula = calculate_score(submission)
            approved = str(submission.get("Status", "")).upper() == "APPROVED"

            with st.container():
                st.markdown(
                    f"""
**{submission.get('TeamName', '')}**

- Participant: {submission.get('ParticipantName', '')}
- Mission: {submission.get('MissionID', '')}
- Type: {get_value(submission, 'SubmissionType', '')}
- Submitted: {submission.get('SubmittedAt', '')}
- Status: {get_value(submission, 'Status', 'PENDING')}
- Saved Score: {get_value(submission, 'Score', '')}
"""
                )

                render_submission_details(submission)
                st.info(f"Calculated score: **{format_score(suggested)}** — {formula}")

                override = st.checkbox(
                    "Override calculated score",
                    value=False,
                    key=f"override_{submission_id}",
                )

                final_score = suggested
                if override:
                    final_score = st.number_input(
                        "Override Score",
                        min_value=0.0,
                        max_value=1000.0,
                        value=float(suggested),
                        step=1.0,
                        key=f"score_{submission_id}",
                    )

                remarks = st.text_area(
                    "Remarks",
                    value=get_value(submission, "Remarks", ""),
                    key=f"remarks_{submission_id}",
                )

                button_label = "🔄 Update Score" if approved else "✅ Approve Submission"
                if st.button(
                    button_label,
                    key=f"approve_{submission_id}",
                    width="stretch",
                ):
                    db.update_submission_score(
                        submission_id=submission_id,
                        score=round(final_score, 1),
                        remarks=remarks,
                        judged="Yes",
                        status="APPROVED",
                    )
                    st.success("Submission updated.")
                    st.rerun()

                st.divider()

    if st.button("🔄 Refresh Now", width="stretch"):
        db.clear_cache()
        st.rerun()
