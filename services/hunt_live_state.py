"""Scoped five-second Hunt participant watcher; it never performs a write."""
from __future__ import annotations

import streamlit as st

from data.runtime_database import RuntimeDatabaseError


POLL_INTERVAL_SECONDS = 5


def hunt_live_signature(workspace: dict, announcements: list[dict] | None) -> tuple:
    missions = tuple(sorted(
        (str(row.get("MissionID", "")), str(row.get("MissionState", "")), bool(row.get("Visible", True)))
        for row in list(workspace.get("Missions") or [])
    ))
    announcement_signature = tuple(sorted(
        (str(row.get("AnnouncementID", "")), str(row.get("AcknowledgedAt", "")))
        for row in list(announcements or [])
    ))
    return (
        str(workspace.get("OperationalState", "")), str(workspace.get("TeamFormationPhase", "")),
        str(workspace.get("CaptainName", "")), tuple(sorted(dict(workspace.get("Progress") or {}).items())),
        missions, announcement_signature,
    )


@st.fragment(run_every=f"{POLL_INTERVAL_SECONDS}s")
def watch_hunt_live_state(runtime, session_token: str, workspace_loader=None) -> None:
    if not str(session_token or "").strip():
        return
    try:
        workspace = (workspace_loader or runtime.hunt_participant_workspace)(session_token)
        announcements = runtime.get_participant_announcements(session_token)
    except RuntimeDatabaseError:
        return
    st.session_state["exos_participant_announcements"] = announcements
    signature = hunt_live_signature(workspace, announcements)
    key = "hunt_live_state_signature"
    previous = st.session_state.get(key)
    st.session_state[key] = signature
    if previous is not None and previous != signature:
        st.rerun(scope="app")
