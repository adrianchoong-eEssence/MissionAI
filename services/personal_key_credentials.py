"""Event-scoped Personal Key credentials for PREASSIGNED Team Formation.

The six-character Personal Key is a human entry secret.  It is normalised and
converted to a deterministic, opaque base64url credential before it crosses
the Team Formation V1 RPC boundary.  Database migrations and RPC contracts are
deliberately unchanged.
"""
from __future__ import annotations

import base64
import hashlib
import re


DERIVATION_VERSION = "EXOS_TEAM_FORMATION_PERSONAL_KEY_V1"
_PERSONAL_KEY_PATTERN = re.compile(r"^[A-Z0-9]{6}$")
_TEAM_FORMATION_CREDENTIAL_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43,128}$")


def normalize_personal_key(personal_key: str) -> str:
    """Apply the authoritative trim/uppercase rule and reject all other forms."""
    normalized = str(personal_key or "").strip().upper()
    if not _PERSONAL_KEY_PATTERN.fullmatch(normalized):
        raise ValueError("Personal Key must be exactly six letters or digits.")
    return normalized


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(4, byteorder="big") + encoded


def derive_personal_key_credential(event_id: str, personal_key: str) -> str:
    """Return a deterministic 43-character event-scoped opaque credential."""
    normalized_event_id = str(event_id or "").strip().upper()
    if not normalized_event_id or "\x00" in normalized_event_id:
        raise ValueError("Event identity is required.")
    normalized_key = normalize_personal_key(personal_key)
    material = (
        DERIVATION_VERSION.encode("ascii")
        + b"\x00"
        + _frame(normalized_event_id)
        + _frame(normalized_key)
    )
    credential = base64.urlsafe_b64encode(hashlib.sha256(material).digest()).rstrip(b"=").decode("ascii")
    if not _TEAM_FORMATION_CREDENTIAL_PATTERN.fullmatch(credential):
        raise RuntimeError("Derived credential violates the Team Formation V1 contract.")
    return credential


def team_formation_credential_hash(derived_credential: str) -> str:
    """Mirror the frozen Team Formation V1 SHA-256 enrollment hash contract."""
    credential = str(derived_credential or "")
    if not _TEAM_FORMATION_CREDENTIAL_PATTERN.fullmatch(credential):
        raise ValueError("Derived credential violates the Team Formation V1 contract.")
    return hashlib.sha256(credential.encode("ascii")).hexdigest()
