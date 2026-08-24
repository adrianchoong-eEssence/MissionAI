"""Shared participant, facilitator and projector surfaces for Theme Park Race.

All state is rebuilt from the Core-v2 adapter on render.  This module does not
own a participant, team, event, submission, Captain or scoring store.
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from data.google_drive import get_photo_url, upload_photo
from data.runtime_database import RuntimeDatabaseError
from engines.theme_park_race import projector_projection
from data.upload_safety import upload_error_message


_LIFECYCLE_COPY = {
    "REGISTRATION": ("Registration", "Register to receive your canonical team assignment."),
    "TEAM_FORMATION": ("Team Formation", "Registration is open. Your team assignment is held by EXOS."),
    "FORMATION_LOCKED": ("Teams Locked", "Team formation has closed. Your team is now final."),
    "CAPTAIN_SELECTION": ("Captain Selection", "Your team must select one Captain before the hunt can start."),
    "READY": ("Ready", "Teams and Captains are ready. Waiting for the facilitator to start the hunt."),
    "ACTIVE": ("Hunt Active", "Follow your team’s configured mission route."),
}


OPEN_MISSION_BOARD = "OPEN_MISSION_BOARD"
_STALE_REVISION_NOTICE = (
    "This submission changed after this page was loaded, so nothing was reviewed. "
    "The board has been refreshed — review the current revision."
)


def _workspace(db, session_token):
    return db.runtime.theme_park_race_participant_workspace(session_token)


def submit_theme_park_race_review(control, strategy_mode, submission, *, decision, score, actor, notes):
    """Route one facilitator decision to the canonical contract for this mode.

    OPEN_MISSION_BOARD reviews go to the installed 039 board contract carrying
    the exact revision the facilitator was shown, so a submission that changed
    in the meantime is refused rather than silently reviewed.  Every other
    engine and strategy keeps its existing review contract untouched.
    """
    submission_id = str(submission.get("SubmissionID", ""))
    approved = str(decision).upper() in {"APPROVE", "APPROVED"}
    if str(strategy_mode or "").upper() != OPEN_MISSION_BOARD:
        control.review_submission(
            submission_id, score if approved else 0, notes,
            status="APPROVED" if approved else "REJECTED",
        )
        return {"Reviewed": True}
    submitted_at = str(submission.get("SubmittedAt", "") or "")
    if not submitted_at:
        return {"Reviewed": False, "Level": "warning", "Message": _STALE_REVISION_NOTICE}
    mapped = "APPROVE" if approved else "REJECT"
    try:
        control.review_theme_park_race_board_submission(
            submission_id, submitted_at, mapped,
            score=score if approved else 0, actor=actor, reason=notes,
            idempotency_key=f"theme-park-race-board-review|{submission_id}|{submitted_at}|{mapped}",
        )
    except RuntimeDatabaseError as error:
        if "revision is stale" in str(error).casefold():
            return {"Reviewed": False, "Level": "warning", "Message": _STALE_REVISION_NOTICE}
        return {"Reviewed": False, "Level": "error", "Message": str(error)}
    return {"Reviewed": True}


def _queue_review_notice(event_id, outcome):
    if outcome.get("Message"):
        st.session_state[f"theme_race_review_notice_{event_id}"] = outcome


def _render_review_notice(event_id):
    outcome = st.session_state.pop(f"theme_race_review_notice_{event_id}", None) or {}
    if not outcome.get("Message"):
        return
    if str(outcome.get("Level", "warning")) == "error":
        st.error(outcome["Message"])
    else:
        st.warning(outcome["Message"])


def _mission_status(workspace, activity_id):
    row = (workspace.get("Progress", {}).get("SubmissionsByActivity", {}) or {}).get(activity_id, {})
    return str(row.get("Status", "AVAILABLE" if activity_id == workspace.get("Progress", {}).get("CurrentActivityID") else "LOCKED")).upper()


def _route_rows(workspace):
    current = str(workspace.get("Progress", {}).get("CurrentActivityID", ""))
    submitted = workspace.get("Progress", {}).get("SubmissionsByActivity", {}) or {}
    rows = []
    for position, activity_id in enumerate(workspace.get("Route", []) or [], 1):
        status = str((submitted.get(activity_id) or {}).get("Status", "")).upper()
        if not status:
            status = "CURRENT" if activity_id == current else "LOCKED"
        rows.append({"#": position, "Mission ID": activity_id, "Status": status})
    return rows


def _restore_captain_recovery(identity):
    """Keep only canonical identity values after the recovery RPC returns."""
    for source, target in (
        ("ParticipantID", "participant_id"),
        ("EventID", "participant_event_id"),
        ("TeamID", "participant_team_id"),
        ("Team", "participant_team"),
        ("Name", "participant_name"),
        ("SessionToken", "participant_session_token"),
    ):
        if identity.get(source) not in (None, ""):
            st.session_state[target] = identity[source]


def _render_captain_authority(db, workspace, enrollment_credential, device_id):
    event_id = workspace.get("EventID", "")
    if not workspace.get("IsCaptain"):
        if workspace.get("Lifecycle") == "CAPTAIN_SELECTION":
            if st.button("Claim Captain authority", type="primary", width="stretch", key=f"theme_race_claim_{event_id}"):
                result = db.runtime.claim_team_formation_captain(
                    st.session_state.get("participant_session_token", ""), device_id,
                )
                if result.get("Claimed"):
                    st.success("Captain authority is now active for this team.")
                    st.rerun()
                st.info("Another team member has already claimed Captain authority.")
        else:
            st.info("Only the selected Captain can submit evidence for this team.")
        return False

    st.success("You are this team’s Captain.")
    if not workspace.get("CaptainSessionActive", False):
        st.warning("Captain authority needs recovery on this device before a mission can be submitted.")
        if st.button("Restore Captain authority", type="primary", width="stretch", key=f"theme_race_recover_captain_{event_id}"):
            if not enrollment_credential:
                st.error("Secure registration is still loading. Try again in a moment.")
                return False
            identity = db.runtime.recover_team_formation_captain(
                st.session_state.get("participant_join_code", ""), enrollment_credential, device_id,
            )
            _restore_captain_recovery(identity)
            st.success("Captain authority restored from the canonical EXOS session.")
            st.rerun()
        return False
    return True


def _render_evidence_form(db, workspace, mission):
    evidence = mission.get("Evidence", {}) or {}
    text_config = evidence.get("Text", {}) or {}
    photo_config = evidence.get("Photo", {}) or {}
    numeric_config = evidence.get("NumericResult", {}) or {}
    activity_id = mission["ActivityID"]
    st.subheader(mission.get("DisplayName") or "Current mission")
    if mission.get("ParticipantInstruction"):
        st.write(mission["ParticipantInstruction"])
    if mission.get("SafetyNote"):
        st.info(f"Safety: {mission['SafetyNote']}")
    if mission.get("FacilitatorInstruction"):
        st.caption("Facilitator notes are not shown to participants.")

    text = ""
    if text_config.get("Required"):
        text = st.text_area(text_config.get("Label") or "Team response", key=f"theme_race_text_{activity_id}")
    elif photo_config.get("Required") or numeric_config.get("Required"):
        text = st.text_area("Optional team note", key=f"theme_race_text_{activity_id}")

    uploaded_photo = None
    if photo_config.get("Required"):
        uploaded_photo = st.file_uploader(
            photo_config.get("Label") or "Private team photo", type=["jpg", "jpeg", "png"],
            key=f"theme_race_photo_{activity_id}",
        )
        if uploaded_photo is not None:
            st.image(uploaded_photo, width="stretch")

    numeric = ""
    if numeric_config.get("Required"):
        numeric = st.text_input(
            numeric_config.get("Label") or "Result", key=f"theme_race_numeric_{activity_id}",
        )

    if st.button("Submit mission evidence", type="primary", width="stretch", key=f"theme_race_submit_{activity_id}"):
        if text_config.get("Required") and not text.strip():
            st.warning("Enter the required text evidence.")
            return
        if photo_config.get("Required") and uploaded_photo is None:
            st.warning("Upload the required private photo evidence.")
            return
        if numeric_config.get("Required"):
            try:
                number = float(numeric)
            except (TypeError, ValueError):
                st.warning("Enter a numeric result.")
                return
            minimum, maximum = numeric_config.get("Minimum"), numeric_config.get("Maximum")
            if minimum is not None and number < float(minimum):
                st.warning("Result is below the configured minimum.")
                return
            if maximum is not None and number > float(maximum):
                st.warning("Result is above the configured maximum.")
                return

        uploaded = {}
        if uploaded_photo is not None:
            try:
                uploaded = upload_photo(
                    event_id=workspace["EventID"], mission_id=activity_id,
                    team_name=st.session_state.get("participant_team", workspace["TeamID"]),
                    participant_name=st.session_state.get("participant_name", ""),
                    uploaded_file=uploaded_photo,
                )
            except (RuntimeDatabaseError, ValueError) as error:
                st.error(upload_error_message("Photo upload", saved=False, retry=True, error=error))
                return
        payload = {
            "TeamName": st.session_state.get("participant_team", workspace["TeamID"]),
            "ParticipantName": st.session_state.get("participant_name", ""),
            "SubmissionType": "THEME_PARK_RACE",
            "Remarks": text.strip(),
            "Metric1": numeric.strip(),
            "ImageURL": uploaded.get("url", ""),
            "DriveFileID": uploaded.get("file_id", ""),
            "SubmittedAtClient": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        }
        try:
            db.runtime.save_theme_park_race_submission(
                st.session_state.get("participant_session_token", ""), activity_id, payload,
            )
        except RuntimeDatabaseError as error:
            st.error(str(error))
            return
        if str(workspace.get("StrategyMode", "")).upper() == "OPEN_MISSION_BOARD":
            st.success("Mission evidence submitted for facilitator review. Your team's board remains canonical after refresh.")
        else:
            st.success("Mission evidence submitted. The next route mission is now available unless this evidence is later rejected.")
        st.rerun()


def _upload_board_photo(workspace, mission_id, suffix, uploaded_photo):
    if uploaded_photo is None:
        return {}
    return upload_photo(
        event_id=workspace["EventID"], mission_id=f"{mission_id}-{suffix}",
        team_name=st.session_state.get("participant_team", workspace["TeamID"]),
        participant_name=st.session_state.get("participant_name", ""), uploaded_file=uploaded_photo,
    )


def _render_ride_evidence_form(db, workspace, mission):
    """Ride proof UI. Server-side board RPC repeats all Captain/team checks."""
    activity_id = mission["ActivityID"]
    evidence = mission.get("Evidence", {}) or {}
    required = mission.get("RideRequiredParticipantCount", 0)
    members = {row.get("ParticipantID", ""): row.get("Name", row.get("ParticipantID", "")) for row in workspace.get("TeamMembers", [])}
    st.subheader(mission.get("DisplayName") or "Ride mission")
    st.info(f"Required riders: {required} of {len(members)} current canonical team members. Full-team participation earns no extra competitive points.")
    st.caption("An attraction exterior photo is not queue-entry proof. Follow attraction staff instructions and never capture evidence where park rules prohibit it.")
    pathway_options = mission.get("RideParticipation", {}).get("EvidencePathways") or []
    pathway = st.selectbox("Evidence pathway", pathway_options, key=f"theme_race_ride_path_{activity_id}")
    riders = st.multiselect(
        "Canonical team members who entered the official queue", list(members),
        format_func=lambda key: members.get(key, key), key=f"theme_race_ride_riders_{activity_id}",
    )
    remaining = [member_id for member_id in members if member_id not in riders]
    ground_control = []
    if pathway == "GROUND_CONTROL":
        ground_control = st.multiselect(
            "Ground Control team members", remaining,
            format_func=lambda key: members.get(key, key), key=f"theme_race_ground_control_{activity_id}",
        )
    remarks = st.text_area(evidence.get("Text", {}).get("Label") or "Team note", key=f"theme_race_ride_text_{activity_id}")
    attempt = st.selectbox(
        "Ride attempt outcome", ["COMPLETED", "ABORTED_BY_ATTRACTION", "TEAM_WITHDREW", "ATTEMPTED"],
        key=f"theme_race_ride_attempt_{activity_id}",
    )
    queue_photo = post_photo = None
    facilitator_request = ""
    if attempt == "COMPLETED" and pathway in {"GROUND_CONTROL", "FULL_TEAM"}:
        queue_photo = st.file_uploader("Private official queue-entry evidence", type=["jpg", "jpeg", "png"], key=f"theme_race_queue_{activity_id}")
        post_photo = st.file_uploader("Private configured post-ride verification", type=["jpg", "jpeg", "png"], key=f"theme_race_postride_{activity_id}")
    elif attempt == "COMPLETED" and pathway == "FACILITATOR_VERIFIED":
        facilitator_request = st.text_input("Facilitator verification request", key=f"theme_race_ride_verify_{activity_id}")

    if st.button("Record ride outcome" if attempt != "COMPLETED" else "Submit ride evidence", type="primary", width="stretch", key=f"theme_race_ride_submit_{activity_id}"):
        if evidence.get("Text", {}).get("Required") and not remarks.strip():
            st.warning("Enter the required text evidence.")
            return
        if attempt == "COMPLETED" and len(riders) < int(required or 0):
            st.warning(f"At least {required} canonical team riders are required.")
            return
        if attempt == "COMPLETED" and pathway in {"GROUND_CONTROL", "FULL_TEAM"} and (queue_photo is None or post_photo is None):
            st.warning("Queue-entry and post-ride evidence are both required for this evidence pathway.")
            return
        try:
            queue = _upload_board_photo(workspace, activity_id, "QUEUE", queue_photo)
            post = _upload_board_photo(workspace, activity_id, "POST", post_photo)
        except (RuntimeDatabaseError, ValueError) as error:
            st.error(upload_error_message("Ride evidence upload", saved=False, retry=True, error=error))
            return
        payload = {
            "TeamName": st.session_state.get("participant_team", workspace["TeamID"]),
            "ParticipantName": st.session_state.get("participant_name", ""),
            "SubmissionType": "THEME_PARK_RACE_RIDE",
            "Remarks": remarks.strip(), "RideEvidencePathway": pathway,
            "RideAttemptStatus": attempt, "RiderParticipantIDs": riders,
            "GroundControlParticipantIDs": ground_control,
            "QueueEntryEvidence": queue.get("url", ""), "PostRideEvidence": post.get("url", ""),
            "FacilitatorVerificationRequest": facilitator_request.strip(),
        }
        try:
            if attempt == "COMPLETED":
                db.runtime.save_theme_park_race_submission(st.session_state.get("participant_session_token", ""), activity_id, payload)
            else:
                db.runtime.record_theme_park_race_ride_outcome(st.session_state.get("participant_session_token", ""), activity_id, attempt, payload)
        except RuntimeDatabaseError as error:
            st.error(str(error))
            return
        st.success("Ride outcome recorded from canonical board state.")
        st.rerun()


def _render_open_mission_board(db, workspace, captain_active):
    """Render only this team's canonical available/selected board state."""
    board = workspace.get("MissionBoard", [])
    if not board:
        st.info("No mission is currently available.")
        return
    st.markdown("#### Mission opportunity board")
    for mission in board:
        activity_id = mission.get("ActivityID", "")
        state = str(mission.get("MissionState", "LOCKED")).upper()
        label = f"{mission.get('DisplayName', activity_id)} · {mission.get('MissionClass', 'STANDARD')} · {state}"
        with st.expander(label, expanded=state in {"SELECTED", "REJECTED"}):
            st.caption(f"{mission.get('Zone', '')} · {mission.get('LocationDescription', '')}")
            st.write(mission.get("ParticipantInstruction", ""))
            if mission.get("SafetyNote"):
                st.info(f"Safety: {mission['SafetyNote']}")
            st.caption(f"Operational status: {mission.get('OperationalStatus', state)}")
            if state == "AVAILABLE" and captain_active:
                if st.button("Select this mission", type="primary", key=f"theme_race_board_select_{activity_id}"):
                    try:
                        db.runtime.select_theme_park_race_mission(st.session_state.get("participant_session_token", ""), activity_id)
                    except RuntimeDatabaseError as error:
                        st.error(str(error))
                        return
                    st.rerun()
            elif state in {"SELECTED", "REJECTED"}:
                if not captain_active:
                    st.caption("Captain authority is required to submit this team mission.")
                elif str(mission.get("MissionClass", "")).upper() == "RIDE":
                    _render_ride_evidence_form(db, workspace, mission)
                else:
                    _render_evidence_form(db, workspace, mission)
            elif state == "TEMPORARILY_UNAVAILABLE":
                st.info("This mission is temporarily unavailable. Choose another available mission; no score penalty applies.")
            elif state == "CLOSED":
                st.info("This mission is closed and cannot be selected.")
            elif state == "SUBMITTED":
                st.info("Evidence is awaiting facilitator review.")
            elif state == "APPROVED":
                st.success("Mission approved.")


def render_theme_park_race_participant(db, enrollment_credential="", device_id=""):
    """Participant/Captain surface driven solely by the canonical workspace."""
    session_token = st.session_state.get("participant_session_token", "")
    try:
        workspace = _workspace(db, session_token)
    except RuntimeDatabaseError as error:
        st.warning("Theme Park Race state is reconnecting.")
        st.caption(str(error))
        return
    lifecycle = workspace.get("Lifecycle", "REGISTRATION")
    title, message = _LIFECYCLE_COPY.get(lifecycle, ("Theme Park Race", "Waiting for canonical event state."))
    st.subheader(title)
    st.info(message)
    strategy_mode = str(workspace.get("StrategyMode", "CONFIGURED_TEAM_ROUTE")).upper()
    progress_label = "Team mission progress" if strategy_mode == "OPEN_MISSION_BOARD" else "Team route progress"
    st.caption(f"{progress_label}: {workspace.get('Progress', {}).get('Completed', 0)} / {workspace.get('Progress', {}).get('Total', 0)}")
    if strategy_mode != "OPEN_MISSION_BOARD":
        route_rows = _route_rows(workspace)
        if route_rows:
            st.dataframe(route_rows, hide_index=True, width="stretch")

    captain_active = _render_captain_authority(db, workspace, enrollment_credential, device_id)
    if lifecycle != "ACTIVE":
        return
    if strategy_mode == "OPEN_MISSION_BOARD":
        _render_open_mission_board(db, workspace, captain_active)
        return
    mission = workspace.get("CurrentMission")
    if not mission:
        st.success("Your team has completed its configured route.")
        return
    if not captain_active:
        st.caption("Mission details and progress remain visible to the whole team. Captain authority is required to submit.")
        st.subheader(mission.get("DisplayName") or "Current mission")
        st.write(mission.get("ParticipantInstruction", ""))
        return
    _render_evidence_form(db, workspace, mission)


def render_theme_park_race_facilitator(db, control, event_id):
    """Facilitator lifecycle, Captain, review, progress, scoring and controls."""
    try:
        workspace = db.runtime.theme_park_race_facilitator_workspace(event_id)
    except RuntimeDatabaseError as error:
        st.error(str(error))
        return
    st.subheader("Theme Park Race Control")
    metrics = st.columns(6)
    metrics[0].metric("Lifecycle", workspace.get("Lifecycle", "—"))
    metrics[1].metric("Registered", workspace.get("RegistrationCount", 0))
    metrics[2].metric("Teams", workspace.get("TeamCount", 0))
    metrics[3].metric("Captains", f"{workspace.get('CaptainCount', 0)}/{workspace.get('TeamCount', 0)}")
    metrics[4].metric("Missions", workspace.get("MissionCount", 0))
    metrics[5].metric("Pending reviews", workspace.get("PendingReviewCount", 0))

    actor = st.text_input("Facilitator identity", key=f"theme_race_actor_{event_id}")
    phase = str(workspace.get("TeamFormationPhase", "")).upper()
    runtime_phase = str(workspace.get("RuntimePhase", "READY")).upper()
    lifecycle_col, hunt_col = st.columns(2)
    with lifecycle_col:
        if phase == "DRAFT":
            if st.button("Open registration", type="primary", disabled=not actor, key=f"theme_race_open_{event_id}"):
                control.open_team_formation(event_id, actor); st.rerun()
        elif phase == "REGISTRATION_OPEN":
            if st.button("Lock team formation", type="primary", disabled=not actor, key=f"theme_race_lock_{event_id}"):
                control.lock_team_formation(event_id, actor); st.rerun()
        elif phase == "FORMATION_LOCKED":
            if st.button("Open Captain selection", type="primary", disabled=not actor, key=f"theme_race_captains_{event_id}"):
                control.open_team_captain_selection(event_id, actor); st.rerun()
        elif phase == "CAPTAIN_SELECTION":
            if st.button("Activate teams", type="primary", disabled=not actor, key=f"theme_race_activate_teams_{event_id}"):
                control.activate_team_formation(event_id, actor); st.rerun()
        else:
            st.success("Team Formation is active.")
    with hunt_col:
        if phase != "ACTIVE":
            st.caption("Hunt start unlocks after every team has an effective Captain.")
        elif runtime_phase != "ACTIVE":
            if st.button("Start Theme Park Race", type="primary", disabled=not actor, key=f"theme_race_start_{event_id}"):
                control.set_theme_park_race_runtime_phase(event_id, "ACTIVE", actor); st.rerun()
        else:
            pause, close = st.columns(2)
            if pause.button("Hold Theme Park Race", disabled=not actor, key=f"theme_race_hold_{event_id}"):
                control.set_theme_park_race_runtime_phase(event_id, "READY", actor); st.rerun()
            if close.button("End Theme Park Race", disabled=not actor, key=f"theme_race_end_{event_id}"):
                control.set_theme_park_race_runtime_phase(event_id, "CLOSED", actor); st.rerun()

    if str(workspace.get("StrategyMode", "")).upper() == "OPEN_MISSION_BOARD":
        with st.expander("Mission Board control", expanded=True):
            operations = {row.get("ActivityID", ""): row for row in workspace.get("MissionOperations", [])}
            if operations:
                activity_id = st.selectbox(
                    "Mission", list(operations),
                    format_func=lambda key: f"{operations[key].get('DisplayName', key)} · {operations[key].get('MissionClass', 'STANDARD')}",
                    key=f"theme_race_board_operation_mission_{event_id}",
                )
                operation = operations[activity_id]
                operational_status = st.selectbox(
                    "Operational status", ["AVAILABLE", "TEMPORARILY_UNAVAILABLE", "CLOSED"],
                    index=["AVAILABLE", "TEMPORARILY_UNAVAILABLE", "CLOSED"].index(str(operation.get("OperationalStatus", "AVAILABLE")).upper()),
                    key=f"theme_race_board_status_{event_id}",
                )
                secret_state = "RELEASED"
                if str(operation.get("MissionClass", "")).upper() == "SECRET":
                    secret_state = st.selectbox(
                        "Secret mission state", ["LOCKED", "RELEASED"],
                        index=["LOCKED", "RELEASED"].index(str(operation.get("SecretState", "LOCKED")).upper()),
                        key=f"theme_race_board_secret_{event_id}",
                    )
                if st.button("Apply mission board control", disabled=not actor, key=f"theme_race_board_apply_{event_id}"):
                    control.set_theme_park_race_mission_operation(event_id, activity_id, operational_status, secret_state, actor)
                    st.rerun()

    st.markdown("#### Team progress and Captain status")
    rows = [{
        "Team": row.get("TeamIdentity", row.get("TeamID")),
        "Registered": row.get("RegisteredParticipants", 0),
        "Captain": row.get("CaptainName") or "Not selected",
        "Progress": f"{row.get('Completed', 0)}/{row.get('Total', 0)}",
        "Current mission": row.get("CurrentActivityID") or "Complete",
        "Selected missions": ", ".join(row.get("SelectedMissionActivityIDs", [])) or "—",
        "Pending review": row.get("PendingReview", 0),
        "Rejected": row.get("Rejected", 0),
    } for row in workspace.get("Teams", [])]
    st.dataframe(rows, hide_index=True, width="stretch")

    if phase in {"CAPTAIN_SELECTION", "ACTIVE"}:
        with st.expander("Facilitator Captain transfer"):
            teams = {row.get("TeamID", ""): row for row in workspace.get("Teams", [])}
            if teams:
                team_id = st.selectbox("Team", list(teams), format_func=lambda key: teams[key].get("TeamIdentity", key), key=f"theme_race_transfer_team_{event_id}")
                members = [row for row in db.runtime.get_theme_park_race_players(event_id) if row.get("TeamID") == team_id]
                choices = {row.get("ParticipantID", ""): row for row in members}
                if choices:
                    participant_id = st.selectbox("New Captain", list(choices), format_func=lambda key: choices[key].get("Name", key), key=f"theme_race_transfer_participant_{event_id}")
                    reason = st.text_input("Transfer reason", key=f"theme_race_transfer_reason_{event_id}")
                    if st.button("Transfer Captain", disabled=not actor or not reason.strip(), key=f"theme_race_transfer_{event_id}"):
                        control.transfer_team_formation_captain(event_id, team_id, participant_id, actor, reason)
                        st.success("Captain transfer recorded. The new Captain must recover Captain authority on their device.")
                        st.rerun()

    st.markdown("#### Submission review")
    _render_review_notice(event_id)
    strategy_mode = str(workspace.get("StrategyMode", "")).upper()
    queue = workspace.get("ReviewQueue", [])
    if not queue:
        st.caption("No submissions are awaiting review.")
    for submission in queue:
        submission_id = submission.get("SubmissionID", "")
        with st.expander(f"{submission.get('TeamName', submission.get('TeamID', 'Team'))} · {submission.get('ActivityID', 'Mission')}"):
            if submission.get("Remarks"):
                st.write(submission["Remarks"])
            photo = get_photo_url(submission.get("ImageURL", ""), submission.get("DriveFileID", ""))
            if photo:
                st.image(photo, width="stretch")
            if submission.get("RideAttemptStatus"):
                st.caption(
                    f"Ride pathway: {submission.get('RideEvidencePathway') or '—'} · "
                    f"Attempt: {submission.get('RideAttemptStatus')} · "
                    f"Canonical riders declared: {len(submission.get('RiderParticipantIDs', []))} / "
                    f"{submission.get('RequiredRideParticipants') or '—'} required from "
                    f"{submission.get('CanonicalTeamMemberCount') or '—'} members"
                )
                if submission.get("GroundControlParticipantIDs"):
                    st.caption(f"Ground Control declared: {len(submission.get('GroundControlParticipantIDs', []))}")
                queue_photo = get_photo_url(submission.get("QueueEntryEvidence", ""), "")
                if queue_photo:
                    st.image(queue_photo, caption="Private queue-entry evidence", width="stretch")
                post_ride_photo = get_photo_url(submission.get("PostRideEvidence", ""), "")
                if post_ride_photo:
                    st.image(post_ride_photo, caption="Private post-ride verification", width="stretch")
                if submission.get("FacilitatorVerificationRequest"):
                    st.write(submission["FacilitatorVerificationRequest"])
            score = st.number_input("Score", value=float(submission.get("Score") or 0), key=f"theme_race_score_{submission_id}")
            notes = st.text_input("Review notes", key=f"theme_race_notes_{submission_id}")
            if strategy_mode == OPEN_MISSION_BOARD:
                st.caption(f"Reviewing revision submitted at {submission.get('SubmittedAt') or 'unknown'}.")
            approve, reject = st.columns(2)
            if approve.button("Approve", type="primary", disabled=not actor, key=f"theme_race_approve_{submission_id}"):
                _queue_review_notice(event_id, submit_theme_park_race_review(
                    control, strategy_mode, submission,
                    decision="APPROVE", score=score, actor=actor, notes=notes,
                ))
                st.rerun()
            if reject.button("Reject / request resubmission", disabled=not actor, key=f"theme_race_reject_{submission_id}"):
                _queue_review_notice(event_id, submit_theme_park_race_review(
                    control, strategy_mode, submission,
                    decision="REJECT", score=0, actor=actor, notes=notes,
                ))
                st.rerun()


def render_theme_park_race_projector(db, event_id):
    """Display-only live projection; no lifecycle, review or score mutations."""
    workspace = db.runtime.theme_park_race_facilitator_workspace(event_id)
    event = db.get_event(event_id) or {}
    projection = projector_projection(workspace, db.runtime.get_theme_park_race_configuration(event_id))
    st.markdown("<div class='projector-header'><div class='projector-kicker'>THEME PARK RACE</div><div class='projector-event-title'>LIVE HUNT</div></div>", unsafe_allow_html=True)
    st.caption(f"{event.get('EventName', '')} · {projection.get('Lifecycle', '')} · {projection.get('PendingReviewCount', 0)} pending review")
    open_board = str(projection.get("StrategyMode", "")).upper() == "OPEN_MISSION_BOARD"
    st.dataframe([(
        {
            "Team": row.get("TeamIdentity", row.get("TeamID")),
            "Approved missions": f"{row.get('Completed', 0)}/{row.get('Total', 0)}",
            "Pending review": row.get("PendingReview", 0),
            "Captain": "Ready" if row.get("CaptainSelected") else "Selecting",
        } if open_board else {
            "Team": row.get("TeamIdentity", row.get("TeamID")),
            "Mission progress": f"{row.get('Completed', 0)}/{row.get('Total', 0)}",
            "Current mission": row.get("CurrentActivityID") or "Complete",
            "Pending review": row.get("PendingReview", 0),
            "Captain": "Ready" if row.get("CaptainSelected") else "Selecting",
        }
    ) for row in projection.get("Teams", [])], hide_index=True, width="stretch")
    if open_board:
        aggregate = projection.get("MissionAggregate", [])
        if aggregate:
            st.markdown("### Mission board status")
            st.dataframe([{
                "Mission": row.get("DisplayName", row.get("ActivityID", "")),
                "Class": row.get("MissionClass", "STANDARD"),
                "Operational status": row.get("OperationalStatus", "AVAILABLE"),
            } for row in aggregate], hide_index=True, width="stretch")
        for mission in projection.get("ReleasedSecretMissionAnnouncements", []):
            st.info(f"Secret mission released: {mission}")
    if projection.get("ShowOverallScoring"):
        leaderboard = projection.get("Leaderboard", [])
        if leaderboard:
            st.markdown("### Overall scoring")
            st.dataframe([{
                "Rank": position,
                "Team": row.get("TeamName", row.get("TeamID", "Team")),
                "Score": row.get("Score", 0),
            } for position, row in enumerate(leaderboard, 1)], hide_index=True, width="stretch")
