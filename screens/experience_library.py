import streamlit as st
from engines.recommendation_engine import RecommendationEngine


def show_experience_library():

    st.title("Experience Library")

    keyword = st.text_input(
        "Search",
        placeholder="leadership, communication..."
    )

    engine = RecommendationEngine()

    if keyword == "":
        activities = engine.engine.all()
    else:
        activities = engine.recommend(keyword)

    for activity in activities:

        name = activity.get("activity", {}).get("name", "Unknown")

        st.subheader(name)

        if "summary" in activity:
            st.write(activity["summary"])

        if "learning_objectives" in activity:

            st.write("Learning Objectives")

            st.write(", ".join(activity["learning_objectives"]))

        st.divider()