"""Participant-controlled browser Live Location component."""
from pathlib import Path
import streamlit.components.v1 as components


_component = components.declare_component("exos_live_location", path=str(Path(__file__).parent / "live_location"))


def participant_live_location(*, cadence_seconds=20, key=None):
    return _component(interval_seconds=max(15, min(int(cadence_seconds or 20), 30)), key=key, default=None)
