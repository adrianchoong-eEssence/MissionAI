"""Event-configurable Formula R.A.C.E. championship component contracts."""
from __future__ import annotations

from copy import deepcopy
from typing import Any
import uuid


COMPONENT_TYPES = ("JUDGING_CRITERION", "TEAM_PHOTO", "RACE_RANK")
TIE_BREAKS = ("RACE_RANK", "TEAM_ID")

# Judging guidance only.  These dimensions reduce facilitator subjectivity and
# are summed into the ONE canonical criterion score; they are never stored as
# separate judging rows and never become separate Championship Components.
AESTHETICS_RUBRIC = (
    ("Craftsmanship & Finish", 10, ("Clean construction", "Neat joins", "Finishing quality", "Attention to detail")),
    ("Creative Design", 10, ("Originality", "Imaginative use of materials", "Distinctive concept")),
    ("Visual Impact & Branding", 10, ("Colour coordination", "Overall visual appearance", "Team/car identity", "Branding")),
    ("Design Integration", 10, ("Cohesive overall design", "Parts work together visually", "Intentional rather than assembled randomly")),
)
AESTHETICS_RUBRIC_TOTAL = sum(maximum for _, maximum, _ in AESTHETICS_RUBRIC)
SCORING_ANCHORS = (
    ("9–10", "Outstanding"), ("7–8", "Strong"), ("5–6", "Competent"),
    ("3–4", "Basic"), ("1–2", "Poor / incomplete"),
)


def uses_aesthetics_rubric(criterion: dict[str, Any]) -> bool:
    """Offer the rubric only for the configured criterion it was written for."""
    name = _text((criterion or {}).get("CriterionName")).casefold()
    return "aesthetic" in name and _number((criterion or {}).get("MaximumScore", 0)) == AESTHETICS_RUBRIC_TOTAL


def aesthetics_total(sub_scores: dict[str, Any]) -> float:
    """Sum the rubric dimensions into the canonical criterion score."""
    total = 0.0
    for name, maximum, _ in AESTHETICS_RUBRIC:
        total += min(max(_number((sub_scores or {}).get(name, 0)), 0.0), float(maximum))
    return total


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def normalise_championship_component(raw: dict[str, Any], fallback_order: int = 1) -> dict[str, Any]:
    raw = dict(raw or {})
    component_type = _text(raw.get("ComponentType", raw.get("component_type"))).upper()
    scoring = deepcopy(raw.get("ScoringConfiguration", raw.get("scoring_configuration", {})) or {})
    source = raw.get("SourceReference", raw.get("source_reference", ""))
    if isinstance(source, dict):
        source = _text(source.get("CriterionName", source.get("criterion_name", source.get("ActivityID", ""))))
    return {
        "ComponentID": _text(raw.get("ComponentID", raw.get("component_id"))) or f"RACE-COMP-{uuid.uuid4().hex[:10].upper()}",
        "DisplayOrder": max(1, int(_number(raw.get("DisplayOrder", raw.get("display_order", fallback_order)), fallback_order))),
        "ComponentType": component_type if component_type in COMPONENT_TYPES else "JUDGING_CRITERION",
        "DisplayName": _text(raw.get("DisplayName", raw.get("display_name"))),
        "MaximumChampionshipPoints": max(0, _number(raw.get("MaximumChampionshipPoints", raw.get("maximum_championship_points", 0)))),
        "Enabled": bool(raw.get("Enabled", raw.get("enabled", True))),
        "SourceReference": _text(source),
        "ScoringConfiguration": scoring,
    }


def normalise_championship_components(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalise_championship_component(row, index) for index, row in enumerate(rows or [], 1)]


def validate_championship_components(rows: list[dict[str, Any]], criteria: list[dict[str, Any]], team_count: int = 0) -> list[str]:
    components = normalise_championship_components(rows)
    names = {str(row.get("CriterionName", "")).strip().casefold() for row in criteria or [] if row.get("Enabled", True)}
    ids = [row["ComponentID"].casefold() for row in components]
    errors: list[str] = []
    if len(ids) != len(set(ids)):
        errors.append("Championship component IDs must be unique within the event.")
    for row in components:
        label = row["DisplayName"] or row["ComponentID"]
        if not row["DisplayName"]:
            errors.append("Every championship component requires a display name.")
        if row["MaximumChampionshipPoints"] < 0:
            errors.append(f"{label}: maximum championship points cannot be negative.")
        if row["ComponentType"] in {"JUDGING_CRITERION", "TEAM_PHOTO"} and row["SourceReference"].casefold() not in names:
            errors.append(f"{label}: source criterion must be an enabled judging criterion.")
        if row["ComponentType"] == "RACE_RANK":
            points = row["ScoringConfiguration"].get("RankPoints", {}) if isinstance(row["ScoringConfiguration"], dict) else {}
            if not isinstance(points, dict):
                errors.append(f"{label}: race rank points must be configured by rank.")
            elif any(_number(value) < 0 for value in points.values()):
                errors.append(f"{label}: race rank points cannot be negative.")
            elif any(_number(value) > row["MaximumChampionshipPoints"] for value in points.values()):
                errors.append(f"{label}: race rank points cannot exceed its maximum championship points.")
            elif team_count and any(str(rank) not in points for rank in range(1, team_count + 1)):
                errors.append(f"{label}: configure every active-team race rank.")
    return errors


def championship_component_points(component: dict[str, Any], source_score: Any, source_maximum: Any, *, team_photo_submitted: bool = True, race_rank: Any = None, race_final_locked: bool = False) -> float:
    component = normalise_championship_component(component)
    if not component["Enabled"]:
        return 0.0
    maximum = component["MaximumChampionshipPoints"]
    if component["ComponentType"] == "RACE_RANK":
        if not race_final_locked or race_rank in (None, ""):
            return 0.0
        points = component["ScoringConfiguration"].get("RankPoints", {}) if isinstance(component["ScoringConfiguration"], dict) else {}
        return max(0.0, _number(points.get(str(int(race_rank)), 0)))
    if component["ComponentType"] == "TEAM_PHOTO" and not team_photo_submitted:
        return 0.0
    scale = _number(source_maximum)
    if scale <= 0:
        return 0.0
    return round(max(0.0, min(_number(source_score), scale)) / scale * maximum, 2)
