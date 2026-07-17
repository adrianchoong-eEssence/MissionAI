import uuid
from datetime import datetime

import pandas as pd
import pydeck as pdk
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from data.google_drive import get_photo_url
from data.google_sheets import GoogleSheetsDB
from data.mission_media import get_mission_media_url
from data.runtime_database import RuntimeDatabaseError
from screens.app_state import select_active_event


APPROVED_VALUES = {"yes", "true", "approved"}

DEFAULT_MARKETPLACE_ITEMS = [
    {
        "ItemID": "FR-WHEEL-UPGRADE",
        "ItemName": "Wheel Upgrade",
        "Description": "Upgrade one set of wheels for the Formula RACE build.",
        "CreditCost": 100,
        "StockQuantity": 10,
        "Active": True,
        "Position": 1,
    },
    {
        "ItemID": "FR-AXLE-UPGRADE",
        "ItemName": "Axle Upgrade",
        "Description": "Upgrade the axle materials for improved reliability.",
        "CreditCost": 120,
        "StockQuantity": 10,
        "Active": True,
        "Position": 2,
    },
    {
        "ItemID": "FR-AERO-KIT",
        "ItemName": "Aerodynamic Body Kit",
        "Description": "Optional materials for an aerodynamic body improvement.",
        "CreditCost": 150,
        "StockQuantity": 10,
        "Active": True,
        "Position": 3,
    },
    {
        "ItemID": "FR-TEST-RUN",
        "ItemName": "Additional Test Run",
        "Description": "Purchase one additional official test run.",
        "CreditCost": 80,
        "StockQuantity": 30,
        "Active": True,
        "Position": 4,
    },
    {
        "ItemID": "FR-EXPERT-ADVICE",
        "ItemName": "Expert Consultation",
        "Description": "Five minutes of technical consultation with a facilitator.",
        "CreditCost": 60,
        "StockQuantity": 20,
        "Active": True,
        "Position": 5,
    },
]


def auto_refresh(seconds=5):
    st_autorefresh(
        interval=seconds * 1000,
        key="live_event_console_refresh",
    )




def get_value(record, field_name, default=""):
    """Read a Google Sheets record safely, even if a header has spaces/case differences."""
    if not isinstance(record, dict):
        return default

    wanted = str(field_name).strip().lower()
    for key, value in record.items():
        if str(key).strip().lower() == wanted:
            return value

    return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_score(score):
    number = safe_float(score)
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def calculate_leaderboard(submissions):
    leaderboard = {}

    for submission in submissions:
        if str(submission.get("Status", "")).upper() != "APPROVED":
            continue

        submission_type = str(submission.get("SubmissionType", "")).upper()
        if submission_type in {"NASI", "PIPELINE_ENTERPRISE"}:
            continue

        team = str(submission.get("TeamName", "Unknown Team") or "Unknown Team")
        score = safe_float(submission.get("Score", 0))
        leaderboard[team] = leaderboard.get(team, 0.0) + score

    return sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)


def calculate_score(submission):
    submission_type = str(get_value(submission, "SubmissionType", "")).upper().strip()
    metric1 = get_value(submission, "Metric1", "")
    metric2 = get_value(submission, "Metric2", "")
    metric3 = get_value(submission, "Metric3", "")

    if submission_type in {"PIPELINE", "PIPELINE_ENTERPRISE"}:
        target = safe_float(metric1)
        achieved = safe_float(metric2)
        lost = safe_float(metric3)

        if target <= 0:
            return 0.0, (
                f"Target must be greater than zero. "
                f"Received Target={metric1!r}, Achieved={metric2!r}, Lost={metric3!r}."
            )

        score = ((achieved - lost) / target) * 100
        return round(max(score, 0), 1), "(Achieved - Lost Clients) ÷ Target × 100"

    if submission_type == "HELIUM":
        completed = str(metric1).strip().upper() == "YES"
        return (100.0 if completed else 0.0), "Completed = 100; Not completed = 0"

    if submission_type == "KEYPUNCH":
        highest = min(max(safe_float(metric1), 0), 30)
        return round((highest / 30) * 100, 1), "Highest Number ÷ 30 × 100"

    if submission_type == "CATALYST":
        completed = str(metric1).strip().upper() == "YES"
        return (100.0 if completed else 0.0), "Completed = 100; Not completed = 0"

    if submission_type == "NASI":
        return 0.0, "Reflection only — no score"

    return safe_float(get_value(submission, "Score", 0)), "Manual score"


def mission_defaults(submission_type):
    defaults = {
        "PIPELINE": {
            "mission_id": "P02",
            "title": "Customer Journey: Pipeline Challenge",
            "description": "Submit Target, Achieved and Lost Clients after the official team run.",
            "points": 100,
            "clue": "Score = (Achieved - Lost Clients) ÷ Target × 100. Scores may exceed 100.",
        },
        "PIPELINE_ENTERPRISE": {
            "mission_id": "P03",
            "title": "Enterprise Collaboration: Pipeline Challenge",
            "description": "All six groups operate as one enterprise. The facilitator records one collective result.",
            "points": 0,
            "clue": "One enterprise. One target. One collective result.",
        },
        "HELIUM": {
            "mission_id": "H01",
            "title": "Taking Ownership Together: Helium Stick",
            "description": "Lower the stick together while every finger remains in contact.",
            "points": 100,
            "clue": "Completed = 100 points. Not completed = 0 points.",
        },
        "KEYPUNCH": {
            "mission_id": "K01",
            "title": "Balancing Speed, Accuracy and Compliance: Key Punch",
            "description": "Submit the highest correct number reached within the official 60-second attempt.",
            "points": 100,
            "clue": "Score = Highest Number ÷ 30 × 100.",
        },
        "CATALYST": {
            "mission_id": "C01",
            "title": "Creating Enterprise Success: Catalyst Challenge",
            "description": "Build, integrate and complete the full enterprise chain reaction.",
            "points": 100,
            "clue": "Completed = 100 points. Not completed = 0 points.",
        },
        "NASI": {
            "mission_id": "N01",
            "title": "NASI",
            "description": "New Ideas, Areas for Improvement, Strengths and Implementation.",
            "points": 0,
            "clue": "Individual reflection. No points awarded.",
        },
        "PHOTO": {
            "mission_id": "M01",
            "title": "Photo Evidence Mission",
            "description": "Upload one photo as evidence of mission completion.",
            "points": 100,
            "clue": "One submission per team is enough.",
        },
        "NONE": {
            "mission_id": "M00",
            "title": "Programme Stage",
            "description": "No participant submission is required.",
            "points": 0,
            "clue": "Await facilitator instruction.",
        },
    }
    return defaults.get(submission_type, defaults["PHOTO"])


def render_submission_details(submission):
    submission_type = str(get_value(submission, "SubmissionType", "")).upper().strip()
    metric1 = get_value(submission, "Metric1", "")
    metric2 = get_value(submission, "Metric2", "")
    metric3 = get_value(submission, "Metric3", "")
    remarks = get_value(submission, "Remarks", "")
    image_url = get_value(submission, "ImageURL", "")
    drive_file_id = get_value(submission, "DriveFileID", "")

    if submission_type in {"PIPELINE", "PIPELINE_ENTERPRISE"}:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Target", metric1)
        with col2:
            st.metric("Achieved", metric2)
        with col3:
            st.metric("Lost Clients", metric3)
    elif submission_type == "KEYPUNCH":
        st.metric("Highest Number Reached", metric1)
    elif submission_type in {"HELIUM", "CATALYST"}:
        st.metric("Completed", metric1)
    elif submission_type == "NASI":
        st.markdown("### NASI Reflection")
        st.info(remarks or "No reflection text recorded.")
    elif remarks:
        st.info(remarks)

    display_url = get_photo_url(image_url, drive_file_id)
    if display_url:
        st.image(
            display_url,
            caption="Mission Submission",
            width="stretch",
        )
    elif image_url or drive_file_id:
        st.warning("Submission image is temporarily unavailable.")


def render_enterprise_pipeline_form(db, event_id, mission):
    if not mission:
        return

    mission_type = str(mission.get("SubmissionType", "")).upper()
    if mission_type != "PIPELINE_ENTERPRISE":
        return

    st.divider()
    st.subheader("🤝 Enterprise Pipeline Result")
    st.caption("Facilitator enters one collective result for all six groups.")

    existing = db.get_team_submission(event_id, mission.get("MissionID"), "ENTERPRISE")
    if existing:
        render_submission_details(existing)
        score, formula = calculate_score(existing)
        st.success(f"Collective enterprise score: {format_score(score)}%")
        st.caption(formula)
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        target = st.number_input("Enterprise Target", min_value=1, value=300, step=1)
    with col2:
        achieved = st.number_input("Enterprise Achieved", min_value=0, value=0, step=1)
    with col3:
        lost = st.number_input("Enterprise Lost Clients", min_value=0, value=0, step=1)

    score = max(((achieved - lost) / target) * 100, 0)
    st.metric("Calculated Enterprise Score", f"{format_score(score)}%")

    if st.button("✅ Save Enterprise Result", width="stretch"):
        db.save_submission(
            submission_id=str(uuid.uuid4()),
            event_id=event_id,
            mission_id=mission.get("MissionID"),
            team_name="ENTERPRISE",
            participant_name="Facilitator",
            image_url="",
            drive_file_id="FACILITATOR-ENTRY",
            submitted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            score=round(score, 1),
            judged="Yes",
            remarks="Collective enterprise result",
            submission_type="PIPELINE_ENTERPRISE",
            metric1=target,
            metric2=achieved,
            metric3=lost,
            status="APPROVED",
        )
        st.success("Enterprise result saved.")
        st.rerun()


def render_credit_wallet_control(db, event_id):
    st.divider()
    st.subheader("💳 Credits & Marketplace")
    if not db.runtime.can_publish:
        st.info("Supabase administrator access is required for credit controls.")
        return

    try:
        status = db.runtime.get_credit_wallet_status(event_id)
    except RuntimeDatabaseError as error:
        st.warning(
            "Credit Wallet is not installed or is temporarily unavailable."
        )
        st.caption(str(error))
        return

    if not status:
        st.info("Publish this event to the Supabase runtime first.")
        return

    if not status.get("Enabled"):
        st.info(
            "Enable Credits for programmes where teams earn credits and spend "
            "them in a marketplace. The normal competition leaderboard remains separate."
        )
        if st.button("Enable Credit Wallet", width="stretch"):
            db.runtime.configure_credit_wallet(event_id, enabled=True, reset=False)
            st.success("Credit Wallet enabled for this event.")
            st.rerun()
        return

    wallets = status.get("Wallets", []) or []
    total_earned = sum(safe_float(row.get("EarnedCredits")) for row in wallets)
    total_spent = sum(safe_float(row.get("SpentCredits")) for row in wallets)
    total_balance = sum(safe_float(row.get("Balance")) for row in wallets)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Credits Earned", format_score(total_earned))
    with col2:
        st.metric("Credits Spent", format_score(total_spent))
    with col3:
        st.metric("Available Balance", format_score(total_balance))

    if wallets:
        st.dataframe(wallets, width="stretch", hide_index=True)

    frozen = bool(status.get("EarningFrozen"))
    if frozen:
        st.success(
            "Day 1 Credit Leaderboard is frozen. New approvals will not change earned credits."
        )
        if st.button("Unfreeze Credit Earnings", width="stretch"):
            db.runtime.set_credit_freeze(event_id, False)
            st.rerun()
    else:
        st.warning(
            "Credit earnings are live. Approving or updating a scored submission "
            "will update that team's earned credits."
        )
        if st.button("Freeze Day 1 Credit Leaderboard", width="stretch"):
            db.runtime.set_credit_freeze(event_id, True)
            st.rerun()

    st.markdown("#### Marketplace Catalogue")
    items = status.get("Items", []) or DEFAULT_MARKETPLACE_ITEMS
    editor_rows = []
    for position, item in enumerate(items, start=1):
        editor_rows.append({
            "ItemID": item.get("ItemID", f"ITEM-{position:02d}"),
            "ItemName": item.get("ItemName", ""),
            "Description": item.get("Description", ""),
            "CreditCost": safe_float(item.get("CreditCost")),
            "StockQuantity": item.get("StockQuantity"),
            "Active": bool(item.get("Active", True)),
            "Position": int(item.get("Position", position) or position),
        })

    catalogue = st.data_editor(
        pd.DataFrame(editor_rows),
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key=f"marketplace_catalogue_{event_id}",
        column_config={
            "CreditCost": st.column_config.NumberColumn(min_value=0, step=10),
            "StockQuantity": st.column_config.NumberColumn(
                help="Leave blank for unlimited stock.",
                min_value=0,
                step=1,
            ),
            "Position": st.column_config.NumberColumn(min_value=0, step=1),
        },
    )
    if st.button("Publish Marketplace Catalogue", width="stretch"):
        result = db.runtime.publish_marketplace(
            event_id,
            catalogue.fillna("").to_dict("records"),
        )
        st.success(f"Published {result.get('ItemsPublished', 0)} marketplace item(s).")
        st.rerun()

    if wallets:
        with st.expander("Facilitator Credit Adjustment"):
            team_name = st.selectbox(
                "Team",
                [row.get("TeamName", "") for row in wallets],
                key=f"credit_adjustment_team_{event_id}",
            )
            amount = st.number_input(
                "Credit Adjustment",
                value=0.0,
                step=10.0,
                help="Use a positive number to add credits or a negative number to deduct.",
                key=f"credit_adjustment_amount_{event_id}",
            )
            description = st.text_input(
                "Reason",
                value="Facilitator adjustment",
                key=f"credit_adjustment_reason_{event_id}",
            )
            if st.button("Apply Credit Adjustment", width="stretch"):
                if amount == 0:
                    st.error("Enter a non-zero adjustment.")
                else:
                    result = db.runtime.adjust_team_credits(
                        event_id,
                        team_name,
                        amount,
                        description,
                    )
                    st.success(
                        f"{team_name} balance is now "
                        f"{format_score(result.get('Balance', 0))} credits."
                    )
                    st.rerun()

    purchases = status.get("Purchases", []) or []
    if purchases:
        with st.expander("Marketplace Purchases"):
            st.dataframe(purchases, width="stretch", hide_index=True)

    with st.expander("Reset Credit Runtime"):
        confirmed = st.checkbox(
            "I understand this deletes all credit transactions and purchases for this event",
            key=f"confirm_credit_reset_{event_id}",
        )
        if st.button(
            "Reset Credits and Purchases",
            disabled=not confirmed,
            width="stretch",
        ):
            db.runtime.configure_credit_wallet(event_id, enabled=True, reset=True)
            st.success("Credit balances and purchases reset to zero.")
            st.rerun()


def render_road_hunt_operations(db, event_id):
    """Show the live navigator and geofence status for Road Hunt events."""
    if not db.runtime.can_publish:
        return
    try:
        status = db.runtime.get_road_hunt_status(event_id)
    except RuntimeDatabaseError as error:
        message = str(error)
        if "PGRST202" in message or "exos_road_hunt_status" in message:
            return
        st.warning("Road Hunt operations are temporarily reconnecting.")
        st.caption(message)
        return

    if not status.get("Enabled"):
        return

    st.divider()
    st.subheader("🗺️ Road Hunt Operations")
    teams = status.get("Teams", []) or []
    stops = status.get("Stops", []) or []
    arrivals = status.get("Arrivals", []) or []
    try:
        road_submissions = db.runtime.get_submissions(event_id)
    except RuntimeDatabaseError:
        road_submissions = []
    mission_ids_by_stop = {
        str(stop.get("StopID", "")): {
            str(mission_id)
            for mission_id in (stop.get("MissionIDs", []) or [])
            if str(mission_id)
        }
        for stop in stops
    }
    interval = int(status.get("LocationIntervalSeconds", 20) or 20)
    stale_after = max(interval * 3, 60)
    now = pd.Timestamp.now(tz="UTC")
    participant_names = {
        str(row.get("ParticipantID", "")): str(row.get("Name", ""))
        for row in db.runtime.get_players(event_id)
    }

    team_rows = []
    reporting = 0
    recent = 0
    for team in teams:
        captured_at = team.get("CapturedAt") or team.get("LastSeenAt")
        last_seen = pd.to_datetime(captured_at, utc=True, errors="coerce")
        age_seconds = None
        if not pd.isna(last_seen):
            age_seconds = max((now - last_seen).total_seconds(), 0)
            reporting += 1
            if age_seconds <= stale_after:
                recent += 1

        team_arrivals = [
            row for row in arrivals
            if str(row.get("TeamName", "")) == str(team.get("TeamName", ""))
        ]
        team_name = str(team.get("TeamName", ""))
        unlocked_mission_ids = set()
        for arrival in team_arrivals:
            unlocked_mission_ids.update(
                mission_ids_by_stop.get(str(arrival.get("StopID", "")), set())
            )
        team_submissions = [
            row for row in road_submissions
            if str(row.get("TeamName", "")) == team_name
            and str(row.get("MissionID", "")) in unlocked_mission_ids
        ]
        submitted_mission_ids = {
            str(row.get("MissionID", ""))
            for row in team_submissions
        }
        approved_mission_ids = {
            str(row.get("MissionID", ""))
            for row in team_submissions
            if str(row.get("Status", "")).upper() == "APPROVED"
        }
        if age_seconds is None:
            gps_status = "Not started"
            status_colour = [100, 116, 139, 210]
        elif age_seconds <= stale_after:
            gps_status = "Live"
            status_colour = [34, 197, 94, 230]
        elif age_seconds <= stale_after * 3:
            gps_status = f"Delayed ({int(age_seconds // 60)} min)"
            status_colour = [250, 204, 21, 230]
        else:
            gps_status = f"Offline ({int(age_seconds // 60)} min)"
            status_colour = [239, 68, 68, 230]

        navigator_id = str(team.get("NavigatorParticipantID", ""))
        navigator_name = participant_names.get(navigator_id, "")
        if not navigator_name and team.get("HasNavigator"):
            navigator_name = "Navigator claimed"
        last_seen_text = ""
        if not pd.isna(last_seen):
            last_seen_text = last_seen.tz_convert(
                "Asia/Kuala_Lumpur"
            ).strftime("%H:%M:%S")
        accuracy = team.get("AccuracyMeters")
        accuracy_value = (
            max(float(accuracy), 5)
            if accuracy not in (None, "")
            else 25.0
        )

        team_rows.append({
            "Team": team.get("TeamName", ""),
            "Navigator": navigator_name or "Waiting",
            "GPS": gps_status,
            "Last Seen": last_seen_text,
            "Accuracy (m)": (
                round(float(accuracy), 1)
                if accuracy not in (None, "")
                else None
            ),
            "Stops Reached": len(team_arrivals),
            "Missions Unlocked": len(unlocked_mission_ids),
            "Missions Submitted": len(submitted_mission_ids),
            "Missions Approved": len(approved_mission_ids),
            "Latitude": team.get("Latitude"),
            "Longitude": team.get("Longitude"),
            "StatusColour": status_colour,
            "AccuracyRadius": accuracy_value,
        })

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Teams", len(teams))
    metric2.metric("GPS Reporting", reporting)
    metric3.metric("Live Now", recent)
    metric4.metric("Arrivals", len(arrivals))

    map_rows = [
        {
            **row,
            "Latitude": float(row["Latitude"]),
            "Longitude": float(row["Longitude"]),
            "Label": f"{row['Team']} · {row['Navigator']}",
            "AccuracyColour": [
                row["StatusColour"][0],
                row["StatusColour"][1],
                row["StatusColour"][2],
                45,
            ],
            "AccuracyLabel": row.get("Accuracy (m)") or "Unknown",
        }
        for row in team_rows
        if row.get("Latitude") not in (None, "")
        and row.get("Longitude") not in (None, "")
    ]
    if map_rows:
        latitudes = [row["Latitude"] for row in map_rows]
        longitudes = [row["Longitude"] for row in map_rows]
        span = max(
            max(latitudes) - min(latitudes),
            max(longitudes) - min(longitudes),
        )
        if span <= 0.005:
            zoom = 15
        elif span <= 0.02:
            zoom = 13
        elif span <= 0.08:
            zoom = 11
        elif span <= 0.3:
            zoom = 9
        elif span <= 1:
            zoom = 7
        else:
            zoom = 5

        accuracy_layer = pdk.Layer(
            "ScatterplotLayer",
            map_rows,
            get_position="[Longitude, Latitude]",
            get_radius="AccuracyRadius",
            radius_units="meters",
            get_fill_color="AccuracyColour",
            get_line_color="StatusColour",
            line_width_min_pixels=1,
            stroked=True,
            pickable=False,
        )
        marker_layer = pdk.Layer(
            "ScatterplotLayer",
            map_rows,
            get_position="[Longitude, Latitude]",
            get_radius=8,
            radius_units="pixels",
            get_fill_color="StatusColour",
            get_line_color=[255, 255, 255, 240],
            line_width_min_pixels=2,
            stroked=True,
            pickable=True,
        )
        label_layer = pdk.Layer(
            "TextLayer",
            map_rows,
            get_position="[Longitude, Latitude]",
            get_text="Label",
            get_size=15,
            get_color=[15, 23, 42, 255],
            get_pixel_offset=[0, -20],
            get_text_anchor="middle",
            get_alignment_baseline="bottom",
            pickable=True,
        )
        deck = pdk.Deck(
            layers=[accuracy_layer, marker_layer, label_layer],
            initial_view_state=pdk.ViewState(
                latitude=sum(latitudes) / len(latitudes),
                longitude=sum(longitudes) / len(longitudes),
                zoom=zoom,
                pitch=0,
            ),
            map_style=(
                "https://basemaps.cartocdn.com/gl/positron-gl-style/"
                "style.json"
            ),
            tooltip={
                "html": (
                    "<b>{Team}</b><br/>Navigator: {Navigator}<br/>"
                    "GPS: {GPS}<br/>Last seen: {Last Seen}<br/>"
                    "Accuracy: ±{AccuracyLabel} m<br/>"
                    "Stops reached: {Stops Reached}<br/>"
                    "Missions: {Missions Submitted}/{Missions Unlocked} submitted"
                ),
                "style": {"backgroundColor": "#0f172a", "color": "white"},
            },
        )
        st.pydeck_chart(deck, width="stretch")
        st.caption(
            "The translucent circle shows the phone's reported GPS accuracy."
        )
    else:
        st.info("Waiting for nominated navigator phones to start GPS.")

    if team_rows:
        st.dataframe(
            pd.DataFrame(team_rows).drop(
                columns=[
                    "Latitude",
                    "Longitude",
                    "StatusColour",
                    "AccuracyRadius",
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    if stops:
        with st.expander("Route Stops and Arrivals"):
            stop_names = {
                str(stop.get("StopID", "")): str(stop.get("StopName", ""))
                for stop in stops
            }
            route_rows = []
            for stop in stops:
                stop_id = str(stop.get("StopID", ""))
                reached = {
                    str(row.get("TeamName", ""))
                    for row in arrivals
                    if str(row.get("StopID", "")) == stop_id
                }
                route_rows.append({
                    "Order": stop.get("Position", ""),
                    "Stop": stop.get("StopName", stop_id),
                    "Radius (m)": stop.get("RadiusMeters", ""),
                    "Teams Reached": len(reached),
                    "Mission IDs": ", ".join(stop.get("MissionIDs", []) or []),
                })
            st.dataframe(route_rows, width="stretch", hide_index=True)

            st.markdown("#### Manual Arrival Fallback")
            st.caption(
                "Use only when a navigator has a GPS or mobile-data problem."
            )
            col1, col2 = st.columns(2)
            with col1:
                fallback_team = st.selectbox(
                    "Team",
                    [str(row.get("TeamName", "")) for row in teams],
                    key=f"road_hunt_manual_team_{event_id}",
                )
            with col2:
                fallback_stop = st.selectbox(
                    "Route Stop",
                    list(stop_names),
                    format_func=lambda value: stop_names.get(value, value),
                    key=f"road_hunt_manual_stop_{event_id}",
                )
            if st.button(
                "Record Manual Arrival",
                width="stretch",
                key=f"road_hunt_manual_arrival_{event_id}",
            ):
                db.runtime.record_manual_arrival(
                    event_id,
                    fallback_team,
                    fallback_stop,
                )
                st.success("Manual arrival recorded.")
                st.rerun()

    claimed_teams = [
        str(team.get("TeamName", ""))
        for team in teams
        if team.get("HasNavigator")
    ]
    if claimed_teams:
        with st.expander("Navigator Device Control"):
            release_team = st.selectbox(
                "Release Navigator for Team",
                claimed_teams,
                key=f"road_hunt_release_team_{event_id}",
            )
            st.caption(
                "Release only when the nominated phone is lost, flat, or being replaced."
            )
            if st.button(
                "Release Navigator Device",
                width="stretch",
                key=f"road_hunt_release_{event_id}",
            ):
                db.runtime.release_team_tracker(event_id, release_team)
                st.success(f"{release_team} may nominate a new navigator phone.")
                st.rerun()


def show_live_event_console():
    st.title("🎮 Live Event Console")

    db = GoogleSheetsDB()
    events = db.get_events()

    if not events:
        st.warning("No events found. Create an event first.")
        return

    event = select_active_event(
        events,
        label="Active Event",
        key="live_console_event",
    )
    event_id = event.get("EventID")

    auto_refresh_on = st.toggle("Auto Refresh", value=False)
    if auto_refresh_on:
        auto_refresh(5)

    st.divider()
    st.subheader(event.get("EventName", "Unnamed Event"))
    st.caption(f"Client: {event.get('Client', '')}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Join Code", event.get("JoinCode", ""))
    with col2:
        st.metric("Participants", db.get_participant_count(event_id))
    with col3:
        st.metric("Teams", db.get_team_count(event_id))

    submissions = db.get_submissions(event_id)

    st.divider()
    st.subheader("🏆 Live Leaderboard")

    leaderboard = calculate_leaderboard(submissions)
    if not leaderboard:
        st.info("No approved team scores yet.")
    else:
        for index, (team, score) in enumerate(leaderboard, start=1):
            medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else "⭐"
            st.metric(f"{medal} {index}. {team}", f"{format_score(score)} pts")

    enterprise_results = [
        s for s in submissions
        if str(s.get("SubmissionType", "")).upper() == "PIPELINE_ENTERPRISE"
        and str(s.get("Status", "")).upper() == "APPROVED"
    ]
    if enterprise_results:
        latest_enterprise = enterprise_results[-1]
        st.success(
            f"🤝 Enterprise Pipeline Score: {format_score(latest_enterprise.get('Score', 0))}%"
        )

    render_credit_wallet_control(db, event_id)
    render_road_hunt_operations(db, event_id)

    st.divider()
    st.subheader("🚀 Launch Mission")

    event_missions = db.get_event_missions(event_id, include_closed=True)
    if event_missions:
        mission_options = {
            f"{row.get('MissionID', '')} | {row.get('Title', '')} | {row.get('Status', '')}": row
            for row in event_missions
        }
        mission_label = st.selectbox(
            "Event Mission",
            list(mission_options),
            key="console_event_mission",
        )
        selected_mission = mission_options[mission_label]
        facilitator_instructions = str(
            selected_mission.get("FacilitatorInstructions", "") or ""
        ).strip()
        if facilitator_instructions:
            st.info("Facilitator: " + facilitator_instructions)
        if st.button("🚀 Launch Selected Mission", width="stretch"):
            db.launch_event_mission(
                event_id,
                selected_mission.get("MissionID", ""),
            )
            st.success("Mission launched. Previous LIVE mission closed automatically.")
            st.rerun()
    else:
        st.info("No event missions yet. Add them in Mission Studio or use Quick Create.")

    with st.expander("Quick Create Mission"):
        submission_type = st.selectbox(
            "Mission Type",
            [
                "PIPELINE",
                "PIPELINE_ENTERPRISE",
                "HELIUM",
                "KEYPUNCH",
                "CATALYST",
                "NASI",
                "PHOTO",
                "TEXT",
                "NONE",
            ],
            key="quick_mission_type",
        )
        defaults = mission_defaults(submission_type)

        mission_id = st.text_input("Mission ID", value=defaults["mission_id"])
        title = st.text_input("Mission Title", value=defaults["title"])
        description = st.text_area("Mission Instructions", value=defaults["description"])
        facilitator_instructions = st.text_area("Facilitator Instructions", value="")
        points = st.number_input("Points", min_value=0, value=defaults["points"], step=10)
        video_url = st.text_input("Video URL", value="")
        image_url = st.text_input("Image URL", value="")
        document_url = st.text_input("Document / PDF URL", value="")
        clue = st.text_area("Clue", value=defaults["clue"])
        answer = st.text_input("Answer", value="")
        hint1 = st.text_input("Hint 1", value="")
        hint2 = st.text_input("Hint 2", value="")
        hint3 = st.text_input("Hint 3", value="")
        ai_help_enabled = st.selectbox("AI Help Enabled", ["Yes", "No"])

        if st.button("🚀 Create and Launch", width="stretch"):
            db.send_mission(
                event_id=event_id,
                mission_id=mission_id,
                title=title,
                description=description,
                points=points,
                submission_type=submission_type,
                clue=clue,
                answer=answer,
                hint1=hint1,
                hint2=hint2,
                hint3=hint3,
                ai_help_enabled=ai_help_enabled,
                participant_instructions=description,
                facilitator_instructions=facilitator_instructions,
                video_url=video_url,
                image_url=image_url,
                document_url=document_url,
            )
            st.success("Mission created and launched.")
            st.rerun()

    st.divider()
    st.subheader("Current Mission")

    mission = db.get_current_mission(event_id)
    if mission:
        st.success(mission.get("Title", "Mission"))
        participant_instructions = str(
            mission.get("ParticipantInstructions", "")
            or mission.get("Description", "")
        ).strip()
        facilitator_instructions = str(
            mission.get("FacilitatorInstructions", "") or ""
        ).strip()
        if participant_instructions:
            st.write(participant_instructions)
        if facilitator_instructions:
            st.info("Facilitator: " + facilitator_instructions)
        display_video_url = get_mission_media_url(mission.get("VideoURL"))
        display_image_url = get_mission_media_url(mission.get("ImageURL"))
        display_document_url = get_mission_media_url(
            mission.get("DocumentURL")
        )
        if display_video_url:
            st.video(display_video_url)
        if display_image_url:
            st.image(display_image_url, width="stretch")
        if display_document_url:
            st.link_button(
                "📄 Open Mission Document",
                display_document_url,
            )
        if mission.get("DebriefQuestions"):
            with st.expander("Debrief Questions"):
                st.markdown(str(mission.get("DebriefQuestions")))
        st.caption(f"Submission Type: {mission.get('SubmissionType', '')}")
    else:
        st.info("No live mission yet.")

    render_enterprise_pipeline_form(db, event_id, mission)

    st.divider()
    st.subheader("📥 Mission Submissions")

    current_mission_id = mission.get("MissionID") if mission else None
    current_submissions = [
        row for row in submissions
        if not current_mission_id
        or str(row.get("MissionID", "")) == str(current_mission_id)
    ]

    pending_current = [
        row for row in current_submissions
        if str(row.get("Status", "")).upper() == "PENDING"
    ]

    if pending_current:
        mission_type = str(mission.get("SubmissionType", "") if mission else "").upper()
        bulk_score = 0 if mission_type == "NASI" else None

        if st.button(
            f"✅ Approve All Pending ({len(pending_current)})",
            width="stretch",
        ):
            count = 0
            for submission in pending_current:
                calculated_score, _ = calculate_score(submission)
                final_score = bulk_score if bulk_score is not None else calculated_score
                updated = db.update_submission_score(
                    submission_id=submission.get("SubmissionID"),
                    score=round(final_score, 1),
                    remarks=submission.get("Remarks", ""),
                    judged="Yes",
                    status="APPROVED",
                )
                if updated:
                    count += 1

            st.success(f"Approved {count} submission(s).")
            st.rerun()

    if not current_submissions:
        st.info("No submissions received for the current mission yet.")
    else:
        for submission in current_submissions:
            submission_id = submission.get("SubmissionID")
            suggested, formula = calculate_score(submission)
            approved = str(submission.get("Status", "")).upper() == "APPROVED"

            with st.container():
                st.markdown(
                    f"""
**{submission.get('TeamName', '')}**

- Participant: {submission.get('ParticipantName', '')}
- Mission: {submission.get('MissionID', '')}
- Type: {get_value(submission, 'SubmissionType', '')}
- Submitted: {submission.get('SubmittedAt', '')}
- Status: {get_value(submission, 'Status', 'PENDING')}
- Saved Score: {get_value(submission, 'Score', '')}
"""
                )

                render_submission_details(submission)
                st.info(f"Calculated score: **{format_score(suggested)}** — {formula}")

                override = st.checkbox(
                    "Override calculated score",
                    value=False,
                    key=f"override_{submission_id}",
                )

                final_score = suggested
                if override:
                    final_score = st.number_input(
                        "Override Score",
                        min_value=0.0,
                        max_value=1000.0,
                        value=float(suggested),
                        step=1.0,
                        key=f"score_{submission_id}",
                    )

                remarks = st.text_area(
                    "Remarks",
                    value=get_value(submission, "Remarks", ""),
                    key=f"remarks_{submission_id}",
                )

                button_label = "🔄 Update Score" if approved else "✅ Approve Submission"
                if st.button(
                    button_label,
                    key=f"approve_{submission_id}",
                    width="stretch",
                ):
                    db.update_submission_score(
                        submission_id=submission_id,
                        score=round(final_score, 1),
                        remarks=remarks,
                        judged="Yes",
                        status="APPROVED",
                    )
                    st.success("Submission updated.")
                    st.rerun()

                st.divider()

    if st.button("🔄 Refresh Now", width="stretch"):
        db.clear_cache()
        st.rerun()
