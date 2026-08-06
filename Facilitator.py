import streamlit as st
from branding import apply_branding, configure_page, footer
from data.google_sheets import GoogleSheetsDB
from screens.app_state import ACTIVE_EVENT_KEY
from screens.control_centre import show_control_centre
from screens.formula_race import show_formula_race
from screens.live_event_console import show_live_event_console
from screens.event_manager import FORMULA_RACE_TEAMS
from data.control_runtime import ControlRuntime

configure_page(layout="wide")
apply_branding()

db = GoogleSheetsDB()
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
