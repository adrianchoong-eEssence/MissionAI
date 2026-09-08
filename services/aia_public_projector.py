"""AIA's fixed-event public projector client: publishable key, read-only RPC."""
from __future__ import annotations

from services.maxis_public_projector import (POLL_INTERVAL_SECONDS, PublicProjectorError,
                                             normalise_public_projection)
from services.maxis_public_projector import PublicProjectorClient as _Client

PUBLIC_PROJECTOR_RPC = "exos_v2_aia_tech_projector_projection"


class AIAPublicProjectorClient(_Client):
    def projection(self) -> dict:
        # Keep this call's only browser capability as one fixed, public SQL projection.
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen
        import json
        request = Request(f"{self.url}/rest/v1/rpc/{PUBLIC_PROJECTOR_RPC}", data=b"{}", headers={
            "apikey": self.publishable_key, "Authorization": f"Bearer {self.publishable_key}",
            "Accept": "application/json", "Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=12) as response:
                return normalise_public_projection(json.loads(response.read().decode("utf-8")))
        except (HTTPError, URLError, TimeoutError, ValueError, TypeError):
            raise PublicProjectorError("Live leaderboard is reconnecting. Please wait.") from None
