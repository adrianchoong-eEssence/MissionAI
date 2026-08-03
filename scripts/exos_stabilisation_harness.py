#!/usr/bin/env python3
"""Deterministic EXOS concurrency and recovery harness.

This is a dependency-free pre-production gate. It validates the invariants
expected from the Supabase join RPC without writing to a live event. Live
production testing remains a separate, explicitly authorised operation.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


class TransientFailure(RuntimeError):
    pass


class RuntimeModel:
    """Small transactional model of the production join invariants."""

    def __init__(self, teams=8, transient_failures=0):
        self._lock = threading.Lock()
        self.teams = [f"Team {number:02d}" for number in range(1, teams + 1)]
        self.participants = {}
        self.tokens = {}
        self.transient_failures = transient_failures
        self.attempts = Counter()

    def join(self, event_id, name, device_id):
        identity = (event_id, " ".join(name.lower().split()))
        request = (identity, device_id)
        with self._lock:
            self.attempts[request] += 1
            if self.attempts[request] <= self.transient_failures:
                raise TransientFailure("injected 503")
            existing = self.participants.get(identity)
            if existing:
                return dict(existing)
            counts = Counter(
                row["Team"] for key, row in self.participants.items()
                if key[0] == event_id
            )
            team = min(self.teams, key=lambda item: (counts[item], item))
            team_id = f"TEAM-{self.teams.index(team) + 1:02d}"
            row = {
                "ParticipantID": str(uuid.uuid4()),
                "EventID": event_id,
                "Name": " ".join(name.split()),
                "Team": team,
                "TeamID": team_id,
                "Country": f"Country {self.teams.index(team) + 1:02d}",
                "Flag": f"FLAG-{self.teams.index(team) + 1:02d}",
                "IsLeader": number_is_leader(identity),
                "IntelligenceCredits": 0,
                "SessionToken": str(uuid.uuid4()),
            }
            self.participants[identity] = row
            self.tokens[row["SessionToken"]] = row
            return dict(row)

    def join_with_retry(self, *args, retries=3):
        for attempt in range(retries):
            try:
                return self.join(*args)
            except TransientFailure:
                if attempt == retries - 1:
                    raise

    def restore(self, token):
        with self._lock:
            row = self.tokens.get(token)
            return dict(row) if row else None


def number_is_leader(identity):
    """Choose deterministic leaders without relying on browser/device state."""
    return identity[1].endswith("00000")


def percentile(values, fraction):
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def run_scenario(participants, workers, events=1, transient_failures=0):
    runtime = RuntimeModel(transient_failures=transient_failures)
    latencies = []
    errors = []
    responses = []
    started = time.perf_counter()

    def request(number):
        event_id = f"EVT-{number % events + 1:02d}"
        name = f"Load Participant {number:05d}"
        device = f"device-{number:05d}"
        before = time.perf_counter()
        player = runtime.join_with_retry(event_id, name, device)
        # A duplicate click from the same identity must return the same record.
        duplicate = runtime.join_with_retry(event_id, f"  {name.upper()}  ", device)
        elapsed = (time.perf_counter() - before) * 1000
        return player, duplicate, elapsed

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(request, number) for number in range(participants)]
        for future in as_completed(futures):
            try:
                player, duplicate, elapsed = future.result()
                responses.append((player, duplicate))
                latencies.append(elapsed)
            except Exception as error:  # captured in report, not hidden
                errors.append(type(error).__name__)

    duration = time.perf_counter() - started
    ids = [row[0]["ParticipantID"] for row in responses]
    duplicate_mismatches = sum(a["ParticipantID"] != b["ParticipantID"] for a, b in responses)
    durable_fields = (
        "ParticipantID", "TeamID", "Team", "Country", "Flag",
        "IsLeader", "IntelligenceCredits",
    )
    restore_failures = 0
    for player, _duplicate in responses:
        restored = runtime.restore(player["SessionToken"])
        if not restored or any(restored[field] != player[field] for field in durable_fields):
            restore_failures += 1
    spreads = []
    for event_number in range(1, events + 1):
        event = f"EVT-{event_number:02d}"
        counts = Counter(row["Team"] for row in runtime.participants.values() if row["EventID"] == event)
        spreads.append(max(counts.values()) - min(counts.values()) if counts else 0)
    passed = not errors and len(set(ids)) == participants and not duplicate_mismatches and not restore_failures and max(spreads) <= 1
    return {
        "participants": participants,
        "concurrent_workers": workers,
        "events": events,
        "injected_failures_per_request": transient_failures,
        "passed": passed,
        "successful": len(responses),
        "errors": dict(Counter(errors)),
        "unique_participants": len(set(ids)),
        "duplicate_identity_mismatches": duplicate_mismatches,
        "session_restore_failures": restore_failures,
        "durable_restore_fields": list(durable_fields),
        "maximum_team_distribution_spread": max(spreads),
        "duration_seconds": round(duration, 4),
        "throughput_joins_per_second": round(participants / duration, 1),
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 3),
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
            "max": round(max(latencies), 3),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    scenarios = [
        run_scenario(100, 100),
        run_scenario(250, 100),
        run_scenario(500, 100),
        run_scenario(200, 100, events=2),
        run_scenario(100, 100, transient_failures=2),
    ]
    report = {
        "suite": "EXOS deterministic identity stabilisation harness",
        "environment": "local in-memory transactional model; not production",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "passed": all(item["passed"] for item in scenarios),
        "scenarios": scenarios,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
