"""AIA UAT presentation over the certified read-only participant experience."""
from __future__ import annotations

from screens import maxis_participant_experience as _experience
from services.aia_personal_key_event import aia_personal_key_event


def render_aia_theme_park_participant(db, enrollment_credential="", device_id="", workspace=None):
    """Use AIA's fixed Personal Key event for Captain recovery and Ask Mission AI.

    The shared presentation calls only the existing Core-v2 participant,
    Captain, evidence, and advisory paths. Overriding its deployment-scoped
    event resolver is local to the AIA entrypoint process; Maxis deployments
    import neither this module nor this resolver.
    """
    _experience.maxis_personal_key_event = aia_personal_key_event
    return _experience.render_maxis_theme_park_participant(
        db, enrollment_credential=enrollment_credential, device_id=device_id, workspace=workspace,
    )
