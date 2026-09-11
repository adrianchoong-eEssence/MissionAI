"""Event-fixed Mission Control for a configured EXOS Hunt."""
from __future__ import annotations

import uuid

import pandas as pd
import streamlit as st

from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import get_standard_database
from engines.live_location import derive_team_locations, distance_meters


def _snapshot(runtime, event_id: str) -> dict | None:
    try:
        return runtime.get_hunt_operator_snapshot(event_id)
    except RuntimeDatabaseError as error:
        st.error("Mission Control is reconnecting.")
        st.caption(str(error))
        return None


def _operator() -> str:
    return str(st.session_state.get("hunt_control_actor", "") or "").strip()


def _overview(runtime, event_id: str, snapshot: dict) -> None:
    configuration = dict(snapshot.get("Configuration") or {})
    st.subheader("OVERVIEW")
    st.json(configuration)
    actor = _operator()
    proposed = st.selectbox("Hunt status", ["READY", "LIVE", "HOLD", "RETURN_NOW", "CLOSED"],
                            index=["READY", "LIVE", "HOLD", "RETURN_NOW", "CLOSED"].index(str(configuration.get("OperationalState") or "READY")),
                            key="hunt_operational_state")
    close_confirmed = proposed != "CLOSED" or st.checkbox("I understand CLOSED is terminal for this Hunt event", key="hunt_close_confirm")
    if st.button("APPLY HUNT STATUS", type="primary", disabled=not actor or not close_confirmed, key="hunt_apply_status"):
        try:
            runtime.set_hunt_operational_state(event_id, proposed, actor)
        except RuntimeDatabaseError as error:
            st.error(str(error))
        else:
            st.success("Hunt operational status updated and audited.")
            st.rerun()
    public = st.checkbox("Enable public projector", key="hunt_public_projector")
    if st.button("SAVE PROJECTOR VISIBILITY", disabled=not actor, key="hunt_projector_visibility"):
        try:
            runtime.set_hunt_projector_visibility(event_id, public, actor)
        except RuntimeDatabaseError as error:
            st.error(str(error))
        else:
            st.success("Public projector visibility updated. It never includes GPS or evidence.")


def _attendance(runtime, event_id: str) -> None:
    st.subheader("ATTENDANCE")
    try:
        roster = runtime.get_attendance_roster(event_id)
    except RuntimeDatabaseError as error:
        st.error(str(error))
        return
    rows = list(roster.get("Participants") or [])
    st.dataframe(rows, hide_index=True, width="stretch")
    if not rows:
        return
    labels = {f"{row.get('DisplayName')} · {row.get('TeamID')}": row for row in rows}
    selected = labels[st.selectbox("Participant", list(labels), key="hunt_attendance_person")]
    state = st.selectbox("Attendance", ["PRESENT", "ABSENT", "PREASSIGNED"], key="hunt_attendance_state")
    actor = _operator()
    reason = st.text_input("Attendance reason", key="hunt_attendance_reason")
    if st.button("SAVE ATTENDANCE", disabled=not actor, key="hunt_attendance_save"):
        try:
            runtime.set_participant_attendance(event_id, selected["ParticipantID"], state, actor, reason)
        except RuntimeDatabaseError as error:
            st.error(str(error))
        else:
            st.success("Attendance updated canonically.")
            st.rerun()


def _captains(runtime, event_id: str) -> None:
    st.subheader("CAPTAINS")
    rows = runtime.get_players(event_id)
    st.dataframe(rows, hide_index=True, width="stretch")
    teams = runtime.get_teams(event_id)
    if not teams:
        return
    team_labels = {str(row.get("TeamName") or row.get("TeamID")): row for row in teams}
    team = team_labels[st.selectbox("Team", list(team_labels), key="hunt_captain_team")]
    members = [row for row in rows if str(row.get("TeamID")) == str(team.get("TeamID"))]
    actor = _operator()
    reason = st.text_input("Transfer / clear reason", key="hunt_captain_reason")
    if members:
        names = {str(row.get("Name") or row.get("ParticipantID")): row for row in members}
        target = names[st.selectbox("Transfer Captain to", list(names), key="hunt_captain_target")]
        if st.button("TRANSFER CAPTAIN", disabled=not actor or not reason, key="hunt_captain_transfer"):
            try:
                runtime.transfer_team_formation_captain(event_id, team["TeamID"], target["ParticipantID"], actor, reason)
            except RuntimeDatabaseError as error:
                st.error(str(error))
            else:
                st.success("Captain transferred and audited.")
                st.rerun()
    if st.button("CLEAR CAPTAIN", disabled=not actor or not reason, key="hunt_captain_clear"):
        try:
            runtime.clear_team_formation_captain(event_id, team["TeamID"], actor, reason)
        except RuntimeDatabaseError as error:
            st.error(str(error))
        else:
            st.success("Captain cleared and audited.")
            st.rerun()


def _live_map(runtime, event_id: str, snapshot: dict) -> None:
    st.subheader("LIVE MAP")
    try:
        location = runtime.get_live_location_operator_map(event_id)
    except RuntimeDatabaseError as error:
        st.error(str(error))
        return
    participants = list(location.get("Participants") or [])
    checkpoints = [row for row in list(snapshot.get("Checkpoints") or []) if row.get("Active")]
    for person in participants:
        if person.get("Latitude") is None or person.get("Longitude") is None:
            person["CheckpointProximity"] = "UNAVAILABLE"
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
            person["CheckpointProximity"] = "OUTSIDE"
            continue
        distance, nearest = min(distances, key=lambda row: row[0])
        radius = float(nearest.get("RadiusMeters") or 0)
        state = "ARRIVED" if distance <= radius else ("NEAR" if distance <= radius * 2 else "OUTSIDE")
        person["CheckpointProximity"] = f"{state} · {nearest.get('Name')} · {distance:.0f}m"
    teams = derive_team_locations(participants, separation_threshold_meters=float(location.get("SeparationThresholdMeters") or 250))
    st.caption(f"Individual mode · CURRENT within {location.get('StaleAfterSeconds', 90)} seconds. Separated teams have no centroid.")
    tabs = st.tabs(["ALL TEAMS", "TEAM", "INDIVIDUAL"])
    with tabs[0]:
        st.dataframe(teams, hide_index=True, width="stretch")
        points = [row for row in participants if str(row.get("Status")) == "CURRENT" and row.get("Latitude") is not None and row.get("Longitude") is not None]
        if points:
            st.map(pd.DataFrame(points), latitude="Latitude", longitude="Longitude", size=40)
    with tabs[1]:
        team_ids = sorted({str(row.get("TeamID")) for row in participants if row.get("TeamID")})
        team_id = st.selectbox("Team", team_ids, key="hunt_map_team") if team_ids else ""
        st.dataframe([row for row in participants if str(row.get("TeamID")) == team_id], hide_index=True, width="stretch")
    with tabs[2]:
        labels = {f"{row.get('ParticipantName')} · {row.get('TeamID')}": row for row in participants}
        label = st.selectbox("Individual", list(labels), key="hunt_map_person") if labels else ""
        row = labels.get(label, {})
        if row:
            try:
                st.dataframe(runtime.get_live_location_history(event_id, row.get("ParticipantID"), 20), hide_index=True, width="stretch")
            except RuntimeDatabaseError as error:
                st.error(str(error))


def _checkpoints(snapshot: dict) -> None:
    st.subheader("CHECKPOINTS")
    st.caption("Proximity states are operational facts. GPS cannot award Hunt score.")
    st.dataframe(list(snapshot.get("Checkpoints") or []), hide_index=True, width="stretch")


def _missions(snapshot: dict) -> None:
    st.subheader("MISSIONS")
    st.dataframe(list(snapshot.get("Missions") or []), hide_index=True, width="stretch")


def _pending_review(runtime, event_id: str, snapshot: dict) -> None:
    st.subheader("PENDING REVIEW")
    rows = list(snapshot.get("PendingReviews") or [])
    st.dataframe(rows, hide_index=True, width="stretch")
    if not rows:
        return
    labels = {f"{row.get('MissionName')} · {row.get('TeamID')} · {row.get('SubmittedAt')}": row for row in rows}
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
        except (RuntimeDatabaseError, ValueError) as error:
            st.error(str(error))
        else:
            st.success("Review saved through the canonical score ledger.")
            st.rerun()


def _announcements(runtime, event_id: str) -> None:
    st.subheader("ANNOUNCEMENTS")
    target = st.radio("Target", ["ALL", "TEAM", "PARTICIPANT"], horizontal=True, key="hunt_announcement_target")
    target_ids: list[str] = []
    if target == "TEAM":
        teams = runtime.get_teams(event_id)
        labels = {str(row.get("TeamName") or row.get("TeamID")): str(row.get("TeamID")) for row in teams}
        target_ids = [labels[label] for label in st.multiselect("Teams", list(labels), key="hunt_announcement_teams")]
    elif target == "PARTICIPANT":
        people = runtime.get_players(event_id)
        labels = {f"{row.get('Name')} · {row.get('TeamID')}": str(row.get("ParticipantID")) for row in people}
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
        except RuntimeDatabaseError as error:
            st.error(str(error))
        else:
            st.session_state["hunt_announcement_key"] = f"hunt-announcement-{uuid.uuid4().hex}"
            st.success("Announcement sent and audited.")
            st.rerun()
    try:
        st.dataframe(runtime.get_event_announcements(event_id), hide_index=True, width="stretch")
    except RuntimeDatabaseError:
        pass


def _leaderboard(snapshot: dict) -> None:
    st.subheader("LEADERBOARD")
    st.dataframe(list(snapshot.get("Teams") or []), hide_index=True, width="stretch")


def _adjustment(runtime, event_id: str, snapshot: dict) -> None:
    st.subheader("BONUS / ADJUSTMENT")
    teams = {str(row.get("TeamName") or row.get("TeamID")): row for row in list(snapshot.get("Teams") or [])}
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
        except RuntimeDatabaseError as error:
            st.error(str(error))
        else:
            st.session_state[key_state] = uuid.uuid4().hex
            st.success("Score adjustment ledger entry saved and audited.")
            st.rerun()


def render_hunt_mission_control(event_id: str) -> None:
    st.set_page_config(page_title="George Town Hunt — Mission Control", layout="wide")
    st.title("GEORGE TOWN · WALK HUNT MISSION CONTROL")
    st.caption(f"Canonical EventID: {event_id}. This fixed control surface cannot operate another simultaneous event.")
    st.sidebar.text_input("Authorised operator", key="hunt_control_actor")
    runtime = get_standard_database()
    snapshot = _snapshot(runtime, event_id)
    if snapshot is None:
        return
    tabs = st.tabs(["OVERVIEW", "ATTENDANCE", "CAPTAINS", "LIVE MAP", "CHECKPOINTS", "MISSIONS", "PENDING REVIEW", "ANNOUNCEMENTS", "LEADERBOARD", "BONUS / ADJUSTMENT"])
    with tabs[0]: _overview(runtime, event_id, snapshot)
    with tabs[1]: _attendance(runtime, event_id)
    with tabs[2]: _captains(runtime, event_id)
    with tabs[3]: _live_map(runtime, event_id, snapshot)
    with tabs[4]: _checkpoints(snapshot)
    with tabs[5]: _missions(snapshot)
    with tabs[6]: _pending_review(runtime, event_id, snapshot)
    with tabs[7]: _announcements(runtime, event_id)
    with tabs[8]: _leaderboard(snapshot)
    with tabs[9]: _adjustment(runtime, event_id, snapshot)
