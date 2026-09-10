"""One-link AIA random self-registration and same-device reconnect surface."""
from __future__ import annotations

import html

import streamlit as st

from components.participant_credential import participant_device_binding
from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import get_standard_database
from screens.participant import normalise_join_name, restore_participant_identity
from screens.aia_participant_experience import render_aia_theme_park_participant
from services.live_location_participant import (
    render_live_location_participant,
    render_participant_announcements,
)
from services.aia_random_registration_event import aia_random_registration_event
from services.maxis_live_state import watch_maxis_live_state


def _query_value(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def _valid(player: dict | None, event_id: str) -> bool:
    return bool(
        player
        and str(player.get("EventID", "")) == event_id
        and player.get("ParticipantID")
        and player.get("TeamID")
        and player.get("SessionToken")
    )


def _persist_session(player: dict, event_id: str) -> None:
    """Persist routing/session references only; never an identity input or secret."""
    for key, value in {
        "event_id": event_id,
        "session_token": str(player.get("SessionToken", "") or ""),
    }.items():
        if value and _query_value(key) != value:
            st.query_params[key] = value
    for key in list(st.query_params):
        if str(key).casefold() in {
            "join_code", "personal_key", "enrollment_credential",
            "enrollmentcredential", "participant_name", "device_id",
        }:
            del st.query_params[key]


def _restore(runtime, event_id: str) -> dict | None:
    token = str(st.session_state.get("participant_session_token", "") or _query_value("session_token")).strip()
    if not token:
        return None
    try:
        player = runtime.get_player_by_token(token)
    except RuntimeDatabaseError:
        return None
    if _valid(player, event_id):
        restore_participant_identity(player, fallback_token=token)
        return player
    return None


def _render_team_reveal(workspace: dict) -> None:
    """A mobile-first identity reveal before the Captain-selection phase."""
    participant_id = str(st.session_state.get("participant_id", "") or "")
    team = html.escape(str(workspace.get("TeamIdentity") or workspace.get("TeamID") or "Quest").upper())
    members = list(workspace.get("TeamMembers") or [])
    rows = []
    for member in members:
        name = html.escape(str(member.get("Name") or member.get("DisplayName") or "Team member").strip())
        is_you = str(member.get("ParticipantID") or "") == participant_id
        rows.append(f"<div class='aia-member'>• {name}{' <b>— YOU</b>' if is_you else ''}</div>")
    st.markdown(
        """
        <style>
        .aia-reveal{padding:1.1rem;border-radius:20px;background:linear-gradient(145deg,#09263b,#10183b);border:1px solid #47cfca}
        .aia-kicker{font:800 .7rem Inter,sans-serif;letter-spacing:.2em;color:#72e9e3}.aia-team{font:900 2.3rem/1 Inter,sans-serif;color:#fff;margin:.35rem 0}.aia-mission{margin-top:1rem;padding:.85rem;border-radius:14px;background:#ffffff12;color:#fff;font-weight:800}.aia-member{padding:.52rem 0;border-bottom:1px solid #ffffff1a;color:#e9f5f6}.aia-member b{color:#72e9e3;float:right;font-size:.72rem;letter-spacing:.08em}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='aia-reveal'><div class='aia-kicker'>YOU ARE</div>"
        f"<div class='aia-team'>{team}</div><div class='aia-mission'>MISSION 01<br>FIND YOUR PEOPLE</div>"
        f"<div class='aia-kicker' style='margin-top:1rem'>TEAM ROSTER · {len(members)} MEMBERS</div>{''.join(rows)}</div>",
        unsafe_allow_html=True,
    )
    st.caption("UAT-only technical capacity fixture — Quest teams are not the final AIA grouping.")


def _recover_binding(runtime, event_id: str, join_code: str, credential: str, device_id: str) -> tuple[dict | None, str]:
    """Recover only by the browser-local credential and its device binding."""
    try:
        player = runtime.recover_team_formation_participant(join_code, credential, device_id)
    except RuntimeDatabaseError as error:
        return None, str(error)
    return (player if _valid(player, event_id) else None), ""


def _render_reconnect(runtime, event_id: str, join_code: str, credential: str, device_id: str) -> None:
    """A retry control for a known persisted binding and transient failure only."""
    if st.button("RECONNECT / CONTINUE", width="stretch", key="aia_random_reconnect"):
        player, _ = _recover_binding(runtime, event_id, join_code, credential, device_id)
        if not _valid(player, event_id):
            st.error("This device cannot restore a completed AIA registration. Ask a facilitator for recovery.")
            return
        restore_participant_identity(player)
        _persist_session(player, event_id)
        st.rerun()


def render_aia_random_registration() -> None:
    runtime = get_standard_database()
    event_id, join_code = aia_random_registration_event()
    binding = participant_device_binding(event_id, key=f"aia_random_binding_{event_id}")
    if binding is None:
        st.title("AIA TECH · MISSION AI")
        st.info("Restoring this device securely…")
        return
    credential = binding["Credential"]
    device_id = binding["DeviceID"]
    st.session_state["participant_device_id"] = device_id
    player = _restore(runtime, event_id)
    if not _valid(player, event_id) and binding["HasStoredCredential"]:
        player, recovery_error = _recover_binding(runtime, event_id, join_code, credential, device_id)
        if _valid(player, event_id):
            restore_participant_identity(player)
            _persist_session(player, event_id)
            st.rerun()
        # A stored credential without a completed registration is safe to use
        # for first registration. Any other recovery failure is transient or
        # authoritative and must not fall through to a duplicate registration.
        if recovery_error and "TEAM_FORMATION_RECOVERY_CREDENTIAL_INVALID" not in recovery_error:
            st.error("Mission AI could not restore this device yet.")
            _render_reconnect(runtime, event_id, join_code, credential, device_id)
            return
    if _valid(player, event_id):
        _persist_session(player, event_id)
        watch_maxis_live_state(runtime, player["SessionToken"])
        render_participant_announcements(runtime, session_token=player["SessionToken"])
        render_live_location_participant(
            runtime, session_token=player["SessionToken"], device_id=device_id,
        )
        try:
            workspace = runtime.theme_park_race_participant_workspace(player["SessionToken"])
        except RuntimeDatabaseError:
            st.warning("Mission AI is reconnecting. Please retry in a moment.")
            return
        if str(workspace.get("Lifecycle", "")).upper() in {"TEAM_FORMATION", "FORMATION_LOCKED"}:
            _render_team_reveal(workspace)
            return
        render_aia_theme_park_participant(runtime, enrollment_credential=credential, device_id=device_id, workspace=workspace)
        return

    try:
        event = runtime.get_event_by_join_code(join_code)
    except RuntimeDatabaseError:
        event = None
    if not event or str(event.get("EventID", "")) != event_id:
        st.error("AIA Tech Mission AI is not available yet.")
        return

    st.title("AIA TECH · MISSION AI")
    st.caption("Enter your name once. This device will securely reconnect you to your Mission AI team.")
    with st.form("aia_random_registration", clear_on_submit=False):
        first_name = st.text_input("FIRST / GIVEN NAME", autocomplete="given-name")
        last_name = st.text_input("LAST / FAMILY NAME", autocomplete="family-name")
        submitted = st.form_submit_button("ENTER MISSION AI", type="primary", width="stretch")
    if submitted:
        name = normalise_join_name(first_name, last_name)
        if not first_name.strip() or not last_name.strip():
            st.error("Enter both your first / given name and last / family name.")
        elif not credential:
            st.info("Securing this device. Please tap ENTER MISSION AI once more.")
        else:
            try:
                player = runtime.register_aia_random_participant(name, device_id, credential)
            except RuntimeDatabaseError as error:
                st.error(str(error) or "Registration could not be completed. Please try again.")
                player = None
            if _valid(player, event_id):
                restore_participant_identity(player)
                _persist_session(player, event_id)
                st.rerun()
    st.caption("Changed device, accidental duplicate, or same-name issue? Ask a facilitator for canonical recovery.")
