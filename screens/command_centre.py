import streamlit as st

from data.google_sheets import GoogleSheetsDB
from data.runtime_database import RuntimeDatabaseError
from screens.app_state import request_navigation, select_active_event


def _safe_count(callback):
    try:
        return len(callback() or [])
    except Exception:
        return 0


def _safe_number(callback):
    try:
        return int(callback() or 0)
    except Exception:
        return 0


def _readiness_row(name, ready, detail):
    return {
        "Status": "✅ Ready" if ready else "⚠️ Required",
        "Setup Step": name,
        "Details": detail,
    }


def show_command_centre():
    st.title("🏠 EXOS Command Centre")
    st.caption("Select one event, confirm readiness, then build or run it.")

    db = GoogleSheetsDB()
    events = db.get_events()
    if not events:
        st.warning("No events found.")
        if st.button("Create the First Event", width="stretch"):
            request_navigation("🧰 Build Event", "1. Event & Teams")
        return

    event = select_active_event(
        events,
        label="Active Event",
        key="command_centre_event",
    )
    event_id = str(event.get("EventID", ""))

    teams = _safe_count(lambda: db.get_teams(event_id))
    missions = _safe_count(lambda: db.get_event_missions(event_id))
    stages = _safe_count(lambda: db.get_programme_stages(event_id))
    participants = _safe_number(
        lambda: db.get_participant_count(event_id)
    )
    submissions = _safe_count(lambda: db.get_submissions(event_id))

    runtime_stage = None
    runtime_error = ""
    if db.runtime.can_publish:
        try:
            runtime_stage = db.runtime.get_event_stage(event_id)
        except RuntimeDatabaseError as error:
            runtime_error = str(error)

    st.divider()
    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Participants", participants)
    metric2.metric("Teams", teams)
    metric3.metric("Missions", missions)
    metric4.metric("Submissions", submissions)

    current_stage = str(
        (runtime_stage or {}).get("StageName", "")
        or "Not launched"
    )
    join_code = str(event.get("JoinCode", "") or "—")
    status1, status2 = st.columns(2)
    with status1:
        st.info(f"**Join Code:** {join_code}")
    with status2:
        st.info(f"**Current Stage:** {current_stage}")

    readiness = [
        _readiness_row(
            "Event details",
            bool(event_id and event.get("EventName")),
            str(event.get("EventName", "Unnamed event")),
        ),
        _readiness_row(
            "Teams",
            teams > 0,
            f"{teams} team(s) configured",
        ),
        _readiness_row(
            "Missions",
            missions > 0,
            f"{missions} event mission(s)",
        ),
        _readiness_row(
            "Programme timeline",
            stages > 0,
            f"{stages} stage(s) in Show Control",
        ),
        _readiness_row(
            "Live runtime",
            runtime_stage is not None,
            "Published to Supabase" if runtime_stage else (
                runtime_error or "Publish registration from Build Event"
            ),
        ),
    ]
    ready_count = sum(row["Status"] == "✅ Ready" for row in readiness)

    st.subheader("Event Readiness")
    st.progress(ready_count / len(readiness))
    st.caption(f"{ready_count} of {len(readiness)} readiness checks passed")
    st.dataframe(readiness, width="stretch", hide_index=True)

    st.subheader("What do you want to do?")
    build_col, run_col, display_col = st.columns(3)
    with build_col:
        if st.button("🧰 Build / Prepare Event", width="stretch"):
            request_navigation("🧰 Build Event", "1. Event & Teams")
    with run_col:
        if st.button("🎬 Run Live Event", width="stretch"):
            request_navigation("🎬 Run Event", "1. Control Flow")
    with display_col:
        if st.button("📺 Open Projector Display", width="stretch"):
            request_navigation("📺 Projector Display")

    if ready_count < len(readiness):
        st.warning(
            "Complete the items marked Required before handing the event to another facilitator."
        )


def show_results_reports():
    st.title("📊 Results & Reports")
    st.caption("Review the selected event before generating client reports.")

    db = GoogleSheetsDB()
    events = db.get_events()
    if not events:
        st.warning("No events found.")
        return

    event = select_active_event(
        events,
        label="Event to Review",
        key="results_reports_event",
    )
    event_id = str(event.get("EventID", ""))
    participants = _safe_number(
        lambda: db.get_participant_count(event_id)
    )
    try:
        submissions = db.get_submissions(event_id)
    except Exception as error:
        submissions = []
        st.warning("Results are temporarily reconnecting.")
        st.caption(str(error))

    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("Participants", participants)
    metric2.metric("Submissions", len(submissions))
    metric3.metric(
        "Approved",
        sum(
            str(row.get("Status", "")).upper() == "APPROVED"
            for row in submissions
        ),
    )

    if submissions:
        fields = [
            "MissionID",
            "TeamName",
            "ParticipantName",
            "SubmissionType",
            "Score",
            "Status",
            "Remarks",
            "SubmittedAt",
        ]
        st.dataframe(
            [
                {field: row.get(field, "") for field in fields}
                for row in submissions
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No submissions have been received for this event.")

    st.info(
        "PDF client reporting will be added here after the live Mission AI workflow is completed."
    )
