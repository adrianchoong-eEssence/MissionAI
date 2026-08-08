#!/usr/bin/env python3
"""Scale-readiness harness for EXOS standard participant path.

This tool is non-destructive and intentionally local-first.

Modes:
- local (default): in-memory deterministic model only, no network.
- test / staging: Supabase-backed runtime environment, no production allowed.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
for path in (str(REPO_ROOT), str(CURRENT_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from exos_stabilisation_harness import RuntimeModel as LocalRuntimeModel
from data.google_sheets import GoogleSheetsDB


WORKLOADS = (70, 260, 800)

DEFAULT_WORKERS = {
    70: 24,
    260: 80,
    800: 160,
}


def percentile(values: List[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return round(float(ordered[index]), 3)


@dataclass
class ScenarioResult:
    participants: int
    requested: int
    registration_success: int = 0
    registration_errors: int = 0
    reconnect_success: int = 0
    submission_success: int = 0
    submission_errors: int = 0
    facilitator_errors: int = 0
    duplicate_registrations: int = 0
    duplicate_by_name: int = 0
    registration_latency_ms: List[float] = field(default_factory=list)
    reconnect_latency_ms: List[float] = field(default_factory=list)
    activity_latency_ms: List[float] = field(default_factory=list)
    submission_latency_ms: List[float] = field(default_factory=list)
    facilitator_latency_ms: List[float] = field(default_factory=list)
    team_distribution: Dict[str, int] = field(default_factory=dict)
    team_spread: int = 0
    errors: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    bottlenecks: List[str] = field(default_factory=list)

    @property
    def registration_success_rate(self) -> float:
        return self.registration_success / max(1, self.requested)

    @property
    def registration_error_rate(self) -> float:
        return self.registration_errors / max(1, self.requested)

    @property
    def reconnect_success_rate(self) -> float:
        return self.reconnect_success / max(1, self.registration_success)

    @property
    def submission_success_rate(self) -> float:
        expected = self.registration_success * 2
        return self.submission_success / max(1, expected)

    def _latency_summary(self, values: List[float]) -> Dict[str, float]:
        return {
            "p50": percentile(values, 0.50),
            "p95": percentile(values, 0.95),
            "p99": percentile(values, 0.99),
        }

    def team_balance_ok(self) -> bool:
        if not self.team_distribution:
            return False
        counts = [value for value in self.team_distribution.values() if value > 0]
        if not counts:
            return False
        return max(counts) - min(counts) <= 1

    def as_dict(self):
        return {
            "requested": self.requested,
            "participants": self.participants,
            "registration": {
                "success_rate": round(self.registration_success_rate, 4),
                "error_rate": round(self.registration_error_rate, 4),
                "success_count": self.registration_success,
                "error_count": self.registration_errors,
                "duplicate_registrations": self.duplicate_registrations,
                "duplicate_by_name": self.duplicate_by_name,
                "latency_ms": self._latency_summary(self.registration_latency_ms),
                "errors": dict(self.errors),
            },
            "reconnect": {
                "success_rate": round(self.reconnect_success_rate, 4),
                "success_count": self.reconnect_success,
                "requested": self.registration_success,
            },
            "activity_read": {
                "latency_ms": self._latency_summary(self.activity_latency_ms),
                "success_count": len(self.activity_latency_ms),
                "requested": self.registration_success,
            },
            "submission": {
                "requested": self.registration_success * 2,
                "success_rate": round(self.submission_success_rate, 4),
                "success_count": self.submission_success,
                "error_count": self.submission_errors,
                "latency_ms": self._latency_summary(self.submission_latency_ms),
            },
            "facilitator": {
                "p50": percentile(self.facilitator_latency_ms, 0.50),
                "p95": percentile(self.facilitator_latency_ms, 0.95),
                "p99": percentile(self.facilitator_latency_ms, 0.99),
                "error_count": self.facilitator_errors,
            },
            "team_distribution": self.team_distribution,
            "team_spread": self.team_spread,
            "team_balance_ok": self.team_balance_ok(),
            "bottlenecks": self.bottlenecks,
        }


class BaseBackend:
    def __init__(self, event_id: str, join_code: str, teams: int = 8):
        self.event_id = event_id
        self.join_code = join_code
        self.teams = teams

    def join(self, event_id: str, join_code: str, name: str, device_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def reconnect(self, session_token: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def activity_read(self, session_token: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def facilitator_snapshot(self) -> Dict[str, Any]:
        raise NotImplementedError

    def cleanup(self) -> None:
        return None


class LocalBackend(BaseBackend):
    """Deterministic no-network mode."""

    def __init__(self, event_id: str = "EVT-SCALE-LOCAL", join_code: str = "SCALE", teams: int = 8):
        super().__init__(event_id=event_id, join_code=join_code, teams=teams)
        self.runtime = LocalRuntimeModel(teams=teams)

    def join(self, event_id: str, join_code: str, name: str, device_id: str) -> Dict[str, Any]:
        del join_code
        return self.runtime.join(event_id, name, device_id)

    def reconnect(self, session_token: str) -> Optional[Dict[str, Any]]:
        return self.runtime.restore(session_token)

    def activity_read(self, session_token: str) -> Optional[Dict[str, Any]]:
        return self.runtime.restore(session_token)

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        session_token = payload.get("SessionToken", "")
        if not session_token:
            return {"Error": "missing_session_token"}
        if not self.runtime.restore(session_token):
            return {"Error": "unknown_session"}
        return {
            "SubmissionID": payload.get("SubmissionID", ""),
            "Status": payload.get("Status", "PENDING"),
            "SubmissionType": payload.get("SubmissionType", ""),
        }

    def facilitator_snapshot(self) -> Dict[str, Any]:
        participants = list(self.runtime.participants.values())
        return {
            "ParticipantCount": len(participants),
            "TeamDistribution": dict(Counter(row.get("Team", "") for row in participants)),
            "Submissions": 0,
        }


class RuntimeBackend(BaseBackend):
    """Test/staging runtime mode."""

    def __init__(self, event_id: str, join_code: str, teams: int = 8):
        super().__init__(event_id=event_id, join_code=join_code, teams=teams)
        self.db = GoogleSheetsDB()
        if not self.db.runtime.is_configured:
            raise RuntimeError("Runtime not configured. Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY.")
        resolved = self.db.runtime.get_event_by_join_code(join_code)
        if not resolved:
            raise RuntimeError(f"Join Code {join_code} does not resolve in runtime.")
        resolved_id = resolved.get("event_id", "") if isinstance(resolved, dict) else ""
        if resolved_id and str(resolved_id).strip() != str(event_id).strip():
            raise RuntimeError(f"Join Code {join_code} maps to {resolved_id}, not {event_id}.")
        if not self.db.runtime.can_publish:
            raise RuntimeError("Runtime admin operations not available; set SUPABASE_SECRET_KEY for facilitator/readback metrics.")
        _ = self.db.get_teams(event_id)

    def join(self, event_id: str, join_code: str, name: str, device_id: str) -> Dict[str, Any]:
        del event_id
        payload = self.db.runtime.join_player(join_code=join_code, participant_name=name, device_id=device_id)
        return payload

    def reconnect(self, session_token: str) -> Optional[Dict[str, Any]]:
        return self.db.runtime.get_player_by_token(session_token)

    def activity_read(self, session_token: str) -> Optional[Dict[str, Any]]:
        return self.db.runtime.get_participant_current_mission(session_token)

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.db.runtime.save_submission(payload) or {}

    def facilitator_snapshot(self) -> Dict[str, Any]:
        participants = self.db.runtime.get_players(self.event_id)
        return {
            "ParticipantCount": len(participants),
            "TeamDistribution": dict(Counter(row.get("Team", "") for row in participants)),
            "Submissions": len(self.db.runtime.get_submissions(self.event_id)),
        }


def _safe_error_type(error: BaseException) -> str:
    message = str(error).lower()
    if "connection" in message or "connect" in message:
        return "connection_or_transport"
    if "timeout" in message:
        return "timeout"
    if "429" in message or "ramp" in message or "rate" in message:
        return "rpc_rate_limit_or_backoff"
    if "409" in message:
        return "rpc_idempotency_conflict"
    return "runtime_error"


def _run_concurrently(func: Callable[[int], Any], workers: int, inputs: int) -> List[Any]:
    """Run a fixed number of integer-indexed tasks and return per-task status tuples."""
    results: List[Any] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(func, index): index for index in range(inputs)}
        for future in as_completed(futures):
            try:
                results.append(("ok", future.result()))
            except Exception as error:
                results.append(("error", error))
    return results


def _team_snapshot(participants: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = Counter(row.get("Team", "") for row in participants if row)
    return dict(counts)


def _team_balance_broken(distribution: Dict[str, int]) -> bool:
    if not distribution:
        return True
    values = [count for count in distribution.values() if count]
    return not values or (max(values) - min(values) > 1)


def _build_participant_name(index: int) -> str:
    first = f"Load{index % 40:03d}"
    last = f"User{index:04d}"
    return f"{first} {last}"


def _run_registration(backend: BaseBackend, event_id: str, join_code: str, participants: int, workers: int,
                      result: ScenarioResult) -> List[Dict[str, Any]]:
    registrations: List[Dict[str, Any]] = []

    def _request(index: int):
        full_name = _build_participant_name(index)
        device = f"load-device-{index:04d}"
        started = time.perf_counter()
        player = backend.join(event_id, join_code, full_name, device)
        duplicate = backend.join(event_id, join_code, full_name, device)
        latency = (time.perf_counter() - started) * 1000.0
        if not player.get("SessionToken"):
            raise RuntimeError("missing session token")
        if player.get("ParticipantID") != duplicate.get("ParticipantID"):
            result.duplicate_registrations += 1
        return player, duplicate, latency

    for status, payload in _run_concurrently(_request, workers=workers, inputs=participants):
        if status == "error":
            result.registration_errors += 1
            result.errors[_safe_error_type(payload)] += 1
            continue
        player, _duplicate, latency = payload
        result.registration_latency_ms.append(latency)
        registrations.append(player)
        result.registration_success += 1

    result.team_distribution = _team_snapshot(registrations)
    result.team_spread = max(result.team_distribution.values()) - min(result.team_distribution.values()) if result.team_distribution else 0
    names = [str(row.get("Name", "")).strip().lower() for row in registrations]
    duplicate_by_name = len(names) - len(set(names))
    result.duplicate_by_name = max(0, duplicate_by_name)
    return registrations


def _run_reconnect(backend: BaseBackend, participants: List[Dict[str, Any]], workers: int, result: ScenarioResult) -> None:
    def _request(index: int):
        participant = participants[index]
        token = participant.get("SessionToken", "")
        started = time.perf_counter()
        current = backend.reconnect(token)
        latency = (time.perf_counter() - started) * 1000.0
        if not current:
            raise RuntimeError("reconnect_not_found")
        if current.get("ParticipantID") != participant.get("ParticipantID"):
            result.errors["reconnect_identity_mismatch"] += 1
            raise RuntimeError("participant_identity_changed")
        if current.get("TeamID") != participant.get("TeamID"):
            result.errors["team_changed_on_reconnect"] += 1
            raise RuntimeError("team_changed_on_reconnect")
        return latency

    for status, payload in _run_concurrently(_request, workers=min(workers, len(participants)), inputs=len(participants)):
        if status == "error":
            result.errors[_safe_error_type(payload)] += 1
            continue
        latency = payload
        result.reconnect_latency_ms.append(latency)
        result.reconnect_success += 1


def _run_activity_read(backend: BaseBackend, sessions: List[Dict[str, Any]], workers: int, result: ScenarioResult) -> None:
    def _request(index: int):
        token = sessions[index % len(sessions)].get("SessionToken", "")
        started = time.perf_counter()
        payload = backend.activity_read(token)
        latency = (time.perf_counter() - started) * 1000.0
        if payload is None:
            raise RuntimeError("empty_mission_payload")
        return latency

    for status, payload in _run_concurrently(
        _request,
        workers=min(workers, max(1, len(sessions))),
        inputs=max(1, len(sessions) * 3),
    ):
        # Load tests exercise each participant multiple times to increase contention.
        if status == "error":
            result.errors[_safe_error_type(payload)] += 1
            continue
        result.activity_latency_ms.append(payload)


def _run_submissions(backend: BaseBackend, event_id: str, registrations: List[Dict[str, Any]], result: ScenarioResult) -> None:
    mission_base = f"MISSION-{event_id}"

    def _request(index: int, submission_index: int, is_nasi: bool):
        participant = registrations[index]
        payload = {
            "SubmissionID": f"SUB-{event_id}-{index:04d}-{submission_index:02d}",
            "EventID": event_id,
            "MissionID": f"{mission_base}-{'NASI' if is_nasi else 'TEXT'}",
            "TeamName": participant.get("Team", ""),
            "ParticipantName": participant.get("Name", ""),
            "SessionToken": participant.get("SessionToken", ""),
            "SubmissionType": "NASI" if is_nasi else "TEXT",
            "Metric1": "load-test metric",
            "Status": "PENDING",
            "Judged": "No",
            "Remarks": "Load-readiness harness",
            "SubmittedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if is_nasi:
            payload["Remarks"] = "New Ideas: scale path\nAreas of Improvement: concurrency\nStrengths: deterministic\nImplementation: no-op"
        started = time.perf_counter()
        backend.submit(payload)
        return (time.perf_counter() - started) * 1000.0

    def _run_task(args):
        index, submission_index, is_nasi = args
        return _request(index, submission_index, is_nasi)

    total = len(registrations) * 2
    tasks = []
    for idx, _ in enumerate(registrations):
        tasks.append((idx, 0, False))
        tasks.append((idx, 1, True))

    def runner(i: int):
        task = tasks[i]
        return _run_task(task)

    for status, payload in _run_concurrently(runner, workers=min(max(1, len(tasks)), 160), inputs=total):
        if status == "error":
            result.submission_errors += 1
            result.errors[_safe_error_type(payload)] += 1
            continue
        result.submission_success += 1
        result.submission_latency_ms.append(payload)


def _run_facilitator_reads(backend: BaseBackend, participant_count: int, result: ScenarioResult) -> None:
    reads = max(1, min(30, participant_count))

    def _request(index: int):
        del index
        started = time.perf_counter()
        snapshot = backend.facilitator_snapshot()
        latency = (time.perf_counter() - started) * 1000.0
        if not isinstance(snapshot, dict):
            raise RuntimeError("invalid_snapshot")
        return latency

    for status, payload in _run_concurrently(_request, workers=min(6, reads), inputs=reads):
        if status == "error":
            result.facilitator_errors += 1
            result.errors[_safe_error_type(payload)] += 1
            continue
        result.facilitator_latency_ms.append(payload)


def _classify(result: ScenarioResult) -> str:
    if (
        result.registration_success_rate >= 0.995
        and result.registration_error_rate <= 0.005
        and result.reconnect_success_rate >= 0.995
        and result.submission_success_rate >= 0.995
        and result.team_balance_ok()
        and result.registration_latency_ms
        and percentile(result.registration_latency_ms, 0.99) <= 3000
    ):
        return "PASS"

    if (
        result.registration_success_rate >= 0.95
        and result.reconnect_success_rate >= 0.97
        and result.submission_success_rate >= 0.90
        and not _team_balance_broken(result.team_distribution)
    ):
        return "CONDITIONAL"

    return "FAIL"


def _bottleneck_scan(result: ScenarioResult) -> List[str]:
    bottlenecks = []
    if result.registration_error_rate > 0.01:
        bottlenecks.append("registration_error_rate_exceeded_1_percent")
    if _team_balance_broken(result.team_distribution):
        bottlenecks.append("team_distribution_imbalance")
    if result.reconnect_success_rate < 0.99:
        bottlenecks.append("reconnect_identity_or_team_inconsistency")
    if percentile(result.submission_latency_ms, 0.95) > 3000:
        bottlenecks.append("submission_latency_p95_above_3s")
    if percentile(result.activity_latency_ms, 0.95) > 2000:
        bottlenecks.append("activity_read_latency_p95_above_2s")
    if percentile(result.facilitator_latency_ms, 0.95) > 2000:
        bottlenecks.append("facilitator_read_latency_p95_above_2s")
    for kind, count in result.errors.items():
        if count > 0:
            bottlenecks.append(f"{kind}:{count}")
    return sorted(set(bottlenecks))


def run_scale_suite(
    mode: str,
    event_id: str,
    join_code: str,
    profiles: List[int],
    workers: Dict[int, int],
    teams: int,
    output: Optional[Path] = None,
) -> Dict[str, Any]:
    if mode == "local":
        backend: BaseBackend = LocalBackend(event_id=event_id, join_code=join_code, teams=teams)
    else:
        backend = RuntimeBackend(event_id=event_id, join_code=join_code, teams=teams)

    suite = {
        "environment": {
            "mode": mode,
            "target": "local" if mode == "local" else "test_or_staging",
            "event_id": event_id,
            "join_code": join_code,
            "number_of_teams": teams,
            "worker_preset": workers,
        },
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "profiles": profiles,
        "scales": {},
        "database_safety": {
            "schema_checks": [
                "runtime_participants_event_idx",
                "runtime_participants_event_name_idx",
                "runtime_submissions_event_idx",
                "runtime_submissions_mission_idx",
            ],
            "preflight_sql": "supabase/003_runtime_programme.sql",
            "postflight_sql": "supabase/005_participant_identity.sql",
            "rollback_verification_sql": "supabase/013_experience_definition_assignment_rollback.sql",
            "notes": (
                "Use the listed SQL checks only in test/staging. "
                "This harness does not execute direct catalog SQL in this repository."
            ),
        },
    }

    for participant_count in profiles:
        profile_result = ScenarioResult(participants=participant_count, requested=participant_count)
        profile_workers = workers.get(participant_count, max(1, participant_count // 2))
        try:
            registrations = _run_registration(
                backend=backend,
                event_id=event_id,
                join_code=join_code,
                participants=participant_count,
                workers=profile_workers,
                result=profile_result,
            )
            _run_reconnect(backend, registrations, profile_workers, profile_result)
            _run_activity_read(backend, registrations, profile_workers, profile_result)
            _run_submissions(backend, event_id, registrations, profile_result)
            _run_facilitator_reads(backend, len(registrations), profile_result)
        except Exception as error:
            profile_result.registration_errors += 1
            profile_result.errors[_safe_error_type(error)] += 1
            profile_result.registration_success = 0
            profile_result.bottlenecks.append("test_harness_exception")
            profile_result.bottlenecks.extend(_bottleneck_scan(profile_result))
            suite["scales"][str(participant_count)] = {
                "status": "FAIL",
                "error": str(error),
                **profile_result.as_dict(),
            }
            continue

        profile_result.bottlenecks = _bottleneck_scan(profile_result)
        suite["scales"][str(participant_count)] = {
            "status": _classify(profile_result),
            "profile": profile_result.as_dict(),
        }

    suite["pass_fail"] = {
        size: payload.get("status", "FAIL")
        for size, payload in suite["scales"].items()
    }

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    return suite


def parse_args():
    parser = argparse.ArgumentParser(description="EXOS scale-readiness audit harness.")
    parser.add_argument("--mode", choices=("local", "staging", "test"), default="local")
    parser.add_argument("--event-id", default="EVT-SCALE-LOCAL")
    parser.add_argument("--join-code", default="SCALE")
    parser.add_argument("--teams", type=int, default=8)
    parser.add_argument("--profiles", nargs="*", type=int, default=list(WORKLOADS))
    parser.add_argument("--workers", nargs="*", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.mode in {"test", "staging"}:
        if not args.event_id or not args.join_code:
            raise ValueError("Provide --event-id and --join-code for test/staging.")
    if any(profile <= 0 for profile in args.profiles):
        raise ValueError("Profiles must be positive integers.")
    workers = DEFAULT_WORKERS.copy()
    if args.workers:
        if len(args.workers) == 1:
            workers = {scale: args.workers[0] for scale in args.profiles}
        elif len(args.workers) != len(args.profiles):
            raise ValueError("--workers supports one global value or one value per profile.")
        else:
            workers = dict(zip(args.profiles, args.workers))

    suite = run_scale_suite(
        mode="local" if args.mode == "local" else "staging",
        event_id=args.event_id,
        join_code=args.join_code,
        profiles=args.profiles,
        workers=workers,
        teams=args.teams,
        output=args.output,
    )
    print(json.dumps(suite, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
