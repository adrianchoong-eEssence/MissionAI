"""Generic EXOS result contract: status, manual placement and human durations.

A live event proved that a human exception must be a first-class state.  When
four teams did not finish, the only way to preserve their observed order was to
store fabricated multi-million millisecond finish times, which both lied in the
canonical record and exceeded the entry control's range.

Nothing here is Formula R.A.C.E. specific: a result is a measured value, a
status, and -- when no measurement exists -- an explicitly verified placement.

The ranking rule below is the single written definition.  The lock RPC in SQL
implements the same order, and a contract test asserts the two agree.
"""
from __future__ import annotations

from typing import Any, Optional

# Only FINISHED carries a measured result.  A status is added here only when it
# has an operational meaning a facilitator can decide at the finish line.
RESULT_STATUSES = ("FINISHED", "DNF", "DNS", "DISQUALIFIED")
MEASURED_RESULT_STATUSES = ("FINISHED",)
UNMEASURED_RESULT_STATUSES = tuple(s for s in RESULT_STATUSES if s not in MEASURED_RESULT_STATUSES)

# Ordering among non-finishers that were never given an explicit placement.
# Deterministic, and always after every placed result.
STATUS_PRECEDENCE = {status: index for index, status in enumerate(RESULT_STATUSES)}

# Who owns the official result.  One vocabulary, imported by configuration,
# the Captain surface, Race Control and the contract tests.  SYSTEM is
# deliberately NOT included: no station computes its own official result today,
# and adding a value the submit RPC would reject is the exact contract split
# this module exists to prevent.
RESULT_ENTRY_OWNERS = ("FACILITATOR", "CAPTAIN")
DEFAULT_RESULT_ENTRY_OWNER = "FACILITATOR"

MAX_PENALTY_MS = 3_600_000
_MS_PER_MINUTE = 60_000
_MS_PER_SECOND = 1_000


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalise_result_status(value: Any) -> str:
    """Absent status means FINISHED, so historical rows keep their meaning."""
    status = _text(value).upper().replace("-", "").replace(" ", "")
    aliases = {"DIDNOTFINISH": "DNF", "DIDNOTSTART": "DNS", "DQ": "DISQUALIFIED", "": "FINISHED"}
    status = aliases.get(status, status)
    return status if status in RESULT_STATUSES else "FINISHED"


def is_measured(status: Any) -> bool:
    return normalise_result_status(status) in MEASURED_RESULT_STATUSES


def normalise_result_entry_owner(value: Any) -> str:
    owner = _text(value).upper()
    return owner if owner in RESULT_ENTRY_OWNERS else DEFAULT_RESULT_ENTRY_OWNER


def duration_ms(minutes: Any = 0, seconds: Any = 0, milliseconds: Any = 0) -> int:
    """Compose the canonical millisecond value from human units."""
    return max(0, (_int(minutes, 0) or 0) * _MS_PER_MINUTE
               + (_int(seconds, 0) or 0) * _MS_PER_SECOND
               + (_int(milliseconds, 0) or 0))


def split_duration_ms(value: Any) -> tuple[int, int, int]:
    """Decompose canonical milliseconds into minutes, seconds, milliseconds."""
    total = max(0, _int(value, 0) or 0)
    return total // _MS_PER_MINUTE, (total % _MS_PER_MINUTE) // _MS_PER_SECOND, total % _MS_PER_SECOND


def format_duration_ms(value: Any, empty: str = "—") -> str:
    """Render canonical milliseconds for a human, never as a raw unit."""
    if value in (None, ""):
        return empty
    minutes, seconds, milliseconds = split_duration_ms(value)
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def describe_result(row: dict[str, Any]) -> str:
    """One human string for any result, measured or not."""
    status = normalise_result_status((row or {}).get("result_status", (row or {}).get("ResultStatus")))
    if not is_measured(status):
        placement = _int((row or {}).get("manual_placement", (row or {}).get("ManualPlacement")))
        return f"{status} · placed {placement}" if placement else status
    return format_duration_ms((row or {}).get("time_ms", (row or {}).get("TimeMs")))


def normalise_race_result(row: dict[str, Any]) -> dict[str, Any]:
    """Canonical result shape.  An unmeasured status never carries a time."""
    row = dict(row or {})
    status = normalise_result_status(row.get("result_status", row.get("ResultStatus")))
    measured = is_measured(status)
    time_ms = _int(row.get("time_ms", row.get("TimeMs"))) if measured else None
    penalty_ms = (_int(row.get("penalty_ms", row.get("PenaltyMs")), 0) or 0) if measured else 0
    placement = None if measured else _int(row.get("manual_placement", row.get("ManualPlacement")))
    return {
        "TeamID": _text(row.get("team_id", row.get("TeamID"))),
        "ResultStatus": status,
        "TimeMs": max(0, time_ms) if time_ms is not None else None,
        "PenaltyMs": max(0, penalty_ms),
        "AdjustedMs": (max(0, time_ms) + max(0, penalty_ms)) if time_ms is not None else None,
        "ManualPlacement": placement if (placement is None or placement >= 1) else None,
        "Verified": bool(row.get("verified", row.get("Verified", False))),
        "Reason": _text(row.get("reason", row.get("Reason"))),
        "Judge": _text(row.get("judge", row.get("Judge"))),
        "Locked": bool(row.get("locked", row.get("Locked", False))),
    }


def validate_race_result(row: dict[str, Any]) -> list[str]:
    """Reject a single result that cannot be ranked truthfully."""
    result = normalise_race_result(row)
    errors: list[str] = []
    if result["ResultStatus"] in MEASURED_RESULT_STATUSES:
        if result["TimeMs"] is None:
            errors.append("A finished result requires a finish time.")
        if result["PenaltyMs"] > MAX_PENALTY_MS:
            errors.append("Penalty is outside the supported range.")
    else:
        # The whole point of the contract: never invent a time to be rankable.
        if row.get("time_ms") not in (None, "", 0) or row.get("TimeMs") not in (None, "", 0):
            errors.append(f"A {result['ResultStatus']} result must not carry a finish time.")
        # Read the raw value: normalisation drops an out-of-range placement, so
        # validating the normalised field would silently accept it.
        raw_placement = _int((row or {}).get("manual_placement", (row or {}).get("ManualPlacement")))
        if raw_placement is not None and raw_placement < 1:
            errors.append("Manual placement must be 1 or greater.")
    return errors


def validate_race_results(rows: list[dict[str, Any]]) -> list[str]:
    """Reject a result set that cannot produce a deterministic ranking."""
    results = [normalise_race_result(row) for row in rows or []]
    errors: list[str] = []
    for row in rows or []:
        errors.extend(validate_race_result(row))
    placements = [row["ManualPlacement"] for row in results if row["ManualPlacement"] is not None]
    if len(placements) != len(set(placements)):
        errors.append("Manual placement must be unique within the event.")
    return errors


def rank_race_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The single ranking definition, mirrored by the lock RPC.

    1. Finished results, by adjusted time ascending.
    2. Non-finishers holding an explicit placement, by that placement.
    3. Remaining non-finishers, by status precedence.
    TeamID breaks every tie, so the order is total and reproducible.
    """
    results = [normalise_race_result(row) for row in rows or []]
    ordered = sorted(
        results,
        key=lambda row: (
            0 if row["ResultStatus"] in MEASURED_RESULT_STATUSES else 1,
            row["AdjustedMs"] if row["AdjustedMs"] is not None else 0,
            row["ManualPlacement"] if row["ManualPlacement"] is not None else 2_147_483_647,
            STATUS_PRECEDENCE.get(row["ResultStatus"], len(RESULT_STATUSES)),
            row["TeamID"],
        ),
    )
    for position, row in enumerate(ordered, start=1):
        row["RankingPosition"] = position
    return ordered
