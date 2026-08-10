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
    identity_config = dict(metadata.get("TeamIdentityConfig", {}) or {})
    return {
        "DurationHours": float(metadata.get("DurationHours", 8) or 8),
        "ExpectedParticipants": int(
            metadata.get("ExpectedParticipants", 60) or 60
        ),
        "ThemeType": str(
            identity_config.get("ThemeType")
            or metadata.get("ThemeType")
            or ("COUNTRY" if metadata.get("CountryPool") else "CUSTOM")
        ),
        "ThemeName": str(identity_config.get("ThemeName", metadata.get("TeamTheme", "Teams"))),
    }


def _identity_value(team):
    return str(team.get("TeamIdentity") or team.get("TeamName") or "").strip()


def _identity_option(value, position=0):
    if isinstance(value, dict):
        row = dict(value)
    else:
        row = {"TeamIdentity": str(value)}
    identity = _identity_value(row)
    return {
        "TeamIdentity": identity or f"Team {position or 1}",
        "Country": str(row.get("Country", "") or "").strip(),
        "Icon": str(row.get("Icon", "") or "").strip(),
        "Emoji": str(row.get("Emoji", row.get("Flag", "")) or "").strip(),
        "Image": str(row.get("Image", "") or "").strip(),
    }


def _identity_pool(metadata, existing_teams=()):
    config = dict((metadata or {}).get("TeamIdentityConfig", {}) or {})
    raw = config.get("IdentityPool") or (metadata or {}).get("TeamIdentityPool")
    if not raw and (metadata or {}).get("CountryPool"):
        raw = [{"TeamIdentity": value, "Country": value} for value in metadata["CountryPool"]]
    if not raw:
        raw = list(existing_teams)
    return [_identity_option(value, position) for position, value in enumerate(raw or [], 1)]


def _identity_lines(identities):
    return "\n".join(
        " | ".join([
            item.get("TeamIdentity", ""), item.get("Emoji", ""),
            item.get("Image", ""), item.get("Country", ""),
        ]).rstrip(" |")
        for item in identities
    )


def _parse_identity_lines(value):
    identities = []
    for position, line in enumerate(str(value or "").splitlines(), 1):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|", 3)]
        parts += [""] * (4 - len(parts))
        identities.append(_identity_option({
            "TeamIdentity": parts[0], "Emoji": parts[1],
            "Image": parts[2], "Country": parts[3],
        }, position))
    return identities


def _identity_configuration_error(group_count, identities):
    unique = {_identity_value(item).casefold() for item in identities if _identity_value(item)}
    if len(unique) < int(group_count):
        return (
            f"{int(group_count)} active groups require {int(group_count)} unique team identities. "
            f"{len(unique)} are currently configured."
        )
    if len(unique) != len(identities):
        return "Every configured team identity must be unique."
    return ""


def _regenerate_generic_identities(team_count_key, identity_pool_key):
    count = int(st.session_state.get(team_count_key, 1) or 1)
    st.session_state[identity_pool_key] = _identity_lines([
        _identity_option(f"Team {position}", position)
        for position in range(1, count + 1)
    ])


def _save_event_metadata(db, event_id, duration, participants, theme_type,
                         theme_name, identity_pool, assigned_identities=()):
    db.update_event_metadata(event_id, {
        "DurationHours": float(duration),
        "ExpectedParticipants": int(participants),
        "TeamTheme": str(theme_name).strip(),
        "ThemeType": str(theme_type).strip() or "CUSTOM",
        "TeamIdentityPool": [dict(item) for item in identity_pool],
        "TeamIdentityConfig": {
            "ThemeType": str(theme_type).strip() or "CUSTOM",
            "ThemeName": str(theme_name).strip() or "Teams",
            "IdentityPool": [dict(item) for item in identity_pool],
            "Identities": [{
                "TeamID": str(item.get("TeamID", "")),
                **_identity_option(item, position),
            } for position, item in enumerate(assigned_identities, 1)],
        },
    })


def _resize_event_teams(event_id, existing_teams, target_count, identity_pool=None,
                        theme_type="CUSTOM", theme_name="Teams"):
    """Assign N unique event-configured identities without programme changes."""
    target_count = int(target_count)
    pool = [_identity_option(value, position) for position, value in enumerate(identity_pool or [], 1)]
    if not pool:
        pool = [_identity_option(f"Team {position}", position) for position in range(1, target_count + 1)]
    error = _identity_configuration_error(target_count, pool)
    if error:
        raise ValueError(error)
    revised = [dict(team) for team in list(existing_teams)[:target_count]]
    while len(revised) < target_count:
        position = len(revised) + 1
        revised.append({
            "TeamID": f"{event_id}-TEAM-{position:02d}",
        })
    for position, team in enumerate(revised):
        identity = pool[position]
        team.update(identity)
        team.update({
            "TeamName": identity["TeamIdentity"],
            "ThemeType": str(theme_type).strip() or "CUSTOM",
            "ThemeName": str(theme_name).strip() or "Teams",
        })
    return revised


def _resize_cross_event_teams(db, event, existing_teams, target_count,
                              identity_pool=None, theme_type="", theme_name=""):
    """Apply the optional event-pair uniqueness policy to generic identities."""
    event_id = str(event.get("EventID", ""))
    metadata = StandardCoreV2Adapter.event_metadata(event)
    paired_event_id = str(metadata.get("PairedEventID", "")).strip()
    raw_pool = identity_pool or _identity_pool(metadata, existing_teams)
    pool = [_identity_option(value, position) for position, value in enumerate(raw_pool, 1)]
    paired_unique = bool(
        metadata.get("CrossEventIdentityUnique")
        or metadata.get("CountryAllocationGroupID")
    )
    if not paired_event_id or not paired_unique:
        return _resize_event_teams(
            event_id, existing_teams, target_count, pool,
            theme_type or metadata.get("ThemeType", "CUSTOM"),
            theme_name or metadata.get("TeamTheme", "Teams"),
        )

    paired_event = db.get_event(paired_event_id)
    if not paired_event:
        raise ValueError(
            "The paired event could not be loaded; cross-event team identity allocation was not changed."
        )
    paired_teams = db.get_teams(paired_event_id)
    reserved = {_identity_value(team).casefold() for team in paired_teams if _identity_value(team)}
    available = [item for item in pool if _identity_value(item).casefold() not in reserved]
    total_groups = int(target_count) + len(paired_teams)
    if len({_identity_value(item).casefold() for item in pool}) < total_groups:
        raise ValueError(_identity_configuration_error(total_groups, pool))
    if len(available) < int(target_count):
        raise ValueError(
            f"{total_groups} active groups require {total_groups} unique team identities. "
            f"{len({_identity_value(item).casefold() for item in pool})} are currently configured."
        )
    current = _resize_event_teams(
        event_id, existing_teams, target_count, available,
        theme_type or metadata.get("ThemeType", "CUSTOM"),
        theme_name or metadata.get("TeamTheme", "Teams"),
    )
    existing_signature = [_identity_value(team) for team in existing_teams]
    revised_signature = [_identity_value(team) for team in current]
    if db.get_participant_count(paired_event_id) and existing_signature != revised_signature:
        raise ValueError(
            "Team allocation cannot change after participants have joined either paired event."
        )

    combined = [
        _identity_value(team)
        for team in current + paired_teams
    ]
    if len({value.casefold() for value in combined}) != len(combined):
        raise ValueError("Cross-event team identities must remain unique across both events.")
    configured = {_identity_value(item).casefold() for item in pool}
    if any(value.casefold() not in configured for value in combined):
        raise ValueError("Every paired-event team identity must belong to the configured identity pool.")
    return current


def _event_form(db, event=None):
    editing = bool(event)
    defaults = _event_defaults(event or {})
    event_id = str((event or {}).get("EventID", ""))
    existing_teams = db.get_teams(event_id) if editing else []
    metadata = StandardCoreV2Adapter.event_metadata(event or {})
    default_pool = _identity_pool(metadata, existing_teams)
    if not default_pool:
        default_count = int((event or {}).get("NumberOfTeams", 6) or 6)
        default_pool = [
            _identity_option(f"Team {position}", position)
            for position in range(1, default_count + 1)
        ]
    state_suffix = event_id or "new"
    team_count_key = f"event_team_count_{state_suffix}"
    identity_pool_key = f"event_identity_pool_{state_suffix}"
    if identity_pool_key not in st.session_state:
        st.session_state[identity_pool_key] = _identity_lines(default_pool)
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
        col3, col4, col5 = st.columns(3)
        teams = col3.number_input(
            "Number of teams",
            min_value=1,
            value=int((event or {}).get("NumberOfTeams", 6) or 6),
            step=1,
            key=team_count_key,
        )
        theme_type = col4.text_input(
            "Theme type",
            value=defaults["ThemeType"],
            placeholder="Country, Animal, F1, Colour, Custom…",
        )
        theme_name = col5.text_input(
            "Theme name",
            value=defaults["ThemeName"],
        )
        identity_text = st.text_area(
            "Team identity pool",
            key=identity_pool_key,
            help=(
                "One unique identity per line: Team Identity | Emoji/Icon | Image URL | "
                "Country (optional). Add more lines before increasing group count."
            ),
            height=max(140, min(320, len(default_pool) * 30)),
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
        regenerate_col, save_col = st.columns(2)
        regenerated = regenerate_col.form_submit_button(
            "Regenerate generic team identities",
            on_click=_regenerate_generic_identities,
            args=(team_count_key, identity_pool_key),
            width="stretch",
        )
        submitted = save_col.form_submit_button(
            "Save Changes" if editing else "Create Event",
            type="primary",
            width="stretch",
        )

    if regenerated:
        st.info(f"Generated {int(teams)} editable generic team identities.")
        return None
    if not submitted:
        return None
    if not client.strip() or not event_name.strip() or not venue.strip():
        st.error("Client, event name and venue are required.")
        return None
    identity_pool = _parse_identity_lines(identity_text)
    identity_error = _identity_configuration_error(int(teams), identity_pool)
    if identity_error:
        st.error(identity_error)
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
        revised = _resize_event_teams(
            event_id, db.get_teams(event_id), int(teams), identity_pool,
            theme_type, theme_name,
        )
        db.replace_event_teams(event_id, revised)
    else:
        try:
            revised = _resize_cross_event_teams(
                db, event, existing_teams, int(teams), identity_pool,
                theme_type, theme_name,
            )
        except ValueError as error:
            st.error(str(error))
            return None
        current_signature = [
            (_identity_value(team), team.get("Country", ""),
             team.get("Emoji", ""), team.get("Image", ""))
            for team in existing_teams
        ]
        revised_signature = [
            (_identity_value(team), team.get("Country", ""),
             team.get("Emoji", ""), team.get("Image", ""))
            for team in revised
        ]
        if current_signature != revised_signature:
            if db.get_participant_count(event_id):
                st.error("Team identities cannot change after participants have joined.")
                return None
            db.replace_event_teams(event_id, revised)
            db.update_event_metadata(event_id, {
                "ActiveTeamCount": len(revised),
                "AssignedTeamIdentities": [_identity_value(team) for team in revised],
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
        theme_type,
        theme_name,
        identity_pool,
        revised,
    )
    paired_event_id = str(metadata.get("PairedEventID", "")).strip()
    if paired_event_id and (
        metadata.get("CrossEventIdentityUnique")
        or metadata.get("CountryAllocationGroupID")
    ):
        paired = db.get_event(paired_event_id)
        paired_metadata = StandardCoreV2Adapter.event_metadata(paired)
        paired_config = dict(paired_metadata.get("TeamIdentityConfig", {}) or {})
        paired_config.update({
            "ThemeType": str(theme_type).strip() or "CUSTOM",
            "ThemeName": str(theme_name).strip() or "Teams",
            "IdentityPool": [dict(item) for item in identity_pool],
        })
        db.update_event_metadata(paired_event_id, {
            "TeamTheme": str(theme_name).strip(),
            "ThemeType": str(theme_type).strip() or "CUSTOM",
            "TeamIdentityPool": [dict(item) for item in identity_pool],
            "TeamIdentityConfig": paired_config,
        })
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
