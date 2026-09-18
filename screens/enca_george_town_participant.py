"""Participant surface for ENCA's hybrid anchored George Town architecture."""
from __future__ import annotations

import secrets

import streamlit as st

from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import get_standard_database
from screens.hunt_participant import _dashboard, _persist_session, _restore, _valid
from screens.participant import normalise_join_name, restore_participant_identity
from services.personal_key_credentials import derive_personal_key_credential


_CONNECTION_MESSAGE = (
    "Mission AI is temporarily unavailable. Please retry shortly or contact Mission Control."
)


def _session_binding(event_id: str) -> dict[str, str]:
    """Create opaque, per-browser-session registration values without an iframe.

    Reconnect uses the canonical opaque ``session_token`` URL parameter written
    by ``_persist_session``. These values are only needed for the initial
    registration or HOD claim, so a legacy browser-storage component is not on
    the landing-page render path.
    """
    key = f"enca_participant_binding_{event_id}"
    current = st.session_state.get(key)
    if isinstance(current, dict) and all(
        isinstance(current.get(name), str) and len(current[name]) == 43
        for name in ("Credential", "DeviceID")
    ):
        return {"Credential": current["Credential"], "DeviceID": current["DeviceID"]}
    binding = {
        "Credential": secrets.token_urlsafe(32),
        "DeviceID": secrets.token_urlsafe(32),
    }
    st.session_state[key] = binding
    return binding


def _has_resume_token() -> bool:
    token = st.session_state.get("participant_session_token", "") or st.query_params.get("session_token", "")
    if isinstance(token, (list, tuple)):
        token = token[0] if token else ""
    return bool(str(token or "").strip())


def _event_is_available(runtime, event_id: str, join_code: str) -> bool:
    try:
        event = runtime.get_event_by_join_code(join_code)
    except RuntimeDatabaseError:
        st.error(_CONNECTION_MESSAGE)
        return False
    if event and str(event.get("EventID") or "") == event_id:
        return True
    st.error("This ENCA Mission AI event is not available yet. Please retry shortly or contact Mission Control.")
    return False


def _complete_identity(player: dict | None, event_id: str, *, hod_credential: str = "") -> bool:
    if not _valid(player, event_id):
        return False
    if hod_credential:
        st.session_state["enca_hod_credential"] = hod_credential
    restore_participant_identity(player)
    _persist_session(player, event_id)
    st.rerun()
    return True


def _render_runtime_message() -> None:
    st.error(
        "Mission AI’s secure event connection is not configured yet. "
        "Please ask the event team to verify this deployment, then reload."
    )


def _runtime_or_none():
    """Open the runtime only for an explicit participant action or resume."""
    try:
        return get_standard_database()
    except RuntimeDatabaseError:
        _render_runtime_message()
        return None


def render_enca_george_town_participant(*, event_id: str, join_code: str) -> None:
    """One common QR for general participants plus a separate visible HOD path."""
    # These native elements deliberately precede all runtime work. A future
    # connection or configuration fault therefore presents an actionable page,
    # never an unexplained empty Streamlit shell.
    st.title("ENCA GROUP")
    st.subheader("MISSION AI")
    st.caption("GEORGE TOWN UAT")
    st.info("Enter once to join your country team. Mission AI assigns general participants automatically and reconnects this device safely.")

    if _has_resume_token():
        runtime = _runtime_or_none()
        if runtime is None:
            return
        binding = _session_binding(event_id)
        credential, device_id = binding["Credential"], binding["DeviceID"]
        st.session_state["participant_device_id"] = device_id
        player = _restore(runtime, event_id)
        if _valid(player, event_id):
            _persist_session(player, event_id)
            _dashboard(
                runtime, player, device_id,
                join_code=join_code,
                credential=str(st.session_state.get("enca_hod_credential") or credential),
                workspace_loader=runtime.hybrid_anchored_hunt_workspace,
            )
            return

    st.subheader("GENERAL PARTICIPANT")
    with st.form("enca_general_registration", clear_on_submit=False):
        first_name = st.text_input("First / Given Name", autocomplete="given-name")
        last_name = st.text_input("Last / Family Name", autocomplete="family-name")
        entered = st.form_submit_button("ENTER MISSION AI", type="primary", width="stretch")
    if entered:
        name = normalise_join_name(first_name, last_name)
        if not first_name.strip() or not last_name.strip():
            st.error("Enter both your first / given and last / family name.")
        else:
            runtime = _runtime_or_none()
            if runtime is not None and _event_is_available(runtime, event_id, join_code):
                binding = _session_binding(event_id)
                credential, device_id = binding["Credential"], binding["DeviceID"]
                st.session_state["participant_device_id"] = device_id
                try:
                    player = runtime.register_hybrid_anchored_random_participant(join_code, name, device_id, credential)
                except RuntimeDatabaseError:
                    st.error(_CONNECTION_MESSAGE)
                else:
                    if not _complete_identity(player, event_id):
                        st.error("This registration is already linked to another device. Reopen Mission AI on the original device or contact Mission Control.")

    st.divider()
    st.subheader("HOD / PRE-REGISTERED")
    st.caption("HODs: enter the Personal Key supplied to you. Your team chooses its Mission Captain later.")
    with st.form("enca_hod_personal_key", clear_on_submit=False):
        personal_key = st.text_input("Personal Key", type="password", autocomplete="one-time-code")
        claimed = st.form_submit_button("CONTINUE", width="stretch")
    if claimed:
        if not personal_key.strip():
            st.error("Enter your Personal Key to continue.")
        else:
            runtime = _runtime_or_none()
            if runtime is not None and _event_is_available(runtime, event_id, join_code):
                binding = _session_binding(event_id)
                device_id = binding["DeviceID"]
                st.session_state["participant_device_id"] = device_id
                try:
                    hod_credential = derive_personal_key_credential(event_id, personal_key)
                    player = runtime.claim_hybrid_anchored_hod_personal_key(join_code, hod_credential, device_id)
                except ValueError:
                    st.error("Enter a valid Personal Key and try again.")
                except RuntimeDatabaseError:
                    st.error("This Personal Key could not be used right now. Please retry shortly or contact Mission Control.")
                else:
                    if not _complete_identity(player, event_id, hod_credential=hod_credential):
                        st.error("This HOD identity is already linked to another device. Reopen Mission AI on the original device or contact Mission Control.")
