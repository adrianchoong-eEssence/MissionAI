import streamlit as st

from branding import apply_branding, configure_page, footer
from screens.administration import APP_VERSION, show_administration
from screens.asset_library import show_asset_library
from screens.app_state import ACTIVE_EVENT_KEY, NAVIGATION_REQUEST_KEY
from screens.command_centre import show_results_reports
from screens.control_centre import show_control_centre
from screens.create_event import show_create_event
from screens.events_home import show_events_home
from screens.leaderboard_display import show_leaderboard_display
from screens.mission_setup import show_mission_setup
from screens.programme_builder import show_programme_builder


configure_page(layout="wide")
apply_branding()

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

st.sidebar.caption("eEssence eXperiential OS")
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
st.sidebar.divider()
st.sidebar.caption(APP_VERSION)

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
    show_leaderboard_display()
elif page == "Reports":
    show_results_reports()
elif page == "Administration":
    show_administration()
else:
    show_asset_library()

footer(report=page == "Reports")
