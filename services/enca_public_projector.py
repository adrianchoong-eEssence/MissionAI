"""Public, read-only ENCA cumulative-score projector client."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st


POLL_INTERVAL_SECONDS = 5


class EncaPublicProjectorError(RuntimeError):
    """Safe public projector error with no configuration detail."""


@dataclass(frozen=True)
class EncaPublicProjectorClient:
    url: str
    publishable_key: str
    event_id: str

    @classmethod
    def from_environment(cls, event_id: str) -> "EncaPublicProjectorClient":
        def secret(name: str) -> str:
            try:
                value = st.secrets[name]
            except Exception:
                value = os.getenv(name, "")
            return str(value or "").strip()
        url = secret("SUPABASE_URL").rstrip("/")
        key = secret("SUPABASE_PUBLISHABLE_KEY") or secret("SUPABASE_ANON_KEY")
        if not url or not key:
            raise EncaPublicProjectorError("Projector configuration is unavailable.")
        return cls(url=url, publishable_key=key, event_id=str(event_id or "").strip())

    def projection(self) -> dict:
        request = Request(
            f"{self.url}/rest/v1/rpc/exos_v2_competition_public_projector_projection",
            data=json.dumps({"p_event_id": self.event_id}).encode("utf-8"),
            headers={"apikey": self.publishable_key, "Authorization": f"Bearer {self.publishable_key}",
                     "Accept": "application/json", "Content-Type": "application/json"}, method="POST",
        )
        try:
            with urlopen(request, timeout=12) as response:
                return normalise_enca_projection(json.loads(response.read().decode("utf-8")))
        except (HTTPError, URLError, TimeoutError, ValueError, TypeError):
            raise EncaPublicProjectorError("Live leaderboard is reconnecting. Please wait.") from None


def _number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalise_enca_projection(payload: object) -> dict:
    """Keep only safe team identity, current stage, rank and cumulative score."""
    source = payload if isinstance(payload, dict) else {}
    event = source.get("Event") if isinstance(source.get("Event"), dict) else {}
    state = str(event.get("CurrentStageState") or "READY").upper()
    if state not in {"READY", "LOCKED", "AVAILABLE", "ACTIVE", "COMPLETED"}:
        state = "READY"
    teams = [
        {
            "Country": str(row.get("Country") or row.get("TeamName") or "Team").strip(),
            "Flag": str(row.get("Flag") or "").strip(),
            "Rank": max(0, int(_number(row.get("Rank")))),
            "Score": _number(row.get("Score")),
        }
        for row in source.get("Teams") or [] if isinstance(row, dict)
    ]
    return {
        "Event": {
            "DisplayName": str(event.get("EventName") or "ENCA TEAM BUILDING 2026").strip(),
            "CurrentStage": str(event.get("CurrentStage") or "").strip(),
            "State": state,
        },
        "Teams": sorted(teams, key=lambda row: (row["Rank"], row["Country"])),
    }
