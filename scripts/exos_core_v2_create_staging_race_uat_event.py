#!/usr/bin/env python3
"""Create a persistent Formula R.A.C.E. Core v2 staging UAT event.

This script is staging-only and does not clean up created rows by default.
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

CREATOR = "exos_core_v2_create_staging_race_uat_event"
LAST_RUN_STATE = Path("/tmp") / "exos_core_v2_race_uat_last_run.json"
EVENT_NAME = "L'OREAL FORMULA R.A.C.E. DEMO"


class RequestFailure(RuntimeError):
    def __init__(self, method: str, table: str, status: int | None, body: str, payload: object):
        super().__init__(body)
        self.method = method
        self.table = table
        self.status = status
        self.body = body
        self.payload_keys = sorted(payload.keys()) if isinstance(payload, dict) else []


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


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        try:
            data = json.loads(handle.read() or "{}")
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _clear_state() -> None:
    try:
        LAST_RUN_STATE.unlink(missing_ok=True)  # type: ignore[arg-type]
    except TypeError:
        if LAST_RUN_STATE.exists():
            LAST_RUN_STATE.unlink()


class RestClient:
    def __init__(self, url: str, anon_key: str, service_key: str):
        self.url = url
        self.anon_key = anon_key
        self.service_key = service_key

    def request(self, method: str, path: str, payload=None, query=None, table=None, admin=True):
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
            raise RequestFailure(method.upper(), table or path, error.code, body or error.reason, payload)
        except (URLError, TimeoutError) as exc:
            raise RequestFailure(method.upper(), table or path, None, f"Request failed for {method} {path}: {exc}", payload)

    def get(self, path: str, query=None):
        return self.request("GET", path, query=query, admin=True)

    def post(self, path: str, payload=None):
        return self.request("POST", path, payload=payload, table=path, admin=True)

    def patch(self, path: str, payload=None, query=None):
        return self.request("PATCH", path, payload=payload, query=query, table=path, admin=True)

    def delete(self, path: str, query=None):
        return self.request("DELETE", path, payload=None, query=query, table=path, admin=True)

    def rpc(self, name: str, payload):
        return self.request("POST", f"rpc/{name}", payload=payload, table=name, admin=True)


def _collect_ids(rows: object) -> list[str]:
    if not isinstance(rows, list):
        return []
    ids: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            if "programme_id" in row and isinstance(row["programme_id"], str):
                ids.append(row["programme_id"])
            if "module_id" in row and isinstance(row["module_id"], str):
                ids.append(row["module_id"])
    return ids


def _cleanup_incomplete_event_if_needed(
    client: RestClient,
    event_id: str,
    team_count_min: int,
    item_count_min: int,
) -> bool:
    events = client.get("events_v2", {"event_id": f"eq.{event_id}", "select": "event_id,event_name"})
    if not isinstance(events, list) or not events:
        return False

    programmes = client.get("programmes_v2", {"event_id": f"eq.{event_id}", "select": "programme_id"})
    if not isinstance(programmes, list) or len(programmes) < 1:
        client.delete("events_v2", {"event_id": f"eq.{event_id}"})
        return True
    programme_ids = _collect_ids(programmes)
    if not programme_ids:
        client.delete("events_v2", {"event_id": f"eq.{event_id}"})
        return True

    modules = []
    for programme_id in programme_ids:
        modules.extend(client.get("modules_v2", {"programme_id": f"eq.{programme_id}", "select": "module_id"}) or [])
    module_ids = _collect_ids(modules)
    if not module_ids:
        client.delete("events_v2", {"event_id": f"eq.{event_id}"})
        return True

    activities = []
    for module_id in module_ids:
        activities.extend(client.get("activities_v2", {"module_id": f"eq.{module_id}", "select": "activity_id"}) or [])
    if not isinstance(activities, list) or len(activities) < 4:
        client.delete("events_v2", {"event_id": f"eq.{event_id}"})
        return True

    teams = client.get("teams_v2", {"event_id": f"eq.{event_id}", "select": "team_id"})
    if not isinstance(teams, list) or len(teams) < team_count_min:
        client.delete("events_v2", {"event_id": f"eq.{event_id}"})
        return True

    items = client.get("marketplace_items_v2", {"event_id": f"eq.{event_id}", "select": "item_id"})
    if not isinstance(items, list) or len(items) < item_count_min:
        client.delete("events_v2", {"event_id": f"eq.{event_id}"})
        return True

    return False


def _cleanup_stale_previous_run(client: RestClient, team_count_min: int, item_count_min: int) -> None:
    state = _read_json(LAST_RUN_STATE)
    previous_event_id = str(state.get("event_id", "")).strip()
    previous_join_code = str(state.get("join_code", "")).strip()
    if not previous_event_id or not previous_join_code:
        return
    event_rows = client.get(
        "events_v2",
        {"event_id": f"eq.{previous_event_id}", "join_code": f"eq.{previous_join_code}", "select": "event_name"},
    )
    if not isinstance(event_rows, list) or not event_rows:
        return
    if _cleanup_incomplete_event_if_needed(client, previous_event_id, team_count_min, item_count_min):
        print(f"Removed incomplete stale run from local state: {previous_event_id}")


def _safe_run_step(step: str, table: str, action):
    try:
        return action()
    except RequestFailure as exc:
        print(f"FAILED STEP: {step}")
        print(f"TABLE/RPC: {table}")
        print(f"PAYLOAD KEYS: {', '.join(exc.payload_keys)}")
        print(f"HTTP STATUS: {exc.status}")
        print(f"ERROR: {exc.body}")
        raise


def _persist_pin_report(pin_file: Path, now: str, event_id: str, join_code: str, pin_report: list[dict[str, str]]) -> None:
    with pin_file.open("w", encoding="utf-8") as handle:
        handle.write(f"{EVENT_NAME} PIN REPORT\n")
        handle.write(f"Generated At: {now}\n")
        handle.write(f"EventID: {event_id}\n")
        handle.write(f"Join Code: {join_code}\n")
        handle.write("\nTeam PINs (ONE-TIME local reference only):\n")
        for row in pin_report:
            handle.write(f"{row['team_id']}\t{row['team_name']}\t{row['pin']}\n")


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

    _write_json(
        LAST_RUN_STATE,
        {
            "event_id": event_id,
            "join_code": join_code,
            "run_id": run_id,
            "event_name": EVENT_NAME,
            "created_at": now,
            "creator": CREATOR,
        },
    )

    client = RestClient(supabase_url, anon_key, service_key)

    try:
        _cleanup_stale_previous_run(client, team_count_min=10, item_count_min=2)

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
            "p_event_name": EVENT_NAME,
            "p_teams": teams,
            "p_scoring_mode": "TEAM_COMPETITIVE",
            "p_event_type": "RACE",
        }
        published = _safe_run_step(
            "RPC:exos_v2_publish_event",
            "exos_v2_publish_event",
            lambda: client.rpc("exos_v2_publish_event", publish_payload),
        )
        if not isinstance(published, dict) or published.get("EventID") != event_id:
            raise RuntimeError("Failed to publish persistent UAT event via exos_v2_publish_event.")

        programme_payload = {
            "programme_id": programme_id,
            "event_id": event_id,
            "programme_name": "Formula R.A.C.E. UAT Programme",
            "programme_type": "Formula R.A.C.E.",
            "module_count": 1,
            "is_active": True,
        }
        _safe_run_step(
            "POST",
            "programmes_v2",
            lambda payload=programme_payload: client.post("programmes_v2", payload),
        )

        module_payload = {
            "module_id": module_id,
            "programme_id": programme_id,
            "module_name": "Formula R.A.C.E. Checkpoints",
            "module_payload": {"module_type": "RACE Checkpoints", "is_parallel": True},
            "activity_sequence": 1,
            "scoring_mode": "TEAM_COMPETITIVE",
            "is_active": True,
        }
        _safe_run_step(
            "POST",
            "modules_v2",
            lambda payload=module_payload: client.post("modules_v2", payload),
        )

        for idx, activity_id in enumerate(activity_ids, start=1):
            activity_payload = {
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
            }
            _safe_run_step(
                "POST",
                "activities_v2",
                lambda payload=activity_payload: client.post("activities_v2", payload),
            )

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
            _safe_run_step(
                "POST",
                "marketplace_items_v2",
                lambda payload=item: client.post("marketplace_items_v2", payload),
            )

        pin_report = []
        for idx, team_id in enumerate(team_ids, start=1):
            pin = f"PIN-{idx:02d}"
            pin_payload = {
                "p_event_id": event_id,
                "p_team_id": team_id,
                "p_pin": pin,
                "p_actor": "UAT bootstrap",
            }
            pin_set = _safe_run_step(
                "RPC:exos_v2_set_team_access_pin",
                "exos_v2_set_team_access_pin",
                lambda payload=pin_payload: client.rpc("exos_v2_set_team_access_pin", payload),
            )
            if not isinstance(pin_set, dict) or not pin_set.get("Configured"):
                raise RuntimeError(f"Failed to configure PIN for {team_id}")
            pin_report.append({"team_id": team_id, "team_name": f"CORE-V2-RACE-UAT Team {idx:02d}", "pin": pin})

        _safe_run_step(
            "PATCH",
            "events_v2",
            lambda: client.patch(
                "events_v2",
                {"event_payload": {"creator": CREATOR, "run_id": run_id}},
                {"event_id": f"eq.{event_id}"},
            ),
        )

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
        _persist_pin_report(pin_file, now, event_id, join_code, pin_report)

        _clear_state()
        print(f"EventID: {event_id}")
        print(f"Join Code: {join_code}")
        print(f"PIN report local path: {pin_file}")
        print("10 Team PINs configured.")

        return {**result, "pin_report_path": str(pin_file)}

    except RequestFailure:
        if _cleanup_incomplete_event_if_needed(client, event_id, team_count_min=10, item_count_min=2):
            print("Cleaned incomplete UAT event before exiting. Please rerun command to recreate it.")
        raise
    except RuntimeError as exc:
        print("FAILED STEP: CREATION")
        print("TABLE/RPC: CREATOR")
        print("PAYLOAD KEYS: ")
        print("HTTP STATUS: n/a")
        print(f"ERROR: {exc}")
        if _cleanup_incomplete_event_if_needed(client, event_id, team_count_min=10, item_count_min=2):
            print("Cleaned incomplete UAT event before exiting. Please rerun command to recreate it.")
        raise


def main() -> None:
    print("[Formula R.A.C.E. Core v2] creating persistent staging UAT event")
    created = create_uat_race_event()
    print(json.dumps(created, indent=2))


if __name__ == "__main__":
    main()
