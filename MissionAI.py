import streamlit as st

from screens.event_manager import show_event_manager
from screens.experience_library import show_experience_library
from screens.leaderboard_display import show_leaderboard_display
from screens.live_event_console import show_live_event_console
from screens.participant import show_participant
from screens.programme_builder import show_programme_builder
from screens.show_control import show_show_control

st.set_page_config(
    page_title="EXOS",
    page_icon="🚀",
    layout="wide",
)

st.sidebar.title("🚀 EXOS")

page = st.sidebar.radio(
    "Navigation",
    [
        "🏠 Dashboard",
        "🎬 Show Control",
        "📺 Live Display",
        "🎮 Live Event Console",
        "📱 Mission App",
        "🗓 Events",
        "📚 Experience Library",
        "🛠 Programme Builder",
        "⚙ Settings",
    ],
)

if page == "🏠 Dashboard":
    st.title("🚀 eEssence Experience OS")
    st.subheader("Experiential Learning Operating System")
    st.success("System Status: Online")

    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Platform", "EXOS")

    with col2:
        st.metric("Version", "0.1 Alpha")

    with col3:
        st.metric("Status", "Operational")

    st.markdown("---")

    st.subheader("Saturday Priority Modules")

    st.markdown(
        """
✅ Participant Registration

✅ Round Robin Team Assignment

✅ Mission Launch

✅ Submission Capture

✅ Facilitator Scoring

✅ Live Leaderboard

✅ Live Display

✅ Show Control
"""
    )

elif page == "🎬 Show Control":
    show_show_control()

elif page == "📺 Live Display":
    show_leaderboard_display()

elif page == "🎮 Live Event Console":
    show_live_event_console()

elif page == "📱 Mission App":
    show_participant()

elif page == "🗓 Events":
    show_event_manager()

elif page == "📚 Experience Library":
    show_experience_library()

elif page == "🛠 Programme Builder":
    show_programme_builder()

elif page == "⚙ Settings":
    st.title("⚙ Settings")
    st.info(
        "Global settings will eventually control event defaults, display themes, AI behaviour and organisation preferences."
    )
