"""Generic, event-scoped configuration rules for Formula R.A.C.E.

This module deliberately contains no R/A/C/E names or fixed team/station
counts.  Persistence lives in the Core-v2 adapter; these helpers make the
configuration safe to edit, validate and project after a reconnect.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import uuid4


SCORING_METHODS = (
    "FACILITATOR_SCORE", "LOWEST_TIME", "HIGHEST_COUNT", "SUCCESS_COUNT", "NON_SCORING",
)
EVIDENCE_REQUIREMENTS = ("PHOTO_REQUIRED", "PHOTO_OPTIONAL", "NO_PHOTO")
RESULT_ENTRY_OWNERS = ("FACILITATOR", "CAPTAIN")
CAPTAIN_RESULT_METHODS = ("LOWEST_TIME", "HIGHEST_COUNT", "SUCCESS_COUNT")
MARKETPLACE_CATEGORIES = ("ESSENTIAL", "MATERIAL", "TOOL", "KNOWLEDGE", "CUSTOM")
TIE_POLICIES = ("SHARED_RANK", "TEAM_ID")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any, default: float = 0) -> float:
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return float(default)


def normalise_station(raw: dict[str, Any], fallback_order: int = 1) -> dict[str, Any]:
    """Return the backwards-compatible station payload stored on an activity."""
    raw = dict(raw or {})
    method = _text(raw.get("ScoringMethod", raw.get("scoring_method", "NON_SCORING"))).upper()
    evidence = _text(raw.get("EvidenceRequirement", raw.get("evidence_requirement", "PHOTO_OPTIONAL"))).upper()
    result_owner = _text(raw.get("ResultEntryOwner", raw.get("result_entry_owner", "FACILITATOR"))).upper()
    if result_owner not in RESULT_ENTRY_OWNERS:
        result_owner = "FACILITATOR"
    # A facilitator score is intrinsically official-only.  NON_SCORING has no
    # numeric result control, so its owner is retained only as harmless config.
    if method == "FACILITATOR_SCORE":
        result_owner = "FACILITATOR"
    result = {
        "ActivityID": _text(raw.get("ActivityID", raw.get("activity_id"))),
        "DisplayOrder": int(_number(raw.get("DisplayOrder", raw.get("display_order", fallback_order)), fallback_order)),
        "ShortCode": _text(raw.get("ShortCode", raw.get("short_code"))),
        "DisplayName": _text(raw.get("DisplayName", raw.get("display_name", raw.get("Name", raw.get("activity_name"))))),
        "ParticipantInstruction": _text(raw.get("ParticipantInstruction", raw.get("participant_instruction", raw.get("Instructions", raw.get("instructions"))))),
        "FacilitatorInstruction": _text(raw.get("FacilitatorInstruction", raw.get("facilitator_instruction"))),
        "ScoringMethod": method if method in SCORING_METHODS else "NON_SCORING",
        "ResultEntryOwner": result_owner,
        "ResultLabel": _text(raw.get("ResultLabel", raw.get("result_label", "Result"))),
        "ResultUnit": _text(raw.get("ResultUnit", raw.get("result_unit"))),
        "ResultMinimum": raw.get("ResultMinimum", raw.get("result_minimum")),
        "ResultMaximum": raw.get("ResultMaximum", raw.get("result_maximum")),
        "TiePolicy": _text(raw.get("TiePolicy", raw.get("tie_policy", "SHARED_RANK"))).upper(),
        "EvidenceRequirement": evidence if evidence in EVIDENCE_REQUIREMENTS else "PHOTO_OPTIONAL",
        "BaseCredits": int(_number(raw.get("BaseCredits", raw.get("base_credits", raw.get("credits", 0))), 0)),
        "PerformanceCredits": deepcopy(raw.get("PerformanceCredits", raw.get("performance_credits", {})) or {}),
        "Enabled": bool(raw.get("Enabled", raw.get("enabled", raw.get("Active", raw.get("active", True))))),
        "Icon": _text(raw.get("Icon", raw.get("icon"))),
        "ImageReference": _text(raw.get("ImageReference", raw.get("image_reference"))),
    }
    if result["TiePolicy"] not in TIE_POLICIES:
        result["TiePolicy"] = "SHARED_RANK"
    return result


def validate_stations(stations: list[dict[str, Any]]) -> list[str]:
    rows = [normalise_station(row, position) for position, row in enumerate(stations or [], 1)]
    errors: list[str] = []
    if not rows:
        return ["At least one enabled station is required."]
    for field, title in (("ActivityID", "Activity ID"), ("ShortCode", "Short code"), ("DisplayName", "Display name")):
        values = [row[field].casefold() for row in rows if row[field]]
        if len(values) != len(rows): errors.append(f"Every station requires a {title.lower()}.")
        if len(values) != len(set(values)): errors.append(f"{title} values must be unique within the event.")
    for row in rows:
        if row["BaseCredits"] < 0: errors.append(f"{row['ShortCode'] or row['ActivityID']}: Base Credits cannot be negative.")
        if row["ScoringMethod"] == "FACILITATOR_SCORE" and row["ResultEntryOwner"] != "FACILITATOR":
            errors.append(f"{row['ShortCode'] or row['ActivityID']}: facilitator scores must be entered by a facilitator.")
        performance = row.get("PerformanceCredits", {})
        if row["ScoringMethod"] == "FACILITATOR_SCORE" and isinstance(performance, dict) and _number(performance.get("PerScorePoint", 0)) < 0:
            errors.append(f"{row['ShortCode'] or row['ActivityID']}: Credits per score point cannot be negative.")
        minimum, maximum = row.get("ResultMinimum"), row.get("ResultMaximum")
        if minimum not in (None, "") and maximum not in (None, "") and _number(minimum) > _number(maximum):
            errors.append(f"{row['ShortCode'] or row['ActivityID']}: result minimum exceeds maximum.")
    return errors


def generate_balanced_routes(team_ids: list[str], station_ids: list[str]) -> dict[str, list[str]]:
    """Rotate one common station sequence; starts distribute within one team."""
    teams = [_text(team) for team in team_ids if _text(team)]
    stations = [_text(station) for station in station_ids if _text(station)]
    if not teams or not stations:
        return {}
    return {team: stations[index % len(stations):] + stations[:index % len(stations)] for index, team in enumerate(teams)}


def validate_routes(routes: dict[str, list[str]], team_ids: list[str], station_ids: list[str]) -> list[str]:
    expected_teams, expected_stations = set(team_ids), set(station_ids)
    errors: list[str] = []
    for team in expected_teams:
        route = list((routes or {}).get(team, []))
        if not route: errors.append(f"{team}: no station route configured.")
        elif set(route) != expected_stations or len(route) != len(expected_stations):
            errors.append(f"{team}: route must contain each enabled station exactly once.")
    for team in set((routes or {})) - expected_teams:
        errors.append(f"{team}: route belongs to a team outside this event.")
    return errors


def captain_result_entry_method(station: dict[str, Any]) -> str:
    """Return the numeric control a Captain is explicitly allowed to use."""
    row = normalise_station(station)
    if row["ResultEntryOwner"] == "CAPTAIN" and row["ScoringMethod"] in CAPTAIN_RESULT_METHODS:
        return row["ScoringMethod"]
    return ""


def current_station(route: list[str], submissions: list[dict[str, Any]]) -> tuple[str, str]:
    """Submission, not approval, advances a configured team route."""
    submitted = {
        _text(row.get("ActivityID", row.get("activity_id")))
        for row in submissions or []
        if _text(row.get("Status", row.get("status"))).upper() not in {"REJECTED", "RETURNED", "REJECTED / RESUBMIT"}
    }
    for index, station_id in enumerate(route or []):
        if station_id not in submitted:
            return station_id, (route[index + 1] if index + 1 < len(route) else "")
    return "", ""


def normalise_result(method: str, value: Any, *, minutes: Any = None, seconds: Any = None, precision_ms: Any = 0) -> Optional[float]:
    method = _text(method).upper()
    if method == "FACILITATOR_SCORE" or method == "NON_SCORING": return None
    if method == "LOWEST_TIME" and (minutes not in (None, "") or seconds not in (None, "")):
        return int(_number(minutes) * 60_000 + _number(seconds) * 1_000 + _number(precision_ms))
    return _number(value)


def rank_verified_results(rows: list[dict[str, Any]], method: str, tie_policy: str = "SHARED_RANK") -> list[dict[str, Any]]:
    method = _text(method).upper()
    if method not in {"LOWEST_TIME", "HIGHEST_COUNT", "SUCCESS_COUNT"}: return []
    verified = [dict(row) for row in rows or [] if bool(row.get("Verified", row.get("verified", False)))]
    ascending = method == "LOWEST_TIME"
    def sort_key(row: dict[str, Any]) -> tuple[float, str]:
        value = _number(row.get("OfficialResult", row.get("official_result")))
        team_id = _text(row.get("TeamID", row.get("team_id")))
        return (value, team_id) if ascending else (-value, team_id)

    verified.sort(key=sort_key)
    previous, rank = None, 0
    for position, row in enumerate(verified, 1):
        value = _number(row.get("OfficialResult", row.get("official_result")))
        if _text(tie_policy).upper() == "SHARED_RANK" and previous is not None and value == previous:
            row["Rank"] = rank
        else:
            rank = position
            row["Rank"] = rank
        previous = value
    return verified


def performance_credits(station: dict[str, Any], verified_result: dict[str, Any]) -> int:
    station = normalise_station(station)
    config = station.get("PerformanceCredits", {})
    if station["ScoringMethod"] == "FACILITATOR_SCORE" and isinstance(config, dict):
        return max(0, int(_number(config.get("PerScorePoint", 0)) * _number(verified_result.get("OfficialResult", verified_result.get("official_result", 0)))))
    rank = _text(verified_result.get("Rank", verified_result.get("rank")))
    if isinstance(config, dict) and isinstance(config.get("RankCredits"), dict):
        return int(_number(config["RankCredits"].get(rank, 0)))
    if isinstance(config, dict) and "PerSuccess" in config:
        return int(_number(config.get("PerSuccess")) * _number(verified_result.get("OfficialResult", 0)))
    return 0


def normalise_marketplace_item(raw: dict[str, Any], fallback_order: int = 1) -> dict[str, Any]:
    raw = dict(raw or {})
    category = _text(raw.get("Category", raw.get("category", "CUSTOM"))).upper()
    return {
        "ItemID": _text(raw.get("ItemID", raw.get("item_id"))), "DisplayOrder": int(_number(raw.get("DisplayOrder", fallback_order), fallback_order)),
        "Category": category if category in MARKETPLACE_CATEGORIES else "CUSTOM", "ItemName": _text(raw.get("ItemName", raw.get("item_name"))),
        "Description": _text(raw.get("Description", raw.get("description"))), "CreditCost": int(_number(raw.get("CreditCost", raw.get("credit_cost", raw.get("unit_cost_credits", 0))), 0)),
        "StockLimit": raw.get("StockLimit", raw.get("stock_limit")), "Enabled": bool(raw.get("Enabled", raw.get("enabled", raw.get("is_active", True)))),
        "ImageReference": _text(raw.get("ImageReference", raw.get("image_reference"))), "KnowledgeContent": _text(raw.get("KnowledgeContent", raw.get("knowledge_content"))),
    }


def assign_marketplace_item_ids(items: list[dict[str, Any]], event_id: str) -> list[dict[str, Any]]:
    """Return the catalogue with a unique, stable ItemID on every part.

    Wallets, stock and purchases are keyed on ItemID, so an existing unique
    value is never rewritten.  Only a blank or repeated value is minted, which
    stops a duplicated editor row from sharing the ItemID of the row it was
    copied from and collapsing onto it downstream.
    """
    prefix = _text(event_id) or "RACE"
    assigned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items or []:
        item = dict(raw or {})
        raw_identifier = item.get("ItemID", item.get("item_id"))
        # A data editor round-trip renders an empty cell as NaN, which would
        # otherwise persist as the literal identifier "nan".
        if isinstance(raw_identifier, float) and raw_identifier != raw_identifier:
            raw_identifier = ""
        item_id = _text(raw_identifier)
        if item_id.casefold() in {"nan", "none"}:
            item_id = ""
        while not item_id or item_id in seen:
            item_id = f"{prefix}-ITEM-{uuid4().hex[:8].upper()}"
        seen.add(item_id)
        item["ItemID"] = item_id
        assigned.append(item)
    return assigned


def validate_marketplace_items(items: list[dict[str, Any]]) -> list[str]:
    errors, names, identifiers = [], [], []
    for position, raw in enumerate(items or [], 1):
        item = normalise_marketplace_item(raw, position); names.append(item["ItemName"].casefold()); identifiers.append(item["ItemID"])
        if not item["ItemName"]: errors.append("Every marketplace item requires a name.")
        if item["CreditCost"] < 0: errors.append(f"{item['ItemName']}: Credit Cost cannot be negative.")
        if item["StockLimit"] not in (None, "") and _number(item["StockLimit"]) < 0: errors.append(f"{item['ItemName']}: Stock Limit cannot be negative.")
        if item["Category"] == "KNOWLEDGE" and not item["KnowledgeContent"]: errors.append(f"{item['ItemName']}: knowledge items require configured content or a resource reference.")
    if len([name for name in names if name]) != len(set(name for name in names if name)): errors.append("Marketplace item names must be unique within the event.")
    if len([item_id for item_id in identifiers if item_id]) != len(set(item_id for item_id in identifiers if item_id)): errors.append("Marketplace item IDs must be unique within the event.")
    return errors


def normalise_judging_criteria(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"DisplayOrder": int(_number(row.get("DisplayOrder", index), index)), "CriterionName": _text(row.get("CriterionName", row.get("name"))), "Description": _text(row.get("Description", row.get("description"))), "MaximumScore": _number(row.get("MaximumScore", row.get("maximum_score", 10)), 10), "Enabled": bool(row.get("Enabled", row.get("enabled", True)))} for index, row in enumerate(rows or [], 1)]


def configuration_lock_reasons(*, submissions: int = 0, purchases: int = 0, judging_scores: int = 0) -> dict[str, bool]:
    return {"StationsLocked": submissions > 0, "MarketplacePricesLocked": purchases > 0, "JudgingStructureLocked": judging_scores > 0}
