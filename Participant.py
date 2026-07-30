import streamlit as st
from branding import apply_branding, configure_page
from screens.participant import show_participant

configure_page(layout="centered")
apply_branding()

show_participant()
