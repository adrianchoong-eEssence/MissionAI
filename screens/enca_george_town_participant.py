"""Participant surface for ENCA's hybrid anchored George Town architecture."""
from __future__ import annotations

import secrets

import streamlit as st

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


def _normalise_join_name(first_name: str, last_name: str) -> str:
    return " ".join(" ".join([str(first_name or ""), str(last_name or "")]).split())


def _restore_participant_identity(player: dict) -> None:
    """Persist only canonical identity returned by the public participant RPC."""
    fields = {
        "participant_id": player.get("ParticipantID", ""),
        "participant_event_id": player.get("EventID", ""),
        "participant_name": player.get("Name", ""),
        "participant_team": player.get("Team", ""),
        "participant_team_id": player.get("TeamID", ""),
        "participant_country": player.get("Country", ""),
        "participant_flag": player.get("Flag", ""),
        "participant_is_leader": bool(player.get("IsLeader", False)),
        "participant_points": player.get("Points", 0),
        "participant_event_name": player.get("EventName", "EXOS Event"),
        "participant_session_token": player.get("SessionToken", ""),
    }
    st.session_state.update(fields)


def _persist_session(player: dict, event_id: str) -> None:
    for name, value in {
        "event_id": event_id,
        "session_token": str(player.get("SessionToken") or ""),
    }.items():
        if value and _query_value(name) != value:
            st.query_params[name] = value
    for name in list(st.query_params):
        if str(name).casefold() in {
            "join_code",
            "credential",
            "enrollment_credential",
            "device_id",
            "participant_name",
        }:
            del st.query_params[name]


def _restore(runtime, event_id: str) -> dict | None:
    token = str(st.session_state.get("participant_session_token", "") or _query_value("session_token")).strip()
    if not token:
        return None
    try:
        player = runtime.get_player_by_token(token)
    except Exception:
        return None
    if _valid(player, event_id):
        _restore_participant_identity(player)
        return player
    return None


def _complete_identity(player: dict | None, event_id: str, *, hod_credential: str = "") -> bool:
    if not _valid(player, event_id):
        return False
    if hod_credential:
        st.session_state["enca_hod_credential"] = hod_credential
    _restore_participant_identity(player)
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
        # Keep the cold landing page independent of the full runtime and its
        # legacy participant-component import graph.
        from data.standard_core_v2_adapter import get_standard_database

        return get_standard_database()
    except Exception:
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
            # The dashboard is intentionally lazy: the bare landing page must
            # not load optional browser components before it can render.
            from screens.hunt_participant import _dashboard

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
        name = _normalise_join_name(first_name, last_name)
        if not first_name.strip() or not last_name.strip():
            st.error("Enter both your first / given and last / family name.")
        else:
            runtime = _runtime_or_none()
            if runtime is not None:
                binding = _session_binding(event_id)
                credential, device_id = binding["Credential"], binding["DeviceID"]
                st.session_state["participant_device_id"] = device_id
                try:
                    player = runtime.register_hybrid_anchored_random_participant(join_code, name, device_id, credential)
                except Exception:
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
            if runtime is not None:
                binding = _session_binding(event_id)
                device_id = binding["DeviceID"]
                st.session_state["participant_device_id"] = device_id
                try:
                    hod_credential = derive_personal_key_credential(event_id, personal_key)
                    player = runtime.claim_hybrid_anchored_hod_personal_key(join_code, hod_credential, device_id)
                except ValueError:
                    st.error("Enter a valid Personal Key and try again.")
                except Exception:
                    st.error("This Personal Key could not be used right now. Please retry shortly or contact Mission Control.")
                else:
                    if not _complete_identity(player, event_id, hod_credential=hod_credential):
                        st.error("This HOD identity is already linked to another device. Reopen Mission AI on the original device or contact Mission Control.")
