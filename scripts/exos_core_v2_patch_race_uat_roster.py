#!/usr/bin/env python3
"""Patch a single staging Formula R.A.C.E. UAT event roster."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

KNOWN_PROD_HOSTS = {
    "bqsbkdfzqyiodivhyxnq.supabase.co",
}

TARGET_EVENT_ID = "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"
TARGET_JOIN_CODE = "RACE4CF0CE"
TARGET_EVENT_SUFFIX = TARGET_EVENT_ID.rsplit("-", 1)[-1]
TARGET_NAMES = [
    "SANDSTORM",
    "BOLT",
    "ZENITH",
    "SCUDERIA BEST",
    "APEX VELOCITY",
    "VELOCITY",
    "FAST & CURIOUS",
    "LAKAS",
    "DRIFT CLUB",
    "PAPAYA CREW",
]


class RequestFailure(RuntimeError):
    def __init__(self, method: str, path: str, status: int | None, body: str):
        super().__init__(body)
        self.method = method
        self.path = path
        self.status = status
        self.body = body


def _require_staging_env() -> tuple[str, str, str, str]:
    import os

    env = str(os.getenv("EXOS_ENV", "")).strip().lower()
    if env != "staging":
        raise RuntimeError("Refusing to run: EXOS_ENV must be exactly 'staging'.")

    supabase_url = str(os.getenv("SUPABASE_URL", "")).strip().rstrip("/")
    anon_key = str(os.getenv("SUPABASE_PUBLISHABLE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")).strip()
    service_key = str(os.getenv("SUPABASE_SECRET_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")).strip()

    if not supabase_url:
        raise RuntimeError("SUPABASE_URL is required.")
    if not anon_key:
        raise RuntimeError("SUPABASE_PUBLISHABLE_KEY (or SUPABASE_ANON_KEY) is required.")
    if not service_key:
        raise RuntimeError("SUPABASE_SECRET_KEY (or SUPABASE_SERVICE_ROLE_KEY) is required.")

    host = (urlparse(supabase_url).hostname or "").lower()
    if host in KNOWN_PROD_HOSTS:
        raise RuntimeError(f"Refusing to run against known production host: {host}")
    return supabase_url, anon_key, service_key, host


class RestClient:
    def __init__(self, url: str, anon_key: str, service_key: str):
        self.url = url
        self.anon_key = anon_key
        self.service_key = service_key

    def request(self, method: str, path: str, payload=None, query=None, prefer=None):
        endpoint = f"{self.url}/rest/v1/{path.lstrip('/')}"
        if query:
            endpoint = f"{endpoint}?{urlencode(query, doseq=True, safe='(),.*')}"
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(endpoint, method=method.upper(), headers=headers, data=data)
        if prefer:
            req.add_header("Prefer", prefer)
        try:
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return True
                return json.loads(raw)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RequestFailure(method.upper(), path, exc.code, body or exc.reason)
        except (URLError, TimeoutError) as exc:
            raise RequestFailure(method.upper(), path, None, str(exc))

    def get(self, path: str, query=None):
        return self.request("GET", path, query=query)

    def patch(self, path: str, query=None, payload=None):
        return self.request("PATCH", path, payload=payload, query=query, prefer="return=representation")


def _team_index(team_id: str, event_id: str) -> int | None:
    event_suffix = event_id.rsplit("-", 1)[-1]
    match = re.match(r"^.*-T(\d{2})-([A-F0-9]{10})$", team_id)
    if not match:
        return None
    try:
        idx = int(match.group(1))
    except ValueError:
        return None
    if match.group(2) != event_suffix:
        return None
    return idx if 1 <= idx <= 10 else None


def run() -> dict[str, Any]:
    supabase_url, _, service_key, host = _require_staging_env()
    print(f"Staging host: {host}")

    client = RestClient(supabase_url, "", service_key)

    events = client.get("events_v2", query={"event_id": f"eq.{TARGET_EVENT_ID}", "select": "event_id,join_code"})
    if not isinstance(events, list) or not events:
        raise RuntimeError(f"Event not found: {TARGET_EVENT_ID}")
    if events[0].get("join_code") != TARGET_JOIN_CODE:
        raise RuntimeError(f"Join code mismatch for {TARGET_EVENT_ID}: expected {TARGET_JOIN_CODE}")

    teams = client.get(
        "teams_v2",
        query={"event_id": f"eq.{TARGET_EVENT_ID}", "select": "team_id,team_name,country"},
    )
    if not isinstance(teams, list) or len(teams) != 10:
        raise RuntimeError(f"Expected 10 teams for {TARGET_EVENT_ID}, found {len(teams) if isinstance(teams, list) else 'unknown'}")

    updates = []
    ordered_teams = []
    for team in teams:
        team_id = str(team.get("team_id", "")).strip()
        idx = _team_index(team_id, TARGET_EVENT_ID)
        if idx is None:
            raise RuntimeError(f"Unexpected TeamID format for event {TARGET_EVENT_ID}: {team_id}")
        ordered_teams.append((idx, team))

    ordered_teams.sort(key=lambda item: item[0])
    ordered_indices = [idx for idx, _ in ordered_teams]
    expected_indices = list(range(1, 11))
    if ordered_indices != expected_indices:
        raise RuntimeError(
            f"TeamID sequence mismatch for event {TARGET_EVENT_ID}: expected {expected_indices}, got {ordered_indices}"
        )

    updates = []
    for idx, team in ordered_teams:
        team_id = str(team.get("team_id", "")).strip()
        payload = {"team_name": TARGET_NAMES[idx - 1], "country": ""}
        if team.get("team_name") != payload["team_name"] or team.get("country", "") != "":
            client.patch("teams_v2", query={"team_id": f"eq.{team_id}"}, payload=payload)
            updates.append((team_id, payload))

    pins = client.get(
        "team_access_credentials_v2",
        query={
            "event_id": f"eq.{TARGET_EVENT_ID}",
            "credential_purpose": "eq.TEAM_PIN",
            "select": "team_id,team_access_credential_id",
        },
    )
    # Presence-only check only; mapping values are encrypted, so we preserve by not touching credentials.
    if not isinstance(pins, list) or len(pins) != 10:
        raise RuntimeError(f"Expected 10 pin credentials for {TARGET_EVENT_ID}, found {len(pins) if isinstance(pins, list) else 'unknown'}")

    return {
        "event_id": TARGET_EVENT_ID,
        "join_code": TARGET_JOIN_CODE,
        "team_updates": updates,
        "team_count": len(teams),
        "pin_row_count": len(pins),
    }


def main() -> None:
    result = run()
    print("RESULT:", json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
