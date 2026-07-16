import streamlit as st


ACTIVE_EVENT_KEY = "exos_active_event_id"
NAVIGATION_REQUEST_KEY = "exos_navigation_request"


def event_id(event):
    return str((event or {}).get("EventID", "")).strip()


def active_event_index(events):
    rows = list(events or [])
    active_id = str(st.session_state.get(ACTIVE_EVENT_KEY, "")).strip()
    for index, event in enumerate(rows):
        if event_id(event) == active_id:
            return index
    return 0


def remember_active_event(event):
    selected_id = event_id(event)
    if selected_id:
        st.session_state[ACTIVE_EVENT_KEY] = selected_id
    return event


def get_active_event(events):
    rows = list(events or [])
    if not rows:
        return None
    index = active_event_index(rows)
    return remember_active_event(rows[index])


def select_active_event(
    events,
    label="Active Event",
    key="active_event_picker",
):
    rows = list(events or [])
    if not rows:
        return None

    options = [event_id(event) for event in rows]
    event_map = {
        event_id(event): event
        for event in rows
    }
    desired_value = options[active_event_index(rows)]
    current_widget_value = st.session_state.get(key)
    if current_widget_value != desired_value:
        st.session_state.pop(key, None)

    selected_id = st.selectbox(
        label,
        options,
        index=options.index(desired_value),
        format_func=lambda value: (
            f"{value} — {event_map[value].get('EventName', '')}"
        ),
        key=key,
    )
    return remember_active_event(event_map[selected_id])


def request_navigation(page, workspace=""):
    st.session_state[NAVIGATION_REQUEST_KEY] = str(page)
    if workspace:
        st.session_state["exos_requested_workspace"] = str(workspace)
    st.rerun()
