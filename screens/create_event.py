import json

import streamlit as st

from data.standard_core_v2_adapter import StandardCoreV2Adapter, get_standard_database
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
    metadata = StandardCoreV2Adapter.event_metadata(event)
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


def _resize_event_teams(event_id, existing_teams, target_count, country_pool=None):
    """Resize an event roster without leaking event-specific countries into Core."""
    target_count = int(target_count)
    pool = [str(value).strip() for value in (country_pool or []) if str(value).strip()]
    if pool and target_count > len(pool):
        raise ValueError(
            f"This event has {len(pool)} unique country identities; "
            f"choose between 1 and {len(pool)} active teams."
        )
    revised = [dict(team) for team in list(existing_teams)[:target_count]]
    while len(revised) < target_count:
        position = len(revised) + 1
        country = pool[position - 1] if pool else f"Team {position}"
        revised.append({
            "TeamID": f"{event_id}-TEAM-{position:02d}",
            "TeamName": country,
            "Country": country,
        })
    if pool:
        for position, team in enumerate(revised):
            country = pool[position]
            team.update({"TeamName": country, "Country": country})
    return revised


def _resize_cross_event_teams(db, event, existing_teams, target_count):
    """Resize one member of a configured event pair without country collisions."""
    event_id = str(event.get("EventID", ""))
    metadata = StandardCoreV2Adapter.event_metadata(event)
    paired_event_id = str(metadata.get("PairedEventID", "")).strip()
    pool = [
        str(value).strip() for value in metadata.get("CountryPool", [])
        if str(value).strip()
    ]
    if not paired_event_id or not pool:
        return _resize_event_teams(event_id, existing_teams, target_count, pool)

    paired_event = db.get_event(paired_event_id)
    if not paired_event:
        raise ValueError(
            "The paired event could not be loaded; cross-event country allocation was not changed."
        )
    if db.get_participant_count(paired_event_id):
        raise ValueError(
            "Team allocation cannot change after participants have joined either paired event."
        )

    paired_teams = db.get_teams(paired_event_id)
    reserved = {
        str(team.get("Country", "")).strip().casefold()
        for team in paired_teams if str(team.get("Country", "")).strip()
    }
    current = [dict(team) for team in list(existing_teams)[: int(target_count)]]
    current_identities = {
        str(team.get("Country", "")).strip().casefold()
        for team in current if str(team.get("Country", "")).strip()
    }
    if reserved & current_identities:
        raise ValueError("The paired events already contain a duplicate country identity.")

    available = [
        country for country in pool
        if country.casefold() not in reserved | current_identities
    ]
    required = int(target_count) - len(current)
    if required > len(available):
        raise ValueError(
            f"The paired events can use at most {len(pool)} unique countries in total. "
            "Reduce the other event's group count before increasing this event."
        )
    for country in available[:required]:
        position = len(current) + 1
        current.append({
            "TeamID": f"{event_id}-TEAM-{position:02d}",
            "TeamName": country,
            "Country": country,
        })

    combined = [
        str(team.get("Country", "")).strip()
        for team in current + paired_teams
    ]
    if len(combined) > len(pool) or len({value.casefold() for value in combined}) != len(combined):
        raise ValueError("Cross-event country allocation must remain unique across both events.")
    if any(value.casefold() not in {country.casefold() for country in pool} for value in combined):
        raise ValueError("Every paired-event country must belong to the configured country pool.")
    return current


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
        facilitator = st.text_input(
            "Facilitator",
            value=str((event or {}).get("Facilitator", "")),
        )
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
        current_status = str((event or {}).get("Status", "Draft") or "Draft").title()
        status_options = ["Draft", "Active", "Archived"]
        if current_status not in status_options:
            status_options.append(current_status)
        status = st.selectbox(
            "Status",
            status_options,
            index=status_options.index(current_status),
        )
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
            facilitator,
        )
        if status != "Draft":
            db.update_event(event_id, {"Status": status})
    else:
        existing_teams = db.get_teams(event_id)
        if int(teams) != len(existing_teams):
            if db.get_participant_count(event_id):
                st.error("Team count cannot change after participants have joined.")
                return None
            try:
                revised = _resize_cross_event_teams(
                    db, event, existing_teams, int(teams)
                )
            except ValueError as error:
                st.error(str(error))
                return None
            db.replace_event_teams(event_id, revised)
            db.update_event_metadata(event_id, {
                "ActiveTeamCount": len(revised),
                "AssignedCountries": [team.get("Country", "") for team in revised],
                "CrossEventAllocationValidated": True,
            })
        db.update_event(event_id, {
            "Client": client,
            "Department": department,
            "EventName": event_name,
            "Venue": venue,
            "Facilitator": facilitator,
            "EventDate": str(event_date),
            "ProgrammeType": programme_type,
            "JoinCode": final_join_code,
            "NumberOfTeams": int(teams),
            "Status": status,
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
    db = get_standard_database()
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
