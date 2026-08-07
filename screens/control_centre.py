import html

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from data.google_sheets import GoogleSheetsDB
from data.control_runtime import ControlRuntime
from data.experience_repository import SupabaseExperienceRepository
from engines.stage_timer import remaining_seconds
from engines.programme_hierarchy import (
    activity_content_config,
    activity_details,
    friendly_type,
    linked_content_stage,
)
from engines.programme_adapter import CanonicalProgrammeAdapter, ProgrammeIntegrityError
from screens.app_state import select_active_event
from screens.live_event_console import (
    calculate_leaderboard,
    format_score,
    render_credit_wallet_control,
    render_road_hunt_operations,
    render_review_scoring_widget,
)
from screens.projector_broadcast import (
    DEFAULT_BROADCAST,
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


def _format_timer(seconds):
    seconds = max(int(seconds or 0), 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _set_stage(control, event_id, stage, status="READY"):
    result = control.set_stage(event_id, stage)
    control.control_state(event_id, "CurrentStageStatus", status)
    warning = str((result or {}).get("Warning", "")).strip()
    if warning:
        st.warning(warning)
    st.rerun()


def _start_programme_activity(control, event_id, stage, module):
    """Publish the activity's linked content before broadcasting its stage."""
    if not stage.get("RuntimeEligible", True):
        raise ProgrammeIntegrityError(["Inactive or superseded activities cannot be launched."])
    config = {
        "ContentType": stage.get("ContentType", "Standard Activity"),
        "LinkedContent": stage.get("LinkedContentID", ""),
        "LinkedContentID": stage.get("LinkedContentID", ""),
        "LinkedContentName": stage.get("LinkedContentName", ""),
    }
    live_stage = linked_content_stage(stage, module)
    if (
        config["ContentType"] == "Experience Board"
        and config["LinkedContent"]
    ):
        result = control.activate_experience_set(
            event_id, config["LinkedContent"],
        )
        live_stage = linked_content_stage(
            stage, module, result["ExperiencesPublished"],
        )
    control.set_stage(event_id, live_stage)
    return live_stage


def _render_timer(db, control, event_id, stage):
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
        control.timer(
            event_id,
            stage_no,
            "RESUME" if status == "PAUSED" else "START",
            duration,
        )
        control.control_state(event_id, "CurrentStageStatus", "RUNNING")
        st.rerun()
    if pause.button(
        "Pause",
        width="stretch",
        disabled=status != "RUNNING",
        key=f"timer_pause_{event_id}_{stage_no}",
    ):
        control.timer(event_id, stage_no, "PAUSE", duration)
        control.control_state(event_id, "CurrentStageStatus", "PAUSED")
        st.rerun()
    if reset.button(
        "Reset",
        width="stretch",
        key=f"timer_reset_{event_id}_{stage_no}",
    ):
        control.timer(event_id, stage_no, "RESET", duration)
        control.control_state(event_id, "CurrentStageStatus", "READY")
        st.rerun()
    if end.button(
        "End Stage",
        width="stretch",
        key=f"timer_end_{event_id}_{stage_no}",
    ):
        control.timer(event_id, stage_no, "END", duration)
        control.control_state(event_id, "CurrentStageStatus", "ENDED")
        st.rerun()


def _render_registration(db, control, event_id):
    event = db.get_event(event_id)
    runtime_control = db.get_runtime_control_state(event_id)
    is_open = bool(runtime_control.get("RegistrationOpen", False))
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
        control.control_state(event_id, "RegistrationOpen", not is_open)
        st.rerun()
    formation.info("Launch Group Formation with the Next Stage control.")


def _render_team_management(db, control, event_id):
    """Facilitator-only recovery controls backed by audited runtime RPCs."""
    runtime = db.runtime
    st.subheader("Team Management")
    if not runtime.can_publish:
        st.warning("Team Management requires the protected runtime service credential.")
        return
    participants = runtime.get_players(event_id)
    teams = db.get_teams(event_id)
    if not participants:
        st.info("No runtime participants are registered for this event.")
        return

    actor = st.text_input("Facilitator name", key=f"identity_actor_{event_id}")
    st.caption("Every recovery override is written to the identity audit log.")
    event_override = st.toggle(
        "Allow any team member in this event to submit",
        key=f"event_submission_override_{event_id}",
    )
    if event_override:
        st.warning("Emergency event-wide submission override is enabled in this control session.")
    if st.button("Apply event submission policy", key=f"apply_event_override_{event_id}"):
        control.set_submission_override(event_id, "*", event_override, actor)
        st.success("Event submission policy updated and audited.")

    for team in teams:
        team_id = str(team.get("TeamID", ""))
        team_name = str(team.get("TeamName", ""))
        members = [row for row in participants if row.get("Team") == team_name]
        leader = next((row for row in members if row.get("IsLeader")), None)
        with st.expander(f"{team_name} · {team_id}"):
            st.caption(
                f"Leader: {(leader or {}).get('Name', 'Not assigned')} · "
                f"{len(members)} participant(s)"
            )
            st.dataframe([{
                "ParticipantID": row.get("ParticipantID", ""),
                "Name": row.get("Name", ""),
                "Country": row.get("Country", ""),
                "Leader": row.get("IsLeader", False),
                "Last active": row.get("LastSeenAt", row.get("JoinedAt", "")),
            } for row in members], hide_index=True, width="stretch")
            if members:
                choices = {row.get("ParticipantID", ""): row for row in members}
                selected = st.selectbox(
                    "Team member", list(choices),
                    format_func=lambda value: choices[value].get("Name", value),
                    key=f"identity_member_{event_id}_{team_id}",
                )
                if st.button("Recover Participant", key=f"recover_participant_{event_id}_{team_id}"):
                    recovery = control.recover_participant(event_id, selected)
                    st.session_state[f"recovery_{event_id}_{selected}"] = recovery
                    st.success(
                        "Authoritative identity, team, country, leader rights, credits and "
                        "session token recovered without reallocation."
                    )
                    st.json(recovery)
                if st.button("Transfer Team Leader", key=f"transfer_leader_{event_id}_{team_id}"):
                    control.transfer_leader(event_id, team_id, selected, actor)
                    st.success("Leadership transferred immediately and audited.")
                    st.rerun()
                destination_ids = [
                    str(item.get("TeamID", "")) for item in teams
                    if str(item.get("TeamID", "")) != team_id
                ]
                if destination_ids:
                    destination = st.selectbox(
                        "Correct team", destination_ids,
                        format_func=lambda value: next(
                            str(item.get("TeamName", value)) for item in teams
                            if str(item.get("TeamID", "")) == value
                        ),
                        key=f"identity_destination_{event_id}_{team_id}",
                    )
                    move_reason = st.text_input(
                        "Team correction reason",
                        key=f"identity_move_reason_{event_id}_{team_id}",
                    )
                    move_confirmed = st.checkbox(
                        "Confirm authorised team correction",
                        key=f"identity_move_confirm_{event_id}_{team_id}",
                    )
                    if st.button(
                        "Move Participant to Correct Team",
                        disabled=not move_confirmed or not move_reason.strip(),
                        key=f"identity_move_{event_id}_{team_id}",
                    ):
                        control.move_participant(selected, destination, move_reason, actor)
                        st.success("Participant identity restored to the selected team and audited.")
                        st.rerun()
            team_override = st.toggle(
                "Allow any member of this team to submit",
                key=f"team_override_{event_id}_{team_id}",
            )
            if team_override:
                st.warning("Leader-only submission is temporarily disabled for this team.")
            if st.button("Apply team submission policy", key=f"apply_team_override_{event_id}_{team_id}"):
                control.set_submission_override(event_id, team_id, team_override, actor)
                st.success("Team submission policy updated and audited.")

    with st.expander("Duplicate and migration audit"):
        st.warning("Audit only. Records are never merged or deleted automatically.")
        if st.button("Run identity audit", key=f"run_identity_audit_{event_id}"):
            st.json(runtime.identity_migration_audit(event_id))
        duplicate_report = runtime.audit_participant_duplicates(event_id)
        groups = duplicate_report.get("DuplicateGroups", [])
        if not groups:
            st.success("No normalized-name duplicate candidates found.")
        for position, group in enumerate(groups):
            st.markdown(f"**{group.get('NormalizedName', '')}** · {group.get('Count', 0)} records")
            ids = group.get("ParticipantIDs", [])
            if len(ids) < 2:
                continue
            canonical = st.selectbox(
                "Canonical ParticipantID", ids,
                key=f"duplicate_canonical_{event_id}_{position}",
            )
            duplicate_choices = [value for value in ids if value != canonical]
            duplicate = st.selectbox(
                "Duplicate ParticipantID", duplicate_choices,
                key=f"duplicate_record_{event_id}_{position}",
            )
            reason = st.text_input(
                "Decision reason", key=f"duplicate_reason_{event_id}_{position}",
            )
            confirmed = st.checkbox(
                "I verified these production records and understand merge is permanent",
                key=f"duplicate_confirm_{event_id}_{position}",
            )
            keep, confirm, merge = st.columns(3)
            if keep.button("Keep Separate", key=f"keep_duplicate_{event_id}_{position}"):
                control.decide_duplicate(event_id, canonical, duplicate, "KEEP_SEPARATE", reason, actor)
                st.success("Decision recorded; neither record changed.")
            if confirm.button("Confirm Same Participant", key=f"confirm_duplicate_{event_id}_{position}"):
                control.decide_duplicate(event_id, canonical, duplicate, "CONFIRM_SAME", reason, actor)
                st.success("Identity relationship recorded; records remain unchanged.")
            if merge.button(
                "Merge Records", disabled=not confirmed,
                key=f"merge_duplicate_{event_id}_{position}",
            ):
                control.decide_duplicate(event_id, canonical, duplicate, "MERGE", reason, actor)
                st.success("Records merged into the selected canonical ParticipantID and audited.")
                st.rerun()


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
    canonical = []
    if db.runtime.can_publish:
        try:
            canonical = db.runtime.get_canonical_leaderboard(event_id)
        except Exception:
            canonical = []
    leaderboard = (
        [(row["TeamID"], float(row["Score"])) for row in canonical]
        if canonical else calculate_leaderboard(db.get_submissions(event_id))
    )
    st.subheader("Final Rankings" if final else "Current Ranking")
    if not leaderboard:
        st.info("No approved scores yet.")
        return
    for position, (team, score) in enumerate(leaderboard, start=1):
        st.metric(f"{position}. {team}", f"{format_score(score)} pts")


def _render_stage_widgets(db, control, event_id, family):
    if family == "registration":
        _render_registration(db, control, event_id)
    elif family == "scored":
        render_review_scoring_widget(db, event_id, control=control)
        _render_rankings(db, event_id)
    elif family == "mission":
        _render_mission_board(db, event_id)
        render_road_hunt_operations(db, event_id, control=control)
        render_review_scoring_widget(db, event_id, control=control)
        render_credit_wallet_control(db, event_id, control=control)
    elif family == "review":
        render_review_scoring_widget(db, event_id, show_all=True, control=control)
        render_credit_wallet_control(db, event_id, control=control)
        _render_rankings(db, event_id)
    elif family == "purchasing":
        render_credit_wallet_control(db, event_id, control=control)
    elif family == "performance":
        render_review_scoring_widget(db, event_id, show_all=True, control=control)
        _render_rankings(db, event_id)
    else:
        _render_rankings(db, event_id, final=True)
        st.info("Export the detailed result table from Results & Reports.")


def _render_nasi_operations(db, control, event_id, activity_id):
    """Show the live, individual NASI queue using the existing submission store."""
    submissions = [
        row for row in db.get_submissions(event_id)
        if str(row.get("MissionID", "")) == str(activity_id)
        and str(row.get("SubmissionType", "")).upper() == "NASI"
    ]
    submitted_people = {
        str(row.get("ParticipantName", "")).strip().casefold()
        for row in submissions
        if str(row.get("ParticipantName", "")).strip()
    }
    registered = db.get_participant_count(event_id)
    submitted = len(submitted_people)
    outstanding = max(registered - submitted, 0)

    st.subheader("NASI Live Status")
    participant_metric, submitted_metric, outstanding_metric = st.columns(3)
    participant_metric.metric("Registered participants", registered)
    submitted_metric.metric("NASI submitted", submitted)
    outstanding_metric.metric("NASI outstanding", outstanding)
    st.caption("NASI is an individual reflection. It always carries zero competitive credits.")
    render_review_scoring_widget(
        db,
        event_id,
        mission_id=activity_id,
        control=control,
        force_runtime_rows=True,
    )


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
    control = ControlRuntime(db)
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
    programme = CanonicalProgrammeAdapter(event_id, stages).snapshot()
    programme_modules = programme.modules
    if programme.warnings:
        st.caption(" · ".join(programme.warnings))
    if programme.errors:
        st.error("Programme validation failed. Live launch is disabled.")
        for error in programme.errors:
            st.warning(error)
    flattened = [
        (module, activity)
        for module in programme_modules
        for activity in module.get("Activities", [])
    ]
    if not flattened:
        st.warning("No active activities are available for this event.")
        return
    try:
        _, runtime_activity = programme.resolve_runtime(state or {})
        runtime_activity_id = runtime_activity.get("ActivityID", "")
    except ProgrammeIntegrityError:
        runtime_activity_id = ""
    default_activity_index = next((
        position for position, (_, activity) in enumerate(flattened)
        if activity.get("ActivityID", "") == runtime_activity_id
    ), 0)
    default_module_id = flattened[default_activity_index][0].get("ModuleID", "")
    module_ids = [module.get("ModuleID", "") for module in programme_modules]
    selected_module_id = st.selectbox(
        "Select Module", module_ids,
        index=(
            module_ids.index(default_module_id)
            if default_module_id in module_ids else 0
        ),
        format_func=lambda value: next(
            module.get("ModuleName", "Module") for module in programme_modules
            if module.get("ModuleID", "") == value
        ),
        key=f"control_module_{event_id}",
    )
    current_module = next(
        module for module in programme_modules
        if module.get("ModuleID", "") == selected_module_id
    )
    activity_ids = [
        activity.get("ActivityID", "")
        for activity in current_module.get("Activities", [])
    ]
    selected_activity_id = st.selectbox(
        "Select Activity", activity_ids,
        format_func=lambda value: next(
            activity.get("AdminDisplayName", activity.get("StageName", "Activity"))
            for activity in current_module.get("Activities", [])
            if activity.get("ActivityID", "") == value
        ),
        key=f"control_activity_{event_id}_{selected_module_id}",
    )
    current_activity = next(
        activity for activity in current_module.get("Activities", [])
        if activity.get("ActivityID", "") == selected_activity_id
    )
    stage = dict(current_activity)
    canonical_assignments = []
    if db.runtime.can_publish:
        try:
            canonical_assignments = [
                row for row in SupabaseExperienceRepository(db.runtime).assignments(
                    event_id, current_activity["ActivityID"],
                )
                if row.get("Active") and row.get("RuntimeEligible")
            ]
        except Exception:
            canonical_assignments = []
    if canonical_assignments:
        assignment_ids = [row["ExperienceAssignmentID"] for row in canonical_assignments]
        selected_assignment_id = st.selectbox(
            "Assigned Experience", assignment_ids,
            format_func=lambda value: next(
                row["ExperienceDefinitionID"] for row in canonical_assignments
                if row["ExperienceAssignmentID"] == value
            ),
        )
        stage["ExperienceAssignmentID"] = selected_assignment_id
    index = next(
        position for position, (_, activity) in enumerate(flattened)
        if activity.get("ActivityID", "") == selected_activity_id
    )
    selected_event = db.get_event(event_id)
    runtime_control = db.get_runtime_control_state(event_id)
    broadcast_state = dict(DEFAULT_BROADCAST)
    broadcast_state.update(db.get_broadcast_state(event_id))
    stage_status = str(runtime_control.get("CurrentStageStatus", "READY"))
    content_config = activity_content_config(current_activity, current_module)
    linked_content_name = (
        content_config["LinkedContentName"] or "Event-specific activity content"
    )
    participant_details = activity_details(current_activity)

    st.markdown(
        f"""
        <div class="control-hero">
          <div class="control-kicker">{html.escape(str(event.get("EventName", "")))}</div>
          <div class="control-title">{html.escape(str(current_module.get("ModuleName", "")))}</div>
          <div style="font-size:1.25rem">Current activity: {html.escape(str(current_activity.get("StageName", "")))}</div>
          <div>{html.escape(friendly_type(current_activity))} · Activity {index + 1} of {len(flattened)} · {html.escape(stage_status)}</div>
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
            st.success(f"Publishes: {content_config['LinkedContentName']}")

    previous, launch, end_activity, next_col = st.columns([1, 2, 2, 1])
    if previous.button(
        "Previous Activity",
        width="stretch",
        disabled=index == 0,
    ):
        _set_stage(control, event_id, flattened[index - 1][1])
    if launch.button(
        "Start Selected Activity",
        type="primary",
        width="stretch",
        disabled=bool(programme.errors) or not bool(stage.get("RuntimeEligible", True)),
    ):
        programme.require_valid()
        _start_programme_activity(control, event_id, stage, current_module)
        control.timer(
            event_id,
            stage.get("StageNo", ""),
            "START",
            stage.get("DurationMinutes", 0),
        )
        control.control_state(event_id, "CurrentStageStatus", "RUNNING")
        st.rerun()
    if end_activity.button(
        "End Selected Activity",
        width="stretch",
    ):
        control.timer(
            event_id,
            stage.get("StageNo", ""),
            "END",
            stage.get("DurationMinutes", 0),
        )
        control.control_state(event_id, "CurrentStageStatus", "ENDED")
        st.rerun()
    if next_col.button(
        "Next Activity",
        width="stretch",
        disabled=index >= len(flattened) - 1,
    ):
        _set_stage(control, event_id, flattened[index + 1][1])

    timer_col, broadcast_col = st.columns([1, 2])
    with timer_col:
        _render_timer(db, control, event_id, stage)
    with broadcast_col:
        render_broadcast_controller(db, event_id, control=control)

    st.divider()
    if str(stage.get("StageName", "")).strip().upper() == "NASI":
        _render_nasi_operations(db, control, event_id, stage.get("ActivityID", ""))
    else:
        _render_stage_widgets(db, control, event_id, stage_family(stage))
    st.divider()
    _render_team_management(db, control, event_id)

    st.divider()
    st.subheader("Emergency Recovery")
    st.caption("Runtime restart republishes configuration without resetting participant identity.")
    pause, resume, restart = st.columns(3)
    if pause.button("Pause Event", width="stretch"):
        control.pause_event(event_id)
        st.rerun()
    if resume.button("Resume Event", width="stretch"):
        control.resume_event(event_id)
        st.rerun()
    restart_confirmed = st.checkbox("Confirm non-destructive runtime restart")
    if restart.button("Restart Runtime", width="stretch", disabled=not restart_confirmed):
        control.restart_runtime(event_id)
        st.success("Runtime configuration restored; participant records were not reset.")
        st.rerun()
    with st.expander("Scoring Finalisation and Recovery"):
        lock_actor = st.text_input("Authorised facilitator", key=f"scoring_lock_actor_{event_id}")
        lock_reason = st.text_input("Lock or reopen reason", key=f"scoring_lock_reason_{event_id}")
        activity_lock, module_lock, event_lock, reopen = st.columns(4)
        if activity_lock.button("Lock Activity Scoring", disabled=not lock_actor or not lock_reason):
            control.set_scoring_lock(
                event_id, "ACTIVITY", stage["ActivityID"], True, lock_actor, lock_reason,
            )
            st.success("Activity scoring final-locked and audited.")
        if module_lock.button("Lock Module Scoring", disabled=not lock_actor or not lock_reason):
            control.set_scoring_lock(
                event_id, "MODULE", current_module["ModuleID"], True, lock_actor, lock_reason,
            )
            st.success("Module scoring final-locked and audited.")
        if event_lock.button("Lock Event Scoring", disabled=not lock_actor or not lock_reason):
            control.set_scoring_lock(event_id, "EVENT", event_id, True, lock_actor, lock_reason)
            st.success("Event scoring and leaderboard final-locked.")
        if reopen.button("Reopen Activity Judging", disabled=not lock_actor or not lock_reason):
            control.set_scoring_lock(
                event_id, "ACTIVITY", stage["ActivityID"], False, lock_actor, lock_reason,
            )
            st.warning("Activity judging reopened by an audited recovery action.")
