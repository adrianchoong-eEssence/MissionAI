import streamlit as st
from pathlib import Path
import yaml

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

    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_timeline(recommended_names):

    timeline = [
        ("09:00", "Registration"),
        ("09:15", "Opening & Energizer"),
        ("09:30", "Group Formation"),
    ]

    slots = ["10:00", "11:00", "12:00"]

    for i, activity in enumerate(recommended_names[:3]):
        timeline.append((slots[i], activity))
        timeline.append(("After Activity", "Debrief"))

    timeline.append(("End", "Closing & Commitment"))

    return timeline


def show_programme_builder():

    st.title("🛠 Programme Builder")

    programme_engine = ProgrammeEngine()
    recommendation_engine = RecommendationEngine()
    transformation_engine = TransformationEngine()

    pattern = programme_engine.get_pattern("team_building")

    if pattern:

        st.subheader("Learning Journey")

        for stage in pattern.get("learning_journey", []):
            st.write(f"➡️ {stage}")

        st.divider()

    st.subheader("Programme Intent")

    intents = transformation_engine.get_programme_intents()

    selected_intent = st.selectbox(
        "Why is this programme being organised?",
        intents
    )

    intent_info = transformation_engine.analyse_intent(selected_intent)

    if intent_info:

        st.info(intent_info.get("purpose", ""))

        st.write("### Desired Outcomes")

        for item in intent_info.get("outcome", []):
            st.write(f"• {item}")

    st.divider()

    if st.button("🚀 Generate Programme"):

        objectives = intent_info.get("outcome", [])

        results = recommendation_engine.recommend(objectives)

        st.subheader("Mission AI Recommendations")

        recommended = []

        for result in results:

            if result["score"] > 0:

                activity = result["activity"]

                name = get_activity_name(activity)

                recommended.append(name)

                st.success(name)

        st.divider()

        st.subheader("Programme Timeline")

        timeline = build_timeline(recommended)

        for time, activity in timeline:
            st.write(f"**{time}** — {activity}")

        st.divider()

        st.subheader("CodeShift Transformation Lens")

        codeshift = load_codeshift_lens()

        if codeshift:
            st.info(codeshift.get("purpose", ""))

            with st.expander("Facilitator Reflection"):
                for question in codeshift.get("core_lens", []):
                    st.write(f"• {question}")