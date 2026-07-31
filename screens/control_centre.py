import html

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from data.google_sheets import GoogleSheetsDB
from engines.stage_timer import remaining_seconds
from engines.programme_hierarchy import (
    activity_content_config,
    activity_details,
    build_programme_hierarchy,
    current_module_activity,
    friendly_type,
    linked_content_stage,
)
from screens.app_state import select_active_event
from screens.live_event_console import (
    calculate_leaderboard,
    format_score,
    render_credit_wallet_control,
    render_review_scoring_widget,
)
from screens.projector_broadcast import (
    projector_broadcast_state,
    render_broadcast_controller,
)


def stage_family(stage):
    combined = (
        str(stage.get("StageName", ""))
        + " "
        + str(stage.get("StageType", ""))
    ).casefold()
    if any(word in combined for word in ("closing", "winner", "results")):
        return "closing"
    if any(word in combined for word in ("performance", "judging", "race")):
        return "performance"
    if any(word in combined for word in ("sync", "marketplace", "purchase")):
        return "purchasing"
    if any(word in combined for word in ("lunch", "break", "debrief")):
        return "review"
    if any(word in combined for word in ("mission", "active", "road hunt")):
        return "mission"
    if any(word in combined for word in ("bridge", "trust", "scored")):
        return "scored"
    return "registration"


def _current_index(stages, state):
    stage_no = str((state or {}).get("CurrentStageNo", ""))
    for index, stage in enumerate(stages):
        if str(stage.get("StageNo", "")) == stage_no:
            return index
    return 0


def _format_timer(seconds):
    seconds = max(int(seconds or 0), 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _set_stage(db, event_id, stage, status="READY"):
    result = db.set_event_stage(event_id, stage)
    db.update_event_metadata(event_id, {
        "CurrentStageStatus": status,
    })
    warning = str((result or {}).get("Warning", "")).strip()
    if warning:
        st.warning(warning)
    st.rerun()


def _start_programme_activity(db, event_id, stage, module):
    """Publish the activity's linked content before broadcasting its stage."""
    config = activity_content_config(stage, module)
    live_stage = linked_content_stage(stage, module)
    if (
        config["ContentType"] == "Experience Board"
        and config["LinkedContent"]
    ):
        result = db.activate_experience_set(
            event_id, config["LinkedContent"],
        )
        live_stage = linked_content_stage(
            stage, module, result["ExperiencesPublished"],
        )
    db.set_event_stage(event_id, live_stage)
    return live_stage


def _render_timer(db, event_id, stage):
    stage_no = stage.get("StageNo", "")
    duration = stage.get("DurationMinutes", 0)
    timer = db.get_stage_timer(event_id, stage_no, duration)
    remaining = remaining_seconds(timer)
    if str(timer.get("Status", "")).upper() == "RUNNING":
        st_autorefresh(
            interval=1000,
            key=f"control_timer_refresh_{event_id}_{stage_no}",
        )
    st.metric("Stage Timer", _format_timer(remaining), timer.get("Status", "READY"))
    start, pause, reset, end = st.columns(4)
    status = str(timer.get("Status", "READY")).upper()
    if start.button(
        "Resume" if status == "PAUSED" else "Start",
        type="primary",
        width="stretch",
        disabled=status == "RUNNING",
        key=f"timer_start_{event_id}_{stage_no}",
    ):
        db.update_stage_timer(
            event_id,
            stage_no,
            "RESUME" if status == "PAUSED" else "START",
            duration,
        )
        db.update_event_metadata(event_id, {"CurrentStageStatus": "RUNNING"})
        st.rerun()
    if pause.button(
        "Pause",
        width="stretch",
        disabled=status != "RUNNING",
        key=f"timer_pause_{event_id}_{stage_no}",
    ):
        db.update_stage_timer(event_id, stage_no, "PAUSE", duration)
        db.update_event_metadata(event_id, {"CurrentStageStatus": "PAUSED"})
        st.rerun()
    if reset.button(
        "Reset",
        width="stretch",
        key=f"timer_reset_{event_id}_{stage_no}",
    ):
        db.update_stage_timer(event_id, stage_no, "RESET", duration)
        db.update_event_metadata(event_id, {"CurrentStageStatus": "READY"})
        st.rerun()
    if end.button(
        "End Stage",
        width="stretch",
        key=f"timer_end_{event_id}_{stage_no}",
    ):
        db.update_stage_timer(event_id, stage_no, "END", duration)
        db.update_event_metadata(event_id, {"CurrentStageStatus": "ENDED"})
        st.rerun()


def _render_registration(db, event_id):
    event = db.get_event(event_id)
    metadata = db.event_metadata(event)
    is_open = bool(metadata.get("RegistrationOpen", False))
    st.subheader("Registration")
    status, participants, allocation = st.columns(3)
    status.metric("Registration", "Open" if is_open else "Closed")
    participants.metric("Participants", db.get_participant_count(event_id))
    teams = db.get_teams(event_id)
    allocation.metric("Team allocation", f"{len(teams)} teams ready")
    toggle, formation = st.columns(2)
    if toggle.button(
        "Close Registration" if is_open else "Open Registration",
        type="primary",
        width="stretch",
    ):
        db.update_event_metadata(event_id, {"RegistrationOpen": not is_open})
        st.rerun()
    formation.info("Launch Group Formation with the Next Stage control.")


def _render_mission_board(db, event_id):
    mission = db.get_current_mission(event_id)
    submissions = db.get_submissions(event_id)
    if mission:
        st.subheader("Experience Board")
        st.success(mission.get("Title", "Current experience"))
        st.write(
            mission.get("ParticipantInstructions", "")
            or mission.get("Description", "")
        )
        teams = db.get_teams(event_id)
        submitted = {
            str(row.get("TeamName", ""))
            for row in submissions
            if str(row.get("MissionID", ""))
            == str(mission.get("MissionID", ""))
        }
        progress = len(submitted) / max(len(teams), 1)
        st.progress(progress)
        st.caption(f"{len(submitted)} of {len(teams)} teams submitted")
    else:
        st.info("No experience is active for this stage.")


def _render_rankings(db, event_id, final=False):
    leaderboard = calculate_leaderboard(db.get_submissions(event_id))
    st.subheader("Final Rankings" if final else "Current Ranking")
    if not leaderboard:
        st.info("No approved scores yet.")
        return
    for position, (team, score) in enumerate(leaderboard, start=1):
        st.metric(f"{position}. {team}", f"{format_score(score)} pts")


def _render_stage_widgets(db, event_id, family):
    if family == "registration":
        _render_registration(db, event_id)
    elif family == "scored":
        render_review_scoring_widget(db, event_id)
        _render_rankings(db, event_id)
    elif family == "mission":
        _render_mission_board(db, event_id)
        render_review_scoring_widget(db, event_id)
        render_credit_wallet_control(db, event_id)
    elif family == "review":
        render_review_scoring_widget(db, event_id, show_all=True)
        render_credit_wallet_control(db, event_id)
        _render_rankings(db, event_id)
    elif family == "purchasing":
        render_credit_wallet_control(db, event_id)
    elif family == "performance":
        render_review_scoring_widget(db, event_id, show_all=True)
        _render_rankings(db, event_id)
    else:
        _render_rankings(db, event_id, final=True)
        st.info("Export the detailed result table from Results & Reports.")


def show_control_centre():
    st.markdown(
        """
        <style>
        .control-hero {padding:24px;border-radius:22px;
          background:#082D58;
          border:1px solid rgba(181,154,55,.38);margin-bottom:18px;color:#FFFFFF}
        .control-kicker {color:#B59A37;font-size:.78rem;font-weight:800;
          letter-spacing:.14em;text-transform:uppercase}
        .control-title {font-size:clamp(2.1rem,4vw,4rem);font-weight:900;
          letter-spacing:-.04em;line-height:1;margin:.35rem 0}
        </style>
        """,
        unsafe_allow_html=True,
    )
    db = GoogleSheetsDB()
    events = db.get_events()
    if not events:
        st.warning("Create an event before opening Control Centre.")
        return
    event = select_active_event(events, label="Current event", key="control_event")
    event_id = str(event.get("EventID", ""))
    stages = db.get_programme_stages(event_id)
    if not stages:
        st.warning("Build and save the programme before launch.")
        return
    state = db.get_event_state(event_id)
    index = _current_index(stages, state)
    stage = stages[index]
    current_module, current_activity = current_module_activity(
        stages, stage.get("StageNo", "")
    )
    programme_modules = build_programme_hierarchy(stages)
    module_index = next(
        (
            position for position, module in enumerate(programme_modules)
            if module.get("ModuleID") == current_module.get("ModuleID")
        ),
        0,
    )
    selected_event = db.get_event(event_id)
    metadata = db.event_metadata(selected_event)
    broadcast_state = projector_broadcast_state(selected_event)
    stage_status = str(metadata.get("CurrentStageStatus", "READY"))
    content_config = activity_content_config(current_activity, current_module)
    linked_content_name = (
        content_config["LinkedContent"] or "Event-specific activity content"
    )
    participant_details = activity_details(current_activity)

    st.markdown(
        f"""
        <div class="control-hero">
          <div class="control-kicker">{html.escape(str(event.get("EventName", "")))}</div>
          <div class="control-title">{html.escape(str(current_module.get("ModuleName", "")))}</div>
          <div style="font-size:1.25rem">Current activity: {html.escape(str(current_activity.get("StageName", "")))}</div>
          <div>{html.escape(friendly_type(current_activity))} · Activity {index + 1} of {len(stages)} · {html.escape(stage_status)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Participants", db.get_participant_count(event_id))
    c2.metric("Teams", db.get_team_count(event_id))
    c3.metric("Join Code", event.get("JoinCode", "—"))
    c4.metric(
        "Projector",
        broadcast_state.get("Mode", "Welcome"),
        "Facilitator broadcast",
    )

    link_type_col, link_name_col = st.columns(2)
    link_type_col.metric("Linked Content Type", content_config["ContentType"])
    link_name_col.metric("Linked Content Name", linked_content_name)
    with st.expander("Participant Preview", expanded=True):
        st.markdown(f"### {current_activity.get('StageName', 'Activity')}")
        if participant_details["ParticipantNarrative"]:
            st.info(participant_details["ParticipantNarrative"])
        preview_task = (
            participant_details["ParticipantTask"]
            or current_activity.get("ParticipantMessage", "")
        )
        if preview_task:
            st.write(preview_task)
        if participant_details["EvidenceRequirement"]:
            st.caption(participant_details["EvidenceRequirement"])
        if content_config["LinkedContent"]:
            st.success(f"Publishes: {content_config['LinkedContent']}")

    previous, launch, next_col, end_module, next_module = st.columns([1, 2, 1, 1, 1])
    if previous.button(
        "Previous Activity",
        width="stretch",
        disabled=index == 0,
    ):
        _set_stage(db, event_id, stages[index - 1])
    if launch.button(
        "Start Activity",
        type="primary",
        width="stretch",
    ):
        _start_programme_activity(db, event_id, stage, current_module)
        db.update_stage_timer(
            event_id,
            stage.get("StageNo", ""),
            "START",
            stage.get("DurationMinutes", 0),
        )
        db.update_event_metadata(event_id, {"CurrentStageStatus": "RUNNING"})
        st.rerun()
    if next_col.button(
        "Next Activity",
        width="stretch",
        disabled=index >= len(stages) - 1,
    ):
        _set_stage(db, event_id, stages[index + 1])
    if end_module.button(
        "End Activity",
        width="stretch",
    ):
        db.update_stage_timer(
            event_id,
            stage.get("StageNo", ""),
            "END",
            stage.get("DurationMinutes", 0),
        )
        db.update_event_metadata(event_id, {"CurrentStageStatus": "ENDED"})
        st.rerun()
    if next_module.button(
        "Next Module",
        width="stretch",
        disabled=module_index >= len(programme_modules) - 1,
    ):
        following = programme_modules[module_index + 1]["Activities"][0]
        _set_stage(db, event_id, following)

    timer_col, broadcast_col = st.columns([1, 2])
    with timer_col:
        _render_timer(db, event_id, stage)
    with broadcast_col:
        render_broadcast_controller(db, event_id)

    st.divider()
    _render_stage_widgets(db, event_id, stage_family(stage))
