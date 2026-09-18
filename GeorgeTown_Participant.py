"""Dedicated ENCA George Town hybrid participant entrypoint."""
import streamlit as st

from screens.enca_george_town_participant import render_enca_george_town_participant
from services.enca_george_town_event import enca_george_town_event

st.set_page_config(page_title="ENCA GROUP · MISSION AI", layout="centered")
try:
    render_enca_george_town_participant(event_id=enca_george_town_event()[0], join_code=enca_george_town_event()[1])
except Exception:
    # Keep unexpected deployment faults actionable without exposing secrets,
    # storage details, database errors, or a stack trace to participants.
    st.title("ENCA GROUP")
    st.subheader("MISSION AI")
    st.error("Mission AI cannot start this participant session yet. Please reload or contact Mission Control.")
