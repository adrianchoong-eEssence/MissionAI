from pathlib import Path
from datetime import time

import pandas as pd
import streamlit as st
import yaml

from data.aia_customer_contact import (
    AIA_CUSTOMER_CONTACT_MARKETPLACE,
    AIA_CUSTOMER_CONTACT_MISSION_PLAN,
    AIA_CUSTOMER_CONTACT_STAGES,
    AIA_CUSTOMER_CONTACT_TEAMS,
    install_aia_customer_contact_pack,
)
from data.google_sheets import GoogleSheetsDB
from engines.programme_engine import ProgrammeEngine
from engines.recommendation_engine import RecommendationEngine
from engines.transformation_engine import TransformationEngine
from screens.app_state import select_active_event


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

    selected_event = select_active_event(
        events,
        label="Active Event",
        key="programme_builder_event",
    )
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

    option1, option2, option3, option4 = st.columns(4)
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
        include_marketplace = st.checkbox(
            "Include Marketplace",
            value=False,
            key=f"include_marketplace_{event_id}",
        )
    with option4:
        include_closing = st.checkbox(
            "Include Closing",
            value=True,
            key=f"include_closing_{event_id}",
        )

    marketplace_minutes = 30
    if include_marketplace:
        marketplace_minutes = st.number_input(
            "Marketplace Minutes",
            min_value=5,
            max_value=240,
            value=30,
            step=5,
            key=f"marketplace_minutes_{event_id}",
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
                include_marketplace=include_marketplace,
                marketplace_minutes=int(marketplace_minutes),
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


def render_saved_programme_packs(db):
    st.subheader("Reusable Programme Pack Library")
    st.caption(
        "Save a completed event once, then install its teams, missions, timeline "
        "and marketplace into any empty event."
    )

    events = db.get_events()
    if not events:
        st.warning("Create an event before using programme packs.")
        return

    event_options = {
        f"{event.get('EventID', '')} — {event.get('EventName', '')}": event
        for event in events
    }

    with st.expander("➕ Save a configured event as a reusable pack"):
        source_label = st.selectbox(
            "Configured Source Event",
            list(event_options.keys()),
            key="pack_source_event",
        )
        source_event = event_options[source_label]
        source_event_id = str(source_event.get("EventID", ""))
        pack_name = st.text_input(
            "Pack Name",
            value=str(source_event.get("EventName", "")),
            key=f"pack_name_{source_event_id}",
        )
        description = st.text_area(
            "Pack Description",
            value=(
                f"Reusable programme created from {source_event.get('EventName', '')}."
            ),
            key=f"pack_description_{source_event_id}",
        )
        if st.button(
            "💾 Save to Programme Pack Library",
            width="stretch",
            key=f"save_programme_pack_{source_event_id}",
        ):
            try:
                result = db.save_event_as_programme_pack(
                    source_event_id,
                    pack_name,
                    description,
                )
            except Exception as error:
                st.error(f"Programme pack could not be saved: {error}")
            else:
                st.success(
                    f"{result['PackName']} saved as {result['PackID']}."
                )
                st.rerun()

    packs = db.get_programme_packs()
    if not packs:
        st.info(
            "No reusable packs saved yet. The installed AIA event can now be "
            "saved as your first master pack."
        )
        return

    summary_rows = []
    for pack_row in packs:
        pack = db.get_programme_pack(pack_row.get("PackID", "")) or {}
        summary_rows.append({
            "Pack ID": pack.get("PackID", ""),
            "Programme Pack": pack.get("PackName", ""),
            "Source Event": pack.get("SourceEventID", ""),
            "Teams": len(pack.get("Teams", [])),
            "Missions": len(pack.get("Missions", [])),
            "Stages": len(pack.get("Stages", [])),
            "Marketplace": len(pack.get("Marketplace", [])),
            "Version": pack.get("Version", "1.0"),
        })
    st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

    st.markdown("#### Install a Saved Pack")
    pack_options = {
        f"{pack.get('PackID', '')} — {pack.get('PackName', '')}": pack
        for pack in packs
    }
    selected_pack_label = st.selectbox(
        "Programme Pack",
        list(pack_options.keys()),
        key="programme_pack_to_install",
    )
    selected_pack_row = pack_options[selected_pack_label]
    selected_pack = db.get_programme_pack(
        selected_pack_row.get("PackID", ""),
    ) or {}

    target_label = st.selectbox(
        "Empty Target Event",
        list(event_options.keys()),
        key="programme_pack_target_event",
    )
    target_event = event_options[target_label]
    target_event_id = str(target_event.get("EventID", ""))

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Teams", len(selected_pack.get("Teams", [])))
    metric2.metric("Missions", len(selected_pack.get("Missions", [])))
    metric3.metric("Timeline Stages", len(selected_pack.get("Stages", [])))
    metric4.metric("Marketplace", len(selected_pack.get("Marketplace", [])))

    st.warning(
        "Installing replaces the target event's teams, missions and timeline. "
        "It will stop automatically if participants have already joined."
    )
    confirmed = st.checkbox(
        "I confirm the selected target event is correct and has no participants",
        key=f"confirm_pack_install_{target_event_id}",
    )
    if st.button(
        "🚀 Install Selected Programme Pack",
        width="stretch",
        disabled=not confirmed,
        key=(
            f"install_saved_pack_{selected_pack.get('PackID', '')}_"
            f"{target_event_id}"
        ),
    ):
        try:
            result = db.install_programme_pack(
                selected_pack.get("PackID", ""),
                target_event_id,
            )
        except Exception as error:
            st.error(f"Programme pack installation failed: {error}")
        else:
            st.success(
                f"{result['PackName']} installed and published to "
                f"{result['EventID']}."
            )
            result1, result2, result3, result4 = st.columns(4)
            result1.metric("Teams", result["Teams"])
            result2.metric("Missions", result["Missions"])
            result3.metric("Stages", result["Stages"])
            result4.metric("Marketplace", result["MarketplaceItems"])


def render_programme_packs(db):
    render_saved_programme_packs(db)
    st.divider()
    st.markdown("### Ready-made Programme Installers")
    st.subheader("AIA Customer Contact — Innovate to Elevate")
    st.caption(
        "Installs the complete two-day programme into an empty event: six teams, "
        "Mission AI, SYNC AI, Innovation Credits, marketplace and Catalyst."
    )

    events = db.get_events()
    if not events:
        st.warning("Create the AIA event first.")
        return

    event = select_active_event(
        events,
        label="Event to Prepare",
        key="aia_pack_event",
    )
    event_id = str(event.get("EventID", ""))

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Teams", len(AIA_CUSTOMER_CONTACT_TEAMS))
    metric2.metric("Missions", len(AIA_CUSTOMER_CONTACT_MISSION_PLAN))
    metric3.metric("Show Control Stages", len(AIA_CUSTOMER_CONTACT_STAGES))
    metric4.metric("Marketplace Items", len(AIA_CUSTOMER_CONTACT_MARKETPLACE))

    st.info(
        "Mission AI is a synchronized 60-minute mission sprint, not a free-roaming "
        "treasure hunt. All six teams receive the same mission together, and each "
        "team can use its persistent AI Facilitator and controlled hints."
    )
    st.warning(
        "This replaces the selected event's teams and Show Control timeline. "
        "It will stop if any runtime participants already exist."
    )
    confirmed = st.checkbox(
        "I confirm this is the correct event and no participants have joined",
        key=f"confirm_aia_pack_{event_id}",
    )
    if st.button(
        "🚀 Install and Publish AIA Programme",
        width="stretch",
        disabled=not confirmed,
        key=f"install_aia_pack_{event_id}",
    ):
        try:
            result = install_aia_customer_contact_pack(db, event_id)
        except Exception as error:
            st.error(f"AIA programme installation failed: {error}")
            return

        st.success("AIA Customer Contact programme installed and published.")
        result1, result2, result3, result4 = st.columns(4)
        result1.metric("Teams Published", result["Teams"])
        result2.metric("Missions Published", result["Missions"])
        result3.metric("Timeline Stages", result["Stages"])
        result4.metric("Marketplace Items", result["MarketplaceItems"])

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
    pack_tab, live_tab, recommendation_tab = st.tabs([
        "Programme Packs",
        "Build Live Programme",
        "Recommendations",
    ])
    with pack_tab:
        render_programme_packs(db)
    with live_tab:
        render_live_programme_builder(db)
    with recommendation_tab:
        render_recommendation_builder()
