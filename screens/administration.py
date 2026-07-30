import json
from datetime import datetime

import streamlit as st

from data.google_sheets import GoogleSheetsDB


APP_VERSION = "EXOS 2026.07 Consolidation RC1"
BUILD_TIMESTAMP = "2026-07-28"


def show_administration():
    st.title("Administration")
    st.caption("System information, data safety and recoverable archives.")
    st.info(f"Version: {APP_VERSION} · Build: {BUILD_TIMESTAMP}")
    st.toggle(
        "Administration mode",
        key="exos_administration_mode",
        help="Shows internal identifiers in authoring screens.",
    )
    db = GoogleSheetsDB()

    st.subheader("Data Safety & Legacy Events")
    snapshot = db.export_backup_snapshot()
    exported_at = str(snapshot.get("ExportedAt", ""))
    filename = (
        "exos-production-backup-"
        + datetime.now().strftime("%Y%m%d-%H%M%S")
        + ".json"
    )
    st.write(f"File: `{filename}`")
    st.write(f"Export time: `{exported_at}`")
    backup_ready = st.download_button(
        "Download Production Backup",
        data=json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
        file_name=filename,
        mime="application/json",
        type="primary",
        width="stretch",
    )
    if backup_ready:
        st.session_state["exos_backup_created"] = exported_at
        st.success(f"Backup prepared successfully at {exported_at}.")

    st.divider()
    st.subheader("Archive Legacy Event")
    st.caption("Archiving hides an event but does not delete its associated records.")
    events = db.get_events()
    if events:
        options = {
            f"{event.get('EventID', '')} — {event.get('EventName', '')}": event
            for event in events
        }
        label = st.selectbox("Event", list(options))
        event = options[label]
        event_id = str(event.get("EventID", ""))
        st.warning(
            f"Affected event: {event.get('EventName', '')} ({event_id})"
        )
        confirmation = st.text_input(f"Type {event_id} to confirm")
        can_archive = bool(
            st.session_state.get("exos_backup_created")
            and confirmation.strip() == event_id
        )
        if st.button(
            "Archive Event",
            disabled=not can_archive,
            width="stretch",
        ):
            db.archive_event(event_id)
            st.success("Event archived. Its records remain recoverable.")
            st.rerun()
    else:
        st.info("No active events are available to archive.")

    with st.expander("Restore archived event"):
        archived = [
            event for event in db.get_events(include_archived=True)
            if str(event.get("Status", "")).upper() == "ARCHIVED"
        ]
        if archived:
            restore_options = {
                f"{event.get('EventID', '')} — {event.get('EventName', '')}": event
                for event in archived
            }
            restore_label = st.selectbox("Archived event", list(restore_options))
            restore_event = restore_options[restore_label]
            if st.button("Restore Event", width="stretch"):
                db.restore_event(restore_event.get("EventID", ""))
                st.success("Event restored.")
                st.rerun()
        else:
            st.caption("No archived events.")
