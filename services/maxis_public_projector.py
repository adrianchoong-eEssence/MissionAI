"""Public, presentation-only reader for the Maxis live projector.

The browser receives a publishable Supabase key and can call exactly one
allow-listed, fixed-event RPC.  This module deliberately has no service-key
fallback and no mutation method.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st


PUBLIC_PROJECTOR_RPC = "exos_v2_maxis_live_projector_projection"
POLL_INTERVAL_SECONDS = 5
_EVENT_FIELDS = frozenset({"DisplayName", "State", "HasAwardedScore"})
_TEAM_FIELDS = frozenset({"Country", "Flag", "Rank", "Score", "Completed", "Total"})


class PublicProjectorError(RuntimeError):
    """Safe, non-diagnostic public projector error."""


@dataclass(frozen=True)
class PublicProjectorClient:
    url: str
    publishable_key: str

    @classmethod
    def from_environment(cls) -> "PublicProjectorClient":
        def secret(name: str) -> str:
            try:
                value = st.secrets[name]
            except Exception:
                value = os.getenv(name, "")
            return str(value or "").strip()

        url = secret("SUPABASE_URL").rstrip("/")
        key = secret("SUPABASE_PUBLISHABLE_KEY") or secret("SUPABASE_ANON_KEY")
        if not url or not key:
            raise PublicProjectorError("Projector configuration is unavailable.")
        return cls(url=url, publishable_key=key)

    def projection(self) -> dict:
        request = Request(
            f"{self.url}/rest/v1/rpc/{PUBLIC_PROJECTOR_RPC}",
            data=b"{}",
            headers={
                "apikey": self.publishable_key,
                "Authorization": f"Bearer {self.publishable_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=12) as response:
                return normalise_public_projection(json.loads(response.read().decode("utf-8")))
        except (HTTPError, URLError, TimeoutError, ValueError, TypeError):
            raise PublicProjectorError("Live leaderboard is reconnecting. Please wait.") from None


def _number(value, *, integer: bool = False):
    try:
        return int(value) if integer else float(value)
    except (TypeError, ValueError):
        return 0 if integer else 0.0


def normalise_public_projection(payload: object) -> dict:
    """Keep the browser model strictly within the public RPC allow-list."""
    source = payload if isinstance(payload, dict) else {}
    event = source.get("Event") if isinstance(source.get("Event"), dict) else {}
    state = str(event.get("State") or "READY").upper()
    if state not in {"READY", "LIVE", "HOLD", "ENDED"}:
        state = "READY"
    teams = []
    for raw in source.get("Teams") or []:
        if not isinstance(raw, dict):
            continue
        teams.append({
            "Country": str(raw.get("Country") or "Team").strip(),
            "Flag": str(raw.get("Flag") or "🏳️").strip(),
            "Rank": _number(raw.get("Rank"), integer=True) if raw.get("Rank") is not None else None,
            "Score": _number(raw.get("Score")),
            "Completed": max(0, _number(raw.get("Completed"), integer=True)),
            "Total": max(0, _number(raw.get("Total"), integer=True)),
        })
    has_awarded_score = bool(event.get("HasAwardedScore"))
    teams.sort(key=lambda row: ((row["Rank"] if has_awarded_score and row["Rank"] is not None else 999), row["Country"]))
    return {
        "Event": {
            "DisplayName": str(event.get("DisplayName") or "MAXIS MISSION AI").strip(),
            "State": state,
            "HasAwardedScore": has_awarded_score,
        },
        "Teams": teams,
    }
