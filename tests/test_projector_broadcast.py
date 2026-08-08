import json
from pathlib import Path
from unittest.mock import patch

from screens.projector_broadcast import (
    BROADCAST_MODES,
    projector_broadcast_state,
    render_projector_broadcast,
)


ROOT = Path(__file__).resolve().parents[1]


def test_all_facilitator_broadcast_modes_are_available():
    assert BROADCAST_MODES == [
        "Welcome",
        "Current Activity",
        "Multiple Activities",
        "Leaderboard",
        "Scores",
        "Timer",
        "Instructions",
        "Results",
        "Championship",
        "Custom Message",
        "Blank",
    ]


def test_broadcast_state_normalises_legacy_modes():
    event = {
        "EventID": "EVT-0004",
        "Notes": json.dumps({
            "ProjectorBroadcast": {
                "Mode": "Announcement",
                "Title": "Lunch Break",
                "Message": "Return at 2:00 PM",
                "PresentationMode": True,
            },
        }),
    }

    state = projector_broadcast_state(event)

    assert state["Mode"] == "Custom Message"
    assert state["Title"] == "Lunch Break"
    assert state["Message"] == "Return at 2:00 PM"
    assert state["PresentationMode"] is True


def test_custom_message_renders_as_full_screen_projector_content():
    with patch("screens.projector_broadcast.st.markdown") as markdown:
        rendered = render_projector_broadcast(
            {
                "Mode": "Custom Message",
                "Title": "Lunch Break",
                "Message": "Return at 2:00 PM",
                "PresentationMode": True,
            },
            event={},
            mission={},
            leaderboard=[],
            wallet_status={},
            timer={},
        )

    markup = markdown.call_args.args[0]
    assert rendered is True
    assert "Lunch Break" in markup
    assert "Return at 2:00 PM" in markup
    assert "broadcast-presentation" in markup.lower()


def test_blank_mode_is_a_true_black_projector_screen():
    with patch("screens.projector_broadcast.st.markdown") as markdown:
        rendered = render_projector_broadcast(
            {"Mode": "Blank"},
            event={},
            mission={},
            leaderboard=[],
            wallet_status={},
            timer={},
        )

    assert rendered is True
    assert 'class="broadcast-blank"' in markdown.call_args.args[0]


def test_current_activity_mode_uses_current_experience_without_mutating_it():
    mission = {
        "Title": "The Paris Fragment",
        "ParticipantInstructions": "Recover visual confirmation.",
        "ReferenceImageURL": "static/bayu/paris.jpg",
    }
    original = dict(mission)
    with patch(
        "screens.projector_broadcast.get_mission_media_url",
        return_value="https://example.test/paris.jpg",
    ), patch("screens.projector_broadcast.st.markdown") as markdown:
        render_projector_broadcast(
            {"Mode": "Current Activity", "PresentationMode": True},
            event={"EventName": "Demo"},
            mission=mission,
            leaderboard=[],
            wallet_status={},
            timer={},
        )

    markup = markdown.call_args.args[0]
    assert "The Paris Fragment" in markup
    assert "Recover visual confirmation." in markup
    assert "https://example.test/paris.jpg" in markup
    assert mission == original


def test_control_centre_no_longer_writes_projector_copy_to_participants():
    source = (ROOT / "screens" / "control_centre.py").read_text()

    assert "render_broadcast_controller(db, event_id, control=control)" in source
    assert "Broadcast sent to participant and projector views." not in source
