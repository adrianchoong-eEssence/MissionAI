"""Read-only live-state watcher for the Maxis participant shell.

The Maxis Personal Key entrypoint intentionally bypasses the generic
participant shell, so it needs its own narrow bridge to the existing canonical
Theme Park Race workspace.  This module owns no state: it polls the existing
workspace every five seconds and requests a full rerun only after a meaningful
server-side state change.
"""
from __future__ import annotations

import streamlit as st

from data.runtime_database import RuntimeDatabaseError


POLL_INTERVAL_SECONDS = 5
_SIGNATURE_KEY = "maxis_live_state_signature"


def workspace_live_signature(workspace: dict) -> tuple:
    """Return the participant-visible canonical state, in a stable order.

    The workspace is the sole source of truth.  Keeping widget values out of
    this signature means ordinary typing, uploads and Mission AI questions can
    never trigger a rerun; only facilitator/runtime/score changes can.
    """
    board = tuple(sorted(
        (
            str(mission.get("ActivityID") or ""),
            str(mission.get("MissionState") or ""),
            str(mission.get("OperationalStatus") or ""),
            str(mission.get("SecretState") or ""),
        )
        for mission in list(workspace.get("MissionBoard") or [])
    ))
    progress = dict(workspace.get("Progress") or {})
    return (
        str(workspace.get("EventID") or ""),
        str(workspace.get("TeamFormationPhase") or ""),
        str(workspace.get("Lifecycle") or ""),
        str(workspace.get("RuntimePhase") or ""),
        str(workspace.get("CaptainParticipantID") or ""),
        bool(workspace.get("CaptainSessionActive")),
        bool(workspace.get("CanClaimCaptain")),
        int(progress.get("Completed") or 0),
        int(progress.get("PendingReview") or 0),
        int(progress.get("Approved") or 0),
        int(progress.get("Rejected") or 0),
        float(workspace.get("TeamScore") or 0),
        board,
    )


def _canonical_team_score(runtime, workspace: dict) -> float:
    """Read the existing ledger projection only for the live watcher."""
    try:
        leaderboard = runtime.get_canonical_leaderboard(workspace.get("EventID", ""))
    except (AttributeError, RuntimeDatabaseError):
        return 0.0
    team_id = str(workspace.get("TeamID", ""))
    return float(next(
        (row.get("Score", 0) for row in leaderboard
         if str(row.get("TeamID", "")) == team_id),
        0,
    ) or 0)


@st.fragment(run_every=f"{POLL_INTERVAL_SECONDS}s")
def watch_maxis_live_state(runtime, session_token: str) -> None:
    """Watch canonical state without performing any participant-side write.

    A fragment refresh is deliberately cheap and isolated.  It escalates to an
    app rerun only after a canonical-state transition, allowing the surrounding
    Streamlit widgets to keep their keyed state while a participant is entering
    text or selecting evidence.  A real lifecycle safety change (for example a
    HOLD) is applied immediately on the next poll.
    """
    if not str(session_token or "").strip():
        return
    try:
        workspace = runtime.theme_park_race_participant_workspace(session_token)
    except RuntimeDatabaseError:
        # The normal shell already presents human-facing reconnect feedback.
        # Polling never writes an error state or surfaces a raw RPC exception.
        return

    # A review updates both the board and the ledger.  Read the existing
    # canonical score projection here so a ledger-only adjustment is visible,
    # without changing the broadly reused workspace adapter contract.
    workspace = dict(workspace)
    workspace["TeamScore"] = _canonical_team_score(runtime, workspace)
    signature = workspace_live_signature(workspace)
    previous = st.session_state.get(_SIGNATURE_KEY)
    st.session_state[_SIGNATURE_KEY] = signature
    if previous is not None and previous != signature:
        st.rerun(scope="app")
