"""Canonical Marketplace saves must reconcile with existing catalogue rows.

marketplace_items_v2 is unique on item_id AND on (event_id, item_name), but the
migration-030 catalogue upsert only declares `on conflict(item_id)`.  Saving a
configured part whose ItemID is blank therefore tries to insert a brand new row
under a name the event already owns, which fails with a 409 and blocks every
Parts Depot save.  marketplace_transactions_v2.item_id references
marketplace_items_v2(item_id) on delete restrict, so the persisted identity has
to be reused rather than replaced.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
from data.runtime_database import RuntimeDatabaseError

EVENT_ID = "DISPOSABLE-MARKET-EVT"
LEGACY_NAMES = [
    "R.A.C.E. Engineering Manual",
    "Aero Kit",
    "Tyre Set",
    "Fuel Cell",
]
NEW_NAME = "Telemetry Pack"


@contextmanager
def _staging_env():
    original = os.getenv("EXOS_ENV")
    os.environ["EXOS_ENV"] = "staging"
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("EXOS_ENV", None)
        else:
            os.environ["EXOS_ENV"] = original


class _MarketplaceBackend:
    """Model both unique constraints the canonical catalogue save must respect."""

    is_configured = True
    can_publish = True
    url = "https://staging.disposable.example.test"

    def __init__(self, rows, configuration):
        self.rows = {str(row["item_id"]): dict(row) for row in rows}
        self.configuration = dict(configuration)
        self.inserted = []

    def _request(self, method, path, payload=None, query=None, admin=True):
        if method == "GET" and path == "events_v2":
            return [{
                "event_id": EVENT_ID, "event_name": "Disposable", "join_code": "DISPOSABLE",
                "lifecycle_status": "READY", "event_payload": {"RaceConfiguration": self.configuration},
            }]
        if method == "GET" and path == "marketplace_items_v2":
            return [dict(row) for row in self.rows.values()]
        if method == "GET" and path == "teams_v2":
            return [{"team_id": "DISPOSABLE-TEAM", "team_name": "Disposable", "country": "", "team_flag": "", "is_active": True}]
        if method == "POST" and path == "rpc/exos_v2_formula_race_save_event_configuration":
            return self._save(payload or {})
        return []

    def _save(self, payload):
        configuration = dict(payload.get("p_configuration") or {})
        event_id = str(payload.get("p_event_id", ""))
        for item in configuration.get("Marketplace", []) or []:
            item_id = str(item.get("ItemID", "")).strip()
            item_name = str(item.get("ItemName", "")).strip()
            if item_id in self.rows:
                # on conflict(item_id) do update — the declared conflict target.
                self.rows[item_id].update({"item_name": item_name})
                continue
            if any(str(row.get("event_id")) == event_id and str(row.get("item_name")) == item_name for row in self.rows.values()):
                raise RuntimeDatabaseError(
                    'Runtime request failed (409): {"code":"23505","message":"duplicate key value '
                    'violates unique constraint \\"marketplace_items_v2_event_id_item_name_key\\""}'
                )
            self.rows[item_id] = {"item_id": item_id, "event_id": event_id, "item_name": item_name}
            self.inserted.append(item_id)
        self.configuration.update(configuration)
        return {"EventID": event_id, "Saved": True}


def _legacy_rows():
    return [
        {"item_id": f"{EVENT_ID}-LEGACY-{position:02d}", "event_id": EVENT_ID, "item_name": name}
        for position, name in enumerate(LEGACY_NAMES, 1)
    ]


def _catalogue_without_item_ids():
    """The live shape: Parts Depot shows the parts, every ItemID is blank."""
    return [
        {"ItemID": None, "ItemName": name, "CreditCost": 10, "Category": "MATERIAL", "Enabled": True}
        for name in LEGACY_NAMES + [NEW_NAME]
    ]


def _adapter(backend):
    with _staging_env():
        return FormulaRaceCoreV2StagingAdapter(backend)


def test_backend_double_reproduces_the_live_409():
    """A freshly minted ItemID for an existing name hits the uncovered constraint."""
    backend = _MarketplaceBackend(_legacy_rows(), {"Marketplace": []})
    try:
        backend._request("POST", "rpc/exos_v2_formula_race_save_event_configuration", payload={
            "p_event_id": EVENT_ID,
            "p_configuration": {"Marketplace": [{"ItemID": f"{EVENT_ID}-ITEM-DEADBEEF", "ItemName": LEGACY_NAMES[0]}]},
        })
    except RuntimeDatabaseError as error:
        assert "marketplace_items_v2_event_id_item_name_key" in str(error)
        assert "409" in str(error)
    else:
        raise AssertionError("the (event_id, item_name) constraint was not modelled")


def test_blank_item_ids_reconcile_onto_the_existing_catalogue_rows():
    backend = _MarketplaceBackend(_legacy_rows(), {"Marketplace": []})
    adapter = _adapter(backend)

    adapter.save_formula_race_configuration(EVENT_ID, {"Marketplace": _catalogue_without_item_ids()}, "Disposable Facilitator")

    saved = backend.configuration["Marketplace"]
    identifiers = [str(row["ItemID"]) for row in saved]
    by_name = {str(row["ItemName"]): str(row["ItemID"]) for row in saved}

    assert len(saved) == 5
    assert len(set(identifiers)) == 5
    assert all(identifiers)
    # Existing identity preserved, so purchase references stay valid.
    for row in _legacy_rows():
        assert by_name[row["item_name"]] == row["item_id"]
    # Only the genuinely new part is inserted.
    assert backend.inserted == [by_name[NEW_NAME]]
    assert by_name[NEW_NAME] not in {row["item_id"] for row in _legacy_rows()}


def test_resaving_the_reconciled_catalogue_is_idempotent():
    backend = _MarketplaceBackend(_legacy_rows(), {"Marketplace": []})
    adapter = _adapter(backend)

    adapter.save_formula_race_configuration(EVENT_ID, {"Marketplace": _catalogue_without_item_ids()}, "Disposable Facilitator")
    first = [str(row["ItemID"]) for row in backend.configuration["Marketplace"]]
    inserted_once = list(backend.inserted)

    adapter.save_formula_race_configuration(EVENT_ID, {"Marketplace": backend.configuration["Marketplace"]}, "Disposable Facilitator")
    second = [str(row["ItemID"]) for row in backend.configuration["Marketplace"]]

    assert first == second
    assert backend.inserted == inserted_once
    assert len(backend.rows) == 5


def test_existing_purchase_references_survive_the_reconciled_save():
    """marketplace_transactions_v2.item_id is `on delete restrict`."""
    backend = _MarketplaceBackend(_legacy_rows(), {"Marketplace": []})
    adapter = _adapter(backend)
    purchased_item_id = _legacy_rows()[0]["item_id"]

    adapter.save_formula_race_configuration(EVENT_ID, {"Marketplace": _catalogue_without_item_ids()}, "Disposable Facilitator")

    assert purchased_item_id in backend.rows
    saved_ids = {str(row["ItemID"]) for row in backend.configuration["Marketplace"]}
    assert purchased_item_id in saved_ids
    for row in _legacy_rows():
        assert row["item_id"] in backend.rows


def test_renamed_part_keeps_its_identity_instead_of_inserting_a_second_row():
    backend = _MarketplaceBackend(_legacy_rows(), {"Marketplace": []})
    adapter = _adapter(backend)
    legacy = _legacy_rows()[0]

    adapter.save_formula_race_configuration(
        EVENT_ID,
        {"Marketplace": [{"ItemID": legacy["item_id"], "ItemName": "R.A.C.E. Engineering Manual v2", "CreditCost": 10}]},
        "Disposable Facilitator",
    )

    assert backend.inserted == []
    assert backend.rows[legacy["item_id"]]["item_name"] == "R.A.C.E. Engineering Manual v2"
    assert str(backend.configuration["Marketplace"][0]["ItemID"]) == legacy["item_id"]
