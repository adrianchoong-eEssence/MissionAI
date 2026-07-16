import streamlit as st
import pandas as pd

from data.google_sheets import GoogleSheetsDB
from screens.app_state import active_event_index


FORMULA_RACE_TEAMS = [
    "Scuderia Ferrari",
    "McLaren Racing",
    "Mercedes-AMG",
    "Red Bull Racing",
    "Aston Martin",
    "Alpine",
    "Williams Racing",
    "Audi F1 Team",
    "Haas F1 Team",
    "Cadillac F1 Team",
]


def road_hunt_editor_rows(stops):
    rows = []
    for stop in stops or []:
        mission_ids = stop.get("MissionIDs", []) or []
        if not isinstance(mission_ids, str):
            mission_ids = ", ".join(str(value) for value in mission_ids)
        rows.append({
            "StopID": stop.get("StopID", ""),
            "Position": stop.get("Position", len(rows) + 1),
            "StopName": stop.get("StopName", ""),
            "Latitude": stop.get("Latitude"),
            "Longitude": stop.get("Longitude"),
            "RadiusMeters": stop.get("RadiusMeters", 150),
            "MissionIDs": mission_ids,
            "Instructions": stop.get("Instructions", ""),
            "Active": bool(stop.get("Active", True)),
        })
    if not rows:
        rows = [{
            "StopID": "STOP-01",
            "Position": 1,
            "StopName": "",
            "Latitude": None,
            "Longitude": None,
            "RadiusMeters": 150,
            "MissionIDs": "",
            "Instructions": "",
            "Active": True,
        }]
    return pd.DataFrame(rows)


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
            index=active_event_index(events),
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

                if result.get("MarketplaceItemsCopied"):
                    st.success(
                        f"Marketplace copied: "
                        f"{result['MarketplaceItemsCopied']} item(s)."
                    )

                st.info(
                    "Participants, submissions, purchases, scores, and leaderboard "
                    "data were not copied. "
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
    st.subheader("Formula RACE Team Setup")
    st.caption(
        "Use this for an existing event before participants join. It replaces "
        "country teams with ten Formula 1 team names and republishes registration."
    )

    race_events = db.get_events()
    if race_events:
        race_event_options = {
            f"{event.get('EventID', '')} | {event.get('EventName', '')}": event
            for event in race_events
        }
        selected_race_label = st.selectbox(
            "Formula RACE Event",
            list(race_event_options),
            index=active_event_index(race_events),
            key="formula_race_team_event",
        )
        selected_race_event = race_event_options[selected_race_label]
        selected_race_event_id = str(
            selected_race_event.get("EventID", "")
        )

        race_team_rows = pd.DataFrame([
            {
                "TeamID": f"F1-{position:02d}",
                "TeamName": team_name,
            }
            for position, team_name in enumerate(
                FORMULA_RACE_TEAMS,
                start=1,
            )
        ])
        edited_race_teams = st.data_editor(
            race_team_rows,
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            disabled=["TeamID"],
            key=f"formula_race_teams_{selected_race_event_id}",
            column_config={
                "TeamID": st.column_config.TextColumn(),
                "TeamName": st.column_config.TextColumn(required=True),
            },
        )
        confirm_race_teams = st.checkbox(
            "I confirm no participants have joined this event",
            key=f"confirm_formula_race_teams_{selected_race_event_id}",
        )
        if st.button(
            "🏎️ Apply F1 Teams and Publish Registration",
            width="stretch",
            disabled=not confirm_race_teams,
            key=f"apply_formula_race_teams_{selected_race_event_id}",
        ):
            try:
                runtime_players = (
                    db.runtime.get_players(selected_race_event_id)
                    if db.runtime.can_publish
                    else []
                )
                if runtime_players:
                    raise ValueError(
                        "Participants already exist in the runtime. Clear or "
                        "export them before replacing teams."
                    )
                team_result = db.replace_event_teams(
                    selected_race_event_id,
                    edited_race_teams.to_dict("records"),
                )
                runtime_result = db.publish_event_to_runtime(
                    selected_race_event_id,
                    reset_registration=True,
                )
            except Exception as error:
                st.error(f"Formula RACE team setup failed: {error}")
            else:
                st.success(
                    f"Published {team_result.get('TeamsUpdated', 0)} F1 teams. "
                    f"Join code: {runtime_result.get('JoinCode', '')}"
                )

    st.divider()
    st.subheader("🗺️ Road Hunt Setup")
    st.caption(
        "Enable this only for GPS-based Road Hunts. Add each checkpoint's "
        "coordinates and geofence radius before the event."
    )

    road_events = db.get_events()
    if road_events and db.runtime.can_publish:
        road_event_options = {
            f"{event.get('EventID', '')} | {event.get('EventName', '')}": event
            for event in road_events
        }
        selected_road_label = st.selectbox(
            "Road Hunt Event",
            list(road_event_options),
            index=active_event_index(road_events),
            key="road_hunt_setup_event",
        )
        selected_road_event = road_event_options[selected_road_label]
        selected_road_event_id = str(
            selected_road_event.get("EventID", "")
        )

        road_status = {}
        road_hunt_ready = True
        try:
            road_status = db.runtime.get_road_hunt_status(
                selected_road_event_id
            )
        except Exception as error:
            message = str(error)
            if "PGRST202" in message or "exos_road_hunt_status" in message:
                road_hunt_ready = False
                st.info(
                    "Install Supabase migration 008 to activate Road Hunt GPS."
                )
            elif "Runtime event" in message and "not found" in message:
                st.info(
                    "Publish Registration Runtime for this event before saving "
                    "its Road Hunt route."
                )
            else:
                st.warning(f"Road Hunt status is unavailable: {error}")

        enabled = st.toggle(
            "Enable GPS Road Hunt for this event",
            value=bool(road_status.get("Enabled", False)),
            key=f"road_hunt_enabled_{selected_road_event_id}",
        )
        interval_seconds = st.number_input(
            "Navigator GPS interval (seconds)",
            min_value=10,
            max_value=120,
            value=int(
                road_status.get("LocationIntervalSeconds", 20) or 20
            ),
            step=5,
            key=f"road_hunt_interval_{selected_road_event_id}",
        )
        route_editor = st.data_editor(
            road_hunt_editor_rows(road_status.get("Stops", [])),
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            key=f"road_hunt_route_{selected_road_event_id}",
            column_config={
                "Position": st.column_config.NumberColumn(
                    min_value=1,
                    step=1,
                ),
                "Latitude": st.column_config.NumberColumn(
                    format="%.6f",
                    help="Google Maps latitude, for example 4.5975",
                ),
                "Longitude": st.column_config.NumberColumn(
                    format="%.6f",
                    help="Google Maps longitude, for example 101.0901",
                ),
                "RadiusMeters": st.column_config.NumberColumn(
                    min_value=20,
                    max_value=5000,
                    step=10,
                ),
                "MissionIDs": st.column_config.TextColumn(
                    help="Comma-separated mission IDs unlocked at this stop.",
                ),
            },
        )
        reset_tracking = st.checkbox(
            "Clear navigator devices, locations, and arrivals when saving",
            value=False,
            key=f"road_hunt_reset_{selected_road_event_id}",
        )
        if st.button(
            "📍 Save and Publish Road Hunt",
            width="stretch",
            disabled=not road_hunt_ready,
            key=f"publish_road_hunt_{selected_road_event_id}",
        ):
            try:
                db.publish_event_to_runtime(
                    selected_road_event_id,
                    reset_registration=False,
                )
                configuration = db.runtime.configure_road_hunt(
                    selected_road_event_id,
                    enabled=enabled,
                    location_interval_seconds=int(interval_seconds),
                    reset=reset_tracking,
                )
                route = db.runtime.publish_road_hunt_route(
                    selected_road_event_id,
                    route_editor.to_dict("records"),
                )
            except Exception as error:
                st.error(f"Road Hunt setup failed: {error}")
            else:
                st.success(
                    f"Road Hunt {'enabled' if configuration.get('Enabled') else 'disabled'}; "
                    f"{route.get('StopsPublished', 0)} route stop(s) published."
                )
                st.rerun()
    elif not db.runtime.can_publish:
        st.info("Supabase administrator access is required for Road Hunt setup.")

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
                index=active_event_index(runtime_events),
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

            with st.expander("Two-Event Isolation Load Test"):
                st.caption(
                    "Runs registrations, individual submissions, and team photo "
                    "checks in two events at the same time. Test data is removed "
                    "automatically."
                )
                runtime_labels = list(runtime_options.keys())
                if len(runtime_labels) < 2:
                    st.info(
                        "Create and publish a second test event before running "
                        "this test."
                    )
                else:
                    event_a_label = st.selectbox(
                        "Test Event A",
                        runtime_labels,
                        index=0,
                        key="dual_load_event_a",
                    )
                    event_b_label = st.selectbox(
                        "Test Event B",
                        runtime_labels,
                        index=1,
                        key="dual_load_event_b",
                    )
                    dual_test_size = st.number_input(
                        "Participants per event",
                        min_value=12,
                        max_value=300,
                        value=100,
                        step=1,
                        key="dual_load_test_size",
                    )
                    confirm_dual_test = st.checkbox(
                        "I confirm both selected events are test events",
                        key="confirm_dual_load_test",
                    )

                    if st.button(
                        "🧪 Run Two-Event Isolation Test",
                        key="run_dual_event_load_test",
                    ):
                        if event_a_label == event_b_label:
                            st.error("Select two different test events.")
                        elif not confirm_dual_test:
                            st.error("Confirm that both events are test events.")
                        else:
                            event_a = runtime_options[event_a_label]
                            event_b = runtime_options[event_b_label]
                            try:
                                with st.spinner(
                                    f"Running {int(dual_test_size)} participants "
                                    "in each event simultaneously..."
                                ):
                                    dual_result = (
                                        db.runtime.run_dual_event_load_test(
                                            [event_a, event_b],
                                            total_participants_each=int(
                                                dual_test_size
                                            ),
                                        )
                                    )
                            except Exception as error:
                                st.error(f"Two-event test failed: {error}")
                                st.stop()

                            total_individual = sum(
                                row.get("IndividualSubmissions", 0)
                                for row in dual_result["EventResults"]
                            )
                            total_photos = sum(
                                row.get("TeamPhotoSubmissions", 0)
                                for row in dual_result["EventResults"]
                            )
                            metric1, metric2, metric3 = st.columns(3)
                            metric1.metric(
                                "Individual Submissions",
                                total_individual,
                            )
                            metric2.metric("Team Photos", total_photos)
                            metric3.metric(
                                "Duration",
                                f"{dual_result['DurationSeconds']} sec",
                            )

                            summary = [
                                {
                                    "Event": row.get("EventID", ""),
                                    "Joined": row.get("Joined", 0),
                                    "Individual Submissions": row.get(
                                        "IndividualSubmissions",
                                        0,
                                    ),
                                    "Team Photos": row.get(
                                        "TeamPhotoSubmissions",
                                        0,
                                    ),
                                    "Passed": row.get("Passed", False),
                                }
                                for row in dual_result["EventResults"]
                            ]
                            st.dataframe(summary, width="stretch")

                            if dual_result["Passed"]:
                                st.success(
                                    "Two-event isolation test passed. Both events "
                                    "remained separate and test data was cleaned up."
                                )
                            else:
                                st.error(
                                    "Two-event isolation test failed. Do not run "
                                    "simultaneous live events yet."
                                )
                                errors = []
                                for row in dual_result["EventResults"]:
                                    for error in row.get("Errors", []):
                                        errors.append({
                                            "Event": row.get("EventID", ""),
                                            **error,
                                        })
                                if errors:
                                    st.dataframe(errors[:20], width="stretch")
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
