from pathlib import Path
from unittest.mock import patch

from branding import (
    PLATFORM_EXPANSION,
    PLATFORM_TAGLINE,
    PLATFORM_VERSION,
    footer,
    platform_hero,
    sidebar_identity,
)


ROOT = Path(__file__).resolve().parents[1]


def test_official_product_identity_is_canonical():
    assert PLATFORM_EXPANSION == "eEssence Xperiential Operating System"
    assert PLATFORM_TAGLINE == "Where Experiences Come Alive."
    assert PLATFORM_VERSION == "Version 1.0"


def test_product_hero_makes_exos_dominant():
    with patch("branding.st.markdown") as markdown:
        platform_hero()

    rendered = markdown.call_args.args[0]
    assert 'class="exos-product-mark">EXOS' in rendered
    assert PLATFORM_EXPANSION in rendered
    assert PLATFORM_TAGLINE in rendered


def test_sidebar_and_footer_use_official_identity():
    with patch("branding.st.sidebar.markdown") as sidebar_markdown:
        sidebar_identity()
    with patch("branding.st.markdown") as markdown:
        footer()

    sidebar = sidebar_markdown.call_args.args[0]
    footer_markup = markdown.call_args.args[0]
    for rendered in (sidebar, footer_markup):
        assert "EXOS" in rendered
        assert PLATFORM_EXPANSION in rendered
        assert PLATFORM_VERSION in rendered


def test_user_facing_brand_sources_contain_no_retired_product_name():
    paths = [
        ROOT / "MissionAI.py",
        ROOT / "branding.py",
        ROOT / "screens" / "events_home.py",
        ROOT / "screens" / "administration.py",
        ROOT / "screens" / "leaderboard_display.py",
        ROOT / "static" / "exos-participant.webmanifest",
        ROOT / "Assets" / "exos" / "exos-horizontal-light.svg",
        ROOT / "Assets" / "exos" / "exos-horizontal-dark.svg",
        ROOT / "Assets" / "exos" / "exos-vertical-light.svg",
    ]
    retired_names = (
        "Event Operating System",
        "Event OS",
        "eEssence eXperiential OS",
        "EXOS 2026.07 Consolidation RC1",
    )

    for path in paths:
        content = path.read_text()
        for retired_name in retired_names:
            assert retired_name not in content, f"{retired_name} remains in {path}"
