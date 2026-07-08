import streamlit as st
from screens.participant import show_participant

st.set_page_config(
    page_title="EXOS Mission App",
    page_icon="📱",
    layout="centered"
)

show_participant()