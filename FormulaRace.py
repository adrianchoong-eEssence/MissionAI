import streamlit as st

from branding import configure_page
from screens.formula_race import build_formula_race_runtime, show_formula_race
from screens.formula_race_projector import PROJECTOR_VIEWS, show_formula_race_projector


configure_page(layout="wide", initial_sidebar_state="collapsed")

# A projector view is read-only and carries its own event, so it never depends
# on the Race Control browser session.
_view = str(st.query_params.get("view", "")).strip().lower()
if _view in PROJECTOR_VIEWS:
    show_formula_race_projector(
        _view,
        build_formula_race_runtime(),
        str(st.query_params.get("event_id", "")).strip(),
    )
else:
    show_formula_race()
