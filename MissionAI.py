import streamlit as st

from screens.administration import APP_VERSION, show_administration
from screens.app_state import ACTIVE_EVENT_KEY, NAVIGATION_REQUEST_KEY
from screens.command_centre import show_results_reports
from screens.control_centre import show_control_centre
from screens.create_event import show_create_event
from screens.events_home import show_events_home
from screens.leaderboard_display import show_leaderboard_display
from screens.programme_builder import show_programme_builder


st.set_page_config(
    page_title="EXOS",
    page_icon="🚀",
    layout="wide",
)

PAGES = [
    "Events",
    "Create Event",
    "Programme Builder",
    "Control Centre",
    "Projector",
    "Reports",
    "Administration",
]


def apply_navigation_request():
    requested = st.session_state.pop(NAVIGATION_REQUEST_KEY, "")
    if requested in PAGES:
        st.session_state["main_navigation"] = requested
    if st.session_state.get("main_navigation") not in PAGES:
        st.session_state["main_navigation"] = PAGES[0]


apply_navigation_request()

st.sidebar.title("EXOS")
st.sidebar.caption("Event Operating System")
page = st.sidebar.radio("Workspace", PAGES, key="main_navigation")

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
elif page == "Programme Builder":
    show_programme_builder()
elif page == "Control Centre":
    show_control_centre()
elif page == "Projector":
    show_leaderboard_display()
elif page == "Reports":
    show_results_reports()
else:
    show_administration()
