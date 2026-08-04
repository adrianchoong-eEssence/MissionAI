from data.formula_race_contracts import DemoFormulaRaceProvider, snapshot_as_contract
from screens import formula_race


def test_demo_contract_is_explicit_and_complete():
    contract = snapshot_as_contract(DemoFormulaRaceProvider().snapshot())
    assert contract["provenance"] == {"source": "DEMO", "is_demo": True}
    assert len(contract["teams"]) >= 6
    assert contract["transactions"] and contract["submissions"] and contract["stock"]


def test_all_promised_navigation_destinations_exist():
    assert formula_race.NAV == [
        "Overview", "Live Programme", "Championship", "Teams", "Checkpoints",
        "Reviews", "Marketplace", "Race Map", "Control Centre",
    ]


def test_all_fifteen_screen_renderers_are_present():
    expected = {"overview", "live_programme", "championship", "teams", "wallet",
                "checkpoints", "reviews", "gallery", "marketplace", "build_status",
                "race_map", "judging", "drag_results", "control_centre"}
    # Home/Day One is the programme landing state, and both live/final championship
    # are arguments of the shared standings renderer.
    assert expected.issubset(vars(formula_race))


def test_marketplace_catalog_has_stock_contract_keys():
    snapshot = DemoFormulaRaceProvider().snapshot()
    assert {name for name, _ in formula_race.MATERIALS} == set(snapshot.stock)
