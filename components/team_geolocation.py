from pathlib import Path

import streamlit.components.v1 as components


_COMPONENT_PATH = Path(__file__).parent / "team_geolocation"
_team_geolocation = components.declare_component(
    "exos_team_geolocation",
    path=str(_COMPONENT_PATH),
)


def team_geolocation(interval_seconds=20, key=None):
    """Start an explicit, participant-controlled browser GPS watch."""
    return _team_geolocation(
        interval_seconds=max(10, min(int(interval_seconds or 20), 120)),
        key=key,
        default=None,
    )
