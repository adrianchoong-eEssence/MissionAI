"""Participant consent, visible status, and in-app announcements for V1."""
from __future__ import annotations

from datetime import datetime
import html

import streamlit as st

from components.live_location import participant_live_location
from data.runtime_database import RuntimeDatabaseError


def _time(value) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
    except ValueError:
        return str(value)


def _recovery_guidance(status: str) -> str:
    if status == "STALE":
        return "No recent GPS reading. Keep this page open, check permission, GPS and network, then move briefly to refresh."
    if status == "UNAVAILABLE":
        return "Location is unavailable. Check browser permission, device location services and network; reopen this page to resume."
    return "Keep this page open while sharing. Browser background and screen-lock GPS behaviour depends on your device and browser."


def render_live_location_participant(runtime, *, session_token: str, device_id: str) -> None:
    """Render only an event's explicitly configured tracking capability."""
    try:
        state = runtime.get_live_location_participant_state(session_token)
    except RuntimeDatabaseError:
        return  # migration absent or a transient state read must not block play
    if not state.get("Configured"):
        return
    if not state.get("Enabled"):
        st.caption("📍 Live location is not active for this event right now.")
        return
    event_id = str(state.get("EventID", ""))
    consent = str(state.get("ConsentState", "")).upper() == "ENABLED"
    status = str(state.get("Status", "UNAVAILABLE")).upper()
    st.divider()
    st.subheader("📍 LIVE LOCATION")
    if not consent:
        st.info("Mission AI can share your live location with authorised event facilitators during this activity to support navigation, team coordination and safety.")
        if st.button("ENABLE LIVE LOCATION", type="primary", width="stretch", key=f"live_location_enable_{event_id}"):
            try:
                runtime.set_live_location_consent(session_token, True)
            except RuntimeDatabaseError as error:
                st.error("LOCATION UNAVAILABLE. Check that event tracking is active, then try again.")
                st.caption(str(error))
            else:
                st.rerun()
        return
    st.success("📍 LIVE LOCATION ON" if status == "CURRENT" else "📍 LIVE LOCATION ON — waiting for a current GPS reading")
    st.markdown(f"**LOCATION STATUS**  \\n+{status}")
    st.caption(f"LAST UPDATE: {_time(state.get('LastUpdate'))} · ACCURACY: {state.get('AccuracyMeters') if state.get('AccuracyMeters') is not None else '—'} m")
    st.caption(_recovery_guidance(status))
    reading = participant_live_location(cadence_seconds=state.get("CadenceSeconds", 20), key=f"live_location_{event_id}")
    if not isinstance(reading, dict):
        return
    if str(reading.get("Action", "")).upper() == "STOPPED":
        try:
            runtime.set_live_location_consent(session_token, False)
        except RuntimeDatabaseError:
            st.warning("Location stop is reconnecting. Close this control and try again.")
        else:
            st.rerun()
        return
    if str(reading.get("Action", "")).upper() != "LOCATION":
        return
    signature = str(reading.get("Sequence", "")) + str(reading.get("captured_at", ""))
    last_key = f"live_location_sent_{event_id}"
    if not signature or signature == st.session_state.get(last_key):
        return
    try:
        accepted = runtime.submit_live_location(session_token, device_id, reading)
    except (RuntimeDatabaseError, KeyError, TypeError, ValueError) as error:
        st.warning("LOCATION UNAVAILABLE. Keep this page open and check device permission, GPS, and network.")
        st.caption(str(error))
        return
    st.session_state[last_key] = signature
    st.caption(f"📍 LIVE LOCATION ON · Last update: {_time(accepted.get('CapturedAt'))}")


def render_participant_announcements(runtime, *, session_token: str) -> None:
    """Show only canonical, event-targeted in-app announcements."""
    rows = st.session_state.get("exos_participant_announcements")
    if rows is None:
        try:
            rows = runtime.get_participant_announcements(session_token)
        except RuntimeDatabaseError:
            return
        st.session_state["exos_participant_announcements"] = rows
    for announcement in list(rows or []):
        severity = str(announcement.get("Severity", "INFO")).upper()
        title = html.escape(str(announcement.get("Title") or "Mission AI update"))
        message = html.escape(str(announcement.get("Message") or ""))
        label = f"{severity} · {title}"
        if severity == "URGENT":
            st.error(f"{label}\n\n{message}")
        elif severity == "IMPORTANT":
            st.warning(f"{label}\n\n{message}")
        else:
            st.info(f"{label}\n\n{message}")
        if announcement.get("AcknowledgementRequired") and not announcement.get("AcknowledgedAt"):
            announcement_id = str(announcement.get("AnnouncementID", ""))
            if st.button("ACKNOWLEDGE", key=f"announcement_ack_{announcement_id}", width="stretch"):
                try:
                    runtime.acknowledge_event_announcement(session_token, announcement_id)
                except RuntimeDatabaseError as error:
                    st.error("Acknowledgement could not be recorded. Please retry.")
                    st.caption(str(error))
                else:
                    st.session_state.pop("exos_participant_announcements", None)
                    st.rerun()
