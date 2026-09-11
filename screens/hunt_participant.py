"""Generic mobile participant surface for a configured EXOS WALK Hunt."""
from __future__ import annotations

import html

import streamlit as st

from components.participant_credential import participant_device_binding
from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import get_standard_database
from data.upload_safety import validate_image_content, validate_upload
from engines.hunt_engine import participant_hunt_state
from screens.participant import normalise_join_name, restore_participant_identity
from services.hunt_evidence import upload_hunt_evidence
from services.hunt_live_state import watch_hunt_live_state
from services.hunt_mission_ai import ask_hunt_mission_ai
from services.live_location_participant import render_live_location_participant, render_participant_announcements


def _query_value(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def _valid(player: dict | None, event_id: str) -> bool:
    return bool(player and str(player.get("EventID", "")) == event_id and player.get("ParticipantID")
                and player.get("TeamID") and player.get("SessionToken"))


def _persist_session(player: dict, event_id: str) -> None:
    # The browser cache only carries opaque resume state. The canonical session
    # revalidates ParticipantID/EventID/TeamID before every Hunt action.
    for name, value in {"event_id": event_id, "session_token": str(player.get("SessionToken") or "")}.items():
        if value and _query_value(name) != value:
            st.query_params[name] = value
    for name in list(st.query_params):
        if str(name).casefold() in {"join_code", "credential", "enrollment_credential", "device_id", "participant_name"}:
            del st.query_params[name]


def _restore(runtime, event_id: str) -> dict | None:
    token = str(st.session_state.get("participant_session_token", "") or _query_value("session_token")).strip()
    if not token:
        return None
    try:
        player = runtime.get_player_by_token(token)
    except RuntimeDatabaseError:
        return None
    if _valid(player, event_id):
        restore_participant_identity(player, fallback_token=token)
        return player
    return None


def _team_reveal(workspace: dict) -> None:
    team = html.escape(str(workspace.get("TeamName") or workspace.get("TeamID") or "YOUR TEAM").upper())
    members = list(workspace.get("TeamMembers") or [])
    st.markdown(f"## YOU ARE {team}")
    st.info("Find your people. Captain selection opens when Mission Control moves the event forward.")
    if members:
        st.dataframe([{
            "Team member": member.get("DisplayName", "Team member"),
            "Attendance": member.get("AttendanceState", "UNMARKED"),
        } for member in members], hide_index=True, width="stretch")


def _captain_controls(runtime, workspace: dict, device_id: str, *, join_code: str = "", credential: str = "") -> bool:
    phase = str(workspace.get("TeamFormationPhase", "")).upper()
    if not workspace.get("IsCaptain"):
        if phase == "CAPTAIN_SELECTION":
            st.info("Your team is choosing a Mission Captain. Only one effective Captain can hold active submit authority.")
            if st.button("CLAIM CAPTAIN", type="primary", width="stretch", key="hunt_claim_captain"):
                try:
                    runtime.claim_team_formation_captain(st.session_state.get("participant_session_token", ""), device_id)
                except RuntimeDatabaseError as error:
                    st.error(str(error))
                else:
                    st.rerun()
        return False
    st.caption("🧭 You are the Mission Captain. Submissions and participant selections are recorded through your active Captain session.")
    if st.button("RECOVER CAPTAIN ACCESS ON THIS DEVICE", width="stretch", key="hunt_recover_captain"):
        try:
            identity = runtime.recover_team_formation_captain(join_code, credential, device_id)
        except RuntimeDatabaseError as error:
            st.error(str(error))
            return False
        if not _valid(identity, str(workspace.get("EventID") or "")):
            st.error("Captain access could not be recovered on this device. Contact Mission Control.")
            return False
        restore_participant_identity(identity)
        _persist_session(identity, str(workspace.get("EventID") or ""))
        st.success("Captain access recovered.")
        st.rerun()
    return True


def _state_banner(workspace: dict) -> bool:
    state = participant_hunt_state(workspace.get("TeamFormationPhase", ""), workspace.get("OperationalState", "READY"))
    if state == "RETURN_NOW":
        st.error("RETURN TO BASE\n\nFollow facilitator instructions. New Hunt submissions are paused.")
        return False
    if state == "HOLD":
        st.warning("HUNT ON HOLD\n\nWait for your facilitator. New Hunt submissions are paused.")
        return False
    if state == "CLOSED":
        st.info("This Hunt is closed. Thank you for taking part.")
        return False
    if state == "READY":
        st.info("HUNT READY\n\nStay with your team and wait for Mission Control to launch the Walk Hunt.")
        return False
    return True


def _submission_controls(runtime, workspace: dict, mission: dict, captain_active: bool) -> None:
    mission_id = str(mission.get("MissionID") or "")
    state = str(mission.get("MissionState") or "AVAILABLE").upper()
    evidence_required = str(mission.get("EvidenceType") or "NONE").upper()
    title = str(mission.get("Name") or mission_id)
    with st.expander(f"{title} · {state}", expanded=state in {"IN_PROGRESS", "RETURNED"}):
        st.caption(str(mission.get("Instructions") or "Follow the mission briefing."))
        st.caption(f"{mission.get('MissionType', 'MISSION')} · up to {mission.get('MaximumScore', 0)} pts · {mission.get('ScoringMode', 'TEAM_FULL')}")
        if state in {"PENDING_REVIEW", "COMPLETED"}:
            st.success("Awaiting review" if state == "PENDING_REVIEW" else "Completed")
            return
        if not captain_active:
            st.caption("Your Mission Captain submits team evidence.")
            return
        with st.form(f"hunt_submit_{mission_id}", clear_on_submit=False):
            answer = st.text_area("Team response", key=f"hunt_text_{mission_id}")
            selected_evidence = evidence_required
            if evidence_required == "PHOTO_OR_VIDEO":
                selected_evidence = st.radio("Evidence type", ["PHOTO", "VIDEO"], horizontal=True, key=f"hunt_evidence_kind_{mission_id}")
            upload = None
            if selected_evidence in {"PHOTO", "VIDEO"}:
                file_types = ["jpg", "jpeg", "png", "webp", "heic"] if selected_evidence == "PHOTO" else ["mp4", "mov", "m4v", "webm"]
                upload = st.file_uploader(
                    "Private evidence" + (" · video 5–10 seconds recommended, maximum 50 MB" if selected_evidence == "VIDEO" else ""),
                    type=file_types, key=f"hunt_upload_{mission_id}",
                )
            participants = list(workspace.get("TeamMembers") or [])
            completing_ids: list[str] = []
            if str(mission.get("ScoringMode") or "").upper() == "PARTICIPATION_PRORATED":
                present = {str(row.get("DisplayName") or row.get("ParticipantID")): str(row.get("ParticipantID"))
                           for row in participants if str(row.get("AttendanceState") or "").upper() == "PRESENT"}
                selected = st.multiselect("PRESENT teammates who completed this mission", list(present), key=f"hunt_complete_{mission_id}")
                completing_ids = [present[label] for label in selected]
            submitted = st.form_submit_button("SUBMIT FOR REVIEW", type="primary", width="stretch")
        if not submitted:
            return
        evidence: dict = {"EvidenceType": "NONE"}
        try:
            if selected_evidence in {"PHOTO", "VIDEO"}:
                evidence = upload_hunt_evidence(upload, event_id=str(workspace.get("EventID") or ""),
                                                 team_id=str(workspace.get("TeamID") or ""), mission_id=mission_id,
                                                 evidence_type=selected_evidence)
            runtime.submit_hunt_mission(
                st.session_state.get("participant_session_token", ""), mission_id,
                submission_payload={"Response": answer}, evidence=evidence,
                completing_participant_ids=completing_ids,
            )
        except (RuntimeDatabaseError, ValueError) as error:
            st.error(str(error))
            st.caption("Your selected evidence and participant choices remain in this form for a safe retry.")
        else:
            st.success("Submitted for facilitator review.")
            st.rerun()


def _render_mission_ai(workspace: dict) -> None:
    st.divider()
    st.subheader("✨ ASK MISSION AI")
    st.caption("Ask about visible missions, clues, checkpoint information, or what your team could consider next. Mission AI cannot infer your location, score work, or complete a mission.")
    question = st.text_input("Ask Mission AI", key="hunt_ai_question", placeholder="What should we consider next?")
    photo = st.file_uploader("Optional screenshot / photo", type=["jpg", "jpeg", "png", "webp"], key="hunt_ai_photo",
                             help="Used only for this answer. It is not stored as evidence.")
    if st.button("ASK", type="primary", width="stretch", key="hunt_ai_ask"):
        prompt = question.strip() or ("What do you notice in this photo?" if photo else "")
        if not prompt:
            st.info("Ask a question or attach a photo.")
            return
        try:
            image = validate_upload(photo, {"jpg", "jpeg", "png", "webp"}, {"image/jpeg", "image/png", "image/webp"}, 10 * 1024 * 1024, "Mission AI photo") if photo else None
            if image:
                validate_image_content(image, "Mission AI photo")
            answer = ask_hunt_mission_ai(prompt, workspace, image, str(getattr(photo, "type", "") or ""))
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state["hunt_ai_answer"] = (prompt, answer)
    if st.session_state.get("hunt_ai_answer"):
        prompt, answer = st.session_state["hunt_ai_answer"]
        st.caption(prompt)
        st.info(answer)


def _dashboard(runtime, player: dict, device_id: str, *, join_code: str, credential: str) -> None:
    token = str(player.get("SessionToken") or "")
    watch_hunt_live_state(runtime, token)
    render_participant_announcements(runtime, session_token=token)
    render_live_location_participant(runtime, session_token=token, device_id=device_id)
    try:
        workspace = runtime.hunt_participant_workspace(token)
    except RuntimeDatabaseError:
        st.warning("Mission AI is reconnecting. Your canonical team state could not be refreshed yet.")
        return
    st.title("MISSION AI WALK HUNT")
    st.caption(str(workspace.get("TeamName") or workspace.get("TeamID") or ""))
    phase = str(workspace.get("TeamFormationPhase") or "").upper()
    if phase in {"REGISTRATION_OPEN", "FORMATION_LOCKED", "CAPTAIN_SELECTION"}:
        _team_reveal(workspace)
        _captain_controls(runtime, workspace, device_id, join_code=join_code, credential=credential)
        return
    captain_active = _captain_controls(runtime, workspace, device_id, join_code=join_code, credential=credential)
    if not _state_banner(workspace):
        return
    progress = dict(workspace.get("Progress") or {})
    st.caption(f"{progress.get('Completed', 0)} completed · {progress.get('PendingReview', 0)} pending review · {progress.get('Total', 0)} total")
    for mission in list(workspace.get("Missions") or []):
        if mission.get("Visible", True):
            _submission_controls(runtime, workspace, mission, captain_active)
    _render_mission_ai(workspace)


def render_hunt_participant(*, event_id: str, join_code: str, event_title: str = "MISSION AI WALK HUNT") -> None:
    """Render common-QR RANDOM_ASSIGN registration and the WALK Hunt dashboard."""
    runtime = get_standard_database()
    binding = participant_device_binding(event_id, key=f"hunt_binding_{event_id}")
    if binding is None:
        st.title(event_title)
        st.info("Restoring this device securely…")
        return
    credential, device_id = binding["Credential"], binding["DeviceID"]
    st.session_state["participant_device_id"] = device_id
    player = _restore(runtime, event_id)
    if not _valid(player, event_id) and binding.get("HasStoredCredential"):
        try:
            candidate = runtime.recover_team_formation_participant(join_code, credential, device_id)
        except RuntimeDatabaseError as error:
            if "TEAM_FORMATION_RECOVERY_CREDENTIAL_INVALID" not in str(error):
                st.error("Mission AI could not restore this device yet. Please retry shortly.")
                return
        else:
            if _valid(candidate, event_id):
                restore_participant_identity(candidate)
                _persist_session(candidate, event_id)
                st.rerun()
    if _valid(player, event_id):
        _persist_session(player, event_id)
        _dashboard(runtime, player, device_id, join_code=join_code, credential=credential)
        return
    try:
        event = runtime.get_event_by_join_code(join_code)
    except RuntimeDatabaseError:
        event = None
    if not event or str(event.get("EventID") or "") != event_id:
        st.error("This Walk Hunt is not available yet.")
        return
    st.title(event_title)
    st.caption("Enter your name once. This device will securely reconnect you to your assigned team. There is no public join code or personal key.")
    with st.form("hunt_random_registration", clear_on_submit=False):
        first_name = st.text_input("FIRST / GIVEN NAME", autocomplete="given-name")
        last_name = st.text_input("LAST / FAMILY NAME", autocomplete="family-name")
        entered = st.form_submit_button("ENTER HUNT", type="primary", width="stretch")
    if entered:
        name = normalise_join_name(first_name, last_name)
        if not first_name.strip() or not last_name.strip():
            st.error("Enter both your first / given and last / family name.")
        else:
            try:
                player = runtime.register_hunt_random_participant(join_code, name, device_id, credential)
            except RuntimeDatabaseError as error:
                st.error(str(error) or "Registration could not be completed. Please try again.")
            else:
                if _valid(player, event_id):
                    restore_participant_identity(player)
                    _persist_session(player, event_id)
                    st.rerun()
