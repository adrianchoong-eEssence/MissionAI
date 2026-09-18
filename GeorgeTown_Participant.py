"""Dedicated ENCA George Town hybrid participant entrypoint."""
import streamlit as st

from screens.enca_george_town_participant import render_enca_george_town_participant
from services.enca_george_town_event import enca_george_town_event

st.set_page_config(page_title="ENCA GROUP · MISSION AI", layout="centered")
render_enca_george_town_participant(event_id=enca_george_town_event()[0], join_code=enca_george_town_event()[1])
