"""Personal Key-only participant entry for the dedicated Maxis UAT branch.

The screen is presentation-only. It claims an existing PREASSIGNED participant
through Team Formation V1 and never accepts or writes participant identity
fields supplied by a browser.
"""
from __future__ import annotations

import html
from collections.abc import Mapping

import streamlit as st

from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import get_standard_database
from screens.participant import participant_device_id, restore_participant_identity
from services.personal_key_credentials import derive_personal_key_credential


EVENT_ID = "MAXIS-UAT-PREASSIGNED"
JOIN_CODE = "MXKEY7"
INVALID_KEY_MESSAGE = (
    "That Personal Key was not recognised.\n"
    "Check the code beside your name and try again."
)
COUNTRY_GREETING = {
    "Japan": ("🇯🇵", "KONNICHIWA!"),
    "South Korea": ("🇰🇷", "ANNYEONGHASEYO!"),
    "France": ("🇫🇷", "BONJOUR!"),
    "Italy": ("🇮🇹", "CIAO!"),
    "Brazil": ("🇧🇷", "OLÁ!"),
    "Thailand": ("🇹🇭", "SAWASDEE!"),
}


def _query_value(params: Mapping, key: str) -> str:
    value = params.get(key, "")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def is_maxis_personal_key_request(params: Mapping) -> bool:
    """Enable this screen only for the single approved Maxis event URL."""
    return (
        _query_value(params, "personal_key") == "1"
        and _query_value(params, "join_code").upper() == JOIN_CODE
    )


def claim_personal_key(runtime, personal_key: str, device_id: str):
    """Derive an opaque event credential, then claim the canonical participant."""
    derived_credential = derive_personal_key_credential(EVENT_ID, personal_key)
    return runtime.claim_preassigned_team_formation_participant(
        JOIN_CODE,
        derived_credential,
        device_id,
    )


def _valid_identity(player: dict | None) -> bool:
    return bool(
        player
        and str(player.get("EventID", "")) == EVENT_ID
        and player.get("ParticipantID")
        and player.get("TeamID")
        and player.get("SessionToken")
    )


def _restore_session(runtime) -> dict | None:
    """Restore from the canonical session token; never from editable identity."""
    if str(st.session_state.get("participant_event_id", "")) == EVENT_ID:
        return {
            "EventID": EVENT_ID,
            "ParticipantID": st.session_state.get("participant_id", ""),
            "TeamID": st.session_state.get("participant_team_id", ""),
            "Team": st.session_state.get("participant_team", ""),
            "Country": st.session_state.get("participant_country", ""),
            "Flag": st.session_state.get("participant_flag", ""),
            "Name": st.session_state.get("participant_name", ""),
            "SessionToken": st.session_state.get("participant_session_token", ""),
        }

    session_token = _query_value(st.query_params, "session_token")
    if not session_token:
        return None
    try:
        player = runtime.get_player_by_token(session_token)
    except RuntimeDatabaseError:
        return None
    if not _valid_identity(player):
        return None
    restore_participant_identity(player, fallback_token=session_token)
    return player


def _persist_session(player: dict) -> None:
    """Persist only routing, device and canonical session references."""
    desired = {
        "join_code": JOIN_CODE,
        "personal_key": "1",
        "event_id": EVENT_ID,
        "device_id": st.session_state.get("participant_device_id", ""),
        "session_token": player.get("SessionToken", ""),
    }
    for key, value in desired.items():
        if value and _query_value(st.query_params, key) != str(value):
            st.query_params[key] = str(value)

    # A Personal Key is accepted only as a password form value. Remove any
    # similarly named query values except the non-secret mode flag above.
    for key in list(st.query_params):
        if str(key).casefold() in {
            "enrollment_credential",
            "enrollmentcredential",
            "personal_key_value",
            "personalkey",
        }:
            del st.query_params[key]


def _country_reveal(player: dict) -> tuple[str, str, str]:
    country = str(player.get("Country") or player.get("Team") or "").strip()
    configured_flag, greeting = COUNTRY_GREETING.get(country, ("", "HELLO!"))
    flag = str(player.get("Flag") or configured_flag).strip()
    return country, flag, greeting


def _render_reveal(player: dict) -> None:
    country, flag, greeting = _country_reveal(player)
    if country not in COUNTRY_GREETING:
        st.error("Your country assignment could not be loaded. Please contact the facilitator.")
        return

    name = html.escape(str(player.get("Name", "")).strip())
    safe_country = html.escape(country.upper())
    safe_greeting = html.escape(greeting)
    safe_flag = html.escape(flag)
    st.markdown(
        """
        <style>
        .mx-key-reveal{text-align:center;padding:1rem .3rem}
        .mx-key-flag{font-size:5rem;line-height:1;margin:.5rem 0 1rem}
        .mx-key-you-are{font:800 .8rem Inter,sans-serif;letter-spacing:.24em;color:#8CA0BE}
        .mx-key-country{font:900 2.8rem/1 'Barlow Condensed',Impact,sans-serif;color:#fff;margin:.25rem 0}
        .mx-key-greeting{font:900 1.45rem Inter,sans-serif;color:#2DD4BF;margin:.35rem 0 1.5rem}
        .mx-key-name{font:700 .86rem Inter,sans-serif;color:#D6DEEA;margin-bottom:1.4rem}
        .mx-key-mission{text-align:left;padding:1rem;border-radius:16px;background:rgba(16,34,54,.92);border:1px solid rgba(45,212,191,.3)}
        .mx-key-number{font:800 .65rem Inter,sans-serif;letter-spacing:.18em;color:#D9B24C}
        .mx-key-title{font:900 1.55rem/1.05 'Barlow Condensed',Impact,sans-serif;color:#fff;margin:.25rem 0 .65rem}
        .mx-key-copy{font:600 .9rem/1.5 Inter,sans-serif;color:#EAF0F8}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="mx-key-reveal">'
        f'<div class="mx-key-flag">{safe_flag}</div>'
        '<div class="mx-key-you-are">YOU ARE</div>'
        f'<div class="mx-key-country">{safe_country}</div>'
        f'<div class="mx-key-greeting">{safe_greeting}</div>'
        f'<div class="mx-key-name">Welcome, {name}</div>'
        '<div class="mx-key-mission">'
        '<div class="mx-key-number">MISSION 01</div>'
        '<div class="mx-key-title">FIND YOUR PEOPLE</div>'
        '<div class="mx-key-copy">Move around the room using your country\'s greeting.<br>'
        'Find the other members of your country.</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


def _render_post_reveal_experience(runtime, player: dict, device_id: str) -> bool:
    """Hand the same personal-key URL to the canonical team/race projection.

    During REGISTRATION_OPEN, the country reveal is deliberately the only
    surface.  Once Team Formation advances, this remains the same participant
    session and enters the generic Theme Park engine projection rather than a
    parallel Maxis lifecycle.
    """
    try:
        workspace = runtime.theme_park_race_participant_workspace(player["SessionToken"])
    except RuntimeDatabaseError:
        return False
    if str(workspace.get("Lifecycle", "")).upper() == "TEAM_FORMATION":
        return False
    from screens.maxis_participant_experience import render_maxis_theme_park_participant

    render_maxis_theme_park_participant(runtime, device_id=device_id)
    return True


def render_maxis_personal_key_login() -> None:
    runtime = get_standard_database()
    device_id = participant_device_id()
    player = _restore_session(runtime)

    if _valid_identity(player):
        _persist_session(player)
        if _render_post_reveal_experience(runtime, player, device_id):
            return
        _render_reveal(player)
        return

    try:
        event = runtime.get_event_by_join_code(JOIN_CODE)
    except RuntimeDatabaseError:
        event = None
    if not event or str(event.get("EventID", "")) != EVENT_ID:
        st.error("Maxis Mission AI is not available yet.")
        return

    st.markdown("# MAXIS MISSION AI")
    with st.form("maxis_personal_key_form", clear_on_submit=True):
        personal_key = st.text_input(
            "PERSONAL KEY",
            type="password",
            key="maxis_personal_key_input",
            autocomplete="off",
        )
        submitted = st.form_submit_button(
            "ENTER MISSION AI",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    try:
        player = claim_personal_key(runtime, personal_key, device_id)
    except (RuntimeDatabaseError, ValueError):
        player = None

    if not _valid_identity(player) or player.get("RecoveryRequired"):
        st.error(INVALID_KEY_MESSAGE)
        return

    restore_participant_identity(player)
    st.session_state["participant_join_code"] = JOIN_CODE
    _persist_session(player)
    st.rerun()
