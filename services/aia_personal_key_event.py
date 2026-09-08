"""Deployment-scoped identity for the dedicated AIA participant app."""
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


def aia_personal_key_event() -> tuple[str, str]:
    return _value("AIA_PERSONAL_KEY_EVENT_ID", DEFAULT_EVENT_ID).upper(), _value("AIA_PERSONAL_KEY_JOIN_CODE", DEFAULT_JOIN_CODE).upper()


def is_aia_personal_key_request(params) -> bool:
    requested = params.get("join_code", "")
    if isinstance(requested, (list, tuple)):
        requested = requested[0] if requested else ""
    enabled = params.get("personal_key", "")
    if isinstance(enabled, (list, tuple)):
        enabled = enabled[0] if enabled else ""
    _, join_code = aia_personal_key_event()
    return str(enabled).strip() == "1" and str(requested).strip().upper() == join_code
