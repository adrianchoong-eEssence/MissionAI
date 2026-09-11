"""Public, read-only Hunt projector client using a publishable key only."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st


POLL_INTERVAL_SECONDS = 5


class HuntPublicProjectorError(RuntimeError):
    """Safe public-facing error with no deployment diagnostics."""


@dataclass(frozen=True)
class HuntPublicProjectorClient:
    url: str
    publishable_key: str
    event_id: str

    @classmethod
    def from_environment(cls, event_id: str) -> "HuntPublicProjectorClient":
        def secret(name: str) -> str:
            try:
                value = st.secrets[name]
            except Exception:
                value = os.getenv(name, "")
            return str(value or "").strip()
        url = secret("SUPABASE_URL").rstrip("/")
        key = secret("SUPABASE_PUBLISHABLE_KEY") or secret("SUPABASE_ANON_KEY")
        if not url or not key:
            raise HuntPublicProjectorError("Projector configuration is unavailable.")
        return cls(url=url, publishable_key=key, event_id=str(event_id or "").strip())

    def projection(self) -> dict:
        request = Request(
            f"{self.url}/rest/v1/rpc/exos_v2_hunt_public_projector_projection",
            data=json.dumps({"p_event_id": self.event_id}).encode("utf-8"),
            headers={"apikey": self.publishable_key, "Authorization": f"Bearer {self.publishable_key}",
                     "Accept": "application/json", "Content-Type": "application/json"}, method="POST",
        )
        try:
            with urlopen(request, timeout=12) as response:
                return normalise_hunt_projection(json.loads(response.read().decode("utf-8")))
        except (HTTPError, URLError, TimeoutError, ValueError, TypeError):
            raise HuntPublicProjectorError("Live leaderboard is reconnecting. Please wait.") from None


def _number(value: object, *, integer: bool = False):
    try:
        return int(value) if integer else float(value)
    except (TypeError, ValueError):
        return 0 if integer else 0.0


def normalise_hunt_projection(payload: object) -> dict:
    """Drop every field other than the explicit public leaderboard contract."""
    source = payload if isinstance(payload, dict) else {}
    event = source.get("Event") if isinstance(source.get("Event"), dict) else {}
    state = str(event.get("State") or "READY").upper()
    if state not in {"READY", "LIVE", "HOLD", "RETURN_NOW", "CLOSED"}:
        state = "READY"
    teams = [{
        "TeamName": str(row.get("TeamName") or "Team"), "Rank": _number(row.get("Rank"), integer=True),
        "Score": _number(row.get("Score")), "Completed": max(0, _number(row.get("Completed"), integer=True)),
        "Total": max(0, _number(row.get("Total"), integer=True)),
    } for row in source.get("Teams") or [] if isinstance(row, dict)]
    return {"Event": {"DisplayName": str(event.get("EventName") or "GEORGE TOWN").strip(), "State": state},
            "Teams": sorted(teams, key=lambda row: (row["Rank"], row["TeamName"]))}
