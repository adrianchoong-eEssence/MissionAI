"""Deployment-scoped identity for the Maxis Personal Key experience.

The UAT deployment remains compatible by default.  A dedicated live
participant deployment supplies both environment values, which avoids
repointing the UAT app or accepting an arbitrary event from a URL.
"""
from __future__ import annotations

import os

import streamlit as st


DEFAULT_EVENT_ID = "MAXIS-UAT-PREASSIGNED"
DEFAULT_JOIN_CODE = "MXKEY7"


def _configured_value(key: str, default: str) -> str:
    value = str(os.getenv(key, "") or "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get(key, "") or default).strip()
    except Exception:
        return default


def maxis_personal_key_event() -> tuple[str, str]:
    """Return the one event this deployment is allowed to authenticate."""
    event_id = _configured_value("MAXIS_PERSONAL_KEY_EVENT_ID", DEFAULT_EVENT_ID).upper()
    join_code = _configured_value("MAXIS_PERSONAL_KEY_JOIN_CODE", DEFAULT_JOIN_CODE).upper()
    if not event_id or not join_code:
        raise RuntimeError("Maxis Personal Key event configuration is incomplete.")
    return event_id, join_code


def is_maxis_personal_key_request(params) -> bool:
    """Require the configured join code and the non-secret URL mode flag."""
    value = params.get("personal_key", "")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    requested = params.get("join_code", "")
    if isinstance(requested, (list, tuple)):
        requested = requested[0] if requested else ""
    _, join_code = maxis_personal_key_event()
    return str(value or "").strip() == "1" and str(requested or "").strip().upper() == join_code
