import streamlit as st

from branding import configure_page
from screens.formula_race import show_formula_race


configure_page(layout="wide", initial_sidebar_state="collapsed")
show_formula_race()
