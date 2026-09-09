"""Deployment-scoped identity for AIA's common self-registration entry."""
from __future__ import annotations

import os

import streamlit as st


DEFAULT_EVENT_ID = "AIA-TECH-20261023-UAT"
DEFAULT_JOIN_CODE = "AIAUAT"


def _value(name: str, default: str) -> str:
    value = str(os.getenv(name, "") or "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get(name, default) or default).strip()
    except Exception:
        return default


def aia_random_registration_event() -> tuple[str, str]:
    """Return the internally configured event; the join code is never rendered."""
    return (
        _value("AIA_EVENT_ID", DEFAULT_EVENT_ID).upper(),
        _value("AIA_JOIN_CODE", DEFAULT_JOIN_CODE).upper(),
    )
