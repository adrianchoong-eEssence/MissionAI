import streamlit as st
from branding import apply_branding, configure_page, footer
from screens.live_event_console import show_live_event_console

configure_page(layout="wide")
apply_branding()

show_live_event_console()
footer()
