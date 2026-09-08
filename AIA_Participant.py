"""Dedicated AIA Tech participant entrypoint; does not repoint Maxis apps."""
import streamlit as st
from branding import apply_branding, configure_page
from screens.aia_personal_key import render_aia_personal_key_login
from services.aia_personal_key_event import is_aia_personal_key_request

configure_page(layout="centered")
apply_branding(participant_pwa=True)
if is_aia_personal_key_request(st.query_params):
    render_aia_personal_key_login()
else:
    st.title("AIA TECH · MISSION AI")
    st.info("Use the AIA Tech Personal Key link provided by your facilitator.")
