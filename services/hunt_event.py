"""Deployment-scoped identity for dedicated, fixed-event Hunt entrypoints."""
from __future__ import annotations

import os

import streamlit as st


def _value(name: str, default: str) -> str:
    value = str(os.getenv(name, "") or "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get(name, default) or default).strip()
    except Exception:
        return default


def configured_hunt_event(prefix: str, default_event_id: str, default_join_code: str) -> tuple[str, str]:
    """Return a server-owned EventID/join code; neither is participant input."""
    return (
        _value(f"{prefix}_EVENT_ID", default_event_id).upper(),
        _value(f"{prefix}_JOIN_CODE", default_join_code).upper(),
    )
