import streamlit as st


def show_mission_control():

    st.title("🎮 Mission Control")

    missions = [
        "Welcome Briefing",
        "Checkpoint 1",
        "Checkpoint 2",
        "Checkpoint 3",
        "Final Challenge"
    ]

    selected = st.selectbox(
        "Current Mission",
        missions
    )

    description = st.text_area(
        "Mission Instructions",
        value="Complete the assigned challenge."
    )

    if st.button("🚀 Send Mission"):

        st.session_state["current_mission"] = {
            "title": selected,
            "description": description
        }

        st.success("Mission sent.")