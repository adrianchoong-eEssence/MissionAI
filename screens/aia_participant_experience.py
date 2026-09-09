"""AIA UAT presentation over the certified participant experience."""
from __future__ import annotations

from components.participant_credential import participant_enrollment_credential
from screens import maxis_participant_experience as _experience
from services.aia_random_registration_event import aia_random_registration_event


def render_aia_theme_park_participant(db, enrollment_credential="", device_id="", workspace=None):
    """Use AIA's browser-local registration credential for Captain recovery.

    The shared presentation calls only the existing Core-v2 participant,
    Captain, evidence, and advisory paths. Maxis retains its Personal Key
    recovery path because it does not supply the optional callback below.
    """
    event_id, join_code = aia_random_registration_event()

    def recover_captain():
        credential = enrollment_credential or participant_enrollment_credential(
            event_id, key=f"aia_random_credential_{event_id}",
        )
        if not credential:
            raise RuntimeError("Secure registration is still loading.")
        return db.runtime.recover_team_formation_captain(join_code, credential, device_id)

    return _experience.render_maxis_theme_park_participant(
        db, enrollment_credential=enrollment_credential, device_id=device_id,
        workspace=workspace, captain_recovery=recover_captain,
    )
