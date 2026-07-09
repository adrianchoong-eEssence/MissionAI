import streamlit as st

from data.google_sheets import GoogleSheetsDB


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
        "Reflection": "📝 Reflection",
        "Closing": "🏁 Closing",
    }
    return mapping.get(stage_type, f"🎬 {stage_type}")


def _get_selected_event(db):
    events = db.get_events()

    if not events:
        st.warning("No events found. Create an event first.")
        return None, None

    event_options = {
        f"{event.get('EventID')} — {event.get('EventName')}": event
        for event in events
    }

    selected_label = st.selectbox("Select Event", list(event_options.keys()))
    event = event_options[selected_label]
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
            <div style="font-size:14px; margin-top:6px; opacity:0.7;">Mission: {stage.get('MissionID', '') or '-'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_show_control():
    st.title("🎬 Show Control")
    st.caption("Control the live programme flow from one place.")

    db = GoogleSheetsDB()
    event, event_id = _get_selected_event(db)

    if not event:
        return

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
        st.info("For Saturday, click the button below to load the AIA programme flow.")

        if st.button("⚡ Load Saturday AIA Flow", width="stretch"):
            db.seed_aia_saturday_stages(event_id)
            st.success("Saturday programme stages loaded.")
            st.rerun()

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
            db.set_event_stage(event_id, stages[current_index - 1])
            st.rerun()

    with current_col:
        if st.button("🔄 Re-sync Current Stage", width="stretch"):
            db.set_event_stage(event_id, current_stage)
            st.success("Current stage synced.")
            st.rerun()

    with next_col:
        if st.button("Next Stage ▶", width="stretch", disabled=current_index >= len(stages) - 1):
            db.set_event_stage(event_id, stages[current_index + 1])
            st.rerun()

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
                db.set_event_stage(event_id, stage)
                st.rerun()

    st.divider()

    with st.expander("Advanced: Reload Saturday AIA Flow"):
        st.warning("This will replace the current programme stages for this event.")
        if st.button("Reload Saturday Flow", width="stretch"):
            db.seed_aia_saturday_stages(event_id)
            st.success("Programme stages reloaded.")
            st.rerun()
