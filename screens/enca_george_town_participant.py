"""Participant surface for ENCA's hybrid anchored George Town architecture."""
from __future__ import annotations

import streamlit as st

from components.participant_credential import participant_device_binding
from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import get_standard_database
from screens.hunt_participant import _dashboard, _persist_session, _restore, _valid
from screens.participant import normalise_join_name, restore_participant_identity
from services.personal_key_credentials import derive_personal_key_credential


def _recover_common_qr_identity(runtime, event_id: str, join_code: str, credential: str, device_id: str) -> dict | None:
    """Restore only the common-QR browser credential; HOD keys stay manual."""
    try:
        candidate = runtime.recover_team_formation_participant(join_code, credential, device_id)
    except RuntimeDatabaseError as error:
        if "RECOVERY_CREDENTIAL_INVALID" not in str(error):
            st.error("Mission AI could not restore this device yet. Please retry shortly.")
        return None
    return candidate if _valid(candidate, event_id) else None


def render_enca_george_town_participant(*, event_id: str, join_code: str) -> None:
    """One common QR for 124 general participants plus a separate HOD key path."""
    runtime = get_standard_database()
    binding = participant_device_binding(event_id, key=f"enca_hybrid_binding_{event_id}")
    if binding is None:
        st.title("ENCA TEAM BUILDING 2026")
        st.info("Restoring this device securely…")
        return
    credential, device_id = binding["Credential"], binding["DeviceID"]
    st.session_state["participant_device_id"] = device_id
    player = _restore(runtime, event_id)
    if not _valid(player, event_id) and binding.get("HasStoredCredential"):
        player = _recover_common_qr_identity(runtime, event_id, join_code, credential, device_id)
        if _valid(player, event_id):
            restore_participant_identity(player)
            _persist_session(player, event_id)
            st.rerun()
    if _valid(player, event_id):
        _persist_session(player, event_id)
        _dashboard(
            runtime, player, device_id, join_code=join_code,
            credential=str(st.session_state.get("enca_hod_credential") or credential),
            workspace_loader=runtime.hybrid_anchored_hunt_workspace,
        )
        return
    try:
        event = runtime.get_event_by_join_code(join_code)
    except RuntimeDatabaseError:
        event = None
    if not event or str(event.get("EventID") or "") != event_id:
        st.error("This ENCA Mission AI event is not available yet.")
        return
    st.title("ENCA TEAM BUILDING 2026")
    st.caption("GEORGE TOWN · MISSION AI")
    st.info("Enter your name once. Mission AI will assign a country team automatically and reconnect this device safely.")
    with st.form("enca_general_registration", clear_on_submit=False):
        first_name = st.text_input("FIRST / GIVEN NAME", autocomplete="given-name")
        last_name = st.text_input("LAST / FAMILY NAME", autocomplete="family-name")
        entered = st.form_submit_button("ENTER MISSION AI", type="primary", width="stretch")
    if entered:
        name = normalise_join_name(first_name, last_name)
        if not first_name.strip() or not last_name.strip():
            st.error("Enter both your first / given and last / family name.")
        else:
            try:
                player = runtime.register_hybrid_anchored_random_participant(join_code, name, device_id, credential)
            except RuntimeDatabaseError as error:
                st.error(str(error) or "Registration could not be completed. Please try again.")
            else:
                if _valid(player, event_id):
                    restore_participant_identity(player)
                    _persist_session(player, event_id)
                    st.rerun()
                st.error("This registration is already linked to another device. Reopen Mission AI on the original device or contact Mission Control.")
    with st.expander("HOD PERSONAL KEY"):
        st.caption("HODs: enter the Personal Key supplied to you. A Personal Key does not make you Captain.")
        with st.form("enca_hod_personal_key", clear_on_submit=True):
            personal_key = st.text_input("PERSONAL KEY", type="password", autocomplete="one-time-code")
            claimed = st.form_submit_button("ENTER AS HOD", width="stretch")
        if claimed:
            try:
                hod_credential = derive_personal_key_credential(event_id, personal_key)
                player = runtime.claim_hybrid_anchored_hod_personal_key(join_code, hod_credential, device_id)
            except (RuntimeDatabaseError, ValueError) as error:
                st.error(str(error) or "HOD access could not be completed. Please try again.")
            else:
                if _valid(player, event_id):
                    st.session_state["enca_hod_credential"] = hod_credential
                    restore_participant_identity(player)
                    _persist_session(player, event_id)
                    st.rerun()
                st.error("This HOD identity is already linked to another device. Reopen Mission AI on the original device or contact Mission Control.")
