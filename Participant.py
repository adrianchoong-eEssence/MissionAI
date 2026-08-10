import os

import streamlit as st

from branding import apply_branding, configure_page
from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
from data.runtime_database import get_runtime_database
from screens.formula_race_captain import show_formula_race_captain
from screens.participant import show_participant

configure_page(layout="centered")
apply_branding(participant_pwa=True)


def _staging() -> bool:
    return str(os.getenv("EXOS_ENV", "")).strip().lower() == "staging"


def _is_core_v2_race_request() -> bool:
    if not _staging():
        return False

    captain_session = str(st.query_params.get("captain_session", "")).strip()
    if captain_session:
        return True

    join_code = str(st.query_params.get("join_code", "")).strip().upper()
    if not join_code:
        return False

    runtime = FormulaRaceCoreV2StagingAdapter(get_runtime_database())
    if not runtime.can_publish:
        return False

    event = runtime.get_event_by_join_code(join_code)
    event_name = str((event or {}).get("EventName", "")).upper()
    return "FORMULA RACE" in event_name or event_name == "RACE" or join_code.startswith("RACE")


if str(st.query_params.get("race", "")) == "1" or st.session_state.get("race_captain"):
    show_formula_race_captain()
elif _is_core_v2_race_request():
    show_formula_race_captain()
else:
    show_participant()
