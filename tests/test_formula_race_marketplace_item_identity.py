"""Regression coverage for unique, stable Marketplace ItemIDs.

Wallets, stock and purchases are keyed on ItemID, and the Captain renders one
BUY control per configured part.  A blank or repeated ItemID therefore either
hides a part or raises StreamlitDuplicateElementKey in the Parts Depot.
"""
from __future__ import annotations

from pathlib import Path

from engines.formula_race_configuration import (
    assign_marketplace_item_ids,
    normalise_marketplace_item,
    validate_marketplace_items,
)

ROOT = Path(__file__).resolve().parents[1]


def test_existing_unique_item_ids_are_never_rewritten():
    """Stability: credits, stock and purchases stay bound to their part."""
    rows = [{"ItemID": "EVT-ITEM-01", "ItemName": "Chassis"}, {"ItemID": "EVT-ITEM-07", "ItemName": "Tyres"}]
    assert [row["ItemID"] for row in assign_marketplace_item_ids(rows, "EVT")] == ["EVT-ITEM-01", "EVT-ITEM-07"]


def test_blank_and_duplicated_item_ids_are_minted_uniquely():
    rows = [
        {"ItemID": "EVT-ITEM-01", "ItemName": "Chassis"},
        {"ItemID": "EVT-ITEM-01", "ItemName": "Duplicated row"},
        {"ItemID": "", "ItemName": "Blank row"},
        {"ItemName": "Missing key"},
    ]
    assigned = assign_marketplace_item_ids(rows, "EVT")
    identifiers = [row["ItemID"] for row in assigned]

    assert identifiers[0] == "EVT-ITEM-01"
    assert len(identifiers) == len(set(identifiers))
    assert all(str(item_id).strip() for item_id in identifiers)
    assert all(item_id.startswith("EVT-ITEM-") for item_id in identifiers[1:])
    assert [row["ItemName"] for row in assigned] == ["Chassis", "Duplicated row", "Blank row", "Missing key"]


def test_editor_round_trip_placeholders_are_treated_as_missing():
    """pandas renders an empty ItemID cell as NaN; it must not become "nan"."""
    rows = [{"ItemID": float("nan"), "ItemName": "First"}, {"ItemID": "nan", "ItemName": "Second"}, {"ItemID": None, "ItemName": "Third"}]
    identifiers = [row["ItemID"] for row in assign_marketplace_item_ids(rows, "EVT")]
    assert len(set(identifiers)) == 3
    assert all(item_id.startswith("EVT-ITEM-") for item_id in identifiers)


def test_assignment_is_generic_and_needs_no_event_specific_knowledge():
    rows = [{"ItemName": "Part"} for _ in range(5)]
    identifiers = [row["ItemID"] for row in assign_marketplace_item_ids(rows, "")]
    assert len(set(identifiers)) == 5
    assert all(item_id.startswith("RACE-ITEM-") for item_id in identifiers)


def test_duplicate_item_ids_cannot_be_saved():
    duplicated = [
        {"ItemID": "EVT-ITEM-01", "ItemName": "Chassis", "CreditCost": 5},
        {"ItemID": "EVT-ITEM-01", "ItemName": "Tyres", "CreditCost": 5},
    ]
    assert "Marketplace item IDs must be unique within the event." in validate_marketplace_items(duplicated)
    assert validate_marketplace_items(assign_marketplace_item_ids(duplicated, "EVT")) == []


def test_normalisation_keeps_the_identifier_the_captain_keys_on():
    assert normalise_marketplace_item({"item_id": "EVT-ITEM-09"}, 1)["ItemID"] == "EVT-ITEM-09"


def test_captain_buy_controls_stay_unique_for_any_configuration():
    captain = (ROOT / "screens" / "formula_race_captain.py").read_text()
    assert 'key=f"race_buy_{position}_{item.get(\'ItemID\')}"' in captain
    assert "for position, item in enumerate(items, start=1):" in captain

    race_control = (ROOT / "screens" / "formula_race.py").read_text()
    assert "assign_marketplace_item_ids(editor.to_dict(\"records\"), event_id)" in race_control
    assert "ITEM-{index:02d}" not in race_control
