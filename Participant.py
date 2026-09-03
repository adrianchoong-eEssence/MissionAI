import os

import streamlit as st

from branding import apply_branding, configure_page
from data.standard_core_v2_adapter import get_standard_database
from engines.theme_park_race import is_theme_park_race
import screens.participant as participant_screen
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


def _requested_event_identity():
    """Return the (event_id, join_code) this browser is currently acting on."""
    event_id = str(
        st.session_state.get("participant_event_id", "")
        or st.query_params.get("event_id", "")
    ).strip()
    join_code = str(
        st.session_state.get("participant_join_code", "")
        or st.query_params.get("join_code", "")
    ).strip().upper()
    return event_id, join_code


def _is_theme_park_race_request() -> bool:
    """Select the engine only from canonical ``RaceConfiguration.EngineKind``.

    A Theme Park Race participant or Captain stays inside this Core v2
    application for the whole registration → team → Captain lifecycle.  The
    legacy Formula R.A.C.E. captain shell is never their destination, whatever
    ``?race=1`` or a restored PWA session URL asks for.  A lookup failure
    returns False so Formula R.A.C.E. routing is left exactly as it was.
    """
    event_id, join_code = _requested_event_identity()
    if not event_id and not join_code:
        return False
    try:
        runtime = get_standard_database()
        event = runtime.get_event(event_id) if event_id else None
        if not event and join_code:
            event = runtime.get_event_by_join_code(join_code)
    except Exception:
        return False
    return is_theme_park_race(event)


def is_maxis_personal_key_request(params) -> bool:
    """Recognise only the one approved Personal Key UAT URL."""
    return (
        str(params.get("personal_key", "") or "").strip() == "1"
        and str(params.get("join_code", "") or "").strip().upper() == "MXKEY7"
    )


_race_captain_requested = str(st.query_params.get("race", "")).strip() == "1"

# This branch's dedicated Maxis UAT URL has a deliberately smaller entry
# surface. Identity authority still belongs to Team Formation V1; the branch
# only replaces the presentation and supplies the URL's fixed join code.
if is_maxis_personal_key_request(st.query_params):
    from screens.maxis_personal_key import render_maxis_personal_key_login

    render_maxis_personal_key_login()
    st.stop()

# Engine selection precedes every legacy captain route: a Theme Park Race is
# resolved from configuration, never from a query parameter or a programme name.
if _is_theme_park_race_request():
    # UAT-only presentation override. Canonical engine/RPC authority remains
    # unchanged, and the module is loaded only for a Theme Park request.
    from screens.maxis_participant_experience import render_maxis_theme_park_participant

    participant_screen.render_theme_park_race_participant = render_maxis_theme_park_participant
    show_participant()
    st.stop()

if _deployment_environment() == "staging" and not _race_captain_requested:
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
    if is_theme_park_race(event):
        # A configured engine always outranks the legacy name/prefix heuristic.
        return False
    event_name = str((event or {}).get("EventName", "")).upper()
    return "FORMULA RACE" in event_name or event_name == "RACE" or join_code.startswith("RACE")


if _race_captain_requested or st.session_state.get("race_captain"):
    show_formula_race_captain()
elif _is_core_v2_race_request():
    show_formula_race_captain()
else:
    show_participant()
