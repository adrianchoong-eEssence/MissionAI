#!/usr/bin/env python3
"""Create a persistent Formula R.A.C.E. Core v2 staging UAT event.

This script is staging-only and does not clean up created rows.
It prints and persists the generated Team PINs to a one-time local text report
for Adrian UAT testing.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

KNOWN_PROD_HOSTS = {
    "bqsbkdfzqyiodivhyxnq.supabase.co",
}


def _now_id() -> str:
    return uuid.uuid4().hex[:10].upper()


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _require_staging_env() -> tuple[str, str, str, str]:
    env = str(os.getenv("EXOS_ENV", "")).strip().lower()
    if env != "staging":
        raise RuntimeError("Refusing to run: EXOS_ENV must be exactly 'staging'.")

    supabase_url = str(os.getenv("SUPABASE_URL", "")).strip().rstrip("/")
    anon_key = str(
        os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
        or os.getenv("SUPABASE_ANON_KEY", "")
    ).strip()
    service_key = str(
        os.getenv("SUPABASE_SECRET_KEY", "")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    ).strip()

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

    def request(self, method: str, path: str, payload=None, query=None, admin=True):
        endpoint = f"{self.url}/rest/v1/{path.lstrip('/')}"
        if query:
            endpoint = f"{endpoint}?{urlencode(query, doseq=True, safe='(),.*')}"

        headers = {
            "apikey": self.service_key if admin else self.anon_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        token = self.service_key if admin else self.anon_key
        if token.count(".") == 2:
            headers["Authorization"] = f"Bearer {token}"

        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(endpoint, method=method.upper(), headers=headers, data=data)
        if data is not None and method.upper() in {"POST", "PATCH", "PUT"}:
            req.add_header("Prefer", "return=representation")

        try:
            with urlopen(req, timeout=45) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return True
                return json.loads(raw)
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {error.code} {method} {path}: {body or error.reason}")
        except (URLError, TimeoutError) as exc:  # pragma: no cover - network-only failure path
            raise RuntimeError(f"Request failed for {method} {path}: {exc}")

    def get(self, path: str, query=None):
        return self.request("GET", path, query=query, admin=True)

    def post(self, path: str, payload=None):
        return self.request("POST", path, payload=payload, admin=True)

    def rpc(self, name: str, payload):
        return self.post(f"rpc/{name}", payload=payload)


def create_uat_race_event() -> dict:
    supabase_url, anon_key, service_key, host = _require_staging_env()
    print(f"Staging connectivity host: {host}")

    run_id = _now_id()
    event_id = f"CORE-V2-RACE-UAT-EVT-{run_id}"
    join_code = f"RACE{run_id[:6]}"
    programme_id = f"CORE-V2-RACE-UAT-PROG-{run_id}"
    module_id = f"CORE-V2-RACE-UAT-MOD-{run_id}"
    team_ids = [f"CORE-V2-RACE-UAT-T{idx:02d}-{run_id}" for idx in range(1, 11)]
    activity_ids = [f"CORE-V2-RACE-UAT-CP-{idx:02d}-{run_id}" for idx in range(1, 5)]
    now = _now_iso()

    client = RestClient(supabase_url, anon_key, service_key)

    teams = [
        {
            "team_id": team_id,
            "team_name": f"CORE-V2-RACE-UAT Team {idx:02d}",
            "country": f"Country {idx:02d}",
            "team_flag": f"FLAG-{idx:02d}",
        }
        for idx, team_id in enumerate(team_ids, start=1)
    ]

    publish_payload = {
        "p_event_id": event_id,
        "p_join_code": join_code,
        "p_event_name": "Formula R.A.C.E. Core v2 UAT",
        "p_teams": teams,
        "p_scoring_mode": "TEAM_COMPETITIVE",
        "p_event_type": "RACE",
    }

    published = client.rpc("exos_v2_publish_event", publish_payload)
    if not isinstance(published, dict) or published.get("EventID") != event_id:
        raise RuntimeError("Failed to publish persistent UAT event via exos_v2_publish_event.")

    # Programme + module + checkpoints.
    client.post(
        "programmes_v2",
        {
            "programme_id": programme_id,
            "event_id": event_id,
            "programme_name": "Formula R.A.C.E. UAT Programme",
            "programme_type": "Formula R.A.C.E.",
            "module_count": 1,
            "is_active": True,
        },
    )
    client.post(
        "modules_v2",
        {
            "module_id": module_id,
            "programme_id": programme_id,
            "module_name": "Formula R.A.C.E. Checkpoints",
            "module_payload": {"module_type": "RACE Checkpoints", "is_parallel": True},
            "activity_sequence": 1,
            "scoring_mode": "TEAM_COMPETITIVE",
            "is_active": True,
            "module_order": 1,
            "created_at": now,
            "updated_at": now,
        },
    )

    for idx, activity_id in enumerate(activity_ids, start=1):
        client.post(
            "activities_v2",
            {
                "activity_id": activity_id,
                "programme_id": programme_id,
                "module_id": module_id,
                "activity_name": f"RACE Checkpoint {idx}",
                "activity_type": "CHECKPOINT",
                "scoring_mode": "TEAM_COMPETITIVE",
                "activity_order": idx,
                "duration_seconds": 480,
                "activity_payload": {
                    "proof_type": "Text" if idx % 2 == 0 else "Photo",
                    "instructions": f"Checkpoint {idx} proof + notes.",
                    "max_score": 10,
                    "credits": 2,
                },
                "is_active": True,
            },
        )

    # Seed sensible TEST marketplace values.
    items = [
        {
            "event_id": event_id,
            "item_id": f"CORE-V2-RACE-UAT-ITEM-{run_id}-01",
            "item_name": "Carbon Fibre Kit",
            "item_type": "MATERIAL",
            "unit_cost_credits": 20,
            "stock_limit": 40,
            "is_active": True,
        },
        {
            "event_id": event_id,
            "item_id": f"CORE-V2-RACE-UAT-ITEM-{run_id}-02",
            "item_name": "Axle Upgrade",
            "item_type": "UPGRADE",
            "unit_cost_credits": 35,
            "stock_limit": 25,
            "is_active": True,
        },
    ]
    for item in items:
        client.post("marketplace_items_v2", item)

    # Configure team access PINs and keep a local plaintext report.
    pin_report = []
    for idx, team_id in enumerate(team_ids, start=1):
        pin = f"PIN-{idx:02d}"
        pin_set = client.rpc(
            "exos_v2_set_team_access_pin",
            {
                "p_event_id": event_id,
                "p_team_id": team_id,
                "p_pin": pin,
                "p_actor": "UAT bootstrap",
            },
        )
        if not isinstance(pin_set, dict) or not pin_set.get("Configured"):
            raise RuntimeError(f"Failed to configure PIN for {team_id}")
        pin_report.append({"team_id": team_id, "team_name": f"CORE-V2-RACE-UAT Team {idx:02d}", "pin": pin})

    result = {
        "event_id": event_id,
        "join_code": join_code,
        "programme_id": programme_id,
        "module_id": module_id,
        "activity_ids": activity_ids,
        "team_ids": team_ids,
        "marketplace_items": [item["item_name"] for item in items],
        "pin_rows": pin_report,
    }

    output_dir = Path("/tmp")
    output_dir.mkdir(parents=True, exist_ok=True)
    pin_file = output_dir / f"{event_id}_race_uat_pins.txt"
    with pin_file.open("w", encoding="utf-8") as handle:
        handle.write(f"Formula R.A.C.E. Core v2 UAT PIN REPORT\n")
        handle.write(f"Generated At: {now}\n")
        handle.write(f"EventID: {event_id}\n")
        handle.write(f"Join Code: {join_code}\n")
        handle.write("\nTeam PINs (ONE-TIME local reference only):\n")
        for row in pin_report:
            handle.write(f"{row['team_id']}\t{row['team_name']}\t{row['pin']}\n")

    print(f"EventID: {event_id}")
    print(f"Join Code: {join_code}")
    print(f"PIN report local path: {pin_file}")
    print("10 Team PINs configured.")

    return {
        **result,
        "pin_report_path": str(pin_file),
    }


def main() -> None:
    print("[Formula R.A.C.E. Core v2] creating persistent staging UAT event")
    created = create_uat_race_event()
    print(json.dumps(created, indent=2))


if __name__ == "__main__":
    main()
