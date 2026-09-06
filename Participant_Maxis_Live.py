"""Dedicated Streamlit entrypoint for the Maxis live participant app.

Deployment identity is intentionally separate from the Maxis UAT app. All
runtime behaviour remains in :mod:`Participant`, including configuration-driven
``MAXIS_PERSONAL_KEY_EVENT_ID`` and ``MAXIS_PERSONAL_KEY_JOIN_CODE`` selection.
This wrapper gives Streamlit Community Cloud a distinct main-file identity
without duplicating participant, Team Formation, or race logic.
"""
from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).with_name("Participant.py")), run_name="__main__")
