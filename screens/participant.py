import uuid
import math
import html
import os
import subprocess
from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from branding import (
    experience_header,
    experience_title,
    footer,
    participant_install_experience,
)
from ai.facilitator import ask_facilitator
from components.team_geolocation import team_geolocation
from data.google_drive import (
    delete_evidence_file,
    get_photo_url,
    upload_evidence_file,
    upload_photo,
)
from data.google_sheets import GoogleSheetsDB
from data.mission_media import get_mission_media_url
from data.runtime_database import RuntimeDatabaseError, get_runtime_database
from data.experience_repository import SupabaseExperienceRepository
from data.upload_safety import upload_error_message
from engines.programme_hierarchy import (
    activity_details,
    friendly_type,
)
from engines.programme_adapter import CanonicalProgrammeAdapter, ProgrammeIntegrityError
from engines.experience_library import ExperienceLibraryService, ExperienceResolutionError
from components.experience_preview import render_experience_participant
from screens.mission_setup import cropped_reference_image, mission_module_name


def running_build_sha():
    """Return the deployed revision without hard-coding a commit hash."""
    for variable in ("STREAMLIT_GIT_COMMIT", "GIT_COMMIT", "COMMIT_SHA"):
        value = str(os.environ.get(variable, "") or "").strip()
        if value:
            return value[:7]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


COUNTRY_LANGUAGE_PROMPTS = {
    "Korea": "Find everyone from your country. Speak the language.",
    "Japan": "Find your team. You may greet them with: Konnichiwa.",
    "Malaysia": "Find your team. You may greet them with: Apa khabar.",
    "France": "Find your team. You may greet them with: Bonjour.",
    "India": "Find your team. You may greet them with: Namaste.",
    "Philippines": "Find everyone from your country. Speak the language.",
    "Thailand": "Find your team. You may greet them with: Sawadee.",
    "China": "Find your team. You may greet them with: Ni hao.",
}

SESSION_KEYS = [
    "participant_id",
    "participant_event_id",
    "participant_name",
    "participant_team",
    "participant_team_id",
    "participant_country",
    "participant_flag",
    "participant_is_leader",
    "participant_points",
    "participant_event_name",
    "participant_session_token",
    "ai_name",
    "ai_personality",
    "ai_greeting",
    "participant_runtime_signature",
    "participant_runtime_state",
    "participant_runtime_poll_count",
    "participant_runtime_error",
    "participant_device_id",
    "participant_join_request",
    "participant_recovery_candidate",
]


def participant_device_id():
    """Return a refresh-stable, non-secret browser registration identifier."""
    value = str(
        st.session_state.get("participant_device_id", "")
        or st.query_params.get("device_id", "")
    ).strip()
    if not value:
        value = uuid.uuid4().hex
    st.session_state["participant_device_id"] = value
    if str(st.query_params.get("device_id", "")) != value:
        st.query_params["device_id"] = value
    return value


@st.cache_data(ttl=60, show_spinner=False)
def participant_event_by_code(join_code):
    """One lightweight runtime lookup; no Sheets or Experience content."""
    return get_runtime_database().get_event_by_join_code(join_code)


def reset_session():
    for key in SESSION_KEYS:
        st.session_state.pop(key, None)

    for key in [
        "event_id",
        "participant_name",
        "participant_team",
        "event_name",
        "session_token",
    ]:
        if key in st.query_params:
            del st.query_params[key]

    for key in list(st.session_state):
        if str(key).startswith("road_hunt_"):
            st.session_state.pop(key, None)


def restore_participant_identity(player, fallback_token="", fallback_country=""):
    """Restore the complete participant identity returned by the durable store."""
    st.session_state["participant_id"] = player.get("ParticipantID", "")
    st.session_state["participant_event_id"] = player.get("EventID", "")
    st.session_state["participant_name"] = player.get("Name", "")
    st.session_state["participant_team"] = player.get("Team", "")
    st.session_state["participant_team_id"] = player.get("TeamID", "")
    st.session_state["participant_country"] = player.get(
        "Country", fallback_country,
    )
    st.session_state["participant_flag"] = player.get("Flag", "")
    st.session_state["participant_is_leader"] = bool(
        player.get("IsLeader", False)
    )
    st.session_state["participant_points"] = player.get("Points", 0)
    st.session_state["participant_event_name"] = player.get(
        "EventName", "EXOS Event",
    )
    st.session_state["participant_session_token"] = player.get(
        "SessionToken", fallback_token,
    )


def render_recovery_candidate(candidate):
    """Require an explicit human choice before resuming a found identity."""
    st.info("Existing expedition record found.")
    st.write(f"**Participant:** {candidate.get('Name', '')}")
    st.write(
        f"**Country:** {candidate.get('Flag', '')} "
        f"{candidate.get('Country', '')}".strip()
    )
    st.write(f"**Team:** {candidate.get('Team', '')}")
    resume, reject = st.columns(2)
    if resume.button("Resume Expedition", type="primary", width="stretch"):
        restore_participant_identity(candidate)
        st.session_state.pop("participant_recovery_candidate", None)
        persist_session_in_query_params()
        st.rerun()
    if reject.button("This Is Not Me", width="stretch"):
        st.session_state.pop("participant_recovery_candidate", None)
        st.session_state.pop("participant_join_request", None)
        st.warning("Use a distinct full name or ask the facilitator to resolve duplicate identities.")
        st.stop()
    st.stop()


@st.fragment(run_every="5s")
def watch_live_mission_state(session_token):
    """Poll Supabase and rerun the full app when the live stage changes."""
    try:
        runtime_state = (
            get_runtime_database().get_participant_current_mission(
                session_token
            )
            or {}
        )
    except RuntimeDatabaseError as error:
        st.caption("🟠 Live connection reconnecting...")
        st.session_state["participant_runtime_error"] = str(error)
        return

    signature = (
        str(runtime_state.get("EventID", "")),
        str(runtime_state.get("StateVersion", "")),
        str(runtime_state.get("StageType", "")),
        str(runtime_state.get("MissionID", "")),
    )
    previous_signature = st.session_state.get(
        "participant_runtime_signature"
    )
    st.session_state["participant_runtime_signature"] = signature
    st.session_state["participant_runtime_state"] = runtime_state
    st.session_state.pop("participant_runtime_error", None)

    if previous_signature is not None and signature != previous_signature:
        st.rerun(scope="app")


def restore_session_from_query_params(runtime):
    if "participant_event_id" in st.session_state:
        return

    event_id = str(st.query_params.get("event_id", "")).strip()
    participant_name = str(st.query_params.get("participant_name", "")).strip()
    session_token = str(st.query_params.get("session_token", "")).strip()

    if session_token:
        try:
            runtime_player = runtime.get_player_by_token(session_token)
        except RuntimeDatabaseError:
            runtime_player = None

        if runtime_player:
            restore_participant_identity(runtime_player, session_token)
            return

    if runtime.is_configured:
        for key in [
            "event_id",
            "participant_name",
            "participant_team",
            "event_name",
            "session_token",
        ]:
            if key in st.query_params:
                del st.query_params[key]
        return

    db = GoogleSheetsDB()
    if not event_id or not participant_name:
        return

    player = db.get_player(event_id, participant_name)
    if not player:
        return

    event = next(
        (
            row
            for row in db.get_events()
            if str(row.get("EventID", "")) == event_id
        ),
        {},
    )
    team_name = str(
        player.get("Team", "")
        or player.get("TeamName", "")
        or st.query_params.get("participant_team", "")
    )
    ai = db.assign_ai_facilitator(team_name) or {}

    st.session_state["participant_event_id"] = event_id
    st.session_state["participant_name"] = participant_name
    st.session_state["participant_team"] = team_name
    st.session_state["participant_country"] = ""
    st.session_state["participant_points"] = player.get("Points", 0)
    st.session_state["participant_event_name"] = event.get(
        "EventName",
        str(st.query_params.get("event_name", "EXOS Event")),
    )
    st.session_state["participant_session_token"] = ""
    apply_participant_ai_identity(ai, event_id)


def persist_session_in_query_params():
    desired = {
        "event_id": st.session_state["participant_event_id"],
        "participant_name": st.session_state["participant_name"],
        "participant_team": st.session_state["participant_team"],
        "event_name": st.session_state["participant_event_name"],
    }
    session_token = st.session_state.get("participant_session_token", "")
    if session_token:
        desired["session_token"] = session_token
    for key, value in desired.items():
        if str(st.query_params.get(key, "")) != str(value):
            st.query_params[key] = value


def normalise_submission_type(mission):
    raw_type = str(mission.get("SubmissionType", "") or "").strip().upper()
    title = str(mission.get("Title", "") or "").strip().upper()
    description = str(mission.get("Description", "") or "").strip().upper()
    combined = f"{raw_type} {title} {description}"

    if "ENTERPRISE" in combined and (
        "PIPELINE" in combined or "CUSTOMER JOURNEY" in combined
    ):
        return "PIPELINE_ENTERPRISE"

    if "PIPELINE" in combined or "CUSTOMER JOURNEY" in combined:
        return "PIPELINE"

    if "HELIUM" in combined:
        return "HELIUM"

    if "KEY" in combined and "PUNCH" in combined:
        return "KEYPUNCH"

    if "CATALYST" in combined:
        return "CATALYST"

    if "NASI" in combined or "REFLECTION" in combined:
        return "NASI"

    if raw_type in ["PHOTO", "IMAGE"]:
        return "PHOTO"

    if raw_type in ["TEXT", "REFLECTION"]:
        return "TEXT"

    if raw_type in ["NONE", "NO SUBMISSION"]:
        return "NONE"

    return raw_type or "PHOTO"


def render_team_assignment_card(db):
    team = st.session_state.get("participant_team", "")
    country = st.session_state.get("participant_country", "")
    instruction = COUNTRY_LANGUAGE_PROMPTS.get(
        country or team,
        "Find your team members and gather together.",
    )
    try:
        roster = db.get_team_roster(
            st.session_state.get("participant_event_id", ""), team,
        )
    except RuntimeDatabaseError:
        roster = []
    leader = next((row for row in roster if row.get("IsLeader")), None)
    own_name = st.session_state.get("participant_name", "")
    own_record = next(
        (row for row in roster if row.get("Name") == own_name), {},
    )
    st.session_state["participant_is_leader"] = bool(own_record.get("IsLeader"))

    if str(st.session_state.get("participant_event_id", "")) == "EVT-0004":
        flags = {
            "Korea": "🇰🇷", "Japan": "🇯🇵", "Thailand": "🇹🇭",
            "Philippines": "🇵🇭", "Malaysia": "🇲🇾", "India": "🇮🇳",
        }
        flag = flags.get(country, "")
        st.markdown(
            f"""
            <div style="padding:28px;border-radius:22px;background:#082D58;color:white;text-align:center;margin-bottom:18px;">
              <div style="font-size:18px;font-weight:800;letter-spacing:.18em;">YOUR COUNTRY</div>
              <div style="font-size:92px;line-height:1.15;margin:10px 0;">{flag}</div>
              <div style="font-size:42px;font-weight:900;">{country}</div>
              <div style="font-size:21px;margin-top:18px;line-height:1.5;">
                Find everyone from your country.<br>Speak the language.<br><br>
                Once your team has assembled, choose ONE Team Leader.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
        f"""
        <div style="
            padding:24px;
            border-radius:22px;
            background:#082D58;
            color:white;
            text-align:center;
            margin-bottom:18px;
        ">
            <div style="font-size:18px;opacity:.8;">Your Team</div>
            <div style="font-size:46px;font-weight:900;margin-top:8px;">{team}</div>
            <div style="font-size:20px;margin-top:6px;">{country or 'Country team'}</div>
            <div style="font-size:18px;margin-top:12px;opacity:.9;">{instruction}</div>
        </div>
        """,
        unsafe_allow_html=True,
        )
    if roster:
        st.markdown("#### Team Members")
        for member in roster:
            icon = "⭐" if member.get("IsLeader") else "•"
            st.write(f"{icon} {member.get('Name', '')}")
    if leader:
        st.success(f"Team Leader: {leader.get('Name', '')}")
    else:
        st.info("A facilitator assigns or restores the Team Leader in Control Centre.")


def find_existing_submission(db, mission, submission_type):
    event_id = st.session_state["participant_event_id"]
    mission_id = mission["MissionID"]

    if submission_type == "NASI":
        return db.get_participant_submission(
            event_id=event_id,
            mission_id=mission_id,
            participant_name=st.session_state["participant_name"],
            session_token=st.session_state.get(
                "participant_session_token",
                "",
            ),
        )

    return db.get_team_submission(
        event_id=event_id,
        mission_id=mission_id,
        team_name=st.session_state["participant_team"],
    )


def current_team_leader(db):
    """Return the current leader from the authoritative event team roster."""
    roster = db.get_team_roster(
        st.session_state.get("participant_event_id", ""),
        st.session_state.get("participant_team", ""),
    )
    leader = next((row for row in roster if row.get("IsLeader")), None)
    leader_name = str((leader or {}).get("Name", "") or "").strip()
    participant_name = str(
        st.session_state.get("participant_name", "") or ""
    ).strip()
    is_leader = bool(leader_name and leader_name == participant_name)
    st.session_state["participant_is_leader"] = is_leader
    return is_leader, leader_name


def render_team_leader_submission_gate(db):
    """Keep EVT-0004 submission controls exclusive to the active leader."""
    try:
        session_token = st.session_state.get("participant_session_token", "")
        authorization = db.runtime.can_participant_submit(session_token)
        is_leader, leader_name = current_team_leader(db)
    except RuntimeDatabaseError:
        st.warning("Team leadership is reconnecting. Submission is temporarily locked.")
        return False
    if authorization.get("Allowed"):
        if authorization.get("Reason") in {"EVENT_OVERRIDE", "TEAM_OVERRIDE"}:
            st.warning("Emergency submission access is active. This action is audited.")
        return True
    st.info("Only your Team Leader can submit evidence for the team.")
    if leader_name:
        st.caption(f"Current Team Leader: {leader_name}")
    else:
        st.caption("No Team Leader has been selected yet.")
    return False


def render_existing_submission(existing_submission):
    status = str(existing_submission.get("Status", "PENDING")).strip().upper()
    if status == "APPROVED":
        st.success("✅ Evidence approved.")
    elif status == "REJECTED":
        st.error("Evidence rejected.")
    else:
        st.info("Evidence uploaded · Pending Review")

    submitted_at = existing_submission.get("SubmittedAt", "")
    if submitted_at:
        st.caption(f"Submitted at: {submitted_at}")

    submission_type = str(existing_submission.get("SubmissionType", "")).upper()
    metric1 = existing_submission.get("Metric1", "")
    metric2 = existing_submission.get("Metric2", "")
    metric3 = existing_submission.get("Metric3", "")
    remarks = existing_submission.get("Remarks", "")
    image_url = existing_submission.get("ImageURL", "")
    drive_file_id = existing_submission.get("DriveFileID", "")

    if submission_type == "PIPELINE":
        st.write(f"**Target:** {metric1}")
        st.write(f"**Achieved:** {metric2}")
        st.write(f"**Lost clients:** {metric3}")
    elif submission_type == "KEYPUNCH":
        st.write(f"**Highest number reached:** {metric1}")
    elif submission_type in ["HELIUM", "CATALYST"]:
        st.write(f"**Completed:** {metric1}")
    elif submission_type == "NASI" and remarks:
        st.info(remarks)
    elif remarks:
        st.info(remarks)

    display_url = get_photo_url(image_url, drive_file_id)
    if display_url and submission_type == "VIDEO":
        st.video(display_url)
    elif display_url and submission_type == "AUDIO":
        st.audio(display_url)
    elif display_url:
        try:
            st.image(display_url, width="stretch")
        except Exception:
            st.warning("Submission image could not be displayed.")


def save_structured_submission(
    db,
    mission,
    submission_type,
    metric1="",
    metric2="",
    metric3="",
    remarks="",
    image_url="",
    drive_file_id="",
):
    if str(st.session_state.get("participant_event_id", "")) == "EVT-0004":
        is_leader, leader_name = current_team_leader(db)
        if not is_leader:
            name = leader_name or "the selected Team Leader"
            st.error(
                f"Only {name} can submit evidence for this team. "
                "Refresh to update leadership."
            )
            st.stop()
        existing = db.get_team_submission(
            event_id=st.session_state["participant_event_id"],
            mission_id=mission["MissionID"],
            team_name=st.session_state["participant_team"],
        )
        if existing:
            if drive_file_id:
                try:
                    delete_evidence_file(drive_file_id)
                except Exception:
                    pass
            st.info("Evidence has already been submitted for this Experience.")
            st.stop()
    try:
        return db.save_submission(
            submission_id=str(uuid.uuid4()),
            event_id=st.session_state["participant_event_id"],
            mission_id=mission["MissionID"],
            team_name=st.session_state["participant_team"],
            participant_name=st.session_state["participant_name"],
            image_url=image_url,
            drive_file_id=drive_file_id,
            submitted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            score="",
            judged="No",
            remarks=remarks,
            submission_type=submission_type,
            metric1=metric1,
            metric2=metric2,
            metric3=metric3,
            status="PENDING",
            session_token=st.session_state.get("participant_session_token", ""),
        )
    except Exception as error:
        if drive_file_id:
            try:
                delete_evidence_file(drive_file_id)
            except Exception:
                pass
        raise RuntimeDatabaseError(upload_error_message(
            "Evidence metadata save", saved=False, retry=True, error=error,
        )) from None


def render_pipeline_form(db, mission):
    st.subheader("📊 Customer Journey Results")
    st.write("Submit your team's recorded result.")

    target = st.number_input(
        "Target",
        min_value=1,
        value=1,
        step=1,
        key=f"pipeline_target_{mission['MissionID']}",
    )
    achieved = st.number_input(
        "Achieved",
        min_value=0,
        value=0,
        step=1,
        key=f"pipeline_achieved_{mission['MissionID']}",
    )
    lost = st.number_input(
        "Lost Clients",
        min_value=0,
        value=0,
        step=1,
        key=f"pipeline_lost_{mission['MissionID']}",
    )

    net_achievement = max(0, achieved - lost)
    calculated_score = (net_achievement / target) * 100
    st.caption(f"Calculated performance: {calculated_score:.1f}%")

    if st.button(
        "📤 Submit Pipeline Results",
        width="stretch",
        key=f"submit_pipeline_{mission['MissionID']}",
    ):
        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="PIPELINE",
            metric1=target,
            metric2=achieved,
            metric3=lost,
            remarks=(
                f"Net achievement: {net_achievement}; "
                f"Calculated performance: {calculated_score:.1f}%"
            ),
        )
        st.success("✅ Pipeline results submitted.")
        st.balloons()
        st.rerun()


def render_helium_form(db, mission):
    st.subheader("🪄 Taking Ownership Together")
    completed = st.radio(
        "Did your team complete the Helium Stick challenge?",
        ["Yes", "No"],
        horizontal=True,
        key=f"helium_completed_{mission['MissionID']}",
    )

    if st.button(
        "📤 Submit Helium Stick Result",
        width="stretch",
        key=f"submit_helium_{mission['MissionID']}",
    ):
        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="HELIUM",
            metric1=completed.upper(),
        )
        st.success("✅ Helium Stick result submitted.")
        st.balloons()
        st.rerun()


def render_keypunch_form(db, mission):
    st.subheader("⚡ Key Punch")
    st.write("Submit your team's official 60-second attempt.")

    highest_number = st.number_input(
        "Highest Number Reached Within 60 Seconds",
        min_value=0,
        max_value=30,
        value=0,
        step=1,
        key=f"keypunch_highest_{mission['MissionID']}",
    )
    calculated_score = (highest_number / 30) * 100
    st.caption(f"Calculated performance: {calculated_score:.1f}%")

    if st.button(
        "📤 Submit Key Punch Result",
        width="stretch",
        key=f"submit_keypunch_{mission['MissionID']}",
    ):
        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="KEYPUNCH",
            metric1=highest_number,
            remarks=f"Calculated performance: {calculated_score:.1f}%",
        )
        st.success("✅ Key Punch result submitted.")
        st.balloons()
        st.rerun()


def render_catalyst_form(db, mission):
    st.subheader("⚙️ Creating Enterprise Success")
    completed = st.radio(
        "Did your section complete?",
        ["Yes", "No"],
        horizontal=True,
        key=f"catalyst_completed_{mission['MissionID']}",
    )
    uploaded_image = st.file_uploader(
        "Optional Final Structure Photo",
        type=["jpg", "jpeg", "png"],
        key=f"catalyst_photo_{mission['MissionID']}",
    )

    if uploaded_image is not None:
        st.image(uploaded_image, width="stretch")

    if st.button(
        "📤 Submit Catalyst Status",
        width="stretch",
        key=f"submit_catalyst_{mission['MissionID']}",
    ):
        image_url = ""
        drive_file_id = ""

        if uploaded_image is not None:
            try:
                uploaded = upload_photo(
                    event_id=st.session_state["participant_event_id"],
                    mission_id=mission["MissionID"],
                    team_name=st.session_state["participant_team"],
                    participant_name=st.session_state["participant_name"],
                    uploaded_file=uploaded_image,
                )
            except (RuntimeDatabaseError, ValueError) as error:
                st.error(upload_error_message(
                    "Photo upload", saved=False, retry=True, error=error,
                ))
                st.stop()
            image_url = uploaded.get("url", "")
            drive_file_id = uploaded.get("file_id", "")

        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="CATALYST",
            metric1=completed.upper(),
            image_url=image_url,
            drive_file_id=drive_file_id,
        )
        st.success("✅ Catalyst status submitted.")
        st.balloons()
        st.rerun()


def render_nasi_form(db, mission):
    st.subheader("📝 NASI")
    st.write("Submit your individual learning reflection.")

    new_ideas = st.text_area(
        "N — New Ideas",
        placeholder="What new ideas did you discover?",
        key=f"nasi_n_{mission['MissionID']}",
    )
    areas = st.text_area(
        "A — Areas for Improvement",
        placeholder="What should be improved?",
        key=f"nasi_a_{mission['MissionID']}",
    )
    strengths = st.text_area(
        "S — Strengths",
        placeholder="What strengths should be protected and continued?",
        key=f"nasi_s_{mission['MissionID']}",
    )
    implementation = st.text_area(
        "I — Implementation",
        placeholder="What is one action you will implement?",
        key=f"nasi_i_{mission['MissionID']}",
    )

    if st.button(
        "📤 Submit NASI",
        width="stretch",
        key=f"submit_nasi_{mission['MissionID']}",
    ):
        if not any(
            [
                new_ideas.strip(),
                areas.strip(),
                strengths.strip(),
                implementation.strip(),
            ]
        ):
            st.warning("Please enter at least one reflection before submitting.")
            st.stop()

        remarks = (
            f"N - New Ideas:\n{new_ideas.strip() or '-'}\n\n"
            f"A - Areas for Improvement:\n{areas.strip() or '-'}\n\n"
            f"S - Strengths:\n{strengths.strip() or '-'}\n\n"
            f"I - Implementation:\n{implementation.strip() or '-'}"
        )
        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="NASI",
            remarks=remarks,
        )
        st.success("✅ NASI submitted.")
        st.balloons()
        st.rerun()


def render_text_form(db, mission):
    st.subheader("📝 Team Response")
    response = st.text_area(
        "Submit your team's response",
        placeholder="Type your team's response here.",
        key=f"text_response_{mission['MissionID']}",
    )

    if st.button(
        "📤 Submit Response",
        width="stretch",
        key=f"submit_text_{mission['MissionID']}",
    ):
        if not response.strip():
            st.warning("Please enter a response before submitting.")
            st.stop()

        save_structured_submission(
            db=db,
            mission=mission,
            submission_type="TEXT",
            remarks=response.strip(),
        )
        st.success("✅ Response submitted.")
        st.balloons()
        st.rerun()


def render_photo_form(db, mission):
    st.subheader("📸 Photo Evidence")
    uploaded_image = st.file_uploader(
        "Choose Photo",
        type=["jpg", "jpeg", "png"],
        key=f"photo_upload_{mission['MissionID']}",
    )

    if uploaded_image is not None:
        st.image(uploaded_image, width="stretch")

        if st.button(
            "📤 Submit Evidence",
            width="stretch",
            key=f"submit_photo_{mission['MissionID']}",
        ):
            with st.spinner("Submitting experience..."):
                try:
                    uploaded = upload_photo(
                        event_id=st.session_state["participant_event_id"],
                        mission_id=mission["MissionID"],
                        team_name=st.session_state["participant_team"],
                        participant_name=st.session_state["participant_name"],
                        uploaded_file=uploaded_image,
                    )
                except (RuntimeDatabaseError, ValueError) as error:
                    st.error(upload_error_message(
                        "Photo upload", saved=False, retry=True, error=error,
                    ))
                    st.stop()
                try:
                    save_structured_submission(
                        db=db, mission=mission, submission_type="PHOTO",
                        image_url=uploaded.get("url", ""),
                        drive_file_id=uploaded.get("file_id", ""),
                    )
                except RuntimeDatabaseError as error:
                    st.error(str(error))
                    st.stop()

            st.success("✅ Experience submitted successfully.")
            st.balloons()
            st.rerun()


def render_media_evidence_form(db, mission, evidence_type):
    kind = str(evidence_type).strip().upper()
    is_video = kind == "VIDEO"
    icon = "🎥" if is_video else "🎙️"
    label = "Video" if is_video else "Audio"
    extensions = ["mp4", "mov", "m4v", "webm"] if is_video else [
        "mp3", "m4a", "wav", "aac", "ogg",
    ]
    st.subheader(f"{icon} {label} Evidence")
    uploaded_file = st.file_uploader(
        f"Upload {label}",
        type=extensions,
        key=f"{kind.lower()}_upload_{mission['MissionID']}",
    )
    if uploaded_file is None:
        return
    if is_video:
        st.video(uploaded_file)
    else:
        st.audio(uploaded_file)
    if st.button(
        "📤 Submit Evidence",
        width="stretch",
        key=f"submit_{kind.lower()}_{mission['MissionID']}",
    ):
        with st.spinner("Submitting evidence..."):
            try:
                uploaded = upload_evidence_file(
                    event_id=st.session_state["participant_event_id"],
                    mission_id=mission["MissionID"],
                    team_name=st.session_state["participant_team"],
                    participant_name=st.session_state["participant_name"],
                    uploaded_file=uploaded_file,
                    evidence_type=kind,
                )
            except (RuntimeDatabaseError, ValueError) as error:
                st.error(upload_error_message(
                    f"{label} upload", saved=False, retry=True, error=error,
                ))
                st.stop()
            try:
                save_structured_submission(
                    db=db, mission=mission, submission_type=kind,
                    image_url=uploaded.get("url", ""),
                    drive_file_id=uploaded.get("file_id", ""),
                )
            except RuntimeDatabaseError as error:
                st.error(str(error))
                st.stop()
        st.success("✅ Evidence submitted successfully.")
        st.rerun()


def render_multiple_evidence_form(db, mission):
    st.subheader("📎 Evidence")
    selected_type = st.radio(
        "Choose evidence type",
        ["Photo", "Video", "Text", "Audio"],
        horizontal=True,
        key=f"multiple_type_{mission['MissionID']}",
    )
    if selected_type == "Photo":
        render_photo_form(db, mission)
    elif selected_type == "Video":
        render_media_evidence_form(db, mission, "VIDEO")
    elif selected_type == "Audio":
        render_media_evidence_form(db, mission, "AUDIO")
    else:
        render_text_form(db, mission)


def render_submission_form(db, mission, submission_type):
    if submission_type == "PIPELINE":
        render_pipeline_form(db, mission)
    elif submission_type == "PIPELINE_ENTERPRISE":
        st.info(
            "The Enterprise Pipeline result will be entered once by the facilitator."
        )
    elif submission_type == "HELIUM":
        render_helium_form(db, mission)
    elif submission_type == "KEYPUNCH":
        render_keypunch_form(db, mission)
    elif submission_type == "CATALYST":
        render_catalyst_form(db, mission)
    elif submission_type == "NASI":
        render_nasi_form(db, mission)
    elif submission_type == "TEXT":
        render_text_form(db, mission)
    elif submission_type == "VIDEO":
        render_media_evidence_form(db, mission, "VIDEO")
    elif submission_type == "AUDIO":
        render_media_evidence_form(db, mission, "AUDIO")
    elif submission_type == "MULTIPLE":
        render_multiple_evidence_form(db, mission)
    elif submission_type == "QR":
        render_qr_form(db, mission)
    elif submission_type == "GPS":
        render_gps_form(db, mission)
    elif submission_type == "NONE":
        st.info("No participant submission is required for this experience.")
    else:
        render_photo_form(db, mission)


def render_qr_form(db, mission):
    st.subheader("🔳 QR Validation")
    submitted_value = st.text_input(
        "QR Code Value",
        help="Scan the checkpoint QR code, or enter its value.",
    )
    if st.button("Validate QR and Submit", width="stretch"):
        expected = str(mission.get("QRCodeValue", "") or "").strip()
        rule = str(mission.get("QRValidationRule", "Exact match") or "").lower()
        candidate = submitted_value.strip()
        valid = (
            candidate.casefold() == expected.casefold()
            if "case" in rule and "insensitive" in rule
            else candidate == expected
        )
        if not expected:
            st.error("This experience has no QR validation value configured.")
        elif not valid:
            st.error("That QR code is not valid for this experience.")
        else:
            save_structured_submission(
                db, mission, "QR", metric1=candidate,
                remarks="QR checkpoint validated.",
            )
            st.success("QR checkpoint validated.")
            st.rerun()


def _distance_metres(latitude1, longitude1, latitude2, longitude2):
    radius = 6371000.0
    lat1, lat2 = math.radians(latitude1), math.radians(latitude2)
    dlat = math.radians(latitude2 - latitude1)
    dlon = math.radians(longitude2 - longitude1)
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def render_gps_form(db, mission):
    st.subheader("📍 GPS Validation")
    st.caption(str(mission.get("LocationDescription", "") or ""))
    st.info("Location is requested only when you press the button below.")
    location = team_geolocation(
        interval_seconds=20,
        key=f"mission_gps_{mission.get('EventID')}_{mission.get('MissionID')}",
    )
    if location:
        try:
            latitude = float(location.get("latitude"))
            longitude = float(location.get("longitude"))
            target_latitude = float(mission.get("Latitude"))
            target_longitude = float(mission.get("Longitude"))
            radius = float(mission.get("GeofenceRadius", 50) or 50)
            distance = _distance_metres(
                latitude, longitude, target_latitude, target_longitude,
            )
        except (TypeError, ValueError):
            st.error("The configured checkpoint location is incomplete.")
            return
        st.caption(f"Distance to checkpoint: {distance:.0f} metres")
        if distance <= radius:
            if st.button("Confirm Arrival and Submit", width="stretch"):
                save_structured_submission(
                    db, mission, "GPS",
                    metric1=str(latitude), metric2=str(longitude),
                    metric3=f"{distance:.1f}",
                    remarks="GPS checkpoint validated.",
                )
                st.success("Checkpoint arrival confirmed.")
                st.rerun()
        else:
            st.warning(f"Move within {radius:.0f} metres of the checkpoint.")


def render_mission_content(mission):
    story = str(mission.get("Story", "") or "").strip()
    transmission = str(
        mission.get("Transmission", "") or mission.get("Clue", "") or ""
    ).strip()
    character_name = str(
        mission.get("CharacterSource", "") or "Headquarters"
    ).strip()
    portrait_reference = str(
        mission.get("CharacterPortraitURL", "") or ""
    ).strip()
    instructions = str(
        mission.get("ParticipantInstructions", "")
        or mission.get("Description", "")
        or ""
    ).strip()
    video_url = str(mission.get("VideoURL", "") or "").strip()
    image_url = str(mission.get("ImageURL", "") or "").strip()
    reference_image_url = str(
        mission.get("ReferenceImageURL", "") or ""
    ).strip()
    document_url = str(mission.get("DocumentURL", "") or "").strip()

    if transmission:
        st.markdown("#### Transmission")
        if not render_character_card(
            character_name,
            portrait_reference,
            transmission,
        ):
            st.markdown(f"**{character_name}**")
            st.info(transmission)

    if story:
        st.markdown("#### Narrative")
        st.markdown(story)

    display_video_url = get_mission_media_url(video_url)
    display_image_url = get_mission_media_url(image_url)
    display_reference_image_url = get_mission_media_url(reference_image_url)
    display_document_url = get_mission_media_url(document_url)

    if display_video_url:
        try:
            st.video(display_video_url)
        except Exception:
            st.warning("The experience video could not be displayed.")
            st.link_button(
                "▶️ Open Experience Video",
                display_video_url,
                width="stretch",
            )

    if display_image_url:
        try:
            st.image(display_image_url, width="stretch")
        except Exception:
            st.warning("The experience image could not be displayed.")

    if (
        (
            str(mission.get("MissionType", "") or "").strip().casefold()
            == "observe"
            or _is_bayu_event()
        )
        and display_reference_image_url
    ):
        st.markdown("#### Reference Image")
        try:
            cropped_image = cropped_reference_image(
                reference_image_url,
                mission,
            )
            st.image(
                cropped_image or display_reference_image_url,
                width="stretch",
            )
            st.caption("Tap the image to enlarge where supported.")
        except Exception:
            st.warning("The reference image could not be displayed.")

    if instructions:
        st.markdown("#### Experience")
        st.info(instructions)

    evidence = str(mission.get("SubmissionType", "") or "").strip().title()
    evidence_instructions = str(
        mission.get("EvidenceInstructions", "") or ""
    ).strip()
    if yes_no_value(mission.get("EvidenceRequired", "Yes")):
        st.markdown("#### Evidence")
        st.write(f"**{evidence or 'Evidence'}**")
        if evidence_instructions:
            st.caption(evidence_instructions)


EVA_PORTRAIT_REFERENCE = (
    "supabase://exos-mission-media/characters/eva/portrait"
)

EVA_EXPEDITION_OPENING_TRANSMISSION = """CONNECTION ESTABLISHED

EVA ONLINE

Commander...

I am EVA.

Expedition Virtual Assistant.

My purpose is to analyse recovered intelligence, verify discoveries and support your expedition.

I cannot complete this mission for you.

Only your team can.

Every verified discovery strengthens our understanding of The Labyrinth.

Recover intelligence.
Earn Intelligence Credits.

Return safely.

Mission timer is now active.

Good luck, Commander."""


def participant_ai_identity(ai, event_id):
    """Resolve the participant companion without changing stored team AI data."""
    identity = dict(ai or {})
    if str(event_id or "").strip() == "EVT-0004":
        identity.update(
            {
                "Name": "EVA",
                "Role": "Expedition Virtual Assistant",
                "Greeting": EVA_EXPEDITION_OPENING_TRANSMISSION,
                "PortraitURL": EVA_PORTRAIT_REFERENCE,
            }
        )
    return identity


def apply_participant_ai_identity(ai, event_id):
    """Store the event-scoped companion identity in participant session state."""
    identity = participant_ai_identity(ai, event_id)
    st.session_state["ai_name"] = identity.get("Name", "Atlas")
    st.session_state["ai_personality"] = identity.get("Personality", "")
    st.session_state["ai_greeting"] = identity.get("Greeting", "")


def bayu_ai_portrait_reference(db=None):
    """Return the one stored hologram used by EVT-0004 AI companions."""
    if db is not None:
        try:
            portrait = str(db.get_character_portrait("EVA") or "").strip()
            if portrait:
                return portrait
        except Exception:
            pass
    return EVA_PORTRAIT_REFERENCE


def render_ai_response_after_submission(
    mission,
    submission=None,
    ai_portrait_reference="",
):
    """Show the authored character response only after evidence is submitted."""
    if submission is not None and str(
        submission.get("Status", "PENDING")
    ).strip().upper() != "APPROVED":
        return False
    response = str(
        (mission or {}).get("MissionCompleteMessage", "") or ""
    ).strip()
    if not response:
        return False

    character_name = str(
        (mission or {}).get("CharacterSource", "") or "Headquarters"
    ).strip()
    portrait_reference = str(
        ai_portrait_reference
        or (mission or {}).get("CharacterPortraitURL", "")
        or ""
    ).strip()
    st.markdown("#### AI Response")
    if render_character_card(character_name, portrait_reference, response):
        return True

    st.markdown(f"**{character_name}**")
    st.success(response)
    return True

    card1, card2 = st.columns(2)
    with card1:
        credits = mission.get("CreditValue", mission.get("Points", 0))
        st.metric("Credits", _credit_number(credits))
    with card2:
        minutes = int(float(mission.get("TimeLimitMinutes", 0) or 0))
        st.metric("Time Remaining", f"{minutes}:00" if minutes else "No limit")

    hints = [
        str(mission.get(name, "") or "").strip()
        for name in ("Hint1", "Hint2", "Hint3")
    ]
    hints = [hint for hint in hints if hint]
    if hints:
        with st.expander("💡 Hint"):
            st.write(hints[0])
            penalty = mission.get("HintCreditPenalty", mission.get("HintPenalty", 0))
            if penalty:
                st.caption(f"Hint penalty: {_credit_number(penalty)} credits")

    if mission_ai_help_enabled(mission):
        st.info("🤖 AI Companion is enabled for this experience.")

    if display_document_url:
        st.link_button(
            "📄 Open Experience Document",
            display_document_url,
            width="stretch",
        )


def _credit_number(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def yes_no_value(value):
    return str(value or "").strip().upper() not in {"", "NO", "FALSE", "0", "OFF"}


def render_marketplace(session_token):
    st.subheader("🛒 Team Marketplace")
    try:
        marketplace = get_runtime_database().get_team_wallet(session_token)
    except RuntimeDatabaseError as error:
        st.warning("The marketplace is reconnecting. Please try again shortly.")
        st.caption(str(error))
        return

    if not marketplace.get("Enabled"):
        st.info("The facilitator has not opened the marketplace yet.")
        return

    wallet = marketplace.get("Wallet", {}) or {}
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Credits Earned", _credit_number(wallet.get("EarnedCredits")))
    with col2:
        st.metric("Credits Spent", _credit_number(wallet.get("SpentCredits")))
    with col3:
        st.metric("Available Balance", _credit_number(wallet.get("Balance")))

    items = marketplace.get("Items", []) or []
    if not items:
        st.info("No marketplace items are available yet.")
    for item in items:
        item_id = str(item.get("ItemID", ""))
        cost = float(item.get("CreditCost", 0) or 0)
        stock = item.get("StockQuantity")
        stock_text = "Unlimited" if stock is None else str(stock)
        with st.container(border=True):
            st.markdown(f"#### {item.get('ItemName', item_id)}")
            if item.get("Description"):
                st.write(item.get("Description"))
            st.caption(
                f"Cost: {_credit_number(cost)} credits · Stock: {stock_text}"
            )
            maximum = max(int(stock), 1) if stock is not None else 20
            quantity = st.number_input(
                "Quantity",
                min_value=1,
                max_value=maximum,
                value=1,
                step=1,
                key=f"marketplace_quantity_{item_id}",
            )
            total_cost = cost * int(quantity)
            if st.button(
                f"Spend {_credit_number(total_cost)} Credits",
                key=f"marketplace_buy_{item_id}",
                width="stretch",
            ):
                try:
                    purchase = get_runtime_database().purchase_marketplace_item(
                        session_token=session_token,
                        item_id=item_id,
                        quantity=int(quantity),
                    )
                except RuntimeDatabaseError as error:
                    st.error(str(error))
                else:
                    st.success(
                        f"Purchased {purchase.get('Quantity', quantity)} × "
                        f"{purchase.get('ItemName', item.get('ItemName', 'item'))}. "
                        f"Balance: {_credit_number(purchase.get('Balance', 0))} credits."
                    )
                    st.rerun()

    purchases = marketplace.get("Purchases", []) or []
    if purchases:
        with st.expander("Team Purchases"):
            st.dataframe(purchases, width="stretch", hide_index=True)


def mission_ai_help_enabled(mission):
    value = str(
        (mission or {}).get("AIHelpEnabled", "Yes") or "Yes"
    ).strip().upper()
    return value not in {"NO", "FALSE", "0", "OFF"}


CHARACTER_ROLES = {
    "EVA": "Expedition Virtual Assistant",
    "Headquarters": "Command Centre",
    "Captain Amelia Ross": "Expedition Alpha",
    "Dr Marcus Hale": "Expedition Bravo",
    "Unknown Transmission": "Unidentified Signal",
}


def render_character_card(character_name, portrait_reference, message="", role=""):
    """Render a portrait-led hologram card, or return False for text fallback."""
    portrait_url = get_mission_media_url(portrait_reference)
    if not portrait_url:
        return False
    safe_name = html.escape(str(character_name or "AI Companion"))
    safe_url = html.escape(str(portrait_url), quote=True)
    safe_message = html.escape(str(message or "")).replace("\n", "<br>")
    safe_role = html.escape(str(role or CHARACTER_ROLES.get(character_name, "")))
    message_html = (
        f'<div class="exos-character-message">{safe_message}</div>'
        if safe_message
        else '<div class="exos-character-status">Secure contact channel online</div>'
    )
    st.markdown(
        f"""
        <style>
        .exos-character-card{{
          position:relative;overflow:hidden;margin:12px 0 18px;padding:16px;
          border:1px solid rgba(85,220,255,.55);border-radius:20px;
          background:linear-gradient(145deg,rgba(5,20,43,.98),rgba(7,69,104,.94));
          box-shadow:0 0 28px rgba(53,201,255,.2),inset 0 0 25px rgba(53,201,255,.08);
          color:#f7fcff;
        }}
        .exos-character-card:after{{
          content:"";position:absolute;inset:0;pointer-events:none;opacity:.13;
          background:repeating-linear-gradient(0deg,transparent 0 4px,#65dcff 5px);
        }}
        .exos-character-layout{{display:grid;grid-template-columns:minmax(130px,42%) 1fr;gap:16px;align-items:center;position:relative;z-index:1}}
        .exos-character-portrait{{width:100%;height:230px;object-fit:contain;border-radius:14px;background:radial-gradient(circle,#165d7d 0,#071a32 70%)}}
        .exos-character-name{{font-size:1.3rem;font-weight:900;letter-spacing:.04em;color:#80e8ff}}
        .exos-character-status{{margin-top:8px;text-transform:uppercase;font-size:.72rem;letter-spacing:.14em;color:#b9ddea}}
        .exos-character-message{{margin-top:10px;font-size:1rem;line-height:1.55;color:#fff}}
        @media(max-width:640px){{.exos-character-layout{{grid-template-columns:1fr}}.exos-character-portrait{{height:260px}}}}
        </style>
        <div class="exos-character-card">
          <div class="exos-character-layout">
            <img class="exos-character-portrait" src="{safe_url}" alt="{safe_name}">
            <div><div class="exos-character-name">{safe_name}</div>
            <div class="exos-character-status">{safe_role}</div>{message_html}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return True


def render_ai_facilitator(db, mission, runtime_session):
    facilitator_name = st.session_state["ai_name"]
    character_name = str(
        (mission or {}).get("CharacterSource", "") or facilitator_name
    ).strip()
    if character_name.casefold() == "none":
        character_name = facilitator_name
    portrait_reference = str(
        (mission or {}).get("CharacterPortraitURL", "") or ""
    ).strip()
    if _is_bayu_event():
        facilitator_name = "EVA"
        character_name = "EVA"
        portrait_reference = bayu_ai_portrait_reference(db)
    session_token = st.session_state.get("participant_session_token", "")
    mission_id = str((mission or {}).get("MissionID", "")).strip()

    st.divider()
    if not render_character_card(character_name, portrait_reference):
        st.subheader(f"🤖 {character_name}")

    if st.session_state["ai_greeting"]:
        st.info(st.session_state["ai_greeting"])

    if not mission or not mission_id:
        st.caption(
            f"{character_name} will be ready when the facilitator launches an experience."
        )
        return

    conversation_state = {
        "HintLevel": 0,
        "Messages": [],
    }
    try:
        if runtime_session:
            conversation_state = db.get_ai_conversation(
                session_token,
                mission_id,
            )
            conversation = list(
                conversation_state.get("Messages", []) or []
            )
        else:
            conversation = db.get_conversation(
                st.session_state["participant_event_id"],
                st.session_state["participant_team"],
            )
    except RuntimeDatabaseError as error:
        st.warning("AI Facilitator is reconnecting. Please try again shortly.")
        st.caption(str(error))
        conversation = []

    for row in conversation:
        role = (
            "user"
            if str(row.get("Role", "")).lower() == "user"
            else "assistant"
        )
        if role == "assistant" and render_character_card(
            character_name,
            portrait_reference,
            row.get("Message", ""),
        ):
            continue
        with st.chat_message(role):
            st.markdown(row.get("Message", ""))

    if runtime_session and mission_ai_help_enabled(mission):
        hint_level = max(
            0,
            min(int(conversation_state.get("HintLevel", 0) or 0), 3),
        )
        st.markdown("#### Need a Hint?")
        st.caption(
            "Hints unlock in three steps: a nudge, a stronger hint, then a method hint."
        )

        hint_buttons = {
            0: "🧭 Get a Nudge",
            1: "💡 Get a Stronger Hint",
            2: "🛠 Get a Method Hint",
        }
        if hint_level < 3:
            if st.button(
                hint_buttons[hint_level],
                width="stretch",
                key=f"ai_hint_{mission_id}_{hint_level}",
            ):
                try:
                    hint = db.advance_ai_hint(session_token, mission_id)
                    if not hint.get("Enabled", True):
                        st.warning("AI help is disabled for this experience.")
                        return

                    released_level = int(hint.get("Level", 0) or 0)
                    hint_text = str(hint.get("HintText", "")).strip()
                    try:
                        reply = ask_facilitator(
                            facilitator_name=facilitator_name,
                            personality=st.session_state["ai_personality"],
                            greeting=st.session_state["ai_greeting"],
                            mission=mission,
                            user_message=(
                                "Our team requested the approved controlled hint. "
                                "Coach us using only that hint."
                            ),
                            assistance_mode="HINT",
                            allowed_hint=hint_text,
                        )
                    except Exception:
                        reply = (
                            f"**{hint.get('Label', 'Hint')}** — {hint_text}"
                        )

                    db.save_conversation(
                        event_id=st.session_state["participant_event_id"],
                        team=st.session_state["participant_team"],
                        ai=facilitator_name,
                        role="Assistant",
                        message=reply,
                        timestamp=datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        session_token=session_token,
                        mission_id=mission_id,
                        hint_level=released_level,
                    )
                    st.rerun()
                except RuntimeDatabaseError as error:
                    st.error("The hint could not be released. Please try again.")
                    st.caption(str(error))
        else:
            st.caption("All three controlled hint levels have been released.")
    elif not mission_ai_help_enabled(mission):
        st.caption("AI help is disabled for this experience.")

    prompt = st.chat_input(f"Ask {character_name}...")
    if not prompt:
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        db.save_conversation(
            event_id=st.session_state["participant_event_id"],
            team=st.session_state["participant_team"],
            ai=facilitator_name,
            role="User",
            message=prompt,
            timestamp=timestamp,
            session_token=session_token if runtime_session else "",
            mission_id=mission_id,
            hint_level=0,
        )

        reply = ask_facilitator(
            facilitator_name=facilitator_name,
            personality=st.session_state["ai_personality"],
            greeting=st.session_state["ai_greeting"],
            mission=mission,
            user_message=prompt,
            assistance_mode="COACH",
        )
        db.save_conversation(
            event_id=st.session_state["participant_event_id"],
            team=st.session_state["participant_team"],
            ai=facilitator_name,
            role="Assistant",
            message=reply,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            session_token=session_token if runtime_session else "",
            mission_id=mission_id,
            hint_level=0,
        )
        st.rerun()
    except RuntimeDatabaseError as error:
        st.error("AI Facilitator could not save the conversation. Try again.")
        st.caption(str(error))
    except Exception as error:
        st.error("AI Facilitator is temporarily unavailable. Try again shortly.")
        st.caption(str(error))


def _road_hunt_migration_missing(error):
    message = str(error)
    return "PGRST202" in message or "exos_road_hunt_state" in message


def _road_hunt_team_missions_missing(error):
    message = str(error)
    return "PGRST202" in message or "exos_road_hunt_missions" in message


def render_road_hunt_mission_hub(session_token):
    """Return the mission selected from this team's reached checkpoints."""
    runtime = get_runtime_database()
    try:
        state = runtime.get_road_hunt_unlocked_missions(session_token)
    except RuntimeDatabaseError as error:
        if _road_hunt_team_missions_missing(error):
            return None, False
        st.caption("🟠 Team experiences are reconnecting…")
        return None, True

    if not state.get("Enabled"):
        return None, False

    available = state.get("AvailableMissions", []) or []
    total = int(state.get("TotalMissions", 0) or 0)
    unlocked = int(state.get("UnlockedMissions", 0) or 0)
    submitted = int(state.get("SubmittedMissions", 0) or 0)

    st.divider()
    st.subheader("🧭 Your Team's Road Hunt")
    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("Route Experiences", total)
    metric2.metric("Unlocked", unlocked)
    metric3.metric("Submitted", submitted)

    next_stop = state.get("NextStop", {}) or {}
    if next_stop:
        next_name = str(next_stop.get("StopName", "Next checkpoint"))
        next_instruction = str(next_stop.get("Instructions", "") or "").strip()
        st.info(f"Next checkpoint: {next_name}")
        if next_instruction:
            st.caption(next_instruction)
    elif total:
        st.success("All route checkpoints have been reached.")

    if not available:
        st.warning(
            "No route mission is unlocked yet. Reach the next checkpoint with "
            "your navigator GPS active, or ask a facilitator to confirm arrival."
        )
        return None, True

    option_map = {}
    for row in available:
        mission = row.get("Mission", {}) or {}
        mission_id = str(row.get("MissionID", "") or mission.get("MissionID", ""))
        title = str(mission.get("Title", mission_id) or mission_id)
        stop_name = str(row.get("StopName", "Checkpoint"))
        icon = "✅" if row.get("Submitted") else "🎯"
        label = f"{icon} {mission_id} · {title} — {stop_name}"
        option_map[label] = row

    selected_label = st.selectbox(
        "Available Team Experience",
        list(option_map),
        key=(
            f"road_hunt_mission_{state.get('EventID', '')}_"
            f"{state.get('TeamName', '')}"
        ),
    )
    selected = option_map[selected_label]
    mission = dict(selected.get("Mission", {}) or {})
    mission["MissionID"] = str(
        selected.get("MissionID", mission.get("MissionID", ""))
    )
    mission["_RoadHuntStop"] = {
        "StopID": selected.get("StopID", ""),
        "StopName": selected.get("StopName", ""),
        "StopPosition": selected.get("StopPosition", 0),
    }
    st.caption(f"Unlocked at: {selected.get('StopName', 'checkpoint')}")
    return mission, True


def render_road_hunt_navigator(session_token):
    """Render the optional navigator-only GPS control for Road Hunt events."""
    runtime = get_runtime_database()
    try:
        state = runtime.get_road_hunt_participant_state(session_token)
    except RuntimeDatabaseError as error:
        if _road_hunt_migration_missing(error):
            return
        st.caption("🟠 Road Hunt GPS is reconnecting…")
        return

    if not state.get("Enabled"):
        return

    event_id = str(state.get("EventID", "")).strip()
    team_name = str(state.get("TeamName", "")).strip()
    interval_seconds = int(
        state.get("LocationIntervalSeconds", 20) or 20
    )
    consent_key = f"road_hunt_consent_{event_id}_{team_name}"

    st.divider()
    with st.expander(
        "📍 Road Hunt Navigator",
        expanded=bool(state.get("IsNavigator")),
    ):
        st.info(
            "Use one nominated navigator phone per team. Keep EXOS open, "
            "the screen awake, and the phone charging."
        )
        consent = st.checkbox(
            "I consent to sharing this phone's location with the event "
            "facilitators during this Road Hunt. I can stop GPS at any time.",
            key=consent_key,
        )

        if not state.get("HasNavigator"):
            if st.button(
                "Claim Team Navigator Role",
                width="stretch",
                disabled=not consent,
                key=f"road_hunt_claim_{event_id}_{team_name}",
            ):
                try:
                    result = runtime.claim_team_tracker(session_token)
                except RuntimeDatabaseError as error:
                    st.error("Navigator role could not be claimed. Try again.")
                    st.caption(str(error))
                else:
                    if result.get("Claimed"):
                        st.success("This phone is now your team's navigator.")
                        st.rerun()
                    else:
                        st.warning(
                            "Another teammate has already claimed the navigator role."
                        )
            return

        if not state.get("IsNavigator"):
            st.success(
                "Your team already has a navigator phone. Keep using this "
                "phone for missions and submissions."
            )
            return

        st.success("This is the nominated navigator phone for your team.")
        if not consent:
            st.warning("Confirm location consent to start GPS.")
            return

        location = team_geolocation(
            interval_seconds=interval_seconds,
            key=f"road_hunt_gps_{event_id}_{team_name}",
        )
        if location:
            signature = str(location.get("captured_at", ""))
            last_key = f"road_hunt_last_location_{event_id}_{team_name}"
            if signature and signature != st.session_state.get(last_key):
                try:
                    accepted = runtime.submit_team_location(
                        session_token=session_token,
                        latitude=location.get("latitude"),
                        longitude=location.get("longitude"),
                        accuracy_meters=location.get("accuracy_meters"),
                        heading_degrees=location.get("heading_degrees"),
                        speed_mps=location.get("speed_mps"),
                        captured_at=location.get("captured_at"),
                    )
                except (RuntimeDatabaseError, TypeError, ValueError) as error:
                    st.error("This GPS reading could not be saved. GPS will retry.")
                    st.caption(str(error))
                else:
                    st.session_state[last_key] = signature
                    accuracy = accepted.get("AccuracyMeters")
                    accuracy_text = (
                        f" · accuracy ±{float(accuracy):.0f} m"
                        if accuracy not in (None, "")
                        else ""
                    )
                    st.caption(
                        f"Latest team location received{accuracy_text}."
                    )
                    state["Arrivals"] = accepted.get(
                        "Arrivals",
                        state.get("Arrivals", []),
                    )

        stops = state.get("Stops", []) or []
        arrivals = state.get("Arrivals", []) or []
        arrived_ids = {
            str(row.get("StopID", ""))
            for row in arrivals
        }
        if stops:
            st.markdown("#### Route Progress")
            for stop in stops:
                stop_id = str(stop.get("StopID", ""))
                icon = "✅" if stop_id in arrived_ids else "📍"
                st.write(
                    f"{icon} {stop.get('Position', '')}. "
                    f"{stop.get('StopName', stop_id)}"
                )
        if arrivals:
            st.caption(f"{len(arrivals)} route stop(s) reached.")


EVA_LABYRINTH_BRIEFING = """Commander...

Access to The Labyrinth has been granted.

Seventeen intelligence signals are now active across the island.

Your expedition may complete them in any order.

Every verified discovery earns Intelligence Credits.

Collect as many Intelligence Credits as possible before 12:30 PM.

Your Intelligence Credits will determine the resources available to your team during the afternoon operation.

The Labyrinth is now open."""


def _is_bayu_event():
    return str(st.session_state.get("participant_event_id", "")) == "EVT-0004"


def render_programme_activity(stage):
    """Render only participant-facing copy saved on this event activity."""
    stage = dict(stage or {})
    details = activity_details(stage)
    title = str(stage.get("StageName", "Activity") or "Activity").strip()
    narrative = details["ParticipantNarrative"].strip()
    task = details["ParticipantTask"].strip()
    evidence = details["EvidenceRequirement"].strip()

    st.markdown(f"## {title}")
    if narrative:
        st.markdown("#### Narrative")
        st.info(narrative)
    if task:
        st.markdown("#### Task")
        st.success(task)
    if details["EvidenceRequired"] or evidence:
        st.markdown("#### Evidence")
        st.write(f"**{evidence or 'Evidence required.'}**")
    if details["Credits"]:
        st.metric("Credits", details["Credits"])


def render_mission_ai_briefing(db):
    portrait = bayu_ai_portrait_reference(db)
    st.markdown("## Mission AI Briefing")
    if not render_character_card(
        "EVA", portrait, EVA_LABYRINTH_BRIEFING,
        role="Expedition Virtual Assistant",
    ):
        st.markdown("### EVA")
        st.caption("Expedition Virtual Assistant")
        st.info(EVA_LABYRINTH_BRIEFING)
    if st.button("ENTER THE LABYRINTH", type="primary", width="stretch"):
        st.session_state["bayu_board_open"] = True
        st.rerun()


def bayu_morning_experiences(db):
    missions = db.get_event_missions("EVT-0004")
    morning = []
    for mission in missions:
        mission_id = str(mission.get("MissionID", "")).strip().upper()
        title = str(mission.get("Title", "")).strip()
        try:
            order = int(float(mission.get("DisplayOrder", 999) or 999))
        except (TypeError, ValueError):
            order = 999
        if order == 18 or mission_id == "LAB18" or "KING" in title.upper():
            continue
        morning.append(mission)
    return morning


def active_experience_set_missions(db, event_id, experience_set):
    if str(event_id) == "EVT-0004" and "labyrinth" in str(experience_set).casefold():
        source = bayu_morning_experiences(db)
    else:
        source = db.get_event_missions(event_id)
    hidden = {"INACTIVE", "CLOSED", "ARCHIVED"}
    return [
        mission for mission in source
        if mission_module_name(mission).casefold()
        == str(experience_set or "").strip().casefold()
        and str(mission.get("Status", "ACTIVE") or "ACTIVE").strip().upper()
        not in hidden
    ]


def experience_set_label(value):
    return str(value or "Experience Set").replace("Operation: ", "").strip()


def render_experience_set_entry(db, event_id, experience_set, state_version=""):
    label = experience_set_label(experience_set)
    state_key = (
        f"experience_set_entered_{event_id}_"
        f"{label.casefold().replace(' ', '_')}_{state_version}"
    )
    if st.session_state.get(state_key):
        return True
    st.markdown(f"## {label}")
    portrait = bayu_ai_portrait_reference(db)
    message = f"{label} is now active. Choose Experiences in any order."
    if not render_character_card("EVA", portrait, message, role="Expedition AI Companion"):
        st.info(message)
    if st.button(
        f"ENTER {label.upper()}",
        type="primary",
        width="stretch",
        key=f"enter_experience_set_{event_id}_{label}",
    ):
        st.session_state[state_key] = True
        st.rerun()
    return False


def _bayu_submission_status(submission):
    if not submission:
        return "Available"
    status = str(submission.get("Status", "PENDING")).strip().upper()
    if status == "APPROVED":
        return "Approved"
    if status == "REJECTED":
        return "Rejected"
    return "Submitted"


def render_experience_set_board(db, event_id, experience_set):
    missions = active_experience_set_missions(db, event_id, experience_set)
    team = st.session_state.get("participant_team", "")
    submissions = {
        str(row.get("MissionID", "")): row
        for row in db.get_event_submissions(event_id)
        if str(row.get("TeamName", "")) == str(team)
    }
    selected_id = st.session_state.get("bayu_selected_experience", "")
    if selected_id:
        selected = next(
            (row for row in missions if str(row.get("MissionID", "")) == selected_id),
            None,
        )
        if selected:
            if st.button(f"← Back to {len(missions)} Experiences"):
                st.session_state.pop("bayu_selected_experience", None)
                st.rerun()
            st.markdown(f"## {selected.get('Title', 'Experience')}")
            render_mission_content(selected)
            credits = selected.get("CreditValue", selected.get("Points", 0))
            st.metric("Intelligence Credits", _credit_number(credits))
            existing = submissions.get(str(selected.get("MissionID", "")))
            if existing:
                status = _bayu_submission_status(existing)
                if status == "Submitted":
                    st.info("Evidence uploaded · Pending Review")
                    st_autorefresh(
                        interval=5000,
                        key=f"bayu_pending_review_{selected.get('MissionID', '')}",
                    )
                elif status == "Approved":
                    st.success(f"Approved · +{_credit_number(credits)} Intelligence Credits")
                    render_ai_response_after_submission(
                        selected,
                        existing,
                        ai_portrait_reference=bayu_ai_portrait_reference(db),
                    )
                else:
                    st.error("Evidence rejected. Your Team Leader may resubmit when enabled.")
                return
            if render_team_leader_submission_gate(db):
                render_submission_form(
                    db,
                    selected,
                    normalise_submission_type(selected),
                )
            return

    label = experience_set_label(experience_set)
    st.markdown(f"## {label}")
    if str(event_id) == "EVT-0004" and "labyrinth" in label.casefold():
        st.caption("Choose any available Experience. Experience 18 remains locked.")
    else:
        st.caption("Choose any available Experience in this set.")
    if st.button("Check for Experience updates", width="stretch"):
        st.rerun()
    columns = st.columns(2)
    for index, mission in enumerate(missions):
        mission_id = str(mission.get("MissionID", ""))
        status = _bayu_submission_status(submissions.get(mission_id))
        with columns[index % 2]:
            with st.container(border=True):
                reference = str(mission.get("ReferenceImageURL", "") or "")
                try:
                    clue = cropped_reference_image(reference, mission)
                    preview = clue or get_mission_media_url(reference)
                    if preview:
                        st.image(preview, width="stretch")
                except Exception:
                    pass
                portrait = get_mission_media_url(
                    mission.get("CharacterPortraitURL", "")
                )
                if portrait:
                    st.image(portrait, width=110)
                st.markdown(f"### {mission.get('Title', mission_id)}")
                st.caption(
                    f"{str(mission.get('MissionType', 'Observe')).title()} · "
                    f"{_credit_number(mission.get('CreditValue', mission.get('Points', 0)))} Intelligence Credits"
                )
                st.write(f"**{status}**")
                if st.button(
                    "Open Experience", key=f"bayu_open_{mission_id}",
                    width="stretch",
                ):
                    st.session_state["bayu_selected_experience"] = mission_id
                    st.rerun()


def render_bayu_experience_board(db):
    render_experience_set_board(
        db, "EVT-0004", "Operation: The Labyrinth",
    )


def render_sync_ai_participant(db, event_id, session_token):
    """Open the existing event-owned Sync AI content from its programme link."""
    missions = db.get_event_missions(event_id)
    king = next((
        mission for mission in missions
        if str(mission.get("DisplayOrder", "")).strip() in {"18", "18.0"}
        or "audience with the king" in str(mission.get("Title", "")).casefold()
    ), {})
    briefing = str(
        king.get("Transmission", "")
        or king.get("Narrative", "")
        or king.get("Story", "")
        or "The King awaits your expedition's intelligence briefing."
    ).strip()
    st.markdown("## Sync AI")
    if not render_character_card(
        str(king.get("CharacterSource", "") or "The King"),
        str(king.get("CharacterPortraitURL", "") or ""),
        briefing,
        role="The King",
    ):
        st.markdown("### The King")
        st.info(briefing)

    if session_token:
        try:
            marketplace = get_runtime_database().get_team_wallet(session_token)
            wallet = marketplace.get("Wallet", {}) or {}
            st.metric(
                "Approved Intelligence Credits",
                _credit_number(wallet.get("EarnedCredits", wallet.get("Balance", 0))),
            )
        except RuntimeDatabaseError as error:
            st.warning("Intelligence Credits are reconnecting.")
            st.caption(str(error))

    preparation = db.get_mission(event_id, "S01") or {}
    instructions = str(
        preparation.get("ParticipantInstructions", "")
        or preparation.get("Description", "")
        or preparation.get("Story", "")
    ).strip()
    st.markdown("### Performance Preparation")
    if instructions:
        st.write(instructions)
    else:
        st.write("Prepare your team performance using only approved resources.")
    if session_token:
        render_marketplace(session_token)
    else:
        st.info("Reconnect your participant session to open the marketplace.")


def show_participant():
    runtime = get_runtime_database()
    restore_session_from_query_params(runtime)

    candidate = st.session_state.get("participant_recovery_candidate")
    if candidate:
        experience_header("Mission AI")
        render_recovery_candidate(candidate)

    if "participant_event_id" in st.session_state:
        persist_session_in_query_params()

    if "participant_event_id" not in st.session_state:
        experience_header("Mission AI")
        device_id = participant_device_id()
        pending = st.session_state.get("participant_join_request") or {}

        with st.form("participant_join_form", clear_on_submit=False):
            join_code = st.text_input("Join Code").upper().strip()
            first_name = st.text_input("First / Given Name")
            last_name = st.text_input("Last / Family Name")
            submitted = st.form_submit_button(
                "Joining…" if pending else "🚀 Join Event",
                disabled=bool(pending),
                width="stretch",
            )

        join_event = (
            participant_event_by_code(join_code) if join_code else None
        )
        country_options = []
        is_bayu_join = bool(
            join_event
            and str(join_event.get("EventID", "")) == "EVT-0004"
        )
        db = None
        if join_event and not is_bayu_join:
            db = GoogleSheetsDB()
            country_options = list(dict.fromkeys(
                str(team.get("Country", "")).strip()
                for team in db.get_teams(join_event.get("EventID", ""))
                if str(team.get("Country", "")).strip()
            ))
        country = ""
        if join_event and not is_bayu_join:
            country = st.selectbox(
                "Country",
                country_options,
            )
        elif join_event:
            st.info("Your country will be assigned automatically when you join.")

        if submitted and not pending:
            if not join_code:
                st.warning("Enter Join Code")
                st.stop()
            if not first_name.strip():
                st.warning("Enter your first / given name")
                st.stop()
            if not last_name.strip():
                st.warning("Enter your last / family name")
                st.stop()
            if not is_bayu_join and not country_options:
                st.warning("Enter a valid Join Code and select your country.")
                st.stop()

            participant_name = " ".join(
                " ".join([first_name, last_name]).split()
            )
            st.session_state["participant_join_request"] = {
                "join_code": join_code,
                "participant_name": participant_name,
                "country": country,
                "device_id": device_id,
                "is_bayu": is_bayu_join,
            }
            st.rerun()

        pending = st.session_state.get("participant_join_request") or {}
        if pending:
            st.info("Joining your expedition…")
            st.caption("Please do not refresh or tap again.")
            try:
                if pending.get("is_bayu"):
                    player = runtime.join_player(
                        pending["join_code"],
                        pending["participant_name"],
                        pending["device_id"],
                    )
                    player["Country"] = runtime._participant_country(
                        player.get("Status", "")
                    )
                else:
                    db = db or GoogleSheetsDB()
                    player = db.join_player_by_code(
                        pending["join_code"],
                        pending["participant_name"],
                        country=pending.get("country", ""),
                        device_id=pending["device_id"],
                    )
            except RuntimeDatabaseError as error:
                st.session_state.pop("participant_join_request", None)
                st.error(
                    "Your join request is still being processed. Do not submit again."
                )
                st.caption("Use Check Existing Registration to restore the result.")
                st.stop()
            except ValueError as error:
                st.session_state.pop("participant_join_request", None)
                st.error(str(error))
                st.stop()

            if player.get("Ambiguous"):
                st.session_state.pop("participant_join_request", None)
                st.error(player.get("Message", "Multiple expedition records match this name."))
                st.stop()
            if player.get("RecoveryRequired"):
                st.session_state["participant_recovery_candidate"] = player
                st.session_state.pop("participant_join_request", None)
                st.rerun()

            db = db or GoogleSheetsDB()
            ai = db.assign_ai_facilitator(player["Team"]) or {}

            restore_participant_identity(player, fallback_country=country)
            apply_participant_ai_identity(ai, player["EventID"])
            st.session_state.pop("participant_join_request", None)
            persist_session_in_query_params()
            st.rerun()

        if st.button(
            "Check Existing Registration",
            disabled=bool(pending),
            width="stretch",
        ):
            if not join_code or not first_name.strip() or not last_name.strip():
                st.warning("Enter your Join Code, first name and last name first.")
                st.stop()
            participant_name = " ".join(
                " ".join([first_name, last_name]).split()
            )
            try:
                player = runtime.restore_join(
                    join_code, participant_name, device_id,
                )
            except RuntimeDatabaseError:
                player = None
            if not player:
                st.info("No completed registration was found for this device.")
                st.stop()
            if player.get("Ambiguous"):
                st.error(player.get("Message", "Multiple expedition records match this name."))
                st.stop()
            if player.get("RecoveryRequired"):
                st.session_state["participant_recovery_candidate"] = player
                st.rerun()
            db = GoogleSheetsDB()
            ai = db.assign_ai_facilitator(player["Team"]) or {}
            restore_participant_identity(player)
            apply_participant_ai_identity(ai, player["EventID"])
            persist_session_in_query_params()
            st.rerun()

        st.caption(f"Build: {running_build_sha()}")
        return

    db = GoogleSheetsDB()

    experience_header(
        experience_title(
            {"EventName": st.session_state.get("participant_event_name", "")}
        ),
        welcome=False,
    )
    st.success(f"Welcome {st.session_state['participant_name']}")
    st.caption(st.session_state["participant_event_name"])
    render_team_assignment_card(db)
    participant_install_experience()
    st.divider()

    runtime_session = bool(
        st.session_state.get("participant_session_token", "")
    )
    road_hunt_mission = None
    road_hunt_active = False
    if runtime_session:
        watch_live_mission_state(
            st.session_state["participant_session_token"]
        )
        render_road_hunt_navigator(
            st.session_state["participant_session_token"]
        )
        road_hunt_mission, road_hunt_active = (
            render_road_hunt_mission_hub(
                st.session_state["participant_session_token"]
            )
        )
    live_runtime_state = st.session_state.get(
        "participant_runtime_state",
        {},
    )
    hierarchy_module, hierarchy_activity = {}, {}
    try:
        hierarchy = CanonicalProgrammeAdapter.load(
            db, st.session_state["participant_event_id"],
        )
        hierarchy_module, hierarchy_activity = hierarchy.resolve_runtime(live_runtime_state)
        participant_activity = hierarchy.participant_view(live_runtime_state)
    except (Exception, ProgrammeIntegrityError):
        hierarchy_module, hierarchy_activity = {}, {}
        participant_activity = {}
    current_stage_name = str(participant_activity.get("Activity", "")).strip()
    if current_stage_name:
        st.info(f"Current live stage: {current_stage_name}")

    linked_config = {
        "ContentType": participant_activity.get("ContentType", "Standard Activity"),
        "LinkedContent": participant_activity.get("LinkedContentID", ""),
    }
    linked_experience_set = str(
        linked_config.get("LinkedContent", "") or ""
    ).strip()

    assignment_id = str(
        (live_runtime_state.get("Stage", {}) or {}).get("ExperienceAssignmentID", "")
        or live_runtime_state.get("ExperienceAssignmentID", "")
    ).strip()
    if assignment_id:
        try:
            repository = SupabaseExperienceRepository(db.runtime)
            assets = {
                str(row.get("AssetID", "")): row for row in db.get_assets()
                if row.get("AssetID")
            }
            resolved = ExperienceLibraryService(repository).resolve(
                assignment_id, assets=assets,
            )
            render_experience_participant(resolved)
        except (RuntimeDatabaseError, ExperienceResolutionError, ValueError) as error:
            st.error(f"Experience is temporarily unavailable: {error}")
        footer()
        return

    if linked_config["ContentType"] == "Sync AI":
        render_sync_ai_participant(
            db,
            st.session_state["participant_event_id"],
            st.session_state.get("participant_session_token", ""),
        )
        footer()
        return
    if linked_config["ContentType"] in {"Standard Activity", "Briefing", "Break", "Debrief"}:
        render_programme_activity(hierarchy_activity)
        footer()
        return

    if linked_experience_set:
        event_id = st.session_state["participant_event_id"]
        if render_experience_set_entry(
            db,
            event_id,
            linked_experience_set,
            live_runtime_state.get("StateVersion", ""),
        ):
            render_experience_set_board(db, event_id, linked_experience_set)
        footer()
        return

    if road_hunt_active:
        mission = road_hunt_mission
    else:
        try:
            mission = db.get_current_mission(
                st.session_state["participant_event_id"],
                session_token=st.session_state.get(
                    "participant_session_token",
                    "",
                ),
            )
        except RuntimeDatabaseError as error:
            st.warning("Live experience state is reconnecting. Please wait a moment.")
            st.caption(str(error))
            mission = None
    if road_hunt_active:
        st.subheader("🎯 Selected Team Experience" if mission else "📍 Route Stage")
    else:
        st.subheader("🎯 Current Experience" if mission else "🎬 Live Stage")

    if mission is None:
        stage_payload = live_runtime_state.get("Stage", {}) or {}
        stage_name = str(
            live_runtime_state.get("StageName", "")
            or stage_payload.get("StageName", "")
        ).strip()
        current_mission_id = str(
            live_runtime_state.get("MissionID", "")
        ).strip()

        stage_type = str(
            live_runtime_state.get("StageType", "")
            or stage_payload.get("StageType", "")
        ).strip()

        if "MARKETPLACE" in stage_type.upper():
            render_marketplace(
                st.session_state.get("participant_session_token", "")
            )
        elif stage_name:
            render_programme_activity(stage_payload or hierarchy_activity)
            if current_mission_id and not road_hunt_active:
                st.warning(
                    f"Experience {current_mission_id} is being synchronised. "
                    "Press Check for New Experience once."
                )
        else:
            st.info("Waiting for facilitator to launch a stage...")
        if st.button(
            "🔄 Check for New Experience",
            width="stretch",
            key="check_waiting_mission",
        ):
            st.rerun()
        if not runtime_session:
            st_autorefresh(interval=5000, key="waiting_for_mission_refresh")
    else:
        runtime_stage = mission.get("_RuntimeStage", {})
        if runtime_stage:
            st.caption(
                f"Current stage: {runtime_stage.get('StageName', mission.get('Title', 'Experience'))}"
            )
            stage_message = str(
                runtime_stage.get("ParticipantMessage", "") or ""
            ).strip()
            if stage_message:
                st.info(stage_message)

        st.success(mission.get("Title", "Experience"))
        render_mission_content(mission)

        submission_type = normalise_submission_type(mission)
        existing_submission = find_existing_submission(
            db,
            mission,
            submission_type,
        )

        st.divider()
        if existing_submission:
            render_existing_submission(existing_submission)
            render_ai_response_after_submission(
                mission,
                existing_submission,
                ai_portrait_reference=(
                    bayu_ai_portrait_reference(db) if _is_bayu_event() else ""
                ),
            )
            if not runtime_session:
                st_autorefresh(interval=5000, key="submitted_mission_refresh")
        else:
            if runtime_session:
                st.caption(
                    "Experience changes update automatically. Your entered values are preserved."
                )
            else:
                st.caption(
                    "Auto-refresh pauses while you enter results so your values are not reset."
                )
            if st.button(
                "🔄 Check for New Experience",
                width="stretch",
                key=f"check_mission_{mission.get('MissionID', 'current')}",
            ):
                st.rerun()

            if not _is_bayu_event() or render_team_leader_submission_gate(db):
                render_submission_form(db, mission, submission_type)

    render_ai_facilitator(db, mission, runtime_session)

    st.divider()
    _, leave_col = st.columns([3, 1])
    with leave_col:
        if st.button("🚪 Leave Event", width="stretch"):
            reset_session()
            st.rerun()
    footer()
