import uuid
from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from ai.facilitator import ask_facilitator
from components.team_geolocation import team_geolocation
from data.google_drive import get_photo_url, upload_photo
from data.google_sheets import GoogleSheetsDB
from data.mission_media import get_mission_media_url
from data.runtime_database import RuntimeDatabaseError, get_runtime_database


COUNTRY_LANGUAGE_PROMPTS = {
    "Japan": "Find your team. You may greet them with: Konnichiwa.",
    "Malaysia": "Find your team. You may greet them with: Apa khabar.",
    "France": "Find your team. You may greet them with: Bonjour.",
    "India": "Find your team. You may greet them with: Namaste.",
    "Thailand": "Find your team. You may greet them with: Sawadee.",
    "China": "Find your team. You may greet them with: Ni hao.",
}

SESSION_KEYS = [
    "participant_id",
    "participant_event_id",
    "participant_name",
    "participant_team",
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
]


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

    poll_count = int(
        st.session_state.get("participant_runtime_poll_count", 0)
    ) + 1
    st.session_state["participant_runtime_poll_count"] = poll_count
    stage_number = runtime_state.get("StageNo", 0)
    event_id = runtime_state.get("EventID", "")
    st.caption(
        f"🟢 Live connection active · {event_id} · "
        f"stage {stage_number} · check #{poll_count}"
    )

    if previous_signature is not None and signature != previous_signature:
        st.rerun(scope="app")


def restore_session_from_query_params(db):
    if "participant_event_id" in st.session_state:
        return

    event_id = str(st.query_params.get("event_id", "")).strip()
    participant_name = str(st.query_params.get("participant_name", "")).strip()
    session_token = str(st.query_params.get("session_token", "")).strip()

    if session_token:
        try:
            runtime_player = db.get_player_by_session_token(session_token)
        except RuntimeDatabaseError:
            runtime_player = None

        if runtime_player:
            team_name = str(runtime_player.get("Team", ""))
            ai = db.assign_ai_facilitator(team_name) or {}
            st.session_state["participant_id"] = runtime_player.get(
                "ParticipantID",
                "",
            )
            st.session_state["participant_event_id"] = runtime_player.get(
                "EventID", ""
            )
            st.session_state["participant_name"] = runtime_player.get("Name", "")
            st.session_state["participant_team"] = team_name
            st.session_state["participant_points"] = runtime_player.get("Points", 0)
            st.session_state["participant_event_name"] = runtime_player.get(
                "EventName", "EXOS Event"
            )
            st.session_state["participant_session_token"] = runtime_player.get(
                "SessionToken", session_token
            )
            st.session_state["ai_name"] = ai.get("Name", "Atlas")
            st.session_state["ai_personality"] = ai.get("Personality", "")
            st.session_state["ai_greeting"] = ai.get("Greeting", "")
            return

    if db.runtime.is_configured:
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
    st.session_state["participant_points"] = player.get("Points", 0)
    st.session_state["participant_event_name"] = event.get(
        "EventName",
        str(st.query_params.get("event_name", "EXOS Event")),
    )
    st.session_state["participant_session_token"] = ""
    st.session_state["ai_name"] = ai.get("Name", "Atlas")
    st.session_state["ai_personality"] = ai.get("Personality", "")
    st.session_state["ai_greeting"] = ai.get("Greeting", "")


def persist_session_in_query_params():
    st.query_params["event_id"] = st.session_state["participant_event_id"]
    st.query_params["participant_name"] = st.session_state["participant_name"]
    st.query_params["participant_team"] = st.session_state["participant_team"]
    st.query_params["event_name"] = st.session_state["participant_event_name"]
    session_token = st.session_state.get("participant_session_token", "")
    if session_token:
        st.query_params["session_token"] = session_token


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


def render_team_assignment_card():
    team = st.session_state.get("participant_team", "")
    instruction = COUNTRY_LANGUAGE_PROMPTS.get(
        team,
        "Find your team members and gather together.",
    )

    st.markdown(
        f"""
        <div style="
            padding:24px;
            border-radius:22px;
            background:linear-gradient(135deg,#0f172a,#1e293b);
            color:white;
            text-align:center;
            margin-bottom:18px;
        ">
            <div style="font-size:18px;opacity:.8;">Your Team</div>
            <div style="font-size:46px;font-weight:900;margin-top:8px;">{team}</div>
            <div style="font-size:18px;margin-top:12px;opacity:.9;">{instruction}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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


def render_existing_submission(existing_submission):
    st.success("✅ Submission received.")

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
    if display_url:
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
        session_token=st.session_state.get(
            "participant_session_token",
            "",
        ),
    )


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
                st.error(str(error))
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
    st.subheader("📸 Mission Submission")
    uploaded_image = st.file_uploader(
        "Choose Photo",
        type=["jpg", "jpeg", "png"],
        key=f"photo_upload_{mission['MissionID']}",
    )

    if uploaded_image is not None:
        st.image(uploaded_image, width="stretch")

        if st.button(
            "📤 Submit Mission",
            width="stretch",
            key=f"submit_photo_{mission['MissionID']}",
        ):
            with st.spinner("Submitting mission..."):
                try:
                    uploaded = upload_photo(
                        event_id=st.session_state["participant_event_id"],
                        mission_id=mission["MissionID"],
                        team_name=st.session_state["participant_team"],
                        participant_name=st.session_state["participant_name"],
                        uploaded_file=uploaded_image,
                    )
                except (RuntimeDatabaseError, ValueError) as error:
                    st.error(str(error))
                    st.stop()
                save_structured_submission(
                    db=db,
                    mission=mission,
                    submission_type="PHOTO",
                    image_url=uploaded.get("url", ""),
                    drive_file_id=uploaded.get("file_id", ""),
                )

            st.success("✅ Mission submitted successfully.")
            st.balloons()
            st.rerun()


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
    elif submission_type == "NONE":
        st.info("No participant submission is required for this mission.")
    else:
        render_photo_form(db, mission)


def render_mission_content(mission):
    story = str(mission.get("Story", "") or "").strip()
    instructions = str(
        mission.get("ParticipantInstructions", "")
        or mission.get("Description", "")
        or ""
    ).strip()
    video_url = str(mission.get("VideoURL", "") or "").strip()
    image_url = str(mission.get("ImageURL", "") or "").strip()
    document_url = str(mission.get("DocumentURL", "") or "").strip()

    if story:
        st.markdown("#### Mission Story")
        st.markdown(story)

    display_video_url = get_mission_media_url(video_url)
    display_image_url = get_mission_media_url(image_url)
    display_document_url = get_mission_media_url(document_url)

    if display_video_url:
        try:
            st.video(display_video_url)
        except Exception:
            st.warning("The mission video could not be displayed.")
            st.link_button(
                "▶️ Open Mission Video",
                display_video_url,
                width="stretch",
            )

    if display_image_url:
        try:
            st.image(display_image_url, width="stretch")
        except Exception:
            st.warning("The mission image could not be displayed.")

    if instructions:
        st.markdown("#### Instructions")
        st.info(instructions)

    if display_document_url:
        st.link_button(
            "📄 Open Mission Document",
            display_document_url,
            width="stretch",
        )


def _credit_number(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


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


def render_ai_facilitator(db, mission, runtime_session):
    facilitator_name = st.session_state["ai_name"]
    session_token = st.session_state.get("participant_session_token", "")
    mission_id = str((mission or {}).get("MissionID", "")).strip()

    st.divider()
    st.subheader(f"🤖 {facilitator_name}")

    if st.session_state["ai_greeting"]:
        st.info(st.session_state["ai_greeting"])

    if not mission or not mission_id:
        st.caption(
            f"{facilitator_name} will be ready when the facilitator launches a mission."
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
                        st.warning("AI help is disabled for this mission.")
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
        st.caption("AI help is disabled for this mission.")

    prompt = st.chat_input(f"Ask {facilitator_name}...")
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


def show_participant():
    st.title("📱 EXOS Mission")

    db = GoogleSheetsDB()
    restore_session_from_query_params(db)

    if "participant_event_id" in st.session_state:
        persist_session_in_query_params()

    if "participant_event_id" not in st.session_state:
        st.markdown(
            """
            <div style="text-align:center;padding:18px 0 28px 0;">
                <div style="font-size:20px;letter-spacing:3px;font-weight:700;">EXOS</div>
                <div style="font-size:42px;font-weight:900;margin-top:8px;">Mission AI</div>
                <div style="font-size:18px;opacity:.75;margin-top:8px;">Join your live mission experience</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        join_code = st.text_input("Join Code").upper().strip()
        first_name = st.text_input("First / Given Name")
        last_name = st.text_input("Last / Family Name")

        if st.button("🚀 Join Event", width="stretch"):
            if not join_code:
                st.warning("Enter Join Code")
                st.stop()
            if not first_name.strip():
                st.warning("Enter your first / given name")
                st.stop()
            if not last_name.strip():
                st.warning("Enter your last / family name")
                st.stop()

            participant_name = " ".join([
                first_name.strip(),
                last_name.strip(),
            ])

            try:
                player = db.join_player_by_code(
                    join_code,
                    participant_name.strip(),
                )
            except RuntimeDatabaseError as error:
                st.error(
                    "Registration is temporarily busy. Your team has not been changed. "
                    "Please wait a few seconds and press Join Event again."
                )
                st.caption(str(error))
                st.stop()
            except ValueError as error:
                st.error(str(error))
                st.stop()

            ai = db.assign_ai_facilitator(player["Team"]) or {}

            st.session_state["participant_id"] = player.get(
                "ParticipantID",
                "",
            )
            st.session_state["participant_event_id"] = player["EventID"]
            st.session_state["participant_name"] = player["Name"]
            st.session_state["participant_team"] = player["Team"]
            st.session_state["participant_points"] = player.get("Points", 0)
            st.session_state["participant_event_name"] = player.get(
                "EventName", "EXOS Event"
            )
            st.session_state["participant_session_token"] = player.get(
                "SessionToken", ""
            )
            st.session_state["ai_name"] = ai.get("Name", "Atlas")
            st.session_state["ai_personality"] = ai.get("Personality", "")
            st.session_state["ai_greeting"] = ai.get("Greeting", "")
            persist_session_in_query_params()
            st.rerun()

        return

    st.success(f"Welcome {st.session_state['participant_name']}")
    st.caption(st.session_state["participant_event_name"])
    render_team_assignment_card()
    st.divider()

    runtime_session = bool(
        st.session_state.get("participant_session_token", "")
    )
    if runtime_session:
        watch_live_mission_state(
            st.session_state["participant_session_token"]
        )
        render_road_hunt_navigator(
            st.session_state["participant_session_token"]
        )
    live_runtime_state = st.session_state.get(
        "participant_runtime_state",
        {},
    )

    try:
        mission = db.get_current_mission(
            st.session_state["participant_event_id"],
            session_token=st.session_state.get(
                "participant_session_token",
                "",
            ),
        )
    except RuntimeDatabaseError as error:
        st.warning("Live mission state is reconnecting. Please wait a moment.")
        st.caption(str(error))
        mission = None
    st.subheader("🎯 Current Mission" if mission else "🎬 Live Stage")

    if mission is None:
        stage_payload = live_runtime_state.get("Stage", {}) or {}
        stage_name = str(
            live_runtime_state.get("StageName", "")
            or stage_payload.get("StageName", "")
        ).strip()
        participant_message = str(
            stage_payload.get("ParticipantMessage", "")
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
            st.success(stage_name)
            if participant_message:
                st.info(participant_message)
            if current_mission_id:
                st.warning(
                    f"Mission {current_mission_id} is being synchronised. "
                    "Press Check for New Mission once."
                )
        else:
            st.info("Waiting for facilitator to launch a stage...")
        if st.button(
            "🔄 Check for New Mission",
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
                f"Current stage: {runtime_stage.get('StageName', mission.get('Title', 'Mission'))}"
            )
            stage_message = str(
                runtime_stage.get("ParticipantMessage", "") or ""
            ).strip()
            if stage_message:
                st.info(stage_message)

        st.success(mission.get("Title", "Mission"))
        render_mission_content(mission)

        if mission.get("Clue"):
            st.info("💡 " + str(mission["Clue"]))

        submission_type = normalise_submission_type(mission)
        existing_submission = find_existing_submission(
            db,
            mission,
            submission_type,
        )

        st.divider()
        if existing_submission:
            render_existing_submission(existing_submission)
            if not runtime_session:
                st_autorefresh(interval=5000, key="submitted_mission_refresh")
        else:
            if runtime_session:
                st.caption(
                    "Mission changes update automatically. Your entered values are preserved."
                )
            else:
                st.caption(
                    "Auto-refresh pauses while you enter results so your values are not reset."
                )
            if st.button(
                "🔄 Check for New Mission",
                width="stretch",
                key=f"check_mission_{mission.get('MissionID', 'current')}",
            ):
                st.rerun()

            render_submission_form(db, mission, submission_type)

    render_ai_facilitator(db, mission, runtime_session)

    st.divider()
    _, leave_col = st.columns([3, 1])
    with leave_col:
        if st.button("🚪 Leave Event", width="stretch"):
            reset_session()
            st.rerun()
