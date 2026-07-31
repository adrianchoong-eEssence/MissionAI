import json
from datetime import datetime

import streamlit as st

from branding import PLATFORM_EXPANSION, PLATFORM_VERSION
from data.google_sheets import GoogleSheetsDB


APP_VERSION = PLATFORM_VERSION
BUILD_TIMESTAMP = "2026-07-28"
RESET_OPTIONS = {
    "Reset Participants": {
        "Type": "PARTICIPANTS",
        "Deletes": "Participants and their team membership",
        "Keeps": "Experiences and Programme",
    },
    "Reset Runtime": {
        "Type": "RUNTIME",
        "Deletes": (
            "Credits, leaderboard scores, submissions, photos, timers and "
            "live state"
        ),
        "Keeps": "Participants, Experiences and Programme",
    },
    "Factory Reset": {
        "Type": "FACTORY",
        "Deletes": "All other event-related operational records",
        "Keeps": (
            "Event, Programme, Experiences, characters and reference images"
        ),
    },
}


def reset_confirmation_matches(event_id, confirmation):
    expected = f"RESET {str(event_id).strip()}"
    return str(confirmation or "").strip() == expected


def render_event_reset(db):
    st.subheader("Reset Event")
    st.warning(
        "Reset operations are event-scoped and cannot be undone. Programme, "
        "Experience and protected media records are preserved as described."
    )
    events = db.get_events(include_archived=True)
    if not events:
        st.info("No events are available to reset.")
        return

    event_labels = {
        f"{event.get('EventID', '')} | {event.get('EventName', 'Unnamed event')}":
        event
        for event in events
    }
    selected_label = st.selectbox(
        "Event to reset",
        list(event_labels),
        key="administration_reset_event",
    )
    event_id = str(event_labels[selected_label].get("EventID", "")).strip()
    option = st.radio(
        "Reset option",
        list(RESET_OPTIONS),
        key=f"administration_reset_option_{event_id}",
    )
    scope = RESET_OPTIONS[option]
    with st.container(border=True):
        st.markdown(f"**Deletes:** {scope['Deletes']}")
        st.markdown(f"**Keeps:** {scope['Keeps']}")

    expected = f"RESET {event_id}"
    confirmation = st.text_input(
        f"Type {expected} to confirm",
        key=f"administration_reset_confirmation_{event_id}_{scope['Type']}",
    )
    confirmed = reset_confirmation_matches(event_id, confirmation)
    if st.button(
        option,
        type="primary",
        disabled=not confirmed,
        width="stretch",
        key=f"administration_reset_execute_{event_id}_{scope['Type']}",
    ):
        try:
            result = db.reset_event(event_id, scope["Type"])
        except Exception as error:
            st.error(f"Event reset failed: {error}")
        else:
            st.success(
                f"{result['EventID']} {option.lower()} completed. "
                "Programme and Experiences were preserved."
            )
            st.session_state.pop(
                f"administration_reset_confirmation_{event_id}_{scope['Type']}",
                None,
            )
            st.rerun()


def show_administration():
    st.title("Administration")
    st.caption("System information, data safety and recoverable archives.")
    st.info(f"Version: {APP_VERSION} · Build: {BUILD_TIMESTAMP}")
    with st.container(border=True):
        st.subheader("About EXOS")
        st.markdown("### EXOS")
        st.write(PLATFORM_EXPANSION)
        st.caption("Powered by eEssence Consultants Sdn Bhd")
    st.toggle(
        "Administration mode",
        key="exos_administration_mode",
        help="Shows internal identifiers in authoring screens.",
    )
    db = GoogleSheetsDB()

    st.divider()
    render_event_reset(db)

    st.divider()
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
    st.subheader("Archived Events")
    st.caption(
        "Restore an event with all data intact, or create an event-only backup "
        "before permanent deletion."
    )
    archived = [
        event for event in db.get_events(include_archived=True)
        if str(event.get("Status", "")).strip().upper() == "ARCHIVED"
    ]
    if not archived:
        st.info("No archived events.")
        return

    for event in archived:
        event_id = str(event.get("EventID", "")).strip()
        with st.container(border=True):
            st.subheader(str(event.get("EventName", "Unnamed event")))
            st.caption(
                f"{event.get('Client', '—')} · {event.get('EventDate', '—')} · "
                f"Event ID {event_id}"
            )
            restore_col, delete_col = st.columns(2)
            if restore_col.button(
                "Restore",
                key=f"restore_archived_{event_id}",
                width="stretch",
            ):
                db.restore_event(event_id)
                st.success(f"{event_id} restored with all event data intact.")
                st.rerun()

            with delete_col:
                with st.popover("Permanently Delete", width="stretch"):
                    st.error(
                        "This removes only this event and its related records. "
                        "It cannot be undone."
                    )
                    backup_key = f"event_delete_backup_{event_id}"
                    if st.button(
                        "Generate Event Backup",
                        key=f"generate_event_backup_{event_id}",
                        width="stretch",
                    ):
                        try:
                            st.session_state[backup_key] = db.export_event_backup(
                                event_id
                            )
                            st.success("Event backup generated successfully.")
                        except Exception as error:
                            st.session_state.pop(backup_key, None)
                            st.error(f"Backup generation failed: {error}")

                    event_backup = st.session_state.get(backup_key)
                    if event_backup:
                        backup_filename = (
                            f"EXOS-{event_id}-backup-"
                            + datetime.now().strftime("%Y%m%d-%H%M%S")
                            + ".json"
                        )
                        st.download_button(
                            "Download Event Backup",
                            data=json.dumps(
                                event_backup,
                                ensure_ascii=False,
                                indent=2,
                                default=str,
                            ),
                            file_name=backup_filename,
                            mime="application/json",
                            width="stretch",
                            key=f"download_event_backup_{event_id}",
                        )

                    typed_id = st.text_input(
                        f"Type {event_id} to confirm",
                        key=f"type_delete_event_{event_id}",
                    )
                    understands = st.checkbox(
                        "I understand this cannot be undone",
                        key=f"understand_delete_event_{event_id}",
                    )
                    final_confirmation = st.checkbox(
                        f"Final confirmation: permanently delete {event_id}",
                        key=f"final_delete_event_{event_id}",
                    )
                    can_delete = bool(
                        event_backup
                        and typed_id.strip() == event_id
                        and understands
                        and final_confirmation
                    )
                    if st.button(
                        "Permanently Delete",
                        key=f"permanent_delete_event_{event_id}",
                        type="primary",
                        disabled=not can_delete,
                        width="stretch",
                    ):
                        result = db.permanently_delete_event(
                            event_id,
                            event_backup,
                        )
                        st.session_state.pop(backup_key, None)
                        st.success(
                            f"{result['EventID']} permanently deleted. "
                            "Other events and master templates were not changed."
                        )
                        st.rerun()
