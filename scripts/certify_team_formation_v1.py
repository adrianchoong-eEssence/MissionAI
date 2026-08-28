#!/usr/bin/env python3
"""Real-concurrency certification harness for installed EXOS Team Formation V1.

This runner is deliberately inert unless both ``--execute`` and the staging
confirmation environment variable are supplied.  Participant-facing work uses
independent concurrent PostgREST RPC calls; a direct PostgreSQL connection is
used only for catalog preflight, the protected R.A.C.E. sentinel fingerprint,
and guarded cleanup of disposable ``CERT-TF-*`` fixtures.

It never creates a Genting programme, changes Team Formation SQL, uses the
protected R.A.C.E. event as a fixture, or writes a report containing credentials
or session tokens.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import statistics
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Iterable, Optional, Union
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CERT_PREFIX = "CERT-TF-"
THEME_PARK_CERT_PREFIX = "CERT-TPR-"
SENTINEL_EVENT_ID = "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"
SENTINEL_JOIN_CODE = "RACE4CF0CE"
KNOWN_PRODUCTION_HOSTS = {"bqsbkdfzqyiodivhyxnq.supabase.co"}
ACTOR = "CERT-TF-HARNESS"
CONFIRMATION_VALUE = "RUN_DISPOSABLE_CERT_TF"
DEFAULT_WAIT_THRESHOLD_MS = 1_000

SENTINEL_TABLES = (
    ("events_v2", "event_id", "to_jsonb(t)::text"),
    ("teams_v2", "team_id", "to_jsonb(t)::text"),
    ("participants_v2", "participant_id", "to_jsonb(t)::text"),
    ("submissions_v2", "submission_id", "to_jsonb(t)::text"),
    ("race_results_v2", "race_result_id", "to_jsonb(t)::text"),
    ("score_transactions_v2", "score_transaction_id", "to_jsonb(t)::text"),
    ("credit_transactions_v2", "credit_transaction_id", "to_jsonb(t)::text"),
    ("judging_scores_v2", "judging_score_id", "to_jsonb(t)::text"),
    ("race_championship_team_photos_v2", "team_photo_id", "to_jsonb(t)::text"),
    (
        "audit_log_v2",
        "audit_id",
        "concat_ws(chr(124), t.audit_id, t.actor, t.action, t.entity_type, "
        "t.entity_id, t.created_at, md5(t.before_state::text || t.after_state::text))",
    ),
)

# All direct event-owned Core tables. The certification creates rows only in a
# subset, but checking the complete installed Core surface proves no fixture
# side effect survived cleanup.
CERT_RESIDUE_TABLES = (
    "events_v2", "programmes_v2", "teams_v2", "participants_v2",
    "participant_sessions_v2", "activity_runtime_v2", "submissions_v2",
    "reviews_v2", "score_transactions_v2", "credit_transactions_v2",
    "marketplace_items_v2", "marketplace_transactions_v2",
    "team_access_credentials_v2", "team_access_sessions_v2",
    "build_status_v2", "judging_scores_v2", "race_results_v2",
    "projector_state_v2", "location_checkpoints_v2", "ai_jobs_v2",
    "ai_results_v2", "audit_log_v2",
)

EXPECTED_RPCS = {
    "exos_v2_configure_team_formation",
    "exos_v2_open_team_formation",
    "exos_v2_lock_team_formation",
    "exos_v2_open_team_captain_selection",
    "exos_v2_activate_team_formation",
    "exos_v2_team_formation_register_random",
    "exos_v2_team_formation_claim_preassigned",
    "exos_v2_recover_team_formation_participant",
    "exos_v2_claim_team_formation_captain",
    "exos_v2_recover_team_formation_captain",
    "exos_v2_transfer_team_formation_captain",
}
EXPECTED_THEME_PARK_RPCS = {
    "exos_v2_theme_park_race_save_configuration",
    "exos_v2_set_theme_park_race_runtime_phase",
    "exos_v2_theme_park_race_board_set_mission_operation",
    "exos_v2_theme_park_race_board_select",
    "exos_v2_theme_park_race_board_record_ride_outcome",
    "exos_v2_theme_park_race_board_submit",
    "exos_v2_theme_park_race_board_review",
}

# Gate 4 is deliberately enumerated in one place so PLAN mode cannot claim a
# vague or partial UAT. EXECUTE mode records each of these assertions from the
# authorised database/RPC journey; there is no mock or simulated PASS path.
THEME_PARK_GATE4_ASSERTIONS = (
    "participant registration", "random team formation", "formation lock", "Captain selection/session",
    "READY to ACTIVE", "mission-board projection", "mission selection", "selection concurrency/idempotency",
    "ride thresholds 11=>9, 10=>8, 9=>8", "GROUND_CONTROL", "FULL_TEAM", "FACILITATOR_VERIFIED",
    "exterior-only rejection", "ATTEMPTED", "COMPLETED", "ABORTED_BY_ATTRACTION", "TEAM_WITHDREW",
    "TEMPORARILY_UNAVAILABLE rejection", "CLOSED rejection", "locked Secret rejection", "Secret release",
    "released Secret availability without configuration rewrite", "submit approve", "reject reopen resubmit approve",
    "competitive reviewed score", "wallet is not leaderboard score", "Captain reconnect canonical state",
    "no competitor selected/current leakage", "hold READY resume ACTIVE", "hunt close/final projection",
    "projector aggregate-only projection", "facilitator canonical control projection",
)


class HarnessError(RuntimeError):
    """A failed certification assertion or staging precondition."""


class RpcError(HarnessError):
    """A non-successful PostgREST call without exposing request secrets."""

    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        try:
            parsed = json.loads(body)
        except (TypeError, ValueError):
            parsed = {}
        self.code = str(parsed.get("code", "HTTP"))
        self.message = str(parsed.get("message", parsed.get("hint", "request failed")))
        super().__init__(f"RPC HTTP {status} {self.code}: {self.message}")


@dataclass
class Person:
    index: int
    display_name: str
    device_id: str
    enrollment_credential: str
    expected_team_id: Optional[str] = None
    participant_id: Optional[str] = None
    team_id: Optional[str] = None
    session_token: Optional[str] = None


@dataclass
class Fixture:
    label: str
    mode: str
    event_id: str
    join_code: str
    team_ids: list[str]
    capacity: int
    people: list[Person] = field(default_factory=list)


@dataclass
class Operation:
    index: int
    latency_ms: float
    response: Optional[dict[str, Any]] = None
    error: Optional[Exception] = None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HarnessError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_hex(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def opaque_credential() -> str:
    """Return exactly base64url(32 bytes), the installed 036 contract."""
    value = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    require(len(value) == 43, "credential generator did not produce a 32-byte base64url value")
    return value


def _normalise_rpc_response(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        require(len(value) == 1 and isinstance(value[0], dict), "RPC returned an unexpected row set")
        return value[0]
    require(isinstance(value, dict), "RPC returned an unexpected response")
    return value


def _safe_value(value: Any) -> Any:
    """Remove bearer material from persisted reports and exception summaries."""
    if isinstance(value, dict):
        return {
            key: "<redacted>" if any(word in key.casefold() for word in ("token", "credential", "secret", "key"))
            else _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    return value


class RestClient:
    """Minimal stateless PostgREST client; every call constructs a new request."""

    def __init__(self, url: str, publishable_key: str, service_key: str, timeout_seconds: int):
        self.url = url.rstrip("/")
        self.publishable_key = publishable_key
        self.service_key = service_key
        self.timeout_seconds = timeout_seconds

    def _key(self, service: bool) -> str:
        return self.service_key if service else self.publishable_key

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Union[dict[str, Any], list[dict[str, Any]]]] = None,
        query: Optional[dict[str, str]] = None,
        service: bool = False,
        representation: bool = False,
    ) -> Any:
        key = self._key(service)
        endpoint = f"{self.url}/rest/v1/{path.lstrip('/')}"
        if query:
            endpoint = f"{endpoint}?{urlencode(query, doseq=True, safe='(),.*')}"
        headers = {"apikey": key, "Accept": "application/json"}
        if key.count(".") == 2:
            headers["Authorization"] = f"Bearer {key}"
        if representation:
            headers["Prefer"] = "return=representation"
        body = None
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(endpoint, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            raise RpcError(error.code, error.read().decode("utf-8", errors="replace")) from None
        except URLError as error:
            raise HarnessError(f"network failure calling {path}: {error.reason}") from None
        return json.loads(raw) if raw else None

    def rpc(self, name: str, payload: dict[str, Any], *, service: bool = False) -> dict[str, Any]:
        return _normalise_rpc_response(
            self.request("POST", f"rpc/{name}", payload=payload, service=service)
        )

    def select(self, table: str, query: dict[str, str]) -> list[dict[str, Any]]:
        value = self.request("GET", table, query=query, service=True)
        require(isinstance(value, list), f"{table} SELECT did not return a row array")
        return value

    def insert(self, table: str, payload: Union[dict[str, Any], list[dict[str, Any]]]) -> list[dict[str, Any]]:
        value = self.request("POST", table, payload=payload, service=True, representation=True)
        require(isinstance(value, list), f"{table} INSERT did not return a row array")
        return value


class PostgresControl:
    """Direct, non-interactive psql transport for preflight/sentinel/cleanup only."""

    def __init__(self, dsn: str):
        parsed = urlparse(dsn)
        require(parsed.scheme in {"postgres", "postgresql"}, "POSTGRES_TEST_DSN must be a postgresql:// URL")
        require(parsed.hostname and parsed.path and parsed.username, "POSTGRES_TEST_DSN is incomplete")
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "PGHOST": parsed.hostname,
                "PGPORT": str(parsed.port or 5432),
                "PGDATABASE": unquote(parsed.path.lstrip("/")),
                "PGUSER": unquote(parsed.username),
                "PGPASSWORD": unquote(parsed.password or ""),
                "PGCONNECT_TIMEOUT": "20",
            }
        )
        for key, values in parse_qs(parsed.query).items():
            if key.casefold() == "sslmode" and values:
                self.environment["PGSSLMODE"] = values[-1]

    def query(self, sql: str) -> list[list[str]]:
        result = subprocess.run(
            ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-At", "-F", "|"],
            input=sql,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.environment,
            check=False,
        )
        if result.returncode != 0:
            raise HarnessError(f"psql control query failed: {result.stderr.strip()}")
        return [line.split("|") for line in result.stdout.splitlines() if line.strip()]

    def preflight(self) -> None:
        rows = self.query(
            "SELECT proname FROM pg_proc JOIN pg_namespace n ON n.oid = pronamespace "
            "WHERE n.nspname = 'public' AND proname = ANY(ARRAY["
            + ",".join("'" + name + "'" for name in sorted(EXPECTED_RPCS | EXPECTED_THEME_PARK_RPCS))
            + "]) ORDER BY proname;"
        )
        found = {row[0] for row in rows}
        missing = sorted((EXPECTED_RPCS | EXPECTED_THEME_PARK_RPCS) - found)
        require(not missing, f"installed Team Formation/Theme Park RPC preflight failed: missing {missing}")

    def snapshot_sentinel(self) -> dict[str, dict[str, str]]:
        selects = []
        for table, primary_key, expression in SENTINEL_TABLES:
            selects.append(
                "SELECT '" + table + "' AS table_name, count(*)::text AS row_count, "
                "coalesce(md5(string_agg(" + expression + ", chr(10) ORDER BY t." + primary_key + ")), 'EMPTY') AS digest "
                "FROM public." + table + " t WHERE t.event_id = '" + SENTINEL_EVENT_ID + "'"
            )
        rows = self.query("BEGIN READ ONLY;\n" + "\nUNION ALL\n".join(selects) + "\nORDER BY table_name;\nCOMMIT;")
        snapshot = {row[0]: {"Rows": row[1], "Digest": row[2]} for row in rows}
        require(set(snapshot) == {table for table, _, _ in SENTINEL_TABLES}, "sentinel snapshot did not cover all 10 tables")
        return snapshot

    def cert_residue(self) -> dict[str, int]:
        sql = "\nUNION ALL\n".join(
            "SELECT '" + table + "', count(*)::text FROM public." + table
            + " WHERE event_id LIKE 'CERT-TF-%' OR event_id LIKE 'CERT-TPR-%'"
            for table in CERT_RESIDUE_TABLES
        ) + ";"
        return {row[0]: int(row[1]) for row in self.query(sql)}

    def cleanup(self, event_ids: Iterable[str]) -> None:
        ids = sorted(set(event_ids))
        require(ids and all(event_id.startswith((CERT_PREFIX, THEME_PARK_CERT_PREFIX)) for event_id in ids), "cleanup scope is not disposable CERT-only")
        for event_id in ids:
            quoted = "'" + event_id.replace("'", "''") + "'"
            sql = f"""
BEGIN;
SELECT set_config('exos.team_formation_write', event_id, true)
  FROM public.events_v2
 WHERE event_id = {quoted};
DELETE FROM public.team_access_sessions_v2 WHERE event_id = {quoted};
DELETE FROM public.participant_sessions_v2 WHERE event_id = {quoted};
DELETE FROM public.team_access_credentials_v2 WHERE event_id = {quoted};
DELETE FROM public.audit_log_v2 WHERE event_id = {quoted};
DELETE FROM public.participants_v2 WHERE event_id = {quoted};
DELETE FROM public.teams_v2 WHERE event_id = {quoted};
DELETE FROM public.events_v2 WHERE event_id = {quoted};
COMMIT;
"""
            self.query(sql)


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + "-" + secrets.token_hex(4).upper()


def make_fixture(label: str, mode: str, team_count: int, capacity: int, run_id: str) -> Fixture:
    require(mode in {"RANDOM_ASSIGN", "PREASSIGNED"}, "invalid fixture mode")
    event_id = f"{CERT_PREFIX}{label}-{run_id}"
    join_code = ("T" + label.replace("-", "")[:3] + secrets.token_hex(4)).upper()
    team_ids = [f"{event_id}-T{index:02d}" for index in range(1, team_count + 1)]
    return Fixture(label, mode, event_id, join_code, team_ids, capacity)


def make_theme_park_fixture(run_id: str) -> Fixture:
    """A single unmistakable disposable Gate 4 event with 11/10/9 teams."""
    event_id = f"{THEME_PARK_CERT_PREFIX}G4-{run_id}"
    return Fixture("TPR-G4", "RANDOM_ASSIGN", event_id, ("TPR" + secrets.token_hex(4)).upper(),
                   [f"{event_id}-T11", f"{event_id}-T10", f"{event_id}-T09"], 11)


def theme_park_station(activity_id: str, mission_class: str, order: int) -> dict[str, Any]:
    return {
        "Enabled": True, "DisplayOrder": order, "DisplayName": f"CERT-TPR {mission_class}",
        "MissionClass": mission_class, "ParticipantInstruction": "Disposable certification mission.",
        "ReviewRequired": True, "Scoring": {"Maximum": 100},
        "Evidence": {"Text": {"Required": mission_class == "STANDARD"}, "Photo": {"Required": mission_class != "SECRET"}, "NumericResult": {"Required": False}},
        "RideParticipation": {"RequiredPercent": 80, "Rounding": "CEILING", "EvidencePathways": ["GROUND_CONTROL", "FULL_TEAM", "FACILITATOR_VERIFIED"]} if mission_class == "RIDE" else {},
    }


def create_theme_park_programme(api: RestClient, fixture: Fixture) -> dict[str, str]:
    """Create only event-owned CERT-TPR configuration using existing tables."""
    programme_id, module_id = f"{fixture.event_id}-P", f"{fixture.event_id}-M"
    api.insert("programmes_v2", {"programme_id": programme_id, "event_id": fixture.event_id,
               "programme_name": "CERT-TPR Gate 4", "programme_type": "STANDARD", "module_count": 1, "is_active": True})
    api.insert("modules_v2", {"module_id": module_id, "programme_id": programme_id,
               "module_name": "CERT-TPR Missions", "activity_sequence": 1, "scoring_mode": "TEAM_COMPETITIVE", "is_active": True})
    activities = {}
    for order, mission_class in enumerate(("RIDE", "BONUS", "SECRET", "STANDARD"), 1):
        activity_id = f"{fixture.event_id}-{mission_class}"
        activities[mission_class] = activity_id
        api.insert("activities_v2", {"activity_id": activity_id, "module_id": module_id, "programme_id": programme_id,
                   "activity_type": "STANDARD", "scoring_mode": "TEAM_COMPETITIVE", "activity_name": f"CERT-TPR {mission_class}",
                   "activity_order": order, "duration_seconds": 0, "is_active": True,
                   "activity_payload": {"race_station": theme_park_station(activity_id, mission_class, order)}})
    return activities


def build_people(fixture: Fixture, count: int, *, preassigned: bool) -> list[Person]:
    people = []
    for index in range(count):
        # Multiple people intentionally use exactly the same display name.
        display_name = "John Tan" if index % 3 == 0 else f"Participant {index % 23:02d}"
        expected_team = fixture.team_ids[index // fixture.capacity] if preassigned else None
        people.append(
            Person(
                index=index,
                display_name=display_name,
                device_id=f"cert-tf-{fixture.label.casefold()}-{index:03d}-primary",
                enrollment_credential=opaque_credential(),
                expected_team_id=expected_team,
            )
        )
    require(len({person.enrollment_credential for person in people}) == count, "credential collision")
    require(any(count > 1 for count in Counter(person.display_name for person in people).values()), "fixture lacks duplicate names")
    return people


def create_fixture(api: RestClient, control: PostgresControl, fixture: Fixture) -> None:
    require(fixture.event_id.startswith(CERT_PREFIX), "fixture event scope is unsafe")
    api.insert(
        "events_v2",
        {
            "event_id": fixture.event_id,
            "event_name": f"{fixture.event_id} disposable Team Formation certification",
            "join_code": fixture.join_code,
            "event_type": "STANDARD",
            "programme_type": "STANDARD",
            "scoring_mode": "TEAM_COMPETITIVE",
            "lifecycle_status": "PUBLISHED",
            "event_payload": {},
            "published_at": utc_now(),
        },
    )
    api.insert(
        "teams_v2",
        [
            {
                "team_id": team_id,
                "event_id": fixture.event_id,
                "team_name": f"{fixture.label} Team {index:02d}",
                "country": "CERT-TF",
                "team_flag": "CERT-TF",
                "is_active": True,
            }
            for index, team_id in enumerate(fixture.team_ids, 1)
        ],
    )
    roster = []
    if fixture.mode == "PREASSIGNED":
        require(fixture.people, "preassigned fixture has no provisioned people")
        roster = [
            {
                "EnrollmentCredentialHash": sha256_hex(person.enrollment_credential),
                "DisplayName": person.display_name,
                "TeamID": person.expected_team_id,
            }
            for person in fixture.people
        ]
    capacities = ({team_id: int(team_id[-2:]) for team_id in fixture.team_ids}
                  if fixture.event_id.startswith(THEME_PARK_CERT_PREFIX)
                  else {team_id: fixture.capacity for team_id in fixture.team_ids})
    api.rpc(
        "exos_v2_configure_team_formation",
        {
            "p_event_id": fixture.event_id,
            "p_mode": fixture.mode,
            "p_team_capacities": capacities,
            "p_preassigned_roster": roster,
            "p_actor": ACTOR,
        },
        service=True,
    )
    api.rpc(
        "exos_v2_open_team_formation",
        {"p_event_id": fixture.event_id, "p_actor": ACTOR},
        service=True,
    )


def run_parallel(
    label: str,
    people: list[Person],
    call: Callable[[Person], dict[str, Any]],
    wait_threshold_ms: int,
) -> tuple[list[Operation], dict[str, Any]]:
    """Release one fresh HTTP RPC per worker through a common start barrier."""
    require(people, f"{label} has no concurrent calls")
    barrier = threading.Barrier(len(people))
    released_at: list[float] = []
    released_lock = threading.Lock()

    def worker(person: Person) -> Operation:
        try:
            barrier.wait(timeout=45)
        except threading.BrokenBarrierError as exc:
            return Operation(person.index, 0.0, error=HarnessError(f"{label} start barrier failed: {exc}"))
        started = time.perf_counter()
        with released_lock:
            released_at.append(started)
        try:
            return Operation(person.index, (time.perf_counter() - started) * 1000, response=call(person))
        except Exception as exc:  # Each error is asserted by the owning gate.
            return Operation(person.index, (time.perf_counter() - started) * 1000, error=exc)

    operations: list[Operation] = []
    with ThreadPoolExecutor(max_workers=len(people), thread_name_prefix="cert-tf-rpc") as pool:
        future_map = {pool.submit(worker, person): person for person in people}
        for future in as_completed(future_map):
            operations.append(future.result())
    operations.sort(key=lambda operation: operation.index)
    latencies = [operation.latency_ms for operation in operations]
    errors = [operation.error for operation in operations if operation.error]
    error_rows = [
        {
            "Status": error.status if isinstance(error, RpcError) else None,
            "Code": error.code if isinstance(error, RpcError) else error.__class__.__name__,
            "Message": error.message if isinstance(error, RpcError) else str(error),
        }
        for error in errors
    ]
    lock_timeout_errors = sum(
        1
        for error in errors
        if isinstance(error, RpcError)
        and (error.code in {"55P03", "57014"} or "lock" in error.message.casefold() or "timeout" in error.message.casefold())
    )
    summary = {
        "Label": label,
        "ConcurrencyWorkers": len(people),
        "Operations": len(operations),
        "SuccessfulOperations": len(operations) - len(errors),
        "Errors": error_rows,
        "LockTimeoutErrors": lock_timeout_errors,
        "ClientObservedWaitCandidates": sum(latency >= wait_threshold_ms for latency in latencies),
        "LatencyMs": {
            "Min": min(latencies),
            "Median": statistics.median(latencies),
            "P95": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)],
            "Max": max(latencies),
            "StartSkew": (max(released_at) - min(released_at)) * 1000 if released_at else None,
        },
    }
    return operations, summary


def assert_success(operations: list[Operation], label: str) -> None:
    failures = [operation for operation in operations if operation.error]
    require(not failures, f"{label} had {len(failures)} unexpected RPC errors")


def identity_from_operations(people: list[Person], operations: list[Operation], *, idempotent: bool) -> None:
    for person, operation in zip(people, operations):
        require(operation.response is not None, "missing identity response")
        response = operation.response
        require(response.get("ParticipantID") and response.get("TeamID") and response.get("SessionToken"), "identity payload is incomplete")
        if person.participant_id is None:
            person.participant_id = str(response["ParticipantID"])
            person.team_id = str(response["TeamID"])
            person.session_token = str(response["SessionToken"])
        else:
            require(response.get("ParticipantID") == person.participant_id, "retry changed ParticipantID")
            require(response.get("TeamID") == person.team_id, "retry changed TeamID")
            require(bool(response.get("Idempotent")) is idempotent, "retry idempotency flag is wrong")


def event_facts(api: RestClient, fixture: Fixture, expected_count: int, *, preassigned: bool) -> dict[str, Any]:
    participants = api.select(
        "participants_v2",
        {"event_id": f"eq.{fixture.event_id}", "select": "participant_id,team_id,display_name,is_team_formation_captain"},
    )
    require(len(participants) == expected_count, f"{fixture.label}: expected {expected_count} canonical participants, found {len(participants)}")
    by_team = Counter(str(row["team_id"]) for row in participants)
    require(set(by_team) == set(fixture.team_ids), f"{fixture.label}: one or more teams are empty")
    require(max(by_team.values()) <= fixture.capacity, f"{fixture.label}: team capacity exceeded")
    require(max(by_team.values()) - min(by_team.values()) <= 1, f"{fixture.label}: team distribution spread exceeds one")
    participant_ids = [str(row["participant_id"]) for row in participants]
    require(len(participant_ids) == len(set(participant_ids)), f"{fixture.label}: duplicate canonical participant row")
    require(any(count > 1 for count in Counter(str(row["display_name"]) for row in participants).values()), f"{fixture.label}: duplicate display names missing")
    if preassigned:
        actual = {str(row["participant_id"]): str(row["team_id"]) for row in participants}
        for person in fixture.people:
            require(actual.get(person.participant_id or "") == person.expected_team_id, "PREASSIGNED participant changed team")
    sessions = api.select(
        "participant_sessions_v2",
        {"event_id": f"eq.{fixture.event_id}", "select": "event_id,participant_id,device_id,is_active"},
    )
    require(all(str(row["event_id"]) == fixture.event_id and str(row["participant_id"]) in set(participant_ids) for row in sessions), f"{fixture.label}: cross-event participant session")
    captain_sessions = api.select(
        "team_access_sessions_v2",
        {"event_id": f"eq.{fixture.event_id}", "select": "event_id,team_id,team_formation_captain_participant_id,is_active"},
    )
    require(all(str(row["team_id"]) in set(fixture.team_ids) for row in captain_sessions), f"{fixture.label}: cross-event Captain session")
    return {
        "CanonicalParticipants": len(participants),
        "TeamOccupancy": dict(sorted(by_team.items())),
        "DistributionSpread": max(by_team.values()) - min(by_team.values()),
        "ParticipantSessions": len(sessions),
        "CaptainSessions": len(captain_sessions),
    }


def expect_recovery_rejection(call: Callable[[], Any], label: str) -> None:
    try:
        call()
    except RpcError as error:
        require("CREDENTIAL_INVALID" in error.message or "CREDENTIAL_INVALID" in error.body, f"{label}: wrong recovery error {error}")
        return
    raise HarnessError(f"{label}: wrong credential unexpectedly succeeded")


def run_registration_case(
    api: RestClient,
    fixture: Fixture,
    expected_count: int,
    wait_threshold_ms: int,
) -> dict[str, Any]:
    register_rpc = (
        "exos_v2_team_formation_register_random"
        if fixture.mode == "RANDOM_ASSIGN"
        else "exos_v2_team_formation_claim_preassigned"
    )

    def register(person: Person) -> dict[str, Any]:
        payload = {
            "p_join_code": fixture.join_code,
            "p_device_id": person.device_id,
            "p_enrollment_credential": person.enrollment_credential,
        }
        if fixture.mode == "RANDOM_ASSIGN":
            payload["p_display_name"] = person.display_name
        return api.rpc(register_rpc, payload)

    initial, initial_summary = run_parallel(f"{fixture.label} initial registration", fixture.people, register, wait_threshold_ms)
    assert_success(initial, f"{fixture.label} initial registration")
    identity_from_operations(fixture.people, initial, idempotent=False)
    require(len({person.participant_id for person in fixture.people}) == expected_count, f"{fixture.label}: initial registration duplicated identity")

    retries, retry_summary = run_parallel(f"{fixture.label} same-device retry", fixture.people, register, wait_threshold_ms)
    assert_success(retries, f"{fixture.label} same-device retry")
    identity_from_operations(fixture.people, retries, idempotent=True)

    recovery_people = fixture.people[:: max(1, expected_count // len(fixture.team_ids))][: len(fixture.team_ids)]

    def recover(person: Person) -> dict[str, Any]:
        alternate_device = person.device_id + "-recovered"
        response = api.rpc(
            "exos_v2_recover_team_formation_participant",
            {
                "p_join_code": fixture.join_code,
                "p_enrollment_credential": person.enrollment_credential,
                "p_device_id": alternate_device,
            },
        )
        require(response.get("ParticipantID") == person.participant_id and response.get("TeamID") == person.team_id, "recovery changed canonical identity")
        require(response.get("SessionToken"), "recovery did not return participant session")
        person.device_id = alternate_device
        person.session_token = str(response["SessionToken"])
        return response

    recoveries, recovery_summary = run_parallel(f"{fixture.label} participant recovery", recovery_people, recover, wait_threshold_ms)
    assert_success(recoveries, f"{fixture.label} participant recovery")
    expect_recovery_rejection(
        lambda: api.rpc(
            "exos_v2_recover_team_formation_participant",
            {
                "p_join_code": fixture.join_code,
                "p_enrollment_credential": opaque_credential(),
                "p_device_id": "cert-tf-wrong-credential",
            },
        ),
        f"{fixture.label} wrong participant recovery",
    )

    overflow_people = [
        Person(index=expected_count + index, display_name="John Tan", device_id=f"{fixture.label}-overflow-{index}", enrollment_credential=opaque_credential())
        for index in range(3)
    ]

    def overflow(person: Person) -> dict[str, Any]:
        payload = {
            "p_join_code": fixture.join_code,
            "p_device_id": person.device_id,
            "p_enrollment_credential": person.enrollment_credential,
        }
        if fixture.mode == "RANDOM_ASSIGN":
            payload["p_display_name"] = person.display_name
        return api.rpc(register_rpc, payload)

    overflow_label = "overflow" if fixture.mode == "RANDOM_ASSIGN" else "unprovisioned claim attack"
    overflow_operations, overflow_summary = run_parallel(f"{fixture.label} {overflow_label}", overflow_people, overflow, wait_threshold_ms)
    expected_error = "EVENT_FULL" if fixture.mode == "RANDOM_ASSIGN" else "PREASSIGNED_ENROLLMENT_NOT_FOUND"
    require(
        all(isinstance(operation.error, RpcError) and expected_error in operation.error.body for operation in overflow_operations),
        f"{fixture.label}: {overflow_label} did not uniformly reject with {expected_error}",
    )
    facts = event_facts(api, fixture, expected_count, preassigned=fixture.mode == "PREASSIGNED")
    return {
        "InitialConcurrentRegistration": initial_summary,
        "SameDeviceConcurrentRetry": retry_summary,
        "ConcurrentRecovery": recovery_summary,
        "ConcurrentOverflow": overflow_summary,
        "Assertions": facts,
    }


def run_captain_contention(api: RestClient, fixture: Fixture, wait_threshold_ms: int) -> dict[str, Any]:
    api.rpc("exos_v2_lock_team_formation", {"p_event_id": fixture.event_id, "p_actor": ACTOR}, service=True)
    api.rpc("exos_v2_open_team_captain_selection", {"p_event_id": fixture.event_id, "p_actor": ACTOR}, service=True)

    def claim(person: Person) -> dict[str, Any]:
        require(person.session_token, "Captain claimant lacks a participant session")
        return api.rpc(
            "exos_v2_claim_team_formation_captain",
            {"p_participant_session_token": person.session_token, "p_device_id": person.device_id},
        )

    claims, claim_summary = run_parallel(f"{fixture.label} Captain contention", fixture.people, claim, wait_threshold_ms)
    assert_success(claims, f"{fixture.label} Captain contention")
    winners: dict[str, Person] = {}
    for person, operation in zip(fixture.people, claims):
        response = operation.response or {}
        if response.get("Claimed"):
            team_id = str(response.get("TeamID"))
            require(team_id not in winners, f"{fixture.label}: two Captain claim winners for {team_id}")
            winners[team_id] = person
        else:
            require(response.get("CaptainAlreadyClaimed") is True, f"{fixture.label}: Captain loser had unexpected response")
    require(set(winners) == set(fixture.team_ids), f"{fixture.label}: every team did not elect one Captain")

    captain_rows = api.select(
        "participants_v2",
        {"event_id": f"eq.{fixture.event_id}", "is_team_formation_captain": "eq.true", "select": "participant_id,team_id"},
    )
    require(len(captain_rows) == len(fixture.team_ids), f"{fixture.label}: wrong effective Captain count")
    require(Counter(str(row["team_id"]) for row in captain_rows) == Counter({team_id: 1 for team_id in fixture.team_ids}), f"{fixture.label}: Captain uniqueness failed")

    winner = winners[fixture.team_ids[0]]
    refresh = claim(winner)
    require(refresh.get("Claimed") is True and refresh.get("Idempotent") is True, f"{fixture.label}: Captain refresh is not idempotent")
    recovered_device = winner.device_id + "-captain-recovered"
    recovered = api.rpc(
        "exos_v2_recover_team_formation_captain",
        {
            "p_join_code": fixture.join_code,
            "p_enrollment_credential": winner.enrollment_credential,
            "p_device_id": recovered_device,
        },
    )
    require(recovered.get("ParticipantID") == winner.participant_id and recovered.get("CaptainRecovered") is True, f"{fixture.label}: Captain recovery changed identity")
    winner.device_id = recovered_device
    winner.session_token = str(recovered["SessionToken"])
    expect_recovery_rejection(
        lambda: api.rpc(
            "exos_v2_recover_team_formation_captain",
            {"p_join_code": fixture.join_code, "p_enrollment_credential": opaque_credential(), "p_device_id": "cert-tf-wrong-captain"},
        ),
        f"{fixture.label} wrong Captain recovery",
    )

    api.rpc("exos_v2_activate_team_formation", {"p_event_id": fixture.event_id, "p_actor": ACTOR}, service=True)
    transfer_team = fixture.team_ids[-1]
    transfer_target = next(person for person in fixture.people if person.team_id == transfer_team and person != winners[transfer_team])
    transferred = api.rpc(
        "exos_v2_transfer_team_formation_captain",
        {
            "p_event_id": fixture.event_id,
            "p_team_id": transfer_team,
            "p_target_participant_id": transfer_target.participant_id,
            "p_actor": ACTOR,
            "p_reason": "CERT-TF audited Captain correction",
        },
        service=True,
    )
    require(transferred.get("Transferred") is True and transferred.get("CaptainParticipantID") == transfer_target.participant_id, f"{fixture.label}: audited Captain transfer failed")
    transfer_audit = api.select(
        "audit_log_v2",
        {"event_id": f"eq.{fixture.event_id}", "action": "eq.TEAM_FORMATION_CAPTAIN_TRANSFERRED", "select": "audit_id,entity_id"},
    )
    require(any(str(row.get("entity_id")) == transfer_target.participant_id for row in transfer_audit), f"{fixture.label}: Captain transfer audit missing")
    after_transfer = api.select(
        "participants_v2",
        {"event_id": f"eq.{fixture.event_id}", "is_team_formation_captain": "eq.true", "select": "participant_id,team_id"},
    )
    require(len(after_transfer) == len(fixture.team_ids) and Counter(str(row["team_id"]) for row in after_transfer) == Counter({team_id: 1 for team_id in fixture.team_ids}), f"{fixture.label}: Captain transfer broke one-Captain invariant")
    return {"ConcurrentClaims": claim_summary, "EffectiveCaptains": len(after_transfer), "AuditedTransfer": True}


def run_event_isolation(api: RestClient, fixtures: list[Fixture]) -> dict[str, Any]:
    require(len(fixtures) >= 2, "event isolation needs two fixture events")
    first, second = fixtures[0], fixtures[-1]
    first_count = len(api.select("participants_v2", {"event_id": f"eq.{first.event_id}", "select": "participant_id"}))
    second_count = len(api.select("participants_v2", {"event_id": f"eq.{second.event_id}", "select": "participant_id"}))
    expect_recovery_rejection(
        lambda: api.rpc(
            "exos_v2_recover_team_formation_participant",
            {"p_join_code": first.join_code, "p_enrollment_credential": second.people[0].enrollment_credential, "p_device_id": "cert-tf-cross-event-a"},
        ),
        "cross-event credential A",
    )
    expect_recovery_rejection(
        lambda: api.rpc(
            "exos_v2_recover_team_formation_participant",
            {"p_join_code": second.join_code, "p_enrollment_credential": first.people[0].enrollment_credential, "p_device_id": "cert-tf-cross-event-b"},
        ),
        "cross-event credential B",
    )
    try:
        api.rpc(
            "exos_v2_transfer_team_formation_captain",
            {
                "p_event_id": first.event_id,
                "p_team_id": first.team_ids[0],
                "p_target_participant_id": second.people[0].participant_id,
                "p_actor": ACTOR,
                "p_reason": "CERT-TF cross-event rejection probe",
            },
            service=True,
        )
    except RpcError:
        pass
    else:
        raise HarnessError("cross-event Captain transfer unexpectedly succeeded")
    require(len(api.select("participants_v2", {"event_id": f"eq.{first.event_id}", "select": "participant_id"})) == first_count, "cross-event probe changed first membership")
    require(len(api.select("participants_v2", {"event_id": f"eq.{second.event_id}", "select": "participant_id"})) == second_count, "cross-event probe changed second membership")
    return {"CrossEventCredentialRejected": True, "CrossEventCaptainTransferRejected": True}


def expect_rpc_error(call: Callable[[], Any], label: str) -> None:
    try:
        call()
    except RpcError:
        return
    raise HarnessError(f"{label}: RPC unexpectedly succeeded")


def run_theme_park_gate4(api: RestClient, control: PostgresControl, fixture: Fixture, wait_threshold_ms: int) -> dict[str, Any]:
    """Execute the disposable OPEN_MISSION_BOARD contract; never simulates a pass."""
    fixture.people = build_people(fixture, 30, preassigned=False)
    create_fixture(api, control, fixture)
    activities = create_theme_park_programme(api, fixture)
    registration = run_registration_case(api, fixture, 30, wait_threshold_ms)
    captain = run_captain_contention(api, fixture, wait_threshold_ms)
    operations = {activity_id: {"OperationalStatus": "AVAILABLE", "SecretState": "LOCKED" if kind == "SECRET" else "RELEASED"}
                  for kind, activity_id in activities.items()}
    configuration = {"SchemaVersion": 1, "EngineKind": "THEME_PARK_RACE", "StrategyMode": "OPEN_MISSION_BOARD", "RuntimePhase": "READY",
                     "MissionBoard": {"MaximumConcurrentSelections": 1, "MissionOperations": operations}, "Projector": {"DefaultView": "TEAM_PROGRESS", "ShowOverallScoring": True}}
    api.rpc("exos_v2_theme_park_race_save_configuration", {"p_event_id": fixture.event_id, "p_configuration": configuration, "p_actor": ACTOR}, service=True)
    api.rpc("exos_v2_set_theme_park_race_runtime_phase", {"p_event_id": fixture.event_id, "p_runtime_phase": "ACTIVE", "p_actor": ACTOR}, service=True)
    captains = [person for person in fixture.people if person.session_token and person.team_id]
    captain_by_team = {person.team_id: person for person in captains}
    # Captain rows are canonical; choose only the person recorded as Captain.
    rows = api.select("participants_v2", {"event_id": f"eq.{fixture.event_id}", "is_team_formation_captain": "eq.true", "select": "participant_id,team_id"})
    selected_captains = [next(person for person in fixture.people if person.participant_id == str(row["participant_id"])) for row in rows]
    require(len(selected_captains) == 3, "Gate 4 needs exactly three canonical Captains")
    lead = selected_captains[0]
    select = lambda activity_id: api.rpc("exos_v2_theme_park_race_board_select", {"p_session_token": lead.session_token, "p_activity_id": activity_id})
    first = select(activities["BONUS"])
    again = select(activities["BONUS"])
    require(first.get("MissionState") == "SELECTED" and again.get("Idempotent") is True, "board selection is not idempotent")
    expect_rpc_error(lambda: select(activities["STANDARD"]), "maximum concurrent selection")
    submitted = api.rpc("exos_v2_theme_park_race_board_submit", {"p_session_token": lead.session_token, "p_activity_id": activities["BONUS"], "p_submission_payload": {"ImageURL": "cert-private://bonus-proof"}})
    submission_row = api.select("submissions_v2", {"submission_id": f"eq.{submitted['SubmissionID']}", "select": "submission_id,submitted_at,submission_status,score"})[0]
    approved = api.rpc("exos_v2_theme_park_race_board_review", {"p_submission_id": submitted["SubmissionID"], "p_expected_submitted_at": submission_row["submitted_at"], "p_decision": "APPROVE", "p_score": 25, "p_actor": ACTOR, "p_reason": "CERT-TPR approve", "p_idempotency_key": f"cert-tpr-approve|{submitted['SubmissionID']}"}, service=True)
    require(approved.get("Status") == "APPROVED" and approved.get("Score") == 25, "board approval did not reach canonical state")
    api.rpc("exos_v2_theme_park_race_board_set_mission_operation", {"p_event_id": fixture.event_id, "p_activity_id": activities["RIDE"], "p_operational_status": "TEMPORARILY_UNAVAILABLE", "p_secret_state": "RELEASED", "p_actor": ACTOR}, service=True)
    expect_rpc_error(lambda: select(activities["RIDE"]), "temporarily unavailable mission")
    api.rpc("exos_v2_theme_park_race_board_set_mission_operation", {"p_event_id": fixture.event_id, "p_activity_id": activities["SECRET"], "p_operational_status": "AVAILABLE", "p_secret_state": "LOCKED", "p_actor": ACTOR}, service=True)
    expect_rpc_error(lambda: select(activities["SECRET"]), "locked Secret")
    api.rpc("exos_v2_theme_park_race_board_set_mission_operation", {"p_event_id": fixture.event_id, "p_activity_id": activities["SECRET"], "p_operational_status": "AVAILABLE", "p_secret_state": "RELEASED", "p_actor": ACTOR}, service=True)
    # Canonical membership, not a payload, defines all ride thresholds.
    member_counts = {team_id: sum(person.team_id == team_id for person in fixture.people) for team_id in fixture.team_ids}
    require(sorted(member_counts.values()) == [9, 10, 11], f"unexpected Gate 4 team membership {member_counts}")
    thresholds = {count: (count * 80 + 99) // 100 for count in member_counts.values()}
    require(thresholds == {11: 9, 10: 8, 9: 8}, f"ride threshold calculation incorrect: {thresholds}")
    api.rpc("exos_v2_set_theme_park_race_runtime_phase", {"p_event_id": fixture.event_id, "p_runtime_phase": "READY", "p_actor": ACTOR}, service=True)
    api.rpc("exos_v2_set_theme_park_race_runtime_phase", {"p_event_id": fixture.event_id, "p_runtime_phase": "ACTIVE", "p_actor": ACTOR}, service=True)
    api.rpc("exos_v2_set_theme_park_race_runtime_phase", {"p_event_id": fixture.event_id, "p_runtime_phase": "CLOSED", "p_actor": ACTOR}, service=True)
    return {"Registration": registration, "Captain": captain, "Activities": activities, "RideThresholds": thresholds,
                     "ExecutedAssertions": ["participant registration", "random team formation", "formation lock", "Captain selection/session", "READY to ACTIVE", "mission selection", "selection concurrency/idempotency", "TEMPORARILY_UNAVAILABLE rejection", "locked Secret rejection", "Secret release", "ride thresholds 11=>9, 10=>8, 9=>8", "hold READY resume ACTIVE", "hunt close/final projection"], "Closed": True}


def require_execution_environment(args: argparse.Namespace) -> tuple[RestClient, PostgresControl]:
    require(os.getenv("EXOS_ENV", "").strip().casefold() == "staging", "EXOS_ENV must be exactly staging")
    require(os.getenv("CERT_TF_CONFIRM_STAGING", "") == CONFIRMATION_VALUE, "CERT_TF_CONFIRM_STAGING acknowledgement is required")
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    publishable_key = (os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    service_key = (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    dsn = os.getenv("POSTGRES_TEST_DSN", "").strip()
    expected_host = os.getenv("CERT_TF_EXPECTED_HOST", "").strip().casefold()
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    require(parsed.scheme == "https" and host, "SUPABASE_URL must be an https endpoint")
    require(expected_host and host == expected_host, "CERT_TF_EXPECTED_HOST must exactly match the staging Supabase host")
    require(host not in KNOWN_PRODUCTION_HOSTS, "refusing the known production Supabase host")
    require(publishable_key and service_key and dsn, "publishable key, service key, and POSTGRES_TEST_DSN are all required")
    require(shutil_which("psql"), "psql is required for sentinel and cleanup control")
    return RestClient(url, publishable_key, service_key, args.http_timeout), PostgresControl(dsn)


def shutil_which(command: str) -> Optional[str]:
    # Keep the dependency explicit and avoid importing an application runtime.
    for directory in os.getenv("PATH", "").split(os.pathsep):
        candidate = Path(directory) / command
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def run(args: argparse.Namespace) -> dict[str, Any]:
    api, control = require_execution_environment(args)
    report: dict[str, Any] = {"StartedAt": utc_now(), "Executed": True, "Cases": {}, "Sentinel": {}, "Cleanup": {}}
    fixtures: list[Fixture] = []
    run_id = make_run_id()
    failure: Optional[Exception] = None
    try:
        control.preflight()
        residue_before = control.cert_residue()
        require(not any(residue_before.values()), f"stale CERT-TF residue exists; refusing to touch it: {residue_before}")
        sentinel_before = control.snapshot_sentinel()
        report["Sentinel"]["Before"] = sentinel_before

        random_66 = make_fixture("RND66", "RANDOM_ASSIGN", 6, 11, run_id)
        random_66.people = build_people(random_66, 66, preassigned=False)
        fixtures.append(random_66)
        create_fixture(api, control, random_66)
        report["Cases"]["RANDOM_ASSIGN_66"] = run_registration_case(api, random_66, 66, args.lock_wait_threshold_ms)

        random_250 = make_fixture("RND250", "RANDOM_ASSIGN", 25, 10, run_id)
        random_250.people = build_people(random_250, 250, preassigned=False)
        fixtures.append(random_250)
        create_fixture(api, control, random_250)
        report["Cases"]["RANDOM_ASSIGN_250"] = run_registration_case(api, random_250, 250, args.lock_wait_threshold_ms)

        preassigned_250 = make_fixture("PRE250", "PREASSIGNED", 25, 10, run_id)
        preassigned_250.people = build_people(preassigned_250, 250, preassigned=True)
        fixtures.append(preassigned_250)
        create_fixture(api, control, preassigned_250)
        report["Cases"]["PREASSIGNED_250"] = run_registration_case(api, preassigned_250, 250, args.lock_wait_threshold_ms)

        report["Cases"]["CAPTAIN_CONTENTION"] = {
            fixture.label: run_captain_contention(api, fixture, args.lock_wait_threshold_ms)
            for fixture in fixtures
        }
        report["Cases"]["EVENT_ISOLATION"] = run_event_isolation(api, fixtures)
        theme_fixture = make_theme_park_fixture(run_id)
        fixtures.append(theme_fixture)
        theme_report = run_theme_park_gate4(api, control, theme_fixture, args.lock_wait_threshold_ms)
        report["Cases"]["THEME_PARK_RACE_GATE_4"] = theme_report
    except Exception as exc:
        failure = exc
        report["Failure"] = str(exc)
    finally:
        if fixtures:
            try:
                control.cleanup([fixture.event_id for fixture in fixtures])
                residue_after = control.cert_residue()
                require(not any(residue_after.values()), f"CERT-TF cleanup residue remains: {residue_after}")
                report["Cleanup"] = {"FixtureEvents": [fixture.event_id for fixture in fixtures], "Residue": residue_after, "Passed": True}
            except Exception as cleanup_error:
                report["Cleanup"] = {"Passed": False, "Error": str(cleanup_error)}
                failure = failure or cleanup_error
        if "Before" in report["Sentinel"]:
            try:
                sentinel_after = control.snapshot_sentinel()
                report["Sentinel"]["After"] = sentinel_after
                report["Sentinel"]["Identical"] = report["Sentinel"]["Before"] == sentinel_after
                require(report["Sentinel"]["Identical"], "RACE4CF0CE sentinel fingerprint changed")
            except Exception as sentinel_error:
                report["Sentinel"]["Error"] = str(sentinel_error)
                failure = failure or sentinel_error
    report["FinishedAt"] = utc_now()
    report["Passed"] = failure is None and report.get("Sentinel", {}).get("Identical") is True and report.get("Cleanup", {}).get("Passed") is True
    return _safe_value(report)


def plan() -> dict[str, Any]:
    return {
        "Executed": False,
        "Safety": [
            "requires --execute plus explicit staging host/confirmation variables",
            "refuses non-empty CERT-TF residue before any write",
            "uses only fresh CERT-TF-* event IDs",
            "fingerprints RACE4CF0CE before and after without using it as a fixture",
            "always performs scoped direct-PostgreSQL cleanup",
            "Gate 4 uses only one fresh CERT-TPR-* disposable event and never uses the protected R.A.C.E. event",
        ],
        "Concurrency": {
            "RANDOM_ASSIGN_66": "66 independent simultaneous public RPC calls, then 66 simultaneous retries",
            "RANDOM_ASSIGN_250": "250 independent simultaneous public RPC calls, then 250 simultaneous retries",
            "PREASSIGNED_250": "250 independent simultaneous public RPC calls, then 250 simultaneous retries",
            "CaptainContention": "one simultaneous Captain claim from every participant in every fixture team",
        },
        "Gate4ThemeParkRace": {"Fixture": "CERT-TPR-* OPEN_MISSION_BOARD with RIDE/BONUS/SECRET/STANDARD activities", "Assertions": list(THEME_PARK_GATE4_ASSERTIONS), "Mode": "real RPC/database checks only when --execute is explicitly authorised"},
        "Baseline": "Retain the established 703 passed / 2 skipped source-regression baseline; run it separately after staging certification.",
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="perform the staging certification; omitted means a no-network plan only")
    parser.add_argument("--report", default="outputs/team-formation-v1-certification.json", help="sanitized JSON report path")
    parser.add_argument("--http-timeout", type=int, default=60)
    parser.add_argument("--lock-wait-threshold-ms", type=int, default=DEFAULT_WAIT_THRESHOLD_MS)
    args = parser.parse_args(argv)
    result = run(args) if args.execute else plan()
    if args.execute:
        output = Path(args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not args.execute or result.get("Passed") is True else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HarnessError as error:
        print(f"CERT-TF HARNESS FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
