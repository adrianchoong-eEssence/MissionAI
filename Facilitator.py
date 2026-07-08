import streamlit as st
from screens.live_event_console import show_live_event_console

st.set_page_config(
    page_title="EXOS Live Console",
    page_icon="🎮",
    layout="wide"
)

show_live_event_console()