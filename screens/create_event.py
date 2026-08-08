import json

import streamlit as st

from data.google_sheets import GoogleSheetsDB
from screens.app_state import ACTIVE_EVENT_KEY, request_navigation


PROGRAMME_TYPES = [
    "Mission AI",
    "Formula R.A.C.E.",
    "AGILE",
    "Enterprise AGILE",
    "Road Rally",
    "Walk Hunt",
    "F1 Circuit",
    "Catalyst",
    "CSR",
    "Team Building",
    "Corporate Training",
]


def _event_defaults(event):
    metadata = GoogleSheetsDB.event_metadata(event)
    return {
        "DurationHours": float(metadata.get("DurationHours", 8) or 8),
        "ExpectedParticipants": int(
            metadata.get("ExpectedParticipants", 60) or 60
        ),
        "TeamTheme": str(
            metadata.get(
                "TeamTheme",
                event.get("ProgrammeType", "Countries") if event else "Countries",
            )
        ),
    }


def _save_event_metadata(db, event_id, duration, participants, team_theme):
    db.update_event_metadata(event_id, {
        "DurationHours": float(duration),
        "ExpectedParticipants": int(participants),
        "TeamTheme": str(team_theme).strip(),
    })


def _event_form(db, event=None):
    editing = bool(event)
    defaults = _event_defaults(event or {})
    event_id = str((event or {}).get("EventID", ""))
    with st.form(f"{'edit' if editing else 'create'}_event_form_{event_id}"):
        client = st.text_input("Client", value=str((event or {}).get("Client", "")))
        department = st.text_input(
            "Department",
            value=str((event or {}).get("Department", "")),
        )
        event_name = st.text_input(
            "Event name",
            value=str((event or {}).get("EventName", "")),
        )
        venue = st.text_input("Venue", value=str((event or {}).get("Venue", "")))
        event_date = st.date_input(
            "Event date",
            value=(
                str((event or {}).get("EventDate", ""))
                if (event or {}).get("EventDate")
                else "today"
            ),
        )
        programme_default = str(
            (event or {}).get("ProgrammeType", PROGRAMME_TYPES[0])
        )
        programme_type = st.selectbox(
            "Programme type",
            PROGRAMME_TYPES,
            index=(
                PROGRAMME_TYPES.index(programme_default)
                if programme_default in PROGRAMME_TYPES
                else 0
            ),
        )
        col1, col2 = st.columns(2)
        duration = col1.number_input(
            "Duration (hours)",
            min_value=0.5,
            value=defaults["DurationHours"],
            step=0.5,
        )
        expected_participants = col2.number_input(
            "Expected participants",
            min_value=1,
            value=defaults["ExpectedParticipants"],
            step=1,
        )
        col3, col4 = st.columns(2)
        teams = col3.number_input(
            "Number of teams",
            min_value=1,
            value=int((event or {}).get("NumberOfTeams", 6) or 6),
            step=1,
        )
        team_theme = col4.text_input(
            "Team theme",
            value=defaults["TeamTheme"],
        )
        join_code = st.text_input(
            "Join code",
            value=str((event or {}).get("JoinCode", "")),
            placeholder="Leave blank to generate automatically",
        ).upper().strip()
        submitted = st.form_submit_button(
            "Save Changes" if editing else "Create Event",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return None
    if not client.strip() or not event_name.strip() or not venue.strip():
        st.error("Client, event name and venue are required.")
        return None

    final_join_code = join_code or db.create_new_join_code()
    collision = db.get_event_by_join_code(final_join_code)
    if collision and str(collision.get("EventID", "")) != event_id:
        st.error("That join code is already in use.")
        return None

    if not editing:
        event_id = db.generate_next_event_id()
        db.create_event(
            event_id,
            client,
            department,
            event_name,
            str(event_date),
            venue,
            programme_type,
            final_join_code,
            int(teams),
        )
        db.create_teams(event_id, int(teams))
    else:
        existing_teams = db.get_teams(event_id)
        if int(teams) != len(existing_teams):
            if db.get_participant_count(event_id):
                st.error("Team count cannot change after participants have joined.")
                return None
            revised = list(existing_teams[: int(teams)])
            while len(revised) < int(teams):
                position = len(revised) + 1
                revised.append({
                    "TeamID": f"TEAM-{position:02d}",
                    "TeamName": f"Team {position}",
                })
            db.replace_event_teams(event_id, revised)
        db.update_event(event_id, {
            "Client": client,
            "Department": department,
            "EventName": event_name,
            "Venue": venue,
            "EventDate": str(event_date),
            "ProgrammeType": programme_type,
            "JoinCode": final_join_code,
            "NumberOfTeams": int(teams),
        })

    _save_event_metadata(
        db,
        event_id,
        duration,
        expected_participants,
        team_theme,
    )
    st.session_state[ACTIVE_EVENT_KEY] = event_id
    return {
        "EventID": event_id,
        "JoinCode": final_join_code,
        "Created": not editing,
    }


def show_create_event():
    st.title("Create Event")
    st.caption("Enter the event essentials. Programme modules are added next.")
    db = GoogleSheetsDB()
    active_id = str(st.session_state.get(ACTIVE_EVENT_KEY, ""))
    event = db.get_event(active_id) if active_id else None

    mode = st.radio(
        "Mode",
        ["New Event", "Edit Active Event"],
        horizontal=True,
        index=1 if event else 0,
    )
    if mode == "Edit Active Event" and not event:
        st.info("Open an existing event from Events first.")
        return

    result = _event_form(db, event if mode == "Edit Active Event" else None)
    if result:
        if result["Created"]:
            st.success(f"Event created successfully: {result['EventID']}")
            st.write("What would you like to do next?")
        else:
            st.success(f"Event saved · {result['EventID']} · Join code {result['JoinCode']}")
        template, duplicate, blank = st.columns(3)
        if template.button("Use Template", type="primary", width="stretch"):
            request_navigation("Programme Builder")
        if duplicate.button("Duplicate Existing Programme", width="stretch"):
            request_navigation("Programme Builder")
        if blank.button("Build From Scratch", width="stretch"):
            request_navigation("Programme Builder")
