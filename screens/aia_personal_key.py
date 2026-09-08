"""AIA Personal Key entry that claims only canonical PREASSIGNED identities."""
from __future__ import annotations

import streamlit as st

from data.runtime_database import RuntimeDatabaseError
from data.standard_core_v2_adapter import get_standard_database
from screens.participant import participant_device_id, restore_participant_identity
from screens.aia_participant_experience import render_aia_theme_park_participant
from services.maxis_live_state import watch_maxis_live_state
from services.personal_key_credentials import derive_personal_key_credential
from services.aia_personal_key_event import aia_personal_key_event


def _valid(player: dict | None, event_id: str) -> bool:
    return bool(player and str(player.get("EventID", "")) == event_id and player.get("ParticipantID") and player.get("SessionToken"))


def _restore(runtime, event_id: str) -> dict | None:
    token = str(st.session_state.get("participant_session_token", "") or st.query_params.get("session_token", "")).strip()
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
    """Show the canonical UAT team and roster before Captain selection begins."""
    st.title("AIA TECH · MISSION AI")
    st.subheader(f"YOUR TEAM: {workspace.get('TeamIdentity') or 'QUEST'}")
    st.success("Find your Quest team, then wait for Mission Control to open Captain selection.")
    members = [str(row.get("Name") or "").strip() for row in workspace.get("TeamMembers") or []]
    if members:
        st.caption("Canonical team roster")
        st.write(" · ".join(members))
    st.caption("Synthetic UAT roster — not the final AIA participant grouping.")


def render_aia_personal_key_login() -> None:
    runtime = get_standard_database()
    event_id, join_code = aia_personal_key_event()
    player = _restore(runtime, event_id)
    if player:
        watch_maxis_live_state(runtime, player["SessionToken"])
        try:
            workspace = runtime.theme_park_race_participant_workspace(player["SessionToken"])
        except RuntimeDatabaseError:
            workspace = {}
        if str(workspace.get("Lifecycle", "")).upper() in {"TEAM_FORMATION", "FORMATION_LOCKED"}:
            _render_team_reveal(workspace)
            return
        render_aia_theme_park_participant(runtime, device_id=participant_device_id(), workspace=workspace)
        return
    try:
        event = runtime.get_event_by_join_code(join_code)
    except RuntimeDatabaseError:
        event = None
    if not event or str(event.get("EventID", "")) != event_id:
        st.error("AIA Tech Mission AI is not available yet.")
        return
    st.title("AIA TECH · MISSION AI")
    st.caption("Enter the Personal Key issued with your canonical roster identity.")
    with st.form("aia_personal_key_form", clear_on_submit=True):
        personal_key = st.text_input("PERSONAL KEY", type="password", autocomplete="off")
        submitted = st.form_submit_button("ENTER MISSION AI", type="primary", width="stretch")
    if not submitted:
        return
    try:
        credential = derive_personal_key_credential(event_id, personal_key)
        phase = str(((event.get("_EventPayload") or {}).get("TeamFormation") or {}).get("Phase") or "").upper()
        if phase in {"FORMATION_LOCKED", "CAPTAIN_SELECTION", "ACTIVE"}:
            player = runtime.recover_team_formation_participant(join_code, credential, participant_device_id())
        else:
            player = runtime.claim_preassigned_team_formation_participant(join_code, credential, participant_device_id())
    except (RuntimeDatabaseError, ValueError):
        player = None
    if not _valid(player, event_id) or player.get("RecoveryRequired"):
        st.error("That Personal Key was not recognised. Check the code issued beside your roster identity.")
        return
    restore_participant_identity(player)
    st.session_state["participant_join_code"] = join_code
    st.query_params.update({"personal_key": "1", "join_code": join_code, "event_id": event_id,
                            "session_token": player["SessionToken"], "device_id": participant_device_id()})
    st.rerun()
