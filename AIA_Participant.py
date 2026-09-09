"""Dedicated AIA Tech participant entrypoint; does not repoint Maxis apps."""
import streamlit as st
from branding import apply_branding, configure_page
from screens.aia_random_registration import render_aia_random_registration

configure_page(layout="centered")
apply_branding(participant_pwa=True)
render_aia_random_registration()
