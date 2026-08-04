"""Formula R.A.C.E. read models and canonical integration boundary.

The demo provider is deliberately separate from EXOS persistence.  Screens consume
the same read model whether the source is demo data or a future canonical projection.
All live mutations must continue to pass through ``ControlRuntime``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    country: str
    colour: str
    score: int
    balance: int
    build: int
    rank: int


@dataclass(frozen=True)
class Transaction:
    id: str
    team_id: str
    kind: str
    amount: int
    description: str
    time: str


@dataclass(frozen=True)
class Submission:
    id: str
    team_id: str
    checkpoint: str
    status: str
    submitted_at: str
    evidence: str


@dataclass(frozen=True)
class RaceSnapshot:
    event_id: str
    event_name: str
    source: str
    race_status: str
    active_checkpoint: str
    elapsed: str
    teams: tuple[Team, ...]
    transactions: tuple[Transaction, ...]
    submissions: tuple[Submission, ...]
    stock: dict[str, int]
    activity: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_demo(self) -> bool:
        return self.source == "DEMO"


class FormulaRaceProvider(Protocol):
    def snapshot(self, event_id: str = "") -> RaceSnapshot: ...


class DemoFormulaRaceProvider:
    """Deterministic labelled data for shell/UAT. Never writes to persistence."""

    def snapshot(self, event_id: str = "") -> RaceSnapshot:
        teams = (
            Team("TEAM-01", "Velocity", "Malaysia", "#e31b23", 485, 780, 92, 1),
            Team("TEAM-02", "Apex", "Singapore", "#f5c400", 462, 640, 86, 2),
            Team("TEAM-03", "Ignition", "Thailand", "#22a7f0", 438, 520, 78, 3),
            Team("TEAM-04", "Torque", "Indonesia", "#67c23a", 411, 410, 69, 4),
            Team("TEAM-05", "Momentum", "Philippines", "#9b6dff", 389, 350, 61, 5),
            Team("TEAM-06", "Catalyst", "Vietnam", "#ff7a18", 372, 290, 54, 6),
        )
        transactions = (
            Transaction("TX-104", "TEAM-01", "EARN", 200, "Checkpoint 4 award", "11:42"),
            Transaction("TX-103", "TEAM-02", "SPEND", -120, "Axle kit × 2", "11:38"),
            Transaction("TX-102", "TEAM-01", "BONUS", 50, "Safety bonus", "11:31"),
            Transaction("TX-101", "TEAM-03", "PENALTY", -25, "Late checkpoint", "11:25"),
            Transaction("TX-100", "TEAM-04", "REFUND", 30, "Returned material", "11:18"),
        )
        submissions = (
            Submission("SUB-301", "TEAM-03", "CP4 · Chassis", "PENDING", "11:44", "3 photos"),
            Submission("SUB-300", "TEAM-05", "CP4 · Chassis", "PENDING", "11:41", "2 photos"),
            Submission("SUB-299", "TEAM-02", "CP3 · Skeleton", "AWARDED", "11:37", "4 photos"),
            Submission("SUB-298", "TEAM-06", "CP3 · Skeleton", "REVISION", "11:29", "1 photo"),
        )
        return RaceSnapshot(
            event_id=event_id or "FORMULA-RACE-UAT",
            event_name="Formula R.A.C.E. · Day One",
            source="DEMO",
            race_status="RUNNING",
            active_checkpoint="CP4 · Chassis Construction",
            elapsed="02:18:42",
            teams=teams,
            transactions=transactions,
            submissions=submissions,
            stock={"Cardboard sheet": 48, "Wheel set": 19, "Axle kit": 24, "Glue sticks": 63},
            activity=(
                "11:44 · Ignition submitted CP4 evidence",
                "11:42 · Velocity awarded 200 credits",
                "11:38 · Apex purchased 2 axle kits",
                "11:31 · Safety bonus issued to Velocity",
            ),
        )


def snapshot_as_contract(snapshot: RaceSnapshot) -> dict[str, Any]:
    """Stable JSON-shaped contract useful for adapters and contract tests."""
    return {
        "event": {"id": snapshot.event_id, "name": snapshot.event_name},
        "provenance": {"source": snapshot.source, "is_demo": snapshot.is_demo},
        "runtime": {
            "status": snapshot.race_status,
            "active_checkpoint": snapshot.active_checkpoint,
            "elapsed": snapshot.elapsed,
        },
        "teams": [team.__dict__ for team in snapshot.teams],
        "transactions": [transaction.__dict__ for transaction in snapshot.transactions],
        "submissions": [submission.__dict__ for submission in snapshot.submissions],
        "stock": dict(snapshot.stock),
        "activity": list(snapshot.activity),
    }
