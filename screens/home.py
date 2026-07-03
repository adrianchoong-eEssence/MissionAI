import streamlit as st

def show_home(go_to):
    st.title("🚀 Mission AI Studio")
    st.subheader("Facilitator Admin Dashboard")

    st.info("This is Adrian's cockpit. Use this screen to prepare and manage the programme.")

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🚀 Create / Open Mission", use_container_width=True):
            go_to("mission_setup")

        if st.button("📂 Projects", use_container_width=True):
            st.info("Projects module coming soon.")

        if st.button("🎲 Smart Shuffle", use_container_width=True):
            st.info("Smart Shuffle module coming soon.")

    with col2:
        if st.button("📺 Mission Control Display", use_container_width=True):
            go_to("mission_control")

        if st.button("📱 Participant Companion", use_container_width=True):
            go_to("participant")

        if st.button("🎛️ Mission Remote", use_container_width=True):
            go_to("remote")

    st.divider()

    st.caption("Mission AI Studio")
    st.caption("Powered by eEssence")