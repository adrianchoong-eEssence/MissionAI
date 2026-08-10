import os

import streamlit as st

from branding import apply_branding, configure_page
from screens.participant import show_participant

configure_page(layout="centered")
apply_branding(participant_pwa=True)


def _deployment_environment() -> str:
    value = str(os.getenv("EXOS_ENV", "") or "").strip()
    if value:
        return value.casefold()
    try:
        return str(st.secrets.get("EXOS_ENV", "") or "").strip().casefold()
    except Exception:
        return ""


if _deployment_environment() == "staging":
    show_participant()
    st.stop()


# The existing non-staging Formula R.A.C.E. shell remains isolated from the
# Standard Core v2 staging application and is loaded only after its hard stop.
import subprocess
from uuid import UUID

from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
from data.runtime_database import get_runtime_database
from screens.formula_race_captain import show_formula_race_captain


def _staging() -> bool:
    return _deployment_environment() == "staging"


def _captain_deployed_commit():
    configured = str(
        os.getenv("GIT_COMMIT", "") or os.getenv("COMMIT_SHA", "")
    ).strip()
    if configured:
        return configured[:7]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _is_core_v2_race_request() -> bool:
    if not _staging():
        return False

    captain_session = str(st.query_params.get("captain_session", "")).strip()
    if str(os.getenv("EXOS_ENV", "")).strip().lower() == "staging":
        is_valid_uuid = False
        try:
            UUID(captain_session)
            is_valid_uuid = True
        except Exception:
            is_valid_uuid = False
        print(
            f"CAPTAIN UUID TRACE | Participant._is_core_v2_race_request | rpc/table: query_params | field: captain_session | "
            f"is_none: {not captain_session and 'captain_session' not in st.query_params} | "
            f"is_literal_none: {captain_session.lower() == 'none'} | is_valid_uuid: {is_valid_uuid}"
        )
    if captain_session:
        is_uuid = False
        try:
            UUID(captain_session)
            is_uuid = True
        except Exception:
            is_uuid = False
        if not is_uuid:
            if str(os.getenv("EXOS_ENV", "")).strip().lower() == "staging":
                print(
                    f"CAPTAIN UUID TRACE | Participant._is_core_v2_race_request.invalid | rpc/table: query_params | "
                    f"field: captain_session | is_none: False | is_literal_none: {captain_session.lower() == 'none'} | "
                    f"is_valid_uuid: {is_uuid}"
                )
            if "captain_session" in st.query_params:
                st.query_params.pop("captain_session", None)
            return False
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
