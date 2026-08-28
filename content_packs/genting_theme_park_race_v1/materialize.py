"""Local-only renderer for the Genting Theme Park Race V1 content package.

The package contains no EXOS credentials and this module deliberately makes no
network or database calls.  Its sole job is to resolve the future authorised
EventID into the canonical IDs that the existing Team Formation and Theme Park
Race APIs expect.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


PACKAGE_PATH = Path(__file__).with_name("genting_theme_park_race_v1.json")
EVENT_ID_TOKEN = "{{EVENT_ID}}"


def load_genting_package() -> dict[str, Any]:
    """Read the unmodified, versioned local configuration package."""
    return json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))


def _replace_event_id(value: Any, event_id: str) -> Any:
    if isinstance(value, str):
        return value.replace(EVENT_ID_TOKEN, event_id)
    if isinstance(value, list):
        return [_replace_event_id(item, event_id) for item in value]
    if isinstance(value, dict):
        return {str(_replace_event_id(key, event_id)): _replace_event_id(item, event_id) for key, item in value.items()}
    return value


def materialize_genting_content(event_id: str) -> dict[str, Any]:
    """Resolve a future EventID into load-ready content without writing it.

    The caller remains responsible for authorised event/team/programme creation
    and for invoking the existing Team Formation and race-configuration APIs in
    their required order.
    """
    clean_event_id = str(event_id or "").strip()
    if not clean_event_id or EVENT_ID_TOKEN in clean_event_id:
        raise ValueError("A concrete non-empty EventID is required to materialize Genting content.")
    package = _replace_event_id(deepcopy(load_genting_package()), clean_event_id)
    blueprint = package["EventBlueprint"]
    return {
        "Package": package,
        "EventBlueprint": blueprint,
        "TeamTemplates": blueprint["TeamStructure"]["IdentityConfiguration"]["Teams"],
        "TeamFormationConfiguration": blueprint["TeamFormationConfiguration"],
        "RaceConfiguration": blueprint["RaceConfiguration"],
        "Programme": package["Programme"],
        "ActivitiesV2": package["ActivitiesV2"],
    }
