import streamlit as st

from branding import apply_branding, configure_page, footer, sidebar_identity
from screens.administration import APP_VERSION, show_administration
from screens.asset_library import show_asset_library
from screens.app_state import ACTIVE_EVENT_KEY, NAVIGATION_REQUEST_KEY
from screens.command_centre import show_results_reports
from screens.control_centre import show_control_centre
from screens.create_event import show_create_event
from screens.events_home import show_events_home
from screens.leaderboard_display import show_leaderboard_display
from screens.mission_setup import show_mission_setup
from screens.participant import show_participant
from screens.programme_builder import show_programme_builder


requested_view = str(st.query_params.get("view", "")).strip().casefold()
if requested_view == "participant":
    configure_page(layout="centered")
    apply_branding(participant_pwa=True)
    show_participant()
    st.stop()

if requested_view == "projector":
    configure_page(layout="wide", initial_sidebar_state="collapsed")
    event_id = str(st.query_params.get("event_id", "")).strip()
    show_leaderboard_display(event_id=event_id, standalone=True)
    st.stop()


configure_page(layout="wide", initial_sidebar_state="expanded")
apply_branding(lock_sidebar=True)

PAGES = [
    "Events",
    "Create Event",
    "Mission Studio",
    "Programme Builder",
    "Control Centre",
    "Projector",
    "Reports",
    "Administration",
    "Asset Library",
]
PAGE_LABELS = {
    "Mission Studio": "Experience Studio",
}


def apply_navigation_request():
    requested = st.session_state.pop(NAVIGATION_REQUEST_KEY, "")
    if requested in PAGES:
        st.session_state["main_navigation"] = requested
    if st.session_state.get("main_navigation") not in PAGES:
        st.session_state["main_navigation"] = PAGES[0]


apply_navigation_request()

sidebar_identity()
page = st.sidebar.radio(
    "Workspace",
    PAGES,
    key="main_navigation",
    format_func=lambda value: PAGE_LABELS.get(value, value),
)

active_event_id = str(st.session_state.get(ACTIVE_EVENT_KEY, ""))
if active_event_id:
    st.sidebar.divider()
    st.sidebar.caption("Active event")
    st.sidebar.info(active_event_id)

if page == "Events":
    show_events_home()
elif page == "Create Event":
    show_create_event()
elif page == "Mission Studio":
    show_mission_setup()
elif page == "Programme Builder":
    show_programme_builder()
elif page == "Control Centre":
    show_control_centre()
elif page == "Projector":
    selected_event_id = str(st.session_state.get(ACTIVE_EVENT_KEY, "")).strip()
    if selected_event_id:
        st.link_button(
            "Open Selected Event Projector",
            f"?view=projector&event_id={selected_event_id}",
            width="stretch",
        )
        show_leaderboard_display(event_id=selected_event_id)
    else:
        show_leaderboard_display()
elif page == "Reports":
    show_results_reports()
elif page == "Administration":
    show_administration()
else:
    show_asset_library()

footer(report=page == "Reports")
