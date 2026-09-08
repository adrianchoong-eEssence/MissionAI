import unittest

from streamlit.testing.v1 import AppTest


class ActiveEventStateTests(unittest.TestCase):
    def test_changed_event_selection_is_not_reset(self):
        app = AppTest.from_string(
            """
import streamlit as st

from screens.app_state import select_active_event

events = [
    {"EventID": "E1", "EventName": "One"},
    {"EventID": "E2", "EventName": "Two"},
]
event = select_active_event(events, key="picker")
st.write(event["EventID"])
"""
        )

        app.run()
        self.assertEqual(app.markdown[-1].value, "E1")

        app.selectbox[0].select("E2").run()

        self.assertEqual(app.selectbox[0].value, "E2")
        self.assertEqual(app.markdown[-1].value, "E2")
        self.assertEqual(app.exception, [])

    def test_widget_follows_event_selected_in_another_workspace(self):
        app = AppTest.from_string(
            """
import streamlit as st

from screens.app_state import ACTIVE_EVENT_KEY, select_active_event

events = [
    {"EventID": "E1", "EventName": "One"},
    {"EventID": "E2", "EventName": "Two"},
]
if st.button("Use E2"):
    st.session_state[ACTIVE_EVENT_KEY] = "E2"
event = select_active_event(events, key="projector_picker")
st.write(event["EventID"])
"""
        )

        app.run()
        self.assertEqual(app.selectbox[0].value, "E1")

        app.button[0].click().run()

        self.assertEqual(app.selectbox[0].value, "E2")
        self.assertEqual(app.markdown[-1].value, "E2")
        self.assertEqual(app.exception, [])

    def test_control_event_selection_replaces_a_stale_event_id_on_refresh(self):
        app = AppTest.from_string(
            """
import streamlit as st
from screens.app_state import ACTIVE_EVENT_KEY, select_active_event

events = [{"EventID": "UAT", "EventName": "UAT"}, {"EventID": "LIVE", "EventName": "Live"}]
if "event_id" not in st.query_params:
    st.query_params["event_id"] = "UAT"
if "loaded" not in st.session_state:
    st.session_state.loaded = True
    st.session_state[ACTIVE_EVENT_KEY] = st.query_params["event_id"]
event = select_active_event(events, key="control_event")
st.write(f"{event['EventID']}|{st.query_params['event_id']}")
"""
        )
        app.run()
        app.selectbox[0].select("LIVE").run()
        self.assertEqual(app.markdown[-1].value, "LIVE|LIVE")
        app.run()
        self.assertEqual(app.markdown[-1].value, "LIVE|LIVE")


if __name__ == "__main__":
    unittest.main()
