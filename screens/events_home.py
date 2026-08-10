import streamlit as st

from branding import platform_hero
from data.standard_core_v2_adapter import get_standard_database
from screens.app_state import remember_active_event, request_navigation


def show_events_home():
    platform_hero()
    st.title("Events")
    st.caption("Create a new event or continue from where you left off.")
    db = get_standard_database()

    create_col, refresh_col, view_col, open_col = st.columns([1, 1, 1.35, 2])
    with create_col:
        if st.button("Create New Event", type="primary", width="stretch"):
            request_navigation("Create Event")
    with refresh_col:
        if st.button("Refresh Events", width="stretch"):
            db.clear_cache()
            st.rerun()
    with view_col:
        event_view = st.selectbox(
            "Event view",
            ["Current", "Archived / Inactive", "All"],
            label_visibility="collapsed",
        )
    with open_col:
        search = st.text_input(
            "Find an event",
            placeholder="Search client, event name, venue or join code",
            label_visibility="collapsed",
        ).strip().casefold()

    events = db.get_events(include_archived=True)
    inactive_statuses = {"ARCHIVED", "INACTIVE", "COMPLETED", "CLOSED"}
    if event_view == "Current":
        events = [
            event for event in events
            if str(event.get("Status", "Draft")).strip().upper()
            not in inactive_statuses
        ]
    elif event_view == "Archived / Inactive":
        events = [
            event for event in events
            if str(event.get("Status", "Draft")).strip().upper()
            in inactive_statuses
        ]
    status_priority = {
        "ACTIVE": 0, "LIVE": 0, "PUBLISHED": 0, "DRAFT": 1,
        "COMPLETED": 2, "CLOSED": 2, "INACTIVE": 3, "ARCHIVED": 3,
    }
    events.sort(
        key=lambda event: (
            status_priority.get(
                str(event.get("Status", "Draft")).strip().upper(), 2
            ),
            str(event.get("_UpdatedAt", "")),
        ),
        reverse=False,
    )
    grouped = {}
    for event in events:
        priority = status_priority.get(
            str(event.get("Status", "Draft")).strip().upper(), 2
        )
        grouped.setdefault(priority, []).append(event)
    events = [
        event
        for priority in sorted(grouped)
        for event in sorted(
            grouped[priority],
            key=lambda item: str(item.get("_UpdatedAt", "")),
            reverse=True,
        )
    ]
    if search:
        events = [
            event for event in events
            if search in " ".join(
                str(event.get(field, ""))
                for field in (
                    "Client",
                    "EventName",
                    "Venue",
                    "JoinCode",
                    "EventDate",
                )
            ).casefold()
        ]

    if not events:
        st.info("No active events match your search.")
        return

    for event in events:
        event_id = str(event.get("EventID", ""))
        with st.container(border=True):
            title_col, status_col = st.columns([4, 1])
            title_col.subheader(str(event.get("EventName", "Unnamed event")))
            status_col.markdown(
                f"**{str(event.get('Status', 'Draft') or 'Draft')}**"
            )
            st.caption(
                f"{event.get('Client', '—')} · {event.get('EventDate', '—')} · "
                f"{event.get('Venue', '—')} · Join code {event.get('JoinCode', '—')}"
            )
            open_event, build, control, more = st.columns([1, 1, 1, .55])
            if open_event.button(
                "Open Event",
                width="stretch",
                key=f"open_event_{event_id}",
            ):
                remember_active_event(event)
                request_navigation("Create Event")
            if build.button(
                "Programme Builder",
                width="stretch",
                key=f"build_event_{event_id}",
            ):
                remember_active_event(event)
                request_navigation("Programme Builder")
            if control.button(
                "Control Centre",
                width="stretch",
                key=f"control_event_{event_id}",
            ):
                remember_active_event(event)
                request_navigation("Control Centre")
            with more:
                with st.popover("More", width="stretch"):
                    st.markdown("**Archive this event?**")
                    st.caption(
                        "Archived events will disappear from the normal Events "
                        "list but can be restored from Administration."
                    )
                    confirmed = st.checkbox(
                        "Confirm archive",
                        key=f"confirm_archive_{event_id}",
                    )
                    if st.button(
                        "Archive Event",
                        key=f"archive_event_{event_id}",
                        disabled=not confirmed,
                        width="stretch",
                    ):
                        db.archive_event(event_id)
                        st.success("Event archived. All event data is preserved.")
                        st.rerun()
