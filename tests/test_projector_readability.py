from unittest.mock import patch

from screens.leaderboard_display import (
    PROJECTOR_STYLES,
    display_current_mission,
)


def test_projector_styles_are_widescreen_and_distance_readable():
    assert "max-width: 1600px" in PROJECTOR_STYLES
    assert "font-size: clamp(84px, 8vw, 132px)" in PROJECTOR_STYLES
    assert "font-size: clamp(38px, 3.25vw, 54px)" in PROJECTOR_STYLES
    assert "line-height: 1.55" in PROJECTOR_STYLES
    assert "overflow-wrap: break-word" in PROJECTOR_STYLES
    assert "background: #061f3d" in PROJECTOR_STYLES
    assert "color: #ffffff" in PROJECTOR_STYLES


def test_current_experience_uses_non_shrinking_wrapped_text_classes():
    mission = {
        "Title": "A deliberately long Experience title that must wrap",
        "Description": (
            "This deliberately long instruction paragraph must remain readable "
            "from across a live event room without being reduced to tiny text."
        ),
    }

    with patch("screens.leaderboard_display.st.markdown") as markdown:
        display_current_mission(mission)

    rendered = markdown.call_args.args[0]
    assert 'class="projector-mission-title"' in rendered
    assert 'class="projector-body"' in rendered
    assert mission["Title"] in rendered
    assert mission["Description"] in rendered
