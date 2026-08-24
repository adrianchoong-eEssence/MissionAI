"""Browser-local opaque enrollment credential for Team Formation V1.

The raw credential is deliberately never placed in query parameters.  The
database stores only the SHA-256 value through the Team Formation RPCs.
"""
from pathlib import Path

import streamlit.components.v1 as components


_COMPONENT_PATH = Path(__file__).parent / "participant_credential"
_participant_credential = components.declare_component(
    "exos_participant_credential",
    path=str(_COMPONENT_PATH),
)


def participant_enrollment_credential(event_id, key=None):
    """Return the event-scoped base64url 32-byte value retained by this browser."""
    value = _participant_credential(
        event_id=str(event_id or "").strip(),
        key=key or f"team_formation_credential_{event_id}",
        default={},
    )
    credential = value.get("Credential", "") if isinstance(value, dict) else ""
    # base64url(32 bytes), without padding, is always 43 characters.
    return credential if len(str(credential)) == 43 else ""
