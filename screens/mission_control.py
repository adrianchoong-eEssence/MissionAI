import streamlit as st


def show_mission_control():

    st.title("🎮 Experience Control")

    missions = [
        "Welcome Briefing",
        "Checkpoint 1",
        "Checkpoint 2",
        "Checkpoint 3",
        "Final Challenge"
    ]

    selected = st.selectbox(
        "Current Experience",
        missions
    )

    description = st.text_area(
        "Experience Instructions",
        value="Complete the assigned challenge."
    )

    if st.button("🚀 Send Experience"):

        st.session_state["current_mission"] = {
            "title": selected,
            "description": description
        }

        st.success("Experience sent.")
