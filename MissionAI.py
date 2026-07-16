import streamlit as st

from screens.app_state import (
    ACTIVE_EVENT_KEY,
    NAVIGATION_REQUEST_KEY,
)
from screens.command_centre import (
    show_command_centre,
    show_results_reports,
)
from screens.event_manager import show_event_manager
from screens.experience_library import show_experience_library
from screens.leaderboard_display import show_leaderboard_display
from screens.live_event_console import show_live_event_console
from screens.mission_setup import show_mission_setup
from screens.programme_builder import show_programme_builder
from screens.show_control import show_show_control


st.set_page_config(
    page_title="EXOS",
    page_icon="🚀",
    layout="wide",
)


PAGES = [
    "🏠 Command Centre",
    "🧰 Build Event",
    "🎬 Run Event",
    "📺 Projector Display",
    "📊 Results & Reports",
    "⚙️ Administration",
]

BUILD_WORKSPACES = [
    "1. Event & Teams",
    "2. Missions",
    "3. Programme",
    "4. Experience Library",
]

RUN_WORKSPACES = [
    "1. Control Flow",
    "2. Missions, Approvals & Credits",
]


def apply_navigation_request():
    requested_page = st.session_state.pop(
        NAVIGATION_REQUEST_KEY,
        "",
    )
    if requested_page in PAGES:
        st.session_state["main_navigation"] = requested_page

    current_page = st.session_state.get("main_navigation")
    if current_page not in PAGES:
        st.session_state["main_navigation"] = PAGES[0]


def apply_workspace_request(page):
    requested = st.session_state.pop("exos_requested_workspace", "")
    if page == "🧰 Build Event" and requested in BUILD_WORKSPACES:
        st.session_state["build_event_workspace"] = requested
    elif page == "🎬 Run Event" and requested in RUN_WORKSPACES:
        st.session_state["run_event_workspace"] = requested


def show_build_event():
    st.markdown("## 🧰 Build Event")
    st.caption(
        "Work from left to right: event setup, missions, programme, then reusable experiences."
    )
    workspace = st.radio(
        "Build Step",
        BUILD_WORKSPACES,
        horizontal=True,
        key="build_event_workspace",
    )
    st.divider()

    if workspace == "1. Event & Teams":
        show_event_manager()
    elif workspace == "2. Missions":
        show_mission_setup()
    elif workspace == "3. Programme":
        show_programme_builder()
    else:
        show_experience_library()


def show_run_event():
    st.markdown("## 🎬 Run Event")
    st.caption(
        "Use Control Flow to change stages. Use Operations to launch missions, approve submissions and manage credits."
    )
    workspace = st.radio(
        "Live Workspace",
        RUN_WORKSPACES,
        horizontal=True,
        key="run_event_workspace",
    )
    st.divider()

    if workspace == "1. Control Flow":
        show_show_control()
    else:
        show_live_event_console()


def show_administration():
    st.title("⚙️ Administration")
    st.caption("Organisation-wide settings and system information.")

    active_event = st.session_state.get(ACTIVE_EVENT_KEY, "")
    if active_event:
        st.info(f"Current active event: {active_event}")

    st.subheader("System Settings")
    st.info(
        "Event defaults, display themes, AI behaviour and organisation preferences will be managed here."
    )


apply_navigation_request()

st.sidebar.title("🚀 EXOS")
st.sidebar.caption("Experience Operating System")

page = st.sidebar.radio(
    "Workspace",
    PAGES,
    key="main_navigation",
)
apply_workspace_request(page)

active_event_id = st.session_state.get(ACTIVE_EVENT_KEY, "")
if active_event_id:
    st.sidebar.divider()
    st.sidebar.caption("Active Event")
    st.sidebar.info(active_event_id)

st.sidebar.divider()
st.sidebar.caption("Participant Mission App uses its separate participant link.")

if page == "🏠 Command Centre":
    show_command_centre()
elif page == "🧰 Build Event":
    show_build_event()
elif page == "🎬 Run Event":
    show_run_event()
elif page == "📺 Projector Display":
    show_leaderboard_display()
elif page == "📊 Results & Reports":
    show_results_reports()
else:
    show_administration()
