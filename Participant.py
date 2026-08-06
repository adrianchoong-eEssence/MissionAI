import streamlit as st
from branding import apply_branding, configure_page
from screens.participant import show_participant
from screens.formula_race_captain import show_formula_race_captain

configure_page(layout="centered")
apply_branding(participant_pwa=True)

if str(st.query_params.get("race", "")) == "1" or st.session_state.get("race_captain"):
    show_formula_race_captain()
else:
    show_participant()
