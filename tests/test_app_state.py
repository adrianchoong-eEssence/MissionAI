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


if __name__ == "__main__":
    unittest.main()
