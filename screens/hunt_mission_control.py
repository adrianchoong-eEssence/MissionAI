"""Event-fixed Mission Control for a configured EXOS Hunt."""
from __future__ import annotations

import uuid
from datetime import timezone

import pandas as pd
import streamlit as st

from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import get_standard_database
from engines.live_location import derive_team_locations, distance_meters


_INTERNAL_FIELDS = {
    "ActivityID", "CheckpointID", "DeviceID", "EventID", "ParticipantID",
    "SessionToken", "SubmissionID", "TeamID", "MissionID", "Configuration",
    "Payload", "SubmissionPayload", "IdempotencyKey",
}


def _age(value) -> str:
    """Present a server timestamp as a concise facilitator-facing age."""
    if value is None or value == "":
        return "No update yet"
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(timezone.utc)
        seconds = max(int((pd.Timestamp.now(tz="UTC") - timestamp).total_seconds()), 0)
    except (TypeError, ValueError):
        return "No update yet"
    if seconds < 60:
        return f"{seconds} sec ago"
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min ago"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} hr {minutes} min ago"


def _gps_status(value) -> str:
    return {
        "CURRENT": "LIVE",
        "STALE": "LAST SEEN / STALE",
        "UNAVAILABLE": "LOCATION UNAVAILABLE",
    }.get(str(value or "").upper(), "LOCATION UNAVAILABLE")


def _checkpoint_status(state: str, checkpoint_name: str = "", distance: float | None = None) -> str:
    label = {
        "ARRIVED": "Arrived",
        "NEAR": "Near checkpoint",
        "OUTSIDE": "Not near checkpoint",
        "UNAVAILABLE": "Location unavailable",
    }.get(str(state or "").upper(), "Not near checkpoint")
    suffix = f" · {checkpoint_name}" if checkpoint_name else ""
    if distance is not None:
        suffix += f" · {distance:.0f} m"
    return f"{label}{suffix}"


def _team_names(snapshot: dict, participants: list[dict]) -> dict[str, str]:
    """Use configured team names and never fall back to exposing a team key."""
    names = {
        str(row.get("TeamID")): str(row.get("TeamName") or "").strip()
        for row in list(snapshot.get("Teams") or []) if row.get("TeamID")
    }
    for number, team_id in enumerate(sorted({str(row.get("TeamID")) for row in participants if row.get("TeamID")}), start=1):
        names[team_id] = names.get(team_id) or f"Team {number}"
    return names


def _facilitator_rows(rows: list[dict], *, team_names: dict[str, str] | None = None) -> list[dict]:
    """Drop implementation identifiers from ordinary operator tables."""
    labels = {
        "DisplayName": "Participant Name", "ParticipantName": "Participant Name",
        "Name": "Name", "TeamName": "Team", "AttendanceState": "Attendance",
        "SubmittedAt": "Submitted", "CreatedAt": "Created", "UpdatedAt": "Updated",
        "CheckpointName": "Checkpoint", "MissionName": "Mission", "Score": "Score",
        "Status": "Status", "State": "Status", "Message": "Message",
    }
    output: list[dict] = []
    for row in rows or []:
        clean: dict = {}
        for key, value in dict(row).items():
            if key in _INTERNAL_FIELDS or key in {"Latitude", "Longitude", "CapturedAt", "ReceivedAt", "AccuracyMeters"}:
                continue
            if key == "Team" and team_names:
                value = team_names.get(str(value), value)
            if key == "Status":
                value = _gps_status(value) if str(value).upper() in {"CURRENT", "STALE", "UNAVAILABLE"} else str(value).replace("_", " ").title()
            clean[labels.get(key, key.replace("_", " ").title())] = value
        output.append(clean)
    return output


def _render_facilitator_table(rows: list[dict], *, team_names: dict[str, str] | None = None) -> None:
    clean_rows = _facilitator_rows(rows, team_names=team_names)
    if clean_rows:
        st.dataframe(clean_rows, hide_index=True, width="stretch")
    else:
        st.info("Nothing to show yet.")


def _snapshot(runtime, event_id: str) -> dict | None:
    try:
        return runtime.get_hunt_operator_snapshot(event_id)
    except RuntimeDatabaseError:
        st.warning("Mission Control is reconnecting. Refresh in a moment.")
        return None


def _operator() -> str:
    return str(st.session_state.get("hunt_control_actor", "") or "").strip()


def _overview(runtime, event_id: str, snapshot: dict) -> None:
    configuration = dict(snapshot.get("Configuration") or {})
    st.subheader("OVERVIEW")
    current_state = str(configuration.get("OperationalState") or "READY").upper()
    state_labels = {
        "READY": "Ready to start", "LIVE": "Live", "HOLD": "On hold",
        "RETURN_NOW": "Return now", "CLOSED": "Closed",
    }
    st.caption(f"Hunt status: {state_labels.get(current_state, 'Ready to start')}")
    try:
        attendance = runtime.get_attendance_summary(event_id)
    except RuntimeDatabaseError:
        attendance = {}
    if attendance:
        present = int(attendance.get("Present", 0) or 0)
        expected = int(attendance.get("Registered", attendance.get("Expected", 0)) or 0)
        st.metric("Attendance", f"{present} / {expected}" if expected else str(present))
    actor = _operator()
    choices = list(state_labels)
    selected_label = st.selectbox(
        "Hunt status", [state_labels[value] for value in choices],
        index=choices.index(current_state) if current_state in choices else 0,
        key="hunt_operational_state",
    )
    proposed = next(value for value, label in state_labels.items() if label == selected_label)
    close_confirmed = proposed != "CLOSED" or st.checkbox("I understand CLOSED is terminal for this Hunt event", key="hunt_close_confirm")
    if st.button("APPLY HUNT STATUS", type="primary", disabled=not actor or not close_confirmed, key="hunt_apply_status"):
        try:
            runtime.set_hunt_operational_state(event_id, proposed, actor)
        except RuntimeDatabaseError:
            st.warning("Hunt status could not be saved. Check your operator access and try again.")
        else:
            st.success("Hunt operational status updated and audited.")
            st.rerun()
    public = st.checkbox("Enable public projector", key="hunt_public_projector")
    if st.button("SAVE PROJECTOR VISIBILITY", disabled=not actor, key="hunt_projector_visibility"):
        try:
            runtime.set_hunt_projector_visibility(event_id, public, actor)
        except RuntimeDatabaseError:
            st.warning("Projector visibility could not be saved. Try again in a moment.")
        else:
            st.success("Public projector visibility updated. It never includes GPS or evidence.")


def _attendance(runtime, event_id: str) -> None:
    st.subheader("ATTENDANCE")
    try:
        roster = runtime.get_attendance_roster(event_id)
    except RuntimeDatabaseError:
        st.warning("Attendance is temporarily unavailable. Refresh in a moment.")
        return
    rows = list(roster.get("Participants") or [])
    _render_facilitator_table(rows)
    if not rows:
        return
    labels = {str(row.get("DisplayName") or "Participant"): row for row in rows}
    selected = labels[st.selectbox("Participant", list(labels), key="hunt_attendance_person")]
    attendance_labels = {"Present": "PRESENT", "Absent": "ABSENT", "Pre-assigned": "PREASSIGNED"}
    state = attendance_labels[st.selectbox("Attendance", list(attendance_labels), key="hunt_attendance_state")]
    actor = _operator()
    reason = st.text_input("Attendance reason", key="hunt_attendance_reason")
    if st.button("SAVE ATTENDANCE", disabled=not actor, key="hunt_attendance_save"):
        try:
            runtime.set_participant_attendance(event_id, selected["ParticipantID"], state, actor, reason)
        except RuntimeDatabaseError:
            st.warning("Attendance could not be saved. Try again in a moment.")
        else:
            st.success("Attendance updated canonically.")
            st.rerun()


def _captains(runtime, event_id: str) -> None:
    st.subheader("CAPTAINS")
    try:
        hybrid_roster = runtime.get_hybrid_anchored_operator_roster(event_id)
        rows = [{
            "ParticipantID": row.get("ParticipantID"), "EventID": event_id,
            "TeamID": row.get("TeamID"), "Name": row.get("DisplayName"),
            "AssignmentRole": row.get("AssignmentRole"), "AttendanceState": row.get("AttendanceState"),
            "IsCaptain": "Yes" if row.get("IsCaptain") else "No",
        } for row in list(hybrid_roster.get("Participants") or [])]
    except RuntimeDatabaseError:
        rows = runtime.get_players(event_id)
    team_names = {str(row.get("TeamID")): str(row.get("TeamName") or "") for row in runtime.get_teams(event_id)}
    _render_facilitator_table(rows, team_names=team_names)
    teams = runtime.get_teams(event_id)
    if not teams:
        return
    team_labels = {str(row.get("TeamName") or f"Team {index}"): row for index, row in enumerate(teams, start=1)}
    team = team_labels[st.selectbox("Team", list(team_labels), key="hunt_captain_team")]
    members = [row for row in rows if str(row.get("TeamID")) == str(team.get("TeamID"))]
    actor = _operator()
    reason = st.text_input("Transfer / clear reason", key="hunt_captain_reason")
    if members:
        names = {
            f"{row.get('Name') or 'Participant'} · {position}": row
            for position, row in enumerate(members, start=1)
        }
        target = names[st.selectbox("Transfer Captain to", list(names), key="hunt_captain_target")]
        if st.button("TRANSFER CAPTAIN", disabled=not actor or not reason, key="hunt_captain_transfer"):
            try:
                runtime.transfer_team_formation_captain(event_id, team["TeamID"], target["ParticipantID"], actor, reason)
            except RuntimeDatabaseError:
                st.warning("Captain transfer could not be saved. Try again in a moment.")
            else:
                st.success("Captain transferred and audited.")
                st.rerun()
    if st.button("CLEAR CAPTAIN", disabled=not actor or not reason, key="hunt_captain_clear"):
        try:
            runtime.clear_team_formation_captain(event_id, team["TeamID"], actor, reason)
        except RuntimeDatabaseError:
            st.warning("Captain change could not be saved. Try again in a moment.")
        else:
            st.success("Captain cleared and audited.")
            st.rerun()


def _hod_anchors(runtime, event_id: str) -> None:
    """Show HOD status without exposing their Personal Keys or credential hashes."""
    st.subheader("HOD ANCHORS")
    try:
        roster = runtime.get_hybrid_anchored_operator_roster(event_id)
    except RuntimeDatabaseError:
        st.info("HOD anchor status is unavailable until the hybrid formation architecture is configured.")
        return
    anchors = [dict(row) for row in list(roster.get("Participants") or [])
               if str(row.get("AssignmentRole") or "").upper() == "HOD_ANCHOR"]
    if not anchors:
        st.info("No HOD anchors are provisioned yet.")
        return
    teams = {str(row.get("TeamID")): str(row.get("TeamName") or "Team") for row in runtime.get_teams(event_id)}
    _render_facilitator_table([
        {
            "HOD": row.get("DisplayName") or "HOD",
            "Team": teams.get(str(row.get("TeamID")), "Team"),
            "Attendance": row.get("AttendanceState") or "PRE-ASSIGNED",
            "Captain": "Yes" if row.get("IsCaptain") else "No",
        }
        for row in anchors
    ])
    st.caption("Each anchor is pre-assigned to one country team. HOD access is distinct from the Captain role.")


def _stages(runtime, event_id: str) -> None:
    """Operate the three scored stages through the immutable shared ledger."""
    st.subheader("STAGES")
    try:
        snapshot = runtime.get_competition_stage_snapshot(event_id)
    except RuntimeDatabaseError:
        st.info("Competition stages are unavailable until the prepared architecture migration is installed and configured.")
        return
    stages = [dict(row) for row in list(snapshot.get("Stages") or [])]
    teams = [dict(row) for row in list(snapshot.get("Teams") or [])]
    _render_facilitator_table(stages)
    if not stages:
        st.info("No competition stages are configured yet.")
        return
    actor = _operator()
    stage_labels = {f"{row.get('StageNo', '—')} · {row.get('StageName') or row.get('StageID')}": row for row in stages}
    selected = stage_labels[st.selectbox("Stage", list(stage_labels), key="hunt_competition_stage")]
    states = ["LOCKED", "AVAILABLE", "ACTIVE", "COMPLETED"]
    state = st.selectbox("Stage state", states,
                         index=states.index(str(selected.get("State") or "LOCKED").upper())
                         if str(selected.get("State") or "LOCKED").upper() in states else 0,
                         key="hunt_competition_stage_state")
    if st.button("SAVE STAGE STATE", disabled=not actor, key="hunt_competition_stage_save"):
        try:
            runtime.set_competition_stage_state(event_id, selected["StageID"], state, actor)
        except RuntimeDatabaseError as error:
            st.warning(str(error) or "Stage state could not be saved.")
        else:
            st.success("Competition stage state updated and audited.")
            st.rerun()
    if not bool(selected.get("Scored", True)) or not teams:
        return
    st.divider()
    st.caption("Score entries are immutable cumulative ledger transactions. Stage rules and point values remain owner-controlled.")
    team_labels = {str(row.get("TeamName") or row.get("TeamID")): row for row in teams}
    team = team_labels[st.selectbox("Team", list(team_labels), key="hunt_competition_score_team")]
    delta = st.number_input("Stage points (+/−)", min_value=-1000.0, max_value=1000.0, value=0.0,
                            step=1.0, key="hunt_competition_score_delta")
    reason = st.text_input("Score rationale", key="hunt_competition_score_reason")
    key_state = "hunt_competition_score_key"
    if key_state not in st.session_state:
        st.session_state[key_state] = uuid.uuid4().hex
    if st.button("RECORD STAGE SCORE", type="primary", disabled=not actor or not reason or not delta,
                 key="hunt_competition_score_save"):
        try:
            runtime.record_competition_stage_score(event_id, selected["StageID"], team["TeamID"], delta, reason,
                                                   actor, st.session_state[key_state])
        except RuntimeDatabaseError as error:
            st.warning(str(error) or "Stage score could not be saved.")
        else:
            st.session_state[key_state] = uuid.uuid4().hex
            st.success("Cumulative stage score recorded and audited.")
            st.rerun()


def _live_map(runtime, event_id: str, snapshot: dict) -> None:
    st.subheader("LIVE MAP")
    actor = _operator()
    visibility = st.selectbox("Participant map visibility", ["OFF", "TEAM_LEADERS"], key="hunt_location_visibility")
    st.caption("Facilitators retain individual map access. Participant sharing is OFF by default; TEAM LEADERS shares only other teams' effective Captain locations.")
    if st.button("SAVE PARTICIPANT MAP VISIBILITY", disabled=not actor, key="hunt_location_visibility_save"):
        try:
            runtime.set_participant_location_visibility(event_id, visibility, actor)
        except RuntimeDatabaseError as error:
            st.warning(str(error) or "Participant map visibility could not be saved.")
        else:
            st.success("Participant map visibility updated and audited.")
            st.rerun()
    try:
        location = runtime.get_live_location_operator_map(event_id)
    except RuntimeDatabaseError:
        st.warning("Live location is temporarily unavailable. Refresh in a moment.")
        return
    participants = [dict(row) for row in list(location.get("Participants") or [])]
    team_names = _team_names(snapshot, participants)
    checkpoints = [row for row in list(snapshot.get("Checkpoints") or []) if row.get("Active")]
    for person in participants:
        if person.get("Latitude") is None or person.get("Longitude") is None:
            person["CheckpointProximity"] = _checkpoint_status("UNAVAILABLE")
            continue
        distances = []
        for checkpoint in checkpoints:
            try:
                distance = distance_meters((float(person["Latitude"]), float(person["Longitude"])),
                                           (float(checkpoint["Latitude"]), float(checkpoint["Longitude"])))
                distances.append((distance, checkpoint))
            except (TypeError, ValueError):
                continue
        if not distances:
            person["CheckpointProximity"] = _checkpoint_status("OUTSIDE")
            continue
        distance, nearest = min(distances, key=lambda row: row[0])
        radius = float(nearest.get("RadiusMeters") or 0)
        state = "ARRIVED" if distance <= radius else ("NEAR" if distance <= radius * 2 else "OUTSIDE")
        person["CheckpointProximity"] = _checkpoint_status(state, str(nearest.get("Name") or ""), distance)
    teams = derive_team_locations(participants, separation_threshold_meters=float(location.get("SeparationThresholdMeters") or 250))
    stale_after = int(location.get("StaleAfterSeconds", 90) or 90)
    st.caption(f"GPS is LIVE when updated within {stale_after} seconds. Teams are never given a misleading midpoint when separated.")

    def participant_card(person: dict) -> dict:
        return {
            "Participant Name": str(person.get("ParticipantName") or "Participant"),
            "Team": team_names.get(str(person.get("TeamID")), "Team"),
            "GPS Status": _gps_status(person.get("Status")),
            "Last Update": _age(person.get("LastUpdate")),
            "Accuracy": f"±{float(person['AccuracyMeters']):.0f} m" if person.get("AccuracyMeters") is not None else "—",
            "Checkpoint Proximity": person.get("CheckpointProximity", "Location unavailable"),
        }

    def team_card(summary: dict) -> dict:
        members = int(summary.get("Members") or 0)
        reporting = int(summary.get("Reporting") or 0)
        if not reporting:
            status = "NO LIVE LOCATION"
        elif reporting < members:
            status = "PARTIAL REPORTING"
        elif str(summary.get("Status")) == "SEPARATED":
            status = "SEPARATED"
        else:
            status = "TOGETHER"
        members_rows = [row for row in participants if str(row.get("TeamID")) == str(summary.get("TeamID"))]
        latest = max((row.get("LastUpdate") for row in members_rows if row.get("LastUpdate")), default=None)
        return {
            "Team": team_names.get(str(summary.get("TeamID")), "Team"),
            "Reporting": f"{reporting} / {members} reporting",
            "Last Update": _age(latest),
            "Status": status,
        }

    tabs = st.tabs(["ALL TEAMS", "TEAM", "INDIVIDUAL"])
    with tabs[0]:
        st.dataframe([team_card(team) for team in teams], hide_index=True, width="stretch")
        st.markdown("#### Participants")
        st.dataframe([participant_card(person) for person in participants], hide_index=True, width="stretch")
        points = [row for row in participants if str(row.get("Status")) == "CURRENT" and row.get("Latitude") is not None and row.get("Longitude") is not None]
        if points:
            map_rows = pd.DataFrame([{"lat": row["Latitude"], "lon": row["Longitude"]} for row in points])
            st.map(map_rows, latitude="lat", longitude="lon", size=40)
        else:
            st.info("No live locations are available yet.")
    with tabs[1]:
        choices = {team_names[team_id]: team_id for team_id in sorted(team_names)}
        selected_name = st.selectbox("Team", list(choices), key="hunt_map_team") if choices else ""
        team_id = choices.get(selected_name, "")
        matching = [row for row in participants if str(row.get("TeamID")) == team_id]
        summary = next((team for team in teams if str(team.get("TeamID")) == team_id), None)
        if summary:
            st.dataframe([team_card(summary)], hide_index=True, width="stretch")
        st.dataframe([participant_card(person) for person in matching], hide_index=True, width="stretch")
    with tabs[2]:
        labels = {f"{row.get('ParticipantName')} · {team_names.get(str(row.get('TeamID')), 'Team')}": row for row in participants}
        label = st.selectbox("Individual", list(labels), key="hunt_map_person") if labels else ""
        row = labels.get(label, {})
        if row:
            st.dataframe([participant_card(row)], hide_index=True, width="stretch")
            try:
                history = runtime.get_live_location_history(event_id, row.get("ParticipantID"), 20)
            except RuntimeDatabaseError:
                st.warning("Movement trail is temporarily unavailable. Refresh in a moment.")
                history = []
            if isinstance(history, dict):
                history = history.get("History") or history.get("Locations") or [history]
            trail = [dict(point) for point in list(history or []) if isinstance(point, dict)]
            if trail:
                trail_points = [
                    {"lat": point.get("Latitude", point.get("latitude")), "lon": point.get("Longitude", point.get("longitude"))}
                    for point in trail
                    if point.get("Latitude", point.get("latitude")) is not None
                    and point.get("Longitude", point.get("longitude")) is not None
                ]
                if trail_points:
                    st.map(pd.DataFrame(trail_points), latitude="lat", longitude="lon", size=30)
                st.dataframe([
                    {"Recorded": _age(point.get("ReceivedAt") or point.get("CapturedAt")),
                     "Accuracy": f"±{float(point['AccuracyMeters']):.0f} m" if point.get("AccuracyMeters") is not None else "—"}
                    for point in trail
                ], hide_index=True, width="stretch")
            else:
                st.info("No movement trail is available yet.")


def _checkpoints(snapshot: dict) -> None:
    st.subheader("CHECKPOINTS")
    st.caption("Proximity states are operational facts. GPS cannot award Hunt score.")
    rows = []
    for checkpoint in list(snapshot.get("Checkpoints") or []):
        rows.append({
            "Checkpoint": checkpoint.get("Name") or "Checkpoint",
            "Availability": "Active" if checkpoint.get("Active") else "Not active",
            "Arrival area": f"{float(checkpoint['RadiusMeters']):.0f} m" if checkpoint.get("RadiusMeters") is not None else "—",
        })
    _render_facilitator_table(rows)


def _missions(snapshot: dict) -> None:
    st.subheader("MISSIONS")
    _render_facilitator_table(list(snapshot.get("Missions") or []))


def _pending_review(runtime, event_id: str, snapshot: dict) -> None:
    st.subheader("PENDING REVIEW")
    rows = list(snapshot.get("PendingReviews") or [])
    _render_facilitator_table(rows)
    if not rows:
        return
    team_names = _team_names(snapshot, [])
    labels = {
        f"{row.get('MissionName') or 'Mission'} · {team_names.get(str(row.get('TeamID')), 'Team')} · {_age(row.get('SubmittedAt'))}": row
        for row in rows
    }
    selected = labels[st.selectbox("Submission", list(labels), key="hunt_review_submission")]
    decision = st.selectbox("Review decision", ["APPROVE", "RETURN"], key="hunt_review_decision")
    rubric = st.text_area("Rubric scores as JSON (required only for rubric missions)", value="{}", key="hunt_review_rubric")
    actor = _operator()
    reason = st.text_area("Review rationale", key="hunt_review_reason")
    if st.button("SAVE REVIEW", type="primary", disabled=not actor, key="hunt_review_save"):
        try:
            parsed = __import__("json").loads(rubric)
            runtime.review_hunt_submission(selected["SubmissionID"], selected["SubmittedAt"], decision, rubric_scores=parsed,
                                            actor=actor, reason=reason, idempotency_key=f"hunt-review-ui|{selected['SubmissionID']}|{selected['SubmittedAt']}|{decision}")
        except (RuntimeDatabaseError, ValueError):
            st.warning("Review could not be saved. Check the selected decision and try again.")
        else:
            st.success("Review saved through the canonical score ledger.")
            st.rerun()


def _announcements(runtime, event_id: str) -> None:
    st.subheader("ANNOUNCEMENTS")
    target = st.radio("Target", ["ALL", "TEAM", "PARTICIPANT"], horizontal=True, key="hunt_announcement_target")
    target_ids: list[str] = []
    if target == "TEAM":
        teams = runtime.get_teams(event_id)
        labels = {str(row.get("TeamName") or f"Team {index}"): str(row.get("TeamID")) for index, row in enumerate(teams, start=1)}
        target_ids = [labels[label] for label in st.multiselect("Teams", list(labels), key="hunt_announcement_teams")]
    elif target == "PARTICIPANT":
        people = runtime.get_players(event_id)
        labels = {str(row.get("Name") or "Participant"): str(row.get("ParticipantID")) for row in people}
        target_ids = [labels[label] for label in st.multiselect("Participants", list(labels), key="hunt_announcement_people")]
    severity = st.selectbox("Severity", ["INFO", "IMPORTANT", "URGENT"], key="hunt_announcement_severity")
    title = st.text_input("Title", key="hunt_announcement_title")
    message = st.text_area("Message", key="hunt_announcement_message")
    acknowledgement = st.checkbox("Require acknowledgement", key="hunt_announcement_ack")
    confirm = target != "ALL" or severity != "URGENT" or st.checkbox("Confirm ALL + URGENT", key="hunt_announcement_confirm")
    actor = _operator()
    key = f"hunt-announcement-{uuid.uuid4().hex}" if "hunt_announcement_key" not in st.session_state else st.session_state["hunt_announcement_key"]
    st.session_state["hunt_announcement_key"] = key
    if st.button("SEND ANNOUNCEMENT", type="primary", disabled=not actor or not confirm, key="hunt_announcement_send"):
        try:
            runtime.send_event_announcement(event_id, target_type=target, target_ids=target_ids, severity=severity,
                                            title=title, message=message, expires_at=None, acknowledgement_required=acknowledgement,
                                            actor=actor, idempotency_key=key, confirm_all_urgent=confirm)
        except RuntimeDatabaseError:
            st.warning("Announcement could not be sent. Try again in a moment.")
        else:
            st.session_state["hunt_announcement_key"] = f"hunt-announcement-{uuid.uuid4().hex}"
            st.success("Announcement sent and audited.")
            st.rerun()
    try:
        _render_facilitator_table(runtime.get_event_announcements(event_id))
    except RuntimeDatabaseError:
        st.info("Announcements are temporarily unavailable.")


def _leaderboard(runtime, event_id: str, snapshot: dict) -> None:
    st.subheader("LEADERBOARD")
    try:
        competition = runtime.get_competition_stage_snapshot(event_id)
    except RuntimeDatabaseError:
        competition = {}
    if competition.get("Teams"):
        st.caption("Cumulative score across every configured scored stage.")
        _render_facilitator_table(list(competition.get("Teams") or []))
        return
    _render_facilitator_table(list(snapshot.get("Teams") or []))


def _adjustment(runtime, event_id: str, snapshot: dict) -> None:
    st.subheader("BONUS / ADJUSTMENT")
    teams = {str(row.get("TeamName") or f"Team {index}"): row for index, row in enumerate(list(snapshot.get("Teams") or []), start=1)}
    if not teams:
        return
    team = teams[st.selectbox("Team", list(teams), key="hunt_adjust_team")]
    delta = st.number_input("Points (+/−)", min_value=-1000.0, max_value=1000.0, value=0.0, step=1.0, key="hunt_adjust_delta")
    reason = st.text_input("Reason", key="hunt_adjust_reason")
    actor = _operator()
    key_state = "hunt_adjustment_key"
    if key_state not in st.session_state:
        st.session_state[key_state] = uuid.uuid4().hex
    if st.button("APPLY ADJUSTMENT", type="primary", disabled=not actor or not reason or not delta, key="hunt_adjust_apply"):
        try:
            runtime.adjust_hunt_score(event_id, team["TeamID"], delta, reason, actor, st.session_state[key_state])
        except RuntimeDatabaseError:
            st.warning("Score adjustment could not be saved. Try again in a moment.")
        else:
            st.session_state[key_state] = uuid.uuid4().hex
            st.success("Score adjustment ledger entry saved and audited.")
            st.rerun()


def render_hunt_mission_control(event_id: str, event_title: str = "GEORGE TOWN · WALK HUNT MISSION CONTROL") -> None:
    st.set_page_config(page_title="George Town Hunt — Mission Control", layout="wide")
    st.title(event_title)
    st.caption("This Mission Control is dedicated to the configured George Town event.")
    st.sidebar.text_input("Authorised operator", key="hunt_control_actor")
    runtime = get_standard_database()
    snapshot = _snapshot(runtime, event_id)
    if snapshot is None:
        return
    tabs = st.tabs(["OVERVIEW", "ATTENDANCE", "HOD ANCHORS", "CAPTAINS", "STAGES", "LIVE MAP", "CHECKPOINTS", "MISSIONS", "PENDING REVIEW", "ANNOUNCEMENTS", "LEADERBOARD", "BONUS / ADJUSTMENT"])
    with tabs[0]: _overview(runtime, event_id, snapshot)
    with tabs[1]: _attendance(runtime, event_id)
    with tabs[2]: _hod_anchors(runtime, event_id)
    with tabs[3]: _captains(runtime, event_id)
    with tabs[4]: _stages(runtime, event_id)
    with tabs[5]: _live_map(runtime, event_id, snapshot)
    with tabs[6]: _checkpoints(snapshot)
    with tabs[7]: _missions(snapshot)
    with tabs[8]: _pending_review(runtime, event_id, snapshot)
    with tabs[9]: _announcements(runtime, event_id)
    with tabs[10]: _leaderboard(runtime, event_id, snapshot)
    with tabs[11]: _adjustment(runtime, event_id, snapshot)
