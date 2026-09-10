"""Pure, event-scoped projections for Live Location V1.

Database RPCs own consent, identity, event scoping and the raw history.  This
module deliberately only formats already-authorised operator-map rows.  It
never guesses a location from stale or low-quality updates.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any


def location_status(last_update: datetime | None, *, consent_enabled: bool, now: datetime, stale_after_seconds: int) -> str:
    if not consent_enabled or last_update is None:
        return "UNAVAILABLE"
    age = max((now - last_update).total_seconds(), 0)
    return "CURRENT" if age <= stale_after_seconds else "STALE"


def distance_meters(left: tuple[float, float], right: tuple[float, float]) -> float:
    """Great-circle distance; no external map service is needed."""
    lat1, lon1, lat2, lon2 = map(radians, (*left, *right))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(a))


def derive_team_locations(rows: list[dict[str, Any]], *, separation_threshold_meters: float) -> list[dict[str, Any]]:
    """Create team summaries without averaging stale, inaccurate or dispersed GPS.

    A centroid is emitted only when all CURRENT reporters for a team form a
    cluster within the configured separation threshold.  A separated team is
    explicitly labelled rather than represented by a misleading midpoint.
    """
    teams: dict[str, list[dict[str, Any]]] = {}
    for row in rows or []:
        teams.setdefault(str(row.get("TeamID", "")), []).append(dict(row))
    summaries = []
    for team_id, members in sorted(teams.items()):
        current = [row for row in members if str(row.get("Status", "")).upper() == "CURRENT"
                   and row.get("Latitude") is not None and row.get("Longitude") is not None]
        points = [(float(row["Latitude"]), float(row["Longitude"])) for row in current]
        max_distance = max((distance_meters(a, b) for index, a in enumerate(points) for b in points[index + 1:]), default=0.0)
        separated = len(points) > 1 and max_distance > float(separation_threshold_meters)
        centroid = None if not points or separated else {
            "Latitude": sum(point[0] for point in points) / len(points),
            "Longitude": sum(point[1] for point in points) / len(points),
        }
        summaries.append({
            "TeamID": team_id,
            "Reporting": len(current),
            "Members": len(members),
            "Status": "SEPARATED" if separated else ("CURRENT" if current else "UNAVAILABLE"),
            "MaxCurrentDistanceMeters": round(max_distance, 1),
            "Location": centroid,
        })
    return summaries


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
