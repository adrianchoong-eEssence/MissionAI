import streamlit as st

from data.google_sheets import GoogleSheetsDB
from screens.app_state import select_active_event


def _stage_badge(stage_type):
    mapping = {
        "Registration": "🟢 Registration",
        "TeamDiscovery": "🌍 Team Discovery",
        "MissionBriefing": "🎯 Experience Briefing",
        "MissionActive": "🚀 Experience Active",
        "Results": "📊 Results",
        "Debrief": "💬 Debrief",
        "Break": "🍱 Break",
        "Collaboration": "🤝 Collaboration",
        "Marketplace": "🛒 Marketplace",
        "MARKETPLACE": "🛒 Marketplace",
        "Reflection": "📝 Reflection",
        "Closing": "🏁 Closing",
    }
    return mapping.get(stage_type, f"🎬 {stage_type}")


def _get_selected_event(db):
    events = db.get_events()

    if not events:
        st.warning("No events found. Create an event first.")
        return None, None

    event = select_active_event(
        events,
        label="Active Event",
        key="show_control_event",
    )
    return event, event.get("EventID")


def _find_current_index(stages, state):
    if not stages:
        return 0

    if not state:
        return 0

    current_stage_no = str(state.get("CurrentStageNo", ""))

    for index, stage in enumerate(stages):
        if str(stage.get("StageNo", "")) == current_stage_no:
            return index

    return 0


def _render_stage_card(stage, is_current=False):
    border = "3px solid #B59A37" if is_current else "1px solid rgba(255,255,255,0.15)"
    background = "rgba(34,197,94,0.15)" if is_current else "rgba(255,255,255,0.04)"

    st.markdown(
        f"""
        <div style="
            padding:18px 22px;
            margin-bottom:14px;
            border-radius:18px;
            border:{border};
            background:{background};
        ">
            <div style="font-size:16px; opacity:0.75;">Stage {stage.get('StageNo', '')}</div>
            <div style="font-size:24px; font-weight:800;">{stage.get('StageName', '')}</div>
            <div style="font-size:15px; margin-top:6px; opacity:0.85;">{_stage_badge(stage.get('StageType', ''))}</div>
            <div style="font-size:14px; margin-top:6px; opacity:0.75;">{stage.get('StartTime', '') or 'Unscheduled'} • {stage.get('DurationMinutes', '') or '-'} min</div>
            <div style="font-size:14px; margin-top:6px; opacity:0.7;">Experience: {stage.get('MissionID', '') or '-'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _activate_stage(db, event_id, stage):
    del db, event_id, stage
    st.info("Stage mutation is available only in Control Centre.")


def show_show_control():
    st.title("🎬 Show Control")
    st.caption("Control the live programme flow from one place.")

    db = GoogleSheetsDB()
    event, event_id = _get_selected_event(db)

    if not event:
        return

    flash = st.session_state.pop("show_control_flash", None)
    if flash:
        if flash.get("Level") == "warning":
            st.warning(flash.get("Message", ""))
        else:
            st.success(flash.get("Message", ""))

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Event", event.get("EventName", ""))

    with col2:
        st.metric("Join Code", event.get("JoinCode", ""))

    with col3:
        st.metric("Participants", db.get_participant_count(event_id))

    st.divider()

    stages = db.get_programme_stages(event_id)

    if not stages:
        st.warning("No programme stages found for this event.")
        st.info("Open Programme Builder to select experiences and publish the live timeline.")
        return

    state = db.get_event_state(event_id)
    current_index = _find_current_index(stages, state)
    current_stage = stages[current_index]

    st.subheader("Current Stage")

    st.markdown(
        f"""
        <div style="
            padding:28px;
            border-radius:24px;
            background:rgba(8,45,88,0.14);
            border:1px solid rgba(255,255,255,0.16);
        ">
            <div style="font-size:18px; opacity:0.75;">Stage {current_stage.get('StageNo')} of {len(stages)}</div>
            <div style="font-size:42px; font-weight:900; margin-top:8px;">{current_stage.get('StageName')}</div>
            <div style="font-size:20px; margin-top:10px;">{_stage_badge(current_stage.get('StageType', ''))}</div>
            <div style="font-size:18px; margin-top:12px; opacity:0.9;">Scheduled: {current_stage.get('StartTime', '') or 'Unscheduled'} • {current_stage.get('DurationMinutes', '') or '-'} minutes</div>
            <div style="font-size:16px; margin-top:12px; opacity:0.8;">Display Mode: {current_stage.get('DisplayMode', '')}</div>
            <div style="font-size:16px; margin-top:6px; opacity:0.8;">Experience ID: {current_stage.get('MissionID', '') or '-'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Participant Message")
    st.info(current_stage.get("ParticipantMessage", ""))

    st.markdown("### Facilitator Instruction")
    st.warning(current_stage.get("FacilitatorInstruction", ""))

    st.divider()

    st.info(
        "Show Control is a read-only legacy view. Stage controls have moved to Control Centre."
    )

    st.divider()

    st.subheader("Programme Timeline")

    for index, stage in enumerate(stages):
        left, right = st.columns([4, 1])

        with left:
            _render_stage_card(stage, is_current=(index == current_index))

        with right:
            st.write("")
            st.write("")
            if st.button(
                "Go",
                key=f"go_stage_{stage.get('StageNo')}",
                width="stretch",
            ):
                _activate_stage(db, event_id, stage)

    st.divider()

    with st.expander("Advanced: Reload Saturday AIA Flow"):
        st.warning("This will replace the current programme stages for this event.")
        if st.button("Reload Saturday Flow", width="stretch"):
            db.seed_aia_saturday_stages(event_id)
            st.success("Programme stages reloaded.")
            st.rerun()
