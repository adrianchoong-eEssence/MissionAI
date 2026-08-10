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
    connected: bool = False


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
    operations: dict[str, Any] = field(default_factory=dict)

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
            event_name="Formula R.A.C.E. · Day One", source="DEMO", race_status="RUNNING",
            active_checkpoint="CP4 · Chassis Construction", elapsed="02:18:42", teams=teams,
            transactions=transactions, submissions=submissions,
            stock={"Cardboard sheet": 48, "Wheel set": 19, "Axle kit": 24, "Glue sticks": 63},
            activity=("11:44 · Ignition submitted CP4 evidence", "11:42 · Velocity awarded 200 credits",
                      "11:38 · Apex purchased 2 axle kits", "11:31 · Safety bonus issued to Velocity"),
        )


class LiveFormulaRaceProvider:
    """Event-scoped projection over existing EXOS repositories and canonical views."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _number(value, default=0):
        try:
            return int(float(value or default))
        except (TypeError, ValueError):
            return default

    def snapshot(self, event_id: str = "", strict_core_v2: bool = False) -> RaceSnapshot:
        event = None
        if hasattr(self.db, "runtime") and getattr(self.db.runtime, "can_publish", False):
            try:
                event = self.db.runtime.get_runtime_event(event_id)
            except Exception:
                if strict_core_v2:
                    raise RuntimeError("Core v2 runtime unavailable for event lookup.")
                event = None
        if not event:
            if strict_core_v2:
                raise RuntimeError("Core v2 event lookup did not return an event.")
            event = self.db.get_event(event_id) or {}
        if not event:
            raise ValueError("Select a valid Formula R.A.C.E. event.")
        raw_teams = []
        if hasattr(self.db, "runtime") and getattr(self.db.runtime, "can_publish", False):
            try:
                raw_teams = self.db.runtime.get_runtime_teams(event_id)
            except Exception:
                if strict_core_v2:
                    raise RuntimeError("Core v2 runtime unavailable for team lookup.")
                raw_teams = []
        if not raw_teams:
            if strict_core_v2:
                raise RuntimeError("Core v2 runtime unavailable for teams.")
            raw_teams = self.db.get_teams(event_id)

        submissions_raw = []
        if hasattr(self.db, "runtime") and getattr(self.db.runtime, "can_publish", False):
            try:
                submissions_raw = self.db.runtime.get_canonical_submissions(event_id)
            except Exception:
                if strict_core_v2:
                    raise RuntimeError("Core v2 runtime unavailable for submissions.")
                submissions_raw = []
        if not submissions_raw and hasattr(self.db, "get_event_submissions"):
            # Empty submissions is a valid fresh-event state. Keep legacy fallback only for non-empty legacy reads.
            if not strict_core_v2:
                submissions_raw = self.db.get_event_submissions(event_id)

        missions = []
        if hasattr(self.db, "runtime") and getattr(self.db.runtime, "can_publish", False):
            try:
                missions = self.db.runtime.get_programme_hierarchy(event_id)
            except Exception:
                if strict_core_v2:
                    raise RuntimeError("Core v2 runtime unavailable for programme hierarchy.")
                missions = []
        if not missions:
            if strict_core_v2:
                raise RuntimeError("Core v2 programme hierarchy not available.")
            if hasattr(self.db, "get_event_missions"):
                missions = self.db.get_event_missions(event_id)

        if strict_core_v2:
            if not hasattr(self.db.runtime, "get_formula_race_state"):
                raise RuntimeError("Core v2 runtime state reader missing.")
            state = self.db.runtime.get_formula_race_state(event_id) if hasattr(self.db.runtime, "get_formula_race_state") else {}
            control = {
                "CurrentStageStatus": "READY",
                "Elapsed": "00:00",
                "CurrentStageName": "Programme ready",
            }
        else:
            state = self.db.get_event_state(event_id) or {}
            control = self.db.get_runtime_control_state(event_id) or {}
        operations = {}
        if hasattr(self.db, "runtime") and getattr(self.db.runtime, "can_publish", False):
            try:
                operations = self.db.runtime.get_formula_race_state(event_id) or {}
                operations["Checkpoints"] = self.db.runtime.get_formula_race_checkpoints(event_id)
            except Exception: operations = {}
            if strict_core_v2 and not isinstance(operations, dict):
                raise RuntimeError("Core v2 race state unavailable.")
        report = {}
        captain_status = {}
        if self.db.runtime.can_publish:
            try:
                report = self.db.runtime.get_canonical_transaction_report(event_id) or {}
            except Exception:
                report = {}
            try:
                captain_status = {
                    str(row.get("TeamID", "")): bool(row.get("Connected", False))
                    for row in self.db.runtime.formula_race_team_status(event_id)
                }
            except Exception:
                captain_status = {}
        leaderboard = {str(row.get("TeamID", "")): row for row in report.get("Leaderboard", [])}
        balances = {
            str(row.get("team_id", row.get("TeamID", ""))): row
            for row in report.get("TeamBalances", [])
        }
        teams = []
        for position, row in enumerate(raw_teams, start=1):
            team_id = str(row.get("TeamID", ""))
            standing = leaderboard.get(team_id, {})
            balance = balances.get(team_id, {})
            completed = sum(
                1 for item in submissions_raw
                if str(item.get("TeamID", "")) == team_id
                and str(item.get("Status", "")).upper() in {"APPROVED", "AWARDED"}
            )
            raw_checkpoint_state = operations.get("Checkpoints", {})
            checkpoints_snapshot = (
                raw_checkpoint_state.get("Checkpoints", [])
                if isinstance(raw_checkpoint_state, dict) else raw_checkpoint_state
            )
            checkpoint_total = len(checkpoints_snapshot or [])
            build = round(100 * completed / max(checkpoint_total or len(missions), 1))
            teams.append(Team(
                team_id, str(row.get("TeamName", team_id)), str(row.get("Country", "")),
                "#e31b23", self._number(standing.get("Score", row.get("Score", 0))),
                self._number(standing.get("AvailableBalance", balance.get("available_balance", 0))),
                build, self._number(standing.get("Rank", position), position),
                captain_status.get(team_id, False),
            ))
        transactions = tuple(Transaction(
            str(row.get("award_transaction_id", "")), str(row.get("team_id", "")),
            str(row.get("award_type", "")), self._number(row.get("amount", 0)),
            str(row.get("reason", row.get("source", ""))), str(row.get("created_at", "")),
        ) for row in report.get("AwardTransactions", []))
        submissions = tuple(Submission(
            str(row.get("SubmissionID", "")), str(row.get("TeamID", "")),
            str(row.get("MissionName", row.get("ActivityID", row.get("MissionID", "Checkpoint")))),
            str(row.get("Status", "PENDING")), str(row.get("SubmittedAt", row.get("Timestamp", ""))),
            str(row.get("StorageReference", row.get("PhotoURL", row.get("EvidenceType", "Evidence")))),
        ) for row in submissions_raw)
        checkpoint_state = operations.get("Checkpoints", {})
        if isinstance(checkpoint_state, list):
            checkpoint_state = {"Status": ""}
        active = str(
            "LIVE CHECKPOINTS" if str(checkpoint_state.get("Status", "")).upper() == "LIVE" else
            state.get("CurrentStageName", "") or state.get("StageName", "")
            or state.get("CurrentMissionName", "") or "Programme ready"
        )
        return RaceSnapshot(
            event_id=event_id, event_name=str(event.get("EventName", event_id)), source="LIVE",
            race_status=str(control.get("CurrentStageStatus", event.get("Status", "READY"))),
            active_checkpoint=active, elapsed=str(control.get("Elapsed", "—")),
            teams=tuple(sorted(teams, key=lambda row: (row.rank, row.name))),
            transactions=transactions, submissions=submissions, stock={}, operations=operations,
            activity=tuple(
                f"{item.submitted_at} · {item.team_id} · {item.checkpoint} · {item.status}"
                for item in submissions[-6:][::-1]
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
