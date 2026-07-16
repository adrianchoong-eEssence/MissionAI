import streamlit as st

from data.google_sheets import GoogleSheetsDB
from screens.app_state import select_active_event


def _stage_badge(stage_type):
    mapping = {
        "Registration": "🟢 Registration",
        "TeamDiscovery": "🌍 Team Discovery",
        "MissionBriefing": "🎯 Mission Briefing",
        "MissionActive": "🚀 Mission Active",
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
    border = "3px solid #22c55e" if is_current else "1px solid rgba(255,255,255,0.15)"
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
            <div style="font-size:14px; margin-top:6px; opacity:0.7;">Mission: {stage.get('MissionID', '') or '-'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _activate_stage(db, event_id, stage):
    try:
        result = db.set_event_stage(event_id, stage)
    except Exception as error:
        st.error(f"Stage change failed: {error}")
        return

    warning = str((result or {}).get("Warning", "")).strip()
    st.session_state["show_control_flash"] = {
        "Level": "warning" if warning else "success",
        "Message": warning or (
            f"Live stage changed to {stage.get('StageName', 'selected stage')}."
        ),
    }
    st.rerun()


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
        st.info("Open Programme Builder to select missions and publish the live timeline.")
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
            background:linear-gradient(135deg, rgba(37,99,235,0.18), rgba(34,197,94,0.18));
            border:1px solid rgba(255,255,255,0.16);
        ">
            <div style="font-size:18px; opacity:0.75;">Stage {current_stage.get('StageNo')} of {len(stages)}</div>
            <div style="font-size:42px; font-weight:900; margin-top:8px;">{current_stage.get('StageName')}</div>
            <div style="font-size:20px; margin-top:10px;">{_stage_badge(current_stage.get('StageType', ''))}</div>
            <div style="font-size:18px; margin-top:12px; opacity:0.9;">Scheduled: {current_stage.get('StartTime', '') or 'Unscheduled'} • {current_stage.get('DurationMinutes', '') or '-'} minutes</div>
            <div style="font-size:16px; margin-top:12px; opacity:0.8;">Display Mode: {current_stage.get('DisplayMode', '')}</div>
            <div style="font-size:16px; margin-top:6px; opacity:0.8;">Mission ID: {current_stage.get('MissionID', '') or '-'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Participant Message")
    st.info(current_stage.get("ParticipantMessage", ""))

    st.markdown("### Facilitator Instruction")
    st.warning(current_stage.get("FacilitatorInstruction", ""))

    st.divider()

    prev_col, current_col, next_col = st.columns([1, 1, 1])

    with prev_col:
        if st.button("◀ Previous Stage", width="stretch", disabled=current_index == 0):
            _activate_stage(db, event_id, stages[current_index - 1])

    with current_col:
        if st.button("🔄 Re-sync Current Stage", width="stretch"):
            _activate_stage(db, event_id, current_stage)

    with next_col:
        if st.button("Next Stage ▶", width="stretch", disabled=current_index >= len(stages) - 1):
            _activate_stage(db, event_id, stages[current_index + 1])

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
