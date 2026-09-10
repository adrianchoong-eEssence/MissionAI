"""Reusable Mission Control surface for Core Live Location + Announcements V1."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from data.runtime_database import RuntimeDatabaseError
from engines.live_location import derive_team_locations


def render_live_location_and_announcements(db, event_id: str) -> None:
    """Render only when the Core V1 event configuration exists.

    There is deliberately no public projector path here and no source of a
    global current event: every RPC receives the selected Mission Control ID.
    """
    try:
        location = db.runtime.get_live_location_operator_map(event_id)
        announcements = db.runtime.get_event_announcements(event_id)
    except RuntimeDatabaseError as error:
        if "live_location" in str(error).casefold() or "announcement" in str(error).casefold() or "PGRST202" in str(error):
            return
        st.warning("Live Location / announcements are reconnecting.")
        st.caption(str(error))
        return

    st.divider()
    st.subheader("🗺️ LIVE MAP")
    participants = list(location.get("Participants") or [])
    threshold = float(location.get("SeparationThresholdMeters", 250) or 250)
    teams = derive_team_locations(participants, separation_threshold_meters=threshold)
    st.caption(f"Status is CURRENT within {location.get('StaleAfterSeconds', 90)} seconds; stale or dispersed reports are never averaged into a false team position.")
    all_view, team_view, individual_view = st.tabs(["ALL TEAMS", "TEAM", "INDIVIDUAL"])
    with all_view:
        st.dataframe(teams, hide_index=True, width="stretch")
        points = [row for row in participants if row.get("Status") == "CURRENT" and row.get("Latitude") is not None and row.get("Longitude") is not None]
        if points:
            st.map(pd.DataFrame(points), latitude="Latitude", longitude="Longitude", size=40)
        else:
            st.info("No current participant locations are available.")
    with team_view:
        team_ids = sorted({str(row.get("TeamID", "")) for row in participants if row.get("TeamID")})
        selected = st.selectbox("Team", team_ids, key=f"live_location_team_{event_id}") if team_ids else ""
        st.dataframe([row for row in participants if str(row.get("TeamID", "")) == selected], hide_index=True, width="stretch")
    with individual_view:
        options = {f"{row.get('ParticipantName', 'Participant')} · {row.get('TeamID', '')}": row for row in participants}
        selected_label = st.selectbox("Participant", list(options), key=f"live_location_participant_{event_id}") if options else ""
        selected = options.get(selected_label, {})
        if selected:
            try:
                trail = db.runtime.get_live_location_history(event_id, selected.get("ParticipantID"), 20)
            except RuntimeDatabaseError:
                trail = []
            st.caption("Recent movement trail — event-time history only; retention is controlled by event configuration.")
            st.dataframe(trail, hide_index=True, width="stretch")

    st.subheader("📣 SEND ANNOUNCEMENT")
    target_type = st.radio("Target", ["ALL", "TEAM", "PARTICIPANT"], horizontal=True, key=f"announcement_target_{event_id}")
    teams_catalogue = db.runtime.get_teams(event_id)
    people_catalogue = db.runtime.get_players(event_id)
    target_ids = []
    if target_type == "TEAM":
        labels = {str(row.get("Team", row.get("TeamName", row.get("TeamID", "")))): str(row.get("TeamID", "")) for row in teams_catalogue}
        target_ids = [labels[label] for label in st.multiselect("Team(s)", list(labels), key=f"announcement_teams_{event_id}")]
    elif target_type == "PARTICIPANT":
        labels = {f"{row.get('Name', '')} · {row.get('TeamID', '')}": str(row.get("ParticipantID", "")) for row in people_catalogue}
        target_ids = [labels[label] for label in st.multiselect("Participant(s)", list(labels), key=f"announcement_people_{event_id}")]
    severity = st.selectbox("Severity", ["INFO", "IMPORTANT", "URGENT"], key=f"announcement_severity_{event_id}")
    title = st.text_input("Title (optional)", key=f"announcement_title_{event_id}")
    message = st.text_area("Message", key=f"announcement_message_{event_id}")
    acknowledgement = st.checkbox("Require acknowledgement", key=f"announcement_ack_{event_id}")
    actor = st.text_input("Authorised operator", key=f"announcement_actor_{event_id}")
    confirm_all_urgent = target_type == "ALL" and severity == "URGENT" and st.checkbox(
        "Confirm ALL + URGENT announcement", key=f"announcement_confirm_all_urgent_{event_id}",
    )
    if st.button("SEND", type="primary", width="stretch", key=f"announcement_send_{event_id}"):
        try:
            db.runtime.send_event_announcement(
                event_id, target_type=target_type, target_ids=target_ids, severity=severity,
                title=title, message=message, expires_at=None, acknowledgement_required=acknowledgement,
                actor=actor, confirm_all_urgent=confirm_all_urgent,
            )
        except RuntimeDatabaseError as error:
            st.error(str(error))
        else:
            st.success("Announcement sent and audited.")
            st.rerun()
    if announcements:
        st.caption("Recent canonical announcements and acknowledgement counts")
        st.dataframe(announcements, hide_index=True, width="stretch")
