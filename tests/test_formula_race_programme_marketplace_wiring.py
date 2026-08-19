"""Disposable regression coverage for Race Control navigation and catalogue wiring."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def _staging_env():
    old = os.getenv("EXOS_ENV")
    os.environ["EXOS_ENV"] = "staging"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("EXOS_ENV", None)
        else:
            os.environ["EXOS_ENV"] = old


class _Runtime:
    is_configured = True
    can_publish = True
    url = "https://staging.disposable.example.test"

    def _request(self, *_args, **_kwargs):
        return []


def _adapter():
    with _staging_env():
        return FormulaRaceCoreV2StagingAdapter(_Runtime())


def _catalogue():
    return [
        {"ItemID": f"LIVE-{index}", "ItemName": f"Canonical part {index}", "CreditCost": cost, "StockLimit": stock, "Enabled": True, "DisplayOrder": index}
        for index, (cost, stock) in enumerate(((50, 10), (10, 20), (15, 30), (10, 40), (5, 50)), 1)
    ]


def test_programme_navigation_uses_a_pre_widget_callback_not_a_late_session_assignment():
    source = (ROOT / "screens/formula_race.py").read_text()

    assert "def _navigate_race(view: str)" in source
    assert 'st.session_state["race_nav"] = view' in source
    assert 'on_click=_navigate_race, args=("Control",)' in source
    assert "st.session_state.race_nav=\"Control\"" not in source
    assert "control_centre(snapshot,control)" in source
    assert 'runtime_action("LAUNCH CHECKPOINTS","LAUNCH"' in source
    assert 'elif mapped in {"LIVE", "LAUNCH"}' in (ROOT / "data/formula_race_core_v2_adapter.py").read_text()


def test_captain_and_race_control_project_only_the_canonical_configured_catalogue():
    adapter = _adapter()
    catalogue = _catalogue()
    adapter.get_formula_race_configuration = lambda _event_id: {"Marketplace": catalogue}
    table_rows = [
        {"item_id": row["ItemID"], "item_name": "obsolete table name", "unit_cost_credits": 999, "stock_limit": 999, "is_active": True, "item_payload": {}}
        for row in catalogue
    ] + [
        {"item_id": "OLD-AXLE", "item_name": "Old axle", "unit_cost_credits": 35, "stock_limit": 25, "is_active": True, "item_payload": {}},
        {"item_id": "OLD-CARBON", "item_name": "Old carbon", "unit_cost_credits": 20, "stock_limit": 40, "is_active": True, "item_payload": {}},
    ]

    def fake_get(table, query=None, _admin=True):
        if table == "marketplace_items_v2":
            return table_rows
        if table == "marketplace_transactions_v2" and (query or {}).get("select") == "item_id,quantity":
            return [{"item_id": "LIVE-1", "quantity": 2}]
        return []

    adapter._get = fake_get
    projection = adapter._marketplace_payload("DISPOSABLE-EVENT", "DISPOSABLE-TEAM")

    assert [item["ItemID"] for item in projection["items"]] == [f"LIVE-{index}" for index in range(1, 6)]
    assert [item["ItemName"] for item in projection["items"]] == [f"Canonical part {index}" for index in range(1, 6)]
    assert [item["CreditCost"] for item in projection["items"]] == [50, 10, 15, 10, 5]
    assert projection["items"][0]["StockQuantity"] == 8
    assert all("OLD" not in item["ItemID"] for item in projection["items"])


def test_marketplace_runtime_and_purchase_boundary_use_only_configured_item_ids():
    adapter = _adapter()
    catalogue = _catalogue()
    adapter.get_formula_race_configuration = lambda _event_id: {"Marketplace": catalogue}
    writes = []
    adapter._patch = lambda table, query, payload: writes.append((table, query, payload))
    adapter._get = lambda table, query=None, _admin=True: [
        {"item_id": row["ItemID"], "is_active": True} for row in catalogue
    ] if table == "marketplace_items_v2" else []

    result = adapter.set_formula_race_marketplace_runtime("DISPOSABLE-EVENT", "OPEN", "Facilitator")

    assert result["active_item_count"] == 5
    assert [write[1]["item_id"] for write in writes] == [f"eq.LIVE-{index}" for index in range(1, 6)]
    migration = (ROOT / "supabase/034_formula_race_canonical_marketplace_catalogue.sql").read_text()
    assert "Marketplace item is not in the current configured catalogue" in migration
    assert "v_configuration ? 'Marketplace'" in migration
