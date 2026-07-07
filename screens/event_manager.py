import streamlit as st
import random
import string

from data.google_sheets import GoogleSheetsDB


def generate_join_code(length=6):
    characters = string.ascii_uppercase + string.digits
    return "".join(random.choice(characters) for _ in range(length))


def generate_event_id(db):
    events = db.get_events()
    next_no = len(events) + 1
    return f"EVT-{next_no:04d}"


def show_event_manager():
    st.title("🗓 Event Manager")

    db = GoogleSheetsDB()

    st.subheader("Create Event")

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
        step=1
    )

    if st.button("🚀 Create Event"):
        event_id = generate_event_id(db)
        join_code = generate_join_code()

        db.create_event(
            event_id,
            client,
            department,
            event_name,
            str(event_date),
            venue,
            programme_type,
            join_code,
            int(number_of_teams),
        )

        db.create_teams(
            event_id,
            int(number_of_teams)
        )

        st.success("Event Created Successfully!")
        st.metric("Event ID", event_id)
        st.metric("Join Code", join_code)
        st.metric("Teams Created", int(number_of_teams))

    st.divider()

    st.subheader("Existing Events")

    events = db.get_events()

    if events:
        st.dataframe(events, use_container_width=True)
    else:
        st.info("No events created yet.")