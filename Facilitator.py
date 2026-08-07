import csv
import io

import streamlit as st
from branding import apply_branding, configure_page, footer
from data.google_sheets import GoogleSheetsDB
from screens.app_state import ACTIVE_EVENT_KEY
from screens.control_centre import show_control_centre
from screens.formula_race import show_formula_race
from screens.live_event_console import show_live_event_console
from screens.event_manager import FORMULA_RACE_TEAMS
from data.control_runtime import ControlRuntime


NASI_EVENT_ID = "EVT-0016"
NASI_ACTIVITY_ID = "EVT-0016-ACT-2E1376BBA01C"


def _nasi_sections(remarks):
    text = str(remarks or "")
    markers = [
        ("N - New Ideas:", "New Ideas"),
        ("A - Areas for Improvement:", "Areas of Improvement"),
        ("S - Strengths:", "Strengths"),
        ("I - Implementation:", "Implementation"),
    ]
    values = {label: "" for _, label in markers}
    for index, (marker, label) in enumerate(markers):
        if marker not in text:
            continue
        start = text.index(marker) + len(marker)
        ends = [text.index(next_marker, start) for next_marker, _ in markers[index + 1:] if next_marker in text[start:]]
        values[label] = text[start:min(ends) if ends else len(text)].strip()
    return values, text


def _render_nasi_results(db):
    rows = [
        row for row in db.runtime.get_submissions(NASI_EVENT_ID)
        if str(row.get("MissionID", "")) == NASI_ACTIVITY_ID
        and str(row.get("SubmissionType", "")).upper() == "NASI"
    ]
    registered = db.get_participant_count(NASI_EVENT_ID)
    st.divider()
    st.subheader("NASI Results")
    a, b, c = st.columns(3)
    a.metric("Registered Participants", registered)
    b.metric("NASI Submitted", len(rows))
    c.metric("NASI Outstanding", max(registered - len(rows), 0))
    export_rows = []
    for row in rows:
        first, _, last = str(row.get("ParticipantName", "")).strip().partition(" ")
        values, raw = _nasi_sections(row.get("Remarks", ""))
        with st.expander(f"{row.get('ParticipantName', 'Participant')} · {row.get('TeamName', '')}", expanded=True):
            st.caption(f"Submitted: {row.get('SubmittedAt', '')}")
            for label in ("New Ideas", "Areas of Improvement", "Strengths", "Implementation"):
                st.markdown(f"**{label}**")
                st.write(values[label] or raw or "—")
        export_rows.append({"First Name": first, "Last Name": last, "Team": row.get("TeamName", ""), **values, "Submitted At": row.get("SubmittedAt", "")})
    if export_rows:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(export_rows[0]))
        writer.writeheader(); writer.writerows(export_rows)
        st.download_button("Download NASI CSV", output.getvalue(), "nasi-results.csv", "text/csv")

configure_page(layout="wide")
apply_branding()

db = GoogleSheetsDB()
requested_event_id = str(st.query_params.get("event_id", "")).strip()
requested_event = db.get_event(requested_event_id) if requested_event_id else {}
requested_name = str((requested_event or {}).get("EventName", "")).upper().replace(".", "")
requested_client = str((requested_event or {}).get("Client", "")).upper().replace("’", "'")
requested_is_race = (
    "FORMULA RACE" in requested_name
    or str((requested_event or {}).get("IdentityPolicy", "")).upper() == "PREASSIGNED_ONLY"
    or (requested_name.strip() == "RACE" and requested_client.strip() in {"LOREAL", "L'OREAL"})
)

if requested_is_race:
    st.session_state[ACTIVE_EVENT_KEY] = requested_event_id
    show_formula_race(db=db, event_id=requested_event_id)
    footer()
    st.stop()

mode = st.sidebar.radio(
    "Facilitator mode",
    ["Event Control", "Formula R.A.C.E."],
    key="facilitator_mode",
)

if mode == "Event Control":
    # The standard Control Centre is the authoritative operational surface for
    # every non-RACE event.  Keep Formula R.A.C.E. in its dedicated shell below.
    if requested_event_id:
        st.session_state[ACTIVE_EVENT_KEY] = requested_event_id
    show_control_centre()
    if str(st.session_state.get(ACTIVE_EVENT_KEY, "")) == NASI_EVENT_ID:
        _render_nasi_results(db)
else:
    workspace = st.sidebar.radio(
        "Formula R.A.C.E.",
        ["Dashboard", "Race Control", "Legacy Operations"],
        key="formula_race_facilitator_workspace",
    )

    if workspace == "Dashboard":
        events = db.get_events()
        race_events = []
        for event in events:
            event_name = str(event.get("EventName", "")).upper().replace(".", "").strip()
            client = str(event.get("Client", "")).upper().replace("’", "'").strip()
            if (
                "FORMULA RACE" in event_name
                or str(event.get("IdentityPolicy", "")).upper() == "PREASSIGNED_ONLY"
                or (event_name == "RACE" and client in {"LOREAL", "L'OREAL"})
            ):
                race_events.append(event)
        if not race_events:
            st.warning("No Formula R.A.C.E. event is configured. Create or label the event before launch.")
        else:
            labels = {f"{event.get('EventID')} · {event.get('EventName')}": event for event in race_events}
            selected = st.selectbox("Select Formula R.A.C.E. event", list(labels))
            event = labels[selected]
            event_id = str(event.get("EventID", ""))
            st.session_state[ACTIVE_EVENT_KEY] = event_id
            current_names = [str(team.get("TeamName", "")) for team in db.get_teams(event_id)]
            if current_names != FORMULA_RACE_TEAMS:
                st.warning("This event does not yet use the approved ten-team Formula R.A.C.E. roster.")
                confirmed = st.checkbox(
                    "Replace the event roster with the approved ten fixed teams",
                    key=f"confirm_race_roster_{event_id}",
                )
                if st.button("Apply Approved Team Roster", disabled=not confirmed, width="stretch"):
                    rows = [
                        {"TeamID": f"F1-{position:02d}", "TeamName": name, "Status": "Active"}
                        for position, name in enumerate(FORMULA_RACE_TEAMS, start=1)
                    ]
                    db.replace_event_teams(event_id, rows)
                    ControlRuntime(db).restart_runtime(event_id)
                    st.success("The approved ten-team roster is now published.")
                    st.rerun()
            show_formula_race(db=db, event_id=event_id)
    elif workspace == "Race Control":
        show_control_centre()
    else:
        show_live_event_console()
footer()
