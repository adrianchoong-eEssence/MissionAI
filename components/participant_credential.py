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


def participant_device_binding(event_id, key=None):
    """Return the opaque credential and stable event-scoped device binding.

    Both values live only in this browser's local storage. The credential is
    the canonical Team Formation recovery secret; the paired device value is
    never copied into a name field or used to identify a different event.
    ``None`` means the component is still loading, not that this is a new
    browser.
    """
    value = _participant_credential(
        event_id=str(event_id or "").strip(),
        key=key or f"team_formation_binding_{event_id}",
        default={"Ready": False},
    )
    if not isinstance(value, dict) or value.get("Ready") is not True:
        return None
    credential = str(value.get("Credential", "") or "")
    device_id = str(value.get("DeviceID", "") or "")
    if len(credential) != 43 or len(device_id) != 43:
        return None
    return {
        "Credential": credential,
        "DeviceID": device_id,
        "HasStoredCredential": bool(value.get("HasStoredCredential")),
    }
