import streamlit as st

from data.google_sheets import GoogleSheetsDB


def show_event_manager():
    st.title("🗓 Event Manager")

    db = GoogleSheetsDB()

    st.subheader("Create Event")

    with st.form("create_event_form", clear_on_submit=False):
        client = st.text_input("Client")
        department = st.text_input("Department")
        event_name = st.text_input("Event Name")
        venue = st.text_input("Venue")
        event_date = st.date_input("Event Date")

        programme_type = st.selectbox(
            "Programme Type",
            [
                "Team Building",
                "Corporate Training",
                "Amazing Race",
                "CSR",
                "CodeShift",
            ],
        )

        number_of_teams = st.number_input(
            "Number of Teams",
            min_value=1,
            value=6,
            step=1,
        )

        create_submitted = st.form_submit_button("🚀 Create Event")

    if create_submitted:
        if not str(event_name).strip():
            st.error("Event Name is required.")
        else:
            event_id = db.generate_next_event_id()
            join_code = db.create_new_join_code()

            db.create_event(
                event_id,
                client,
                department,
                str(event_name).strip(),
                str(event_date),
                venue,
                programme_type,
                join_code,
                int(number_of_teams),
            )

            db.create_teams(event_id, int(number_of_teams))

            st.success("Event Created Successfully!")
            col1, col2, col3 = st.columns(3)
            col1.metric("Event ID", event_id)
            col2.metric("Join Code", join_code)
            col3.metric("Teams Created", int(number_of_teams))

    st.divider()
    st.subheader("Duplicate Project")

    events = db.get_events()

    if events:
        event_options = {
            f"{event.get('EventID', '')} | {event.get('Client', '')} | {event.get('EventName', '')}": event
            for event in events
        }

        selected_label = st.selectbox(
            "Source Event",
            list(event_options.keys()),
            key="duplicate_source_event",
        )
        selected_event = event_options[selected_label]
        source_event_id = str(selected_event.get("EventID", ""))
        default_copy_name = f"{selected_event.get('EventName', 'Event')} - Copy"

        with st.form("duplicate_event_form", clear_on_submit=False):
            new_event_name = st.text_input(
                "New Event Name",
                value=default_copy_name,
            )
            duplicate_submitted = st.form_submit_button("📄 Duplicate Project")

        if duplicate_submitted:
            try:
                result = db.duplicate_event(source_event_id, new_event_name)
            except Exception as error:
                st.error(f"Duplicate failed: {error}")
            else:
                st.success("Project Duplicated Successfully!")
                col1, col2 = st.columns(2)
                col1.metric("New Event ID", result["EventID"])
                col2.metric("New Join Code", result["JoinCode"])

                col3, col4, col5 = st.columns(3)
                col3.metric("Teams Copied", result["TeamsCopied"])
                col4.metric("Missions Copied", result["MissionsCopied"])
                col5.metric("Stages Copied", result["StagesCopied"])

                st.info(
                    "Participants, submissions, scores, and leaderboard data were not copied. "
                    "The duplicated event is in Draft status."
                )
    else:
        st.info("Create an event before duplicating a project.")

    st.divider()
    st.subheader("Existing Events")

    events = db.get_events()

    if events:
        st.dataframe(events, use_container_width=True)
    else:
        st.info("No events created yet.")
