import streamlit as st

from screens.experience_library import show_experience_library
from screens.programme_builder import show_programme_builder
from screens.participant import show_participant
from screens.mission_control import show_mission_control
from screens.event_manager import show_event_manager
from screens.live_event_console import show_live_event_console

st.set_page_config(
    page_title="EXOS",
    page_icon="🚀",
    layout="wide"
)

st.sidebar.title("🚀 EXOS")

page = st.sidebar.radio(
    "Navigation",
    [
        "🏠 Dashboard",
        "📚 Experience Library",
        "🛠 Programme Builder",
        "🗓 Events",
        "🎮 Live Event Console",
        "📱 Participant",
        "🎛 Facilitator Remote",
        "⚙ Settings"
    ]
)

if page == "🏠 Dashboard":
    st.title("🚀 eEssence Experience OS")
    st.subheader("Experiential Learning Operating System")
    st.success("System Status: Online")

elif page == "📚 Experience Library":
    show_experience_library()

elif page == "🛠 Programme Builder":
    show_programme_builder()

elif page == "🗓 Events":
    show_event_manager()

elif page == "🎮 Live Event Console":
    show_live_event_console()

elif page == "📱 Participant":
    show_participant()

elif page == "🎛 Facilitator Remote":
    st.title("🎛 Facilitator Remote")
    st.info("Coming next.")

elif page == "⚙ Settings":
    st.title("⚙ Settings")
    st.info("Coming soon.")