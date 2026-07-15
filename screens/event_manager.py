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

            runtime_message = ""
            if db.runtime_status()["PublishReady"]:
                try:
                    db.publish_event_to_runtime(
                        event_id,
                        reset_registration=True,
                    )
                    runtime_message = "Transactional registration published."
                except Exception as error:
                    runtime_message = f"Runtime publish needs attention: {error}"

            st.success("Event Created Successfully!")
            col1, col2, col3 = st.columns(3)
            col1.metric("Event ID", event_id)
            col2.metric("Join Code", join_code)
            col3.metric("Teams Created", int(number_of_teams))
            if runtime_message:
                st.info(runtime_message)

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
                if result.get("RuntimePublished"):
                    st.success("Transactional registration was published for the duplicate.")
                elif result.get("RuntimeError"):
                    st.warning(
                        "The project was duplicated, but runtime publishing needs attention: "
                        + result["RuntimeError"]
                    )
    else:
        st.info("Create an event before duplicating a project.")

    st.divider()
    st.subheader("Live Registration Runtime")

    runtime_status = db.runtime_status()
    if runtime_status["PublishReady"]:
        st.success(runtime_status["Message"])

        runtime_events = db.get_events()
        runtime_options = {
            f"{event.get('EventID', '')} | {event.get('EventName', '')}": event
            for event in runtime_events
        }

        if runtime_options:
            selected_runtime_label = st.selectbox(
                "Event to Publish",
                list(runtime_options.keys()),
                key="runtime_publish_event",
            )
            selected_runtime_event = runtime_options[selected_runtime_label]

            with st.form("runtime_publish_form"):
                reset_registration = st.checkbox(
                    "Clear runtime participants and restart team allocation",
                    value=False,
                )
                runtime_submitted = st.form_submit_button(
                    "🚀 Publish Registration Runtime"
                )

            if runtime_submitted:
                try:
                    result = db.publish_event_to_runtime(
                        selected_runtime_event.get("EventID", ""),
                        reset_registration=reset_registration,
                    )
                except Exception as error:
                    st.error(f"Runtime publish failed: {error}")
                else:
                    st.success(
                        f"Published {result.get('TeamsPublished', 0)} teams. "
                        f"Join code: {result.get('JoinCode', '')}"
                    )

            if st.button(
                "📥 Sync Runtime Participants to Google Sheets",
                key="sync_runtime_participants",
            ):
                try:
                    sync_result = db.sync_runtime_participants_to_sheet(
                        selected_runtime_event.get("EventID", "")
                    )
                except Exception as error:
                    st.error(f"Participant sync failed: {error}")
                else:
                    st.success(
                        f"{sync_result.get('RowsAdded', 0)} new participant rows added. "
                        f"Runtime total: {sync_result.get('RuntimeParticipants', 0)}."
                    )

            if st.button(
                "📥 Sync Runtime Submissions to Google Sheets",
                key="sync_runtime_submissions",
            ):
                try:
                    sync_result = db.sync_runtime_submissions_to_sheet(
                        selected_runtime_event.get("EventID", "")
                    )
                except Exception as error:
                    st.error(f"Submission sync failed: {error}")
                else:
                    st.success(
                        f"{sync_result.get('RowsAdded', 0)} new submission rows added. "
                        f"Runtime total: {sync_result.get('RuntimeSubmissions', 0)}."
                    )

            with st.expander("Registration Load Test"):
                st.caption(
                    "Use only with a test event. This creates temporary LOAD participants."
                )
                load_test_size = st.number_input(
                    "Simultaneous test participants",
                    min_value=12,
                    max_value=300,
                    value=100,
                    step=1,
                    key="runtime_load_test_size",
                )
                confirm_load_test = st.checkbox(
                    "I confirm this is a test event",
                    key="confirm_runtime_load_test",
                )

                if st.button(
                    "🧪 Run Registration Load Test",
                    key="run_runtime_load_test",
                ):
                    if not confirm_load_test:
                        st.error("Confirm that the selected event is a test event.")
                    else:
                        with st.spinner(
                            f"Running {int(load_test_size)} simultaneous joins..."
                        ):
                            load_result = db.runtime.run_join_load_test(
                                selected_runtime_event.get("JoinCode", ""),
                                total_participants=int(load_test_size),
                            )

                        metric1, metric2, metric3 = st.columns(3)
                        metric1.metric("Joined", load_result["Joined"])
                        metric2.metric("Failed", load_result["Failed"])
                        metric3.metric(
                            "Duration",
                            f"{load_result['DurationSeconds']} sec",
                        )

                        distribution = [
                            {"Team": team, "Participants": count}
                            for team, count in load_result["TeamCounts"].items()
                        ]
                        st.dataframe(distribution, width="stretch")

                        if load_result["Passed"]:
                            st.success(
                                "Load test passed: no failures, duplicates, or team skew."
                            )
                        else:
                            st.error("Load test failed. Do not use this runtime live yet.")
                            if load_result["Errors"]:
                                st.dataframe(
                                    load_result["Errors"][:20],
                                    width="stretch",
                                )

                        st.info(
                            "After testing, publish this event again with the reset option "
                            "to remove all temporary LOAD participants."
                        )

            with st.expander("Concurrent Submission Load Test"):
                st.caption(
                    "Use only with a test event. Temporary participants, submissions, "
                    "and test photos are removed automatically."
                )
                submission_test_size = st.number_input(
                    "Simultaneous individual submissions",
                    min_value=12,
                    max_value=300,
                    value=100,
                    step=1,
                    key="runtime_submission_load_test_size",
                )
                confirm_submission_test = st.checkbox(
                    "I confirm this is a test event",
                    key="confirm_runtime_submission_load_test",
                )

                if st.button(
                    "🧪 Run Submission Load Test",
                    key="run_runtime_submission_load_test",
                ):
                    if not confirm_submission_test:
                        st.error("Confirm that the selected event is a test event.")
                    else:
                        try:
                            with st.spinner(
                                f"Running {int(submission_test_size)} concurrent "
                                "submissions and team photo checks..."
                            ):
                                load_result = db.runtime.run_submission_load_test(
                                    event_id=selected_runtime_event.get("EventID", ""),
                                    join_code=selected_runtime_event.get("JoinCode", ""),
                                    total_participants=int(submission_test_size),
                                )
                        except Exception as error:
                            st.error(f"Submission load test failed: {error}")
                            st.stop()

                        metric1, metric2, metric3 = st.columns(3)
                        metric1.metric(
                            "Individual Submissions",
                            load_result["IndividualSubmissions"],
                        )
                        metric2.metric(
                            "Team Photos",
                            load_result["TeamPhotoSubmissions"],
                        )
                        metric3.metric(
                            "Duration",
                            f"{load_result['DurationSeconds']} sec",
                        )

                        if load_result["Passed"]:
                            st.success(
                                "Submission load test passed. Temporary test data "
                                "was cleaned up automatically."
                            )
                        else:
                            st.error(
                                "Submission load test failed. Do not use this "
                                "runtime live yet."
                            )
                            if load_result["Errors"]:
                                st.dataframe(
                                    load_result["Errors"][:20],
                                    width="stretch",
                                )
    else:
        st.warning(runtime_status["Message"])
        st.caption(
            "The existing Google Sheets join remains available, but it is not intended "
            "for large simultaneous registrations."
        )

    st.divider()
    st.subheader("Existing Events")

    events = db.get_events()

    if events:
        st.dataframe(events, width="stretch")
    else:
        st.info("No events created yet.")
