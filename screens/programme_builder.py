from pathlib import Path
from datetime import time

import pandas as pd
import streamlit as st
import yaml

from data.google_sheets import GoogleSheetsDB
from engines.programme_engine import ProgrammeEngine
from engines.recommendation_engine import RecommendationEngine
from engines.transformation_engine import TransformationEngine


def get_activity_name(activity):
    activity_data = activity.get("activity", {})
    if isinstance(activity_data, dict):
        return activity_data.get("name", activity.get("name", "Unknown"))
    return activity.get("name", "Unknown")


def load_codeshift_lens():
    file_path = Path("knowledge_base/transformation_frameworks/codeshift.yaml")
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def build_timeline(recommended_names):
    timeline = [
        ("09:00", "Registration"),
        ("09:15", "Opening & Energizer"),
        ("09:30", "Group Formation"),
    ]
    slots = ["10:00", "11:00", "12:00"]
    for index, activity in enumerate(recommended_names[:3]):
        timeline.append((slots[index], activity))
        timeline.append(("After Activity", "Debrief"))
    timeline.append(("End", "Closing & Commitment"))
    return timeline


def render_existing_programme(db, event_id):
    stages = db.get_programme_stages(event_id)
    st.markdown("#### Current Programme Timeline")
    if not stages:
        st.info("No programme has been built for this event yet.")
        return

    columns = [
        "StageNo",
        "StartTime",
        "DurationMinutes",
        "StageName",
        "StageType",
        "MissionID",
        "DisplayMode",
    ]
    st.dataframe(
        [{column: stage.get(column, "") for column in columns} for stage in stages],
        width="stretch",
        hide_index=True,
    )


def render_live_programme_builder(db):
    st.subheader("Build a Live Mission Programme")
    st.caption(
        "Choose missions in running order. EXOS creates the event missions and Show Control timeline together."
    )

    events = db.get_events()
    templates = db.get_mission_templates()
    if not events:
        st.warning("Create an event first.")
        return
    if not templates:
        st.warning("Create or import missions in Mission Studio first.")
        return

    event_options = {
        f"{event.get('EventID', '')} | {event.get('EventName', '')}": event
        for event in events
    }
    selected_event_label = st.selectbox(
        "Event",
        list(event_options),
        key="programme_builder_event",
    )
    selected_event = event_options[selected_event_label]
    event_id = str(selected_event.get("EventID", ""))

    template_options = {
        f"{template.get('TemplateID', '')} | {template.get('Title', '')}": template
        for template in templates
    }
    selected_template_labels = st.multiselect(
        "Missions — select them in running order",
        list(template_options),
        key=f"programme_builder_templates_{event_id}",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        programme_start = st.time_input(
            "Programme Start",
            value=time(9, 0),
            key=f"programme_start_{event_id}",
        )
    with col2:
        registration_minutes = st.number_input(
            "Registration Minutes",
            min_value=0,
            max_value=180,
            value=15,
            step=5,
            key=f"registration_minutes_{event_id}",
        )
    with col3:
        debrief_minutes = st.number_input(
            "Debrief Minutes per Mission",
            min_value=0,
            max_value=120,
            value=15,
            step=5,
            key=f"debrief_minutes_{event_id}",
        )

    option1, option2, option3 = st.columns(3)
    with option1:
        include_registration = st.checkbox(
            "Include Registration",
            value=True,
            key=f"include_registration_{event_id}",
        )
    with option2:
        include_team_discovery = st.checkbox(
            "Include Team Discovery",
            value=True,
            key=f"include_team_discovery_{event_id}",
        )
    with option3:
        include_closing = st.checkbox(
            "Include Closing",
            value=True,
            key=f"include_closing_{event_id}",
        )

    if not selected_template_labels:
        render_existing_programme(db, event_id)
        return

    plan_rows = []
    for index, label in enumerate(selected_template_labels, start=1):
        template = template_options[label]
        plan_rows.append({
            "Order": index,
            "TemplateID": template.get("TemplateID", ""),
            "MissionID": f"M{index:02d}",
            "Mission": template.get("Title", ""),
            "DurationMinutes": 30,
            "IncludeDebrief": True,
        })

    st.markdown("#### Running Order")
    edited_plan = st.data_editor(
        pd.DataFrame(plan_rows),
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        disabled=["TemplateID", "Mission"],
        column_config={
            "Order": st.column_config.NumberColumn(
                "Order",
                min_value=1,
                step=1,
                required=True,
            ),
            "MissionID": st.column_config.TextColumn(
                "Mission ID",
                required=True,
            ),
            "DurationMinutes": st.column_config.NumberColumn(
                "Mission Minutes",
                min_value=1,
                max_value=480,
                step=5,
                required=True,
            ),
            "IncludeDebrief": st.column_config.CheckboxColumn(
                "Add Debrief",
            ),
        },
        key=f"programme_plan_editor_{event_id}",
    )

    confirm_replace = st.checkbox(
        "Replace the current Show Control timeline for this event",
        key=f"confirm_programme_replace_{event_id}",
    )
    if st.button(
        "🚀 Build and Publish Programme",
        width="stretch",
        key=f"build_programme_{event_id}",
    ):
        if not confirm_replace:
            st.error("Confirm the timeline replacement first.")
            return

        plan = edited_plan.sort_values("Order").to_dict("records")
        try:
            result = db.build_event_programme(
                event_id=event_id,
                mission_plan=plan,
                start_time=programme_start.strftime("%H:%M"),
                include_registration=include_registration,
                registration_minutes=int(registration_minutes),
                include_team_discovery=include_team_discovery,
                team_discovery_minutes=15,
                debrief_minutes=int(debrief_minutes),
                include_closing=include_closing,
            )
        except Exception as error:
            st.error(f"Programme build failed: {error}")
            return

        st.success("Programme built and published to Show Control.")
        metric1, metric2, metric3 = st.columns(3)
        metric1.metric("Missions", result["Missions"])
        metric2.metric("Stages", result["Stages"])
        metric3.metric("Scheduled End", result["ProgrammeEndTime"])
        db.clear_cache()
        st.rerun()

    render_existing_programme(db, event_id)


def render_recommendation_builder():
    st.subheader("Programme Recommendations")
    programme_engine = ProgrammeEngine()
    recommendation_engine = RecommendationEngine()
    transformation_engine = TransformationEngine()

    pattern = programme_engine.get_pattern("team_building")
    if pattern:
        st.markdown("#### Learning Journey")
        for stage in pattern.get("learning_journey", []):
            st.write(f"➡️ {stage}")

    st.divider()
    intents = transformation_engine.get_programme_intents()
    selected_intent = st.selectbox(
        "Why is this programme being organised?",
        intents,
        key="recommendation_programme_intent",
    )
    intent_info = transformation_engine.analyse_intent(selected_intent) or {}
    if intent_info:
        st.info(intent_info.get("purpose", ""))
        st.markdown("#### Desired Outcomes")
        for item in intent_info.get("outcome", []):
            st.write(f"• {item}")

    if st.button("Generate Recommendations", key="generate_programme_recommendations"):
        results = recommendation_engine.recommend(intent_info.get("outcome", []))
        recommended = []
        for result in results:
            if result["score"] > 0:
                name = get_activity_name(result["activity"])
                recommended.append(name)
                st.success(name)

        if recommended:
            st.markdown("#### Suggested Timeline")
            for time, activity in build_timeline(recommended):
                st.write(f"**{time}** — {activity}")

        codeshift = load_codeshift_lens()
        if codeshift:
            with st.expander("CodeShift Facilitator Reflection"):
                st.info(codeshift.get("purpose", ""))
                for question in codeshift.get("core_lens", []):
                    st.write(f"• {question}")


def show_programme_builder():
    st.title("🛠 Programme Builder")
    db = GoogleSheetsDB()
    live_tab, recommendation_tab = st.tabs([
        "Build Live Programme",
        "Recommendations",
    ])
    with live_tab:
        render_live_programme_builder(db)
    with recommendation_tab:
        render_recommendation_builder()
